import io
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from davinci.api import create_app
from davinci.config import Settings
from davinci.models import RunRequest


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(davinci_data_dir=tmp_path, _env_file=None))


def test_health_and_no_secret_exposure(app):
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "api_key" not in response.text
    assert client.get("/api/workbench").json()["storage"] == "sqlite-local"


def test_tokens_and_origin_are_enforced(tmp_path):
    app = create_app(Settings(davinci_data_dir=tmp_path, davinci_api_token="test-secret", _env_file=None))
    client = TestClient(app)
    assert client.get("/api/health").status_code == 401
    headers = {"authorization": "Bearer test-secret"}
    assert client.get("/api/health", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/runs/nonexistent/stop", headers={**headers, "origin": "https://example.org"}
        ).status_code
        == 403
    )


def test_live_run_requires_credentials_and_input_validation(app):
    engine = app.state.engine
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        engine.start(RunRequest(mode="live"))
    client = TestClient(app)
    assert client.post("/api/projects/uas-demo/runs", json={"rounds": 99}).status_code == 422
    assert client.get("/api/artifacts/missing").status_code == 404


def test_concurrent_start_accepts_only_one_run(app):
    engine = app.state.engine

    def start(_):
        try:
            return engine.start(RunRequest())
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(start, range(4)))
    assert len([r for r in results if r]) == 1
    assert len(engine.store.list("runs", {"status": "running"})) == 1


def test_export_is_a_readable_reproducibility_bundle(app):
    engine = app.state.engine
    run = engine.start(RunRequest())
    response = TestClient(app).get(f"/api/runs/{run['_id']}/bundle")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert "specification.json" in archive.namelist()
    assert "run.json" in archive.namelist()

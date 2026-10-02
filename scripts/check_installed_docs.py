"""Check packaged documentation via installed HTTP routes; no CAD, credentials or model calls."""

import os
import re
import tempfile
from importlib.resources import files
from pathlib import Path


def main():
    for key in list(os.environ):
        if key.startswith(("OPENAI_", "MONGODB_", "DAVINCI_")) or key == "PYTHONPATH":
            os.environ.pop(key, None)
    from fastapi.testclient import TestClient

    import davinci
    from davinci.product.api import create_app

    assert "site-packages" in Path(davinci.__file__).parts, "Run outside checkout with the installed wheel"
    with tempfile.TemporaryDirectory(prefix="davinci-docs-") as directory:
        workspace = Path(directory)
        (workspace / "workspace.yaml").write_text("default_driver: external\n")
        with TestClient(create_app(workspace, run_worker=False)) as client:
            root = client.get("/docs/")
            assert root.status_code == 200
            assert "External agent" in root.text and "Built-in agent" in root.text
            links = set(re.findall(r'href="(/docs/[^"#]*)', root.text))
            for path in links:
                response = client.get(path)
                assert response.status_code == 200, path
            architecture = client.get("/docs/architecture/").text
            assert 'aria-label="Shared experiment lifecycle"' in architecture
            for slug in ["mechanism", "methodology", "structural"]:
                response = client.get(f"/docs/evidence/{slug}-results.json")
                assert response.status_code == 200 and response.json()["version"] == 1
            assert files("davinci.product").joinpath("static/index.html").is_file()
            print(
                f"Installed UI and {len(links)} guide routes verified; three evidence downloads; no model/solver calls"
            )


if __name__ == "__main__":
    main()

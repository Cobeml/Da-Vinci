import importlib

from pymongo.errors import OperationFailure

from davinci.config import Settings
from davinci.engine import Engine
from davinci.errors import safe_error
from davinci.models import RunRequest


def test_api_import_does_not_initialize_engine(monkeypatch):
    import davinci.api

    def forbidden(*args, **kwargs):
        raise AssertionError("Import must not connect to a database")

    monkeypatch.setattr("davinci.engine.Engine", forbidden)
    importlib.reload(davinci.api)
    monkeypatch.undo()
    importlib.reload(davinci.api)


def test_validation_run_resumes_without_new_allocation(tmp_path):
    engine = Engine(Settings(davinci_data_dir=tmp_path, _env_file=None))
    original = engine.start(RunRequest(rounds=1, budget_usd=5), run_id="validation-fixed")
    engine.stop(original["_id"])
    restarted = Engine(engine.settings)
    resumed = restarted.start(RunRequest(rounds=4, budget_usd=10), run_id="validation-fixed")
    assert resumed["status"] == "stopped"
    assert resumed["budget_usd"] == 5
    assert len(restarted.store.list("runs")) == 1


def test_external_provider_errors_are_redacted():
    secret = "mongodb://user:synthetic-secret@example.invalid"
    assert safe_error(OperationFailure(secret)) == "OperationFailure"

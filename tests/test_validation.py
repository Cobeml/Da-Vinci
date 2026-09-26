import importlib
import subprocess

import pytest
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


@pytest.mark.parametrize("foreign_evaluation", [False, True])
def test_wrong_trigger_source_is_quarantined_without_failing_run(tmp_path, foreign_evaluation):
    engine = Engine(Settings(davinci_data_dir=tmp_path, _env_file=None))
    run = engine.start(RunRequest(rounds=1))
    for queued in engine.store.list("jobs"):
        engine.store.update("jobs", queued["_id"], {"status": "cancelled"})
    if foreign_evaluation:
        engine.store.insert("evaluations", {"_id": "wrong-source", "run_id": "another-run"})
    engine.store.enqueue("reflect_on_evaluation", "wrong-source", run["_id"])
    job = engine.store.claim()
    engine.execute_job(job)
    assert engine.store.get("jobs", job["_id"])["status"] == "dead"
    assert engine.store.get("runs", run["_id"])["status"] == "running"
    assert engine.store.list("events", {"kind": "job_rejected"})


def test_trigger_functions_ignore_updates_and_deduplicate_insert_delivery():
    subprocess.run(
        [
            "node",
            "-e",
            """
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
(async () => {
  for (const [file, kind] of [
    ['atlas/enqueue-candidate.js', 'evaluate_candidate'],
    ['atlas/enqueue-reflection.js', 'reflect_on_evaluation']
  ]) {
    const rows = new Map();
    const collection = { updateOne: async (query, update, options) => {
      assert.equal(options.upsert, true);
      assert.equal(query._id, kind + ':probe');
      assert.equal(update.$setOnInsert.job_key, query._id);
      if (!rows.has(query._id)) rows.set(query._id, update.$setOnInsert);
    }};
    const scope = {context: {
      values: {get: () => 'validation'},
      services: {get: () => ({db: () => ({collection: () => collection})})}
    }};
    vm.createContext(scope);
    vm.runInContext(fs.readFileSync(file, 'utf8'), scope);
    const event = {operationType: 'insert', fullDocument: {_id: 'probe', run_id: 'test'}};
    await scope.exports(event);
    const original = rows.get(kind + ':probe');
    original.status = 'done';
    await scope.exports(event);
    await scope.exports({...event, operationType: 'update'});
    await scope.exports({operationType: 'insert', fullDocument: {_id: 'irrelevant'}});
    assert.equal(rows.size, 1);
    assert.equal(rows.get(kind + ':probe').status, 'done');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

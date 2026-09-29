import json
from types import SimpleNamespace

import pytest
import yaml

from davinci.budget import BudgetExceeded
from davinci.config import Settings
from davinci.product.engine import Engine
from davinci.product.provider import Provider, UncertainRequest
from davinci.product.tasks import template_config


def provider(tmp_path):
    engine = Engine(tmp_path, credentials=Settings(_env_file=None, openai_api_key="test-placeholder"))
    cfg = template_config("sensor")
    cfg["run"]["budget_usd"] = 5
    text = yaml.safe_dump(cfg)
    c, t = engine.validate(text)
    run = engine.create_run(c, t, text, "test-image")
    return Provider(engine, run), engine


def test_paid_response_checkpoint_reuses_completed_output(tmp_path, monkeypatch):
    p, e = provider(tmp_path)
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(
            output_text='{"lesson":"keep fixed checks"}',
            id="response-test",
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=10,
                model_dump=lambda: {"input_tokens": 100, "output_tokens": 10},
            ),
        )

    monkeypatch.setattr(
        "davinci.product.provider.OpenAI",
        lambda **kw: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    assert p.request("reflect-0", "Return JSON", {})["lesson"] == "keep fixed checks"
    assert p.request("reflect-0", "Return JSON", {})["lesson"] == "keep fixed checks"
    assert len(calls) == 1
    assert e.store.get("runs", p.run["_id"])["spent_usd"] > 0
    assert not e.store.get("budgets", "budget-global")["reservations"]


def test_timeout_is_not_automatically_repeated(tmp_path, monkeypatch):
    p, e = provider(tmp_path)
    calls = []

    def create(**kw):
        calls.append(kw)
        raise TimeoutError("No response")

    monkeypatch.setattr(
        "davinci.product.provider.OpenAI",
        lambda **kw: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    for _ in range(2):
        with pytest.raises(UncertainRequest):
            p.request("proposal-1", "Return JSON", {})
    assert len(calls) == 1
    assert e.store.get("runs", p.run["_id"])["spent_usd"] > 0


def test_budget_rejects_before_provider_call(tmp_path, monkeypatch):
    p, e = provider(tmp_path)
    e.store.update("runs", p.run["_id"], {"budget_usd": 0.00001})
    monkeypatch.setattr("davinci.product.provider.OpenAI", lambda **kw: pytest.fail("No API call allowed"))
    with pytest.raises(BudgetExceeded):
        p.request("proposal-1", "Return JSON", {})
    assert not e.store.list("requests")


def test_local_memory_isolates_objects_and_task_versions(tmp_path):
    p, e = provider(tmp_path)
    for index, object_id, version in [
        (0, p.run["object_id"], p.run["task_version"]),
        (1, "unrelated", p.run["task_version"]),
        (2, p.run["object_id"], "different-version"),
    ]:
        e.store.insert(
            "memories",
            {
                "_id": str(index),
                "object_id": object_id,
                "task_version": version,
                "summary": json.dumps({"lesson": "test"}),
            },
        )
    assert [m["_id"] for m in e.memory(p.run, p)] == ["0"]


def test_json_mode_instruction_is_in_input(tmp_path, monkeypatch):
    p, e = provider(tmp_path)

    def create(**kw):
        assert "JSON" in kw["input"]
        return SimpleNamespace(output_text='{"ok":true}', id="test", usage=None)

    monkeypatch.setattr(
        "davinci.product.provider.OpenAI",
        lambda **kw: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    assert p.request("diagnostic", "Return a result", {}) == {"ok": True}

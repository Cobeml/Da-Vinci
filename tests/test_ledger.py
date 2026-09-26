from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from davinci.budget import Budget, BudgetExceeded
from davinci.memory import Memory
from davinci.models import SPECIFICATION
from davinci.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_idempotent_enqueue_and_atomic_claim(store):
    store.insert("runs", {"_id": "run-a", "status": "running"})
    ids = [store.enqueue("evaluate_candidate", "candidate-a", "run-a") for _ in range(3)]
    assert len(set(ids)) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(8)))
    assert len([c for c in claims if c]) == 1


def test_expired_lease_cannot_commit_after_reclaim(store):
    store.insert("runs", {"_id": "run-a", "status": "running"})
    store.enqueue("evaluate_candidate", "candidate-a", "run-a")
    old = store.claim()
    store.update(
        "jobs",
        old["_id"],
        {"lease_expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
    )
    new = store.claim()
    assert not store.owns(old)
    assert store.finish(old) is None
    assert store.finish(new)["status"] == "done"


def test_stop_prevents_pending_work(store):
    store.insert("runs", {"_id": "run-a", "status": "stopped"})
    store.enqueue("evaluate_candidate", "candidate-a", "run-a")
    assert store.claim() is None
    assert store.list("jobs")[0]["status"] == "cancelled"


def test_persistence_across_repository_instances(tmp_path):
    first = Store(tmp_path)
    first.insert("evidence", {"_id": "immutable", "value": 42})
    second = Store(tmp_path)
    assert not second.insert("evidence", {"_id": "immutable", "value": 0})
    assert second.get("evidence", "immutable")["value"] == 42


def test_parallel_budget_reservations_cannot_overspend(store):
    store.insert("runs", {"_id": "run-a", "revision": 0, "budget_usd": 1.0, "spent_usd": 0.0})
    budget = Budget(store, 10)

    def reserve(_):
        try:
            return budget.reserve("run-a", 0.6)
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    accepted = [r for r in results if r]
    assert len(accepted) == 1
    budget.settle(accepted[0], 0.2)
    assert store.get("runs", "run-a")["spent_usd"] == 0.2
    budget.reserve("run-a", 0.7)
    with pytest.raises(BudgetExceeded):
        budget.reserve("run-a", 0.2)


def test_memory_scopes_and_exact_repeat_detection(store):
    memory = Memory(store)
    for subsystem in ("structural", "aerodynamic"):
        c = {
            "_id": subsystem,
            "project_id": "uas-demo",
            "run_id": "run-a",
            "subsystem": subsystem,
            "specification_id": SPECIFICATION["_id"],
            "evaluator_version": "screening-v1",
            "parameters": {"thickness_mm": 1.5},
            "fingerprint": subsystem,
        }
        e = {
            "_id": "eval-" + subsystem,
            "outcome": "failed",
            "violations": [{"code": "MINIMUM_THICKNESS"}],
            "metrics": {},
            "fidelity": "analytic_screening",
        }
        memory.remember(c, e)
    results = memory.search("structural", "minimum thickness")
    assert len(results) == 1 and results[0]["subsystem"] == "structural"
    assert memory.failed_before("structural")
    assert not memory.failed_before("new-fingerprint")

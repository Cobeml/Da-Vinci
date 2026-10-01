import json

from test_external_cli import service  # noqa: F401

from davinci.product.client import Client
from davinci.product.tasks import RESOURCES
from scripts.memory_benchmark import exercise


def test_small_held_out_retrieval_fixture(service):  # noqa: F811
    root, engine = service
    data = json.loads(RESOURCES.joinpath("external/memory-benchmark.json").read_text())
    result = exercise(Client(root), data)
    assert result["held_out_queries"] == 4
    assert result["queries_with_relevant_hit"] == 4
    assert (
        result["misleading_suggestions"] == 1
    )  # retained hypothesis evades metadata filtering; not proven safe advice
    assert all(r["all_require_new_validation"] for r in result["results"])
    assert not engine.store.list("requests")

from types import SimpleNamespace

from davinci.budget import Budget
from davinci.config import Settings
from davinci.providers import AstraProvider
from davinci.store import Store


def test_screenshot_budget_uses_image_allowance_not_base64_byte_length(tmp_path):
    store = Store(tmp_path)
    store.insert("runs", {"_id": "run-a", "revision": 0, "budget_usd": 1.0, "spent_usd": 0.0})
    provider = AstraProvider(
        Settings(openai_api_key="test-only", _env_file=None), Budget(store, 10), store, "run-a"
    )
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="response-test", usage=SimpleNamespace(input_tokens=100, output_tokens=100))

    provider.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    provider._response(
        input=[
            {
                "role": "user",
                "content": [{"type": "input_image", "image_url": "data:image/png;base64," + "A" * 2_000_000}],
            }
        ]
    )
    assert captured["model"] == "gpt-6-astra"
    assert store.get("runs", "run-a")["spent_usd"] == 0.006
    assert not store.get("budgets", "budget-global")["reservations"]

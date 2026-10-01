"""Temporary credential-free replay workspace for product browser acceptance tests."""

import sys
import tempfile
from pathlib import Path

import uvicorn

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.engine import Engine


def main():
    # Explicit test-only provider injection. No model client is ever called by this server.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests/product"))
    from test_managed import DeterministicProvider

    from davinci.product.provider import Provider

    class BrowserProvider(Provider):
        def request(self, stage, instruction, context):
            if stage.startswith("managed-"):
                value = DeterministicProvider(self.engine, self.run).request(stage, instruction, context)
                if (
                    context["stage"] == "requirements"
                    and "force unspecified" in context["description"]
                    and not context["answers"]
                ):
                    value["inputs"] = None
                    value["questions"] = {"force": "What transverse tip force in newtons must it carry?"}
                return value
            if self.run["mode"] != "replay":
                raise ValueError("This browser fixture only supports deterministic generation")
            return super().request(stage, instruction, context)

    with tempfile.TemporaryDirectory(prefix="davinci-browser-") as directory:
        workspace = Path(directory)
        (workspace / "workspace.yaml").write_text("port: 8742\n")
        engine = Engine(
            workspace,
            provider=BrowserProvider,
            credentials=Settings(_env_file=None, openai_api_key="browser-fixture-not-a-key", mongodb_uri=""),
        )
        engine.model_calls = []
        uvicorn.run(create_app(workspace, engine=engine), host="127.0.0.1", port=8742, log_level="warning")


if __name__ == "__main__":
    main()

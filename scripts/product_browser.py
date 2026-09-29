"""Temporary credential-free replay workspace for product browser acceptance tests."""

import tempfile
from pathlib import Path

import uvicorn

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.engine import Engine


def main():
    with tempfile.TemporaryDirectory(prefix="davinci-browser-") as directory:
        workspace = Path(directory)
        (workspace / "workspace.yaml").write_text("port: 8742\n")
        engine = Engine(workspace, credentials=Settings(_env_file=None))
        uvicorn.run(create_app(workspace, engine=engine), host="127.0.0.1", port=8742, log_level="warning")


if __name__ == "__main__":
    main()

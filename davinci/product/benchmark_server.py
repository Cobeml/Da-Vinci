"""Explicit deterministic methodology server. Never uses configured model/DB credentials."""

import argparse
import fcntl
from pathlib import Path

import uvicorn

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.engine import Engine
from davinci.product.methodology import BenchmarkProvider


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--fixture", choices=["methodology", "mechanism"], default="methodology")
    a = p.parse_args()
    from davinci.product.mechanism.walkthrough import MechanismProvider

    provider = MechanismProvider if a.fixture == "mechanism" else BenchmarkProvider
    a.workspace.mkdir(parents=True, exist_ok=True)
    if not (a.workspace / "workspace.yaml").exists():
        (a.workspace / "workspace.yaml").write_text(
            "storage: local\nproject_id: methodology-fixtures\nport: 8745\n"
        )
    engine = Engine(
        a.workspace,
        provider=provider,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
    )
    with (engine.root / "server.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        uvicorn.run(
            create_app(a.workspace, engine=engine),
            host="127.0.0.1",
            port=engine.options.port,
            log_level="warning",
        )


if __name__ == "__main__":
    main()

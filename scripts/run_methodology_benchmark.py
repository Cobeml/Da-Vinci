"""Own one ordinary fixture workspace service; exercise both public routes with native solvers."""

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from davinci.product.client import Client, ClientError
from davinci.product.methodology import Benchmark


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--driver", choices=["both", "external", "managed"], default="both")
    p.add_argument("--skip-structural", action="store_true")
    a = p.parse_args()
    a.workspace.mkdir(parents=True, exist_ok=True)
    a.output.mkdir(parents=True, exist_ok=True)
    if not (a.workspace / "workspace.yaml").exists():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        (a.workspace / "workspace.yaml").write_text(
            f"storage: local\nproject_id: methodology-fixtures\nport: {port}\n"
        )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and not k.startswith(("OPENAI_", "MONGODB_", "DAVINCI_"))
    }
    with (a.output / "service.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "davinci.product.benchmark_server",
                "--workspace",
                str(a.workspace.resolve()),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            client = Client(a.workspace)
            for _ in range(200):
                if server.poll() is not None:
                    raise RuntimeError("Fixture service failed; see service.log")
                try:
                    client.connect()
                    break
                except ClientError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Fixture service did not start")
            summaries = []
            for driver in ("external", "managed") if a.driver == "both" else (a.driver,):
                result = Benchmark(client, driver, a.output / driver).run(structural=not a.skip_structural)
                summaries.append(result)
                print(
                    json.dumps(
                        {"driver": driver, "cases": len(result["cases"]), "output": str(a.output / driver)}
                    ),
                    flush=True,
                )
            parity = []
            if len(summaries) == 2:
                for external, managed in zip(summaries[0]["cases"], summaries[1]["cases"]):
                    same = external["acceptance_contract_id"] == managed["acceptance_contract_id"]
                    metrics = external["final_metrics"]
                    match = metrics.keys() == managed["final_metrics"].keys() and all(
                        v["unit"] == managed["final_metrics"][k]["unit"]
                        and math.isclose(
                            v["value"], managed["final_metrics"][k]["value"], rel_tol=1e-8, abs_tol=1e-6
                        )
                        for k, v in metrics.items()
                    )
                    assert same and match and external["final_accepted"] == managed["final_accepted"]
                    parity.append(
                        dict(
                            external=external["experiment_id"],
                            managed=managed["experiment_id"],
                            same_physical_contract_and_runtime=same,
                            metrics_match=match,
                            absolute_tolerance=1e-6,
                            relative_tolerance=1e-8,
                        )
                    )
            (a.output / "summary.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "runs": summaries,
                        "parity": parity,
                        "paid_calls": 0,
                        "synthetic_reasoning": True,
                    },
                    indent=2,
                )
                + "\n"
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()

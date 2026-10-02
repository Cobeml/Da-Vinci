"""Fresh-wheel public external structural journey, real solver, no checkout imports/keys."""

import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
from importlib.resources import files
from pathlib import Path


def main():
    for key in list(os.environ):
        if key.startswith(("OPENAI_", "MONGODB_", "DAVINCI_")) or key == "PYTHONPATH":
            os.environ.pop(key, None)
    import davinci
    from davinci.product.protocol import build_catalog, schema_catalog
    from davinci.product.structural.adapter import DESCRIPTOR

    assert "site-packages" in Path(davinci.__file__).parts
    assert importlib.util.find_spec("gmsh") is None, "Use a fresh environment without solver extras"
    assert importlib.util.find_spec("numpy") is None, "Host numerical packages must not be needed"
    assert DESCRIPTOR.id == "calculix-static"
    assert schema_catalog() == build_catalog()
    assert files("sandbox").joinpath("Dockerfile.structural").is_file()
    assert files("davinci.product").joinpath("static/docs/structural-simulation/index.html").is_file()
    with tempfile.TemporaryDirectory(prefix="davinci-installed-structural-") as folder:
        root = Path(folder) / "workspace"

        def cli(*args):
            command = subprocess.run(
                [sys.executable, "-m", "davinci.product.cli", "--workspace", str(root), *args],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=40,
            )
            assert command.returncode == 0, command.stdout + command.stderr
            return json.loads(command.stdout)["data"]

        cli("init", str(root), "--driver", "external", "--template", "custom")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        (root / "workspace.yaml").write_text(f"storage: local\ndefault_driver: external\nport: {port}\n")
        health = cli("service", "ensure")
        try:
            assert not health["live_available"]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "davinci.product.structural.walkthrough",
                    "--workspace",
                    str(root),
                    "--report",
                    str(root / "report.json"),
                ],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=600,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            report = json.loads((root / "report.json").read_text())
            assert report["report"]["accepted_candidate_ids"]
            print(
                json.dumps(
                    {
                        "fresh_wheel": True,
                        "checkout_imports": False,
                        "host_solver_packages": False,
                        "provider_calls": 0,
                        "keyless_public_structural_report": True,
                        "runtime": "Gmsh 4.15.2 / CalculiX 2.23",
                    }
                )
            )
        finally:
            os.kill(health["started_pid"], signal.SIGTERM)


if __name__ == "__main__":
    main()

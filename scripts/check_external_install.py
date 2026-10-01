import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    # Test a wheel installed with `uv pip install --no-deps --target DIRECTORY ...`.
    # The calling interpreter supplies the package's already-installed dependencies.
    parser = argparse.ArgumentParser()
    parser.add_argument("package_directory", type=Path)
    package_directory = parser.parse_args().package_directory.resolve()
    sys.path.insert(0, str(package_directory))
    os.environ["PYTHONPATH"] = str(package_directory)
    for key in ("OPENAI_API_KEY", "MONGODB_URI", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        os.environ.pop(key, None)
    import davinci

    assert Path(davinci.__file__).resolve().is_relative_to(package_directory)
    from davinci.product.protocol import build_catalog, schema_catalog

    assert schema_catalog() == build_catalog()
    with tempfile.TemporaryDirectory(prefix="davinci-installed-external-") as folder:
        root = Path(folder) / "workspace"

        def cli(*args):
            run = subprocess.run(
                [sys.executable, "-m", "davinci.product.cli", "--workspace", str(root), *args],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert run.returncode == 0, run.stdout + run.stderr
            return json.loads(run.stdout)["data"]

        cli("init", str(root), "--driver", "external", "--template", "custom")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        (root / "workspace.yaml").write_text(f"storage: local\ndefault_driver: external\nport: {port}\n")
        assert "CandidateCommand" in cli("external", "schemas")["schemas"]
        assert "Da Vinci external-agent instructions" in cli("external", "instructions")["instructions"]
        health = cli("service", "ensure")
        try:
            assert health["external_available"] and not health["live_available"]
            assert "started_pid" not in cli("service", "ensure")
            opened = cli("external", "open", "--file", str(root / "experiment.json"))
            assert opened["driver"] == "external" and opened["mode"] == "live"
            assert cli("external", "status", opened["_id"])["next_actions"]
            assert (root / "AGENTS.md").exists()
            print(
                json.dumps(
                    {
                        "installed_wheel": True,
                        "schemas": True,
                        "instructions": True,
                        "service_start_and_reconnect": True,
                        "keyless_external_open": True,
                    }
                )
            )
        finally:
            os.kill(health["started_pid"], signal.SIGTERM)


if __name__ == "__main__":
    main()

"""Fresh-wheel public CLI/service journey; actual CAD, no generation or DB keys."""

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

    assert "site-packages" in Path(davinci.__file__).parts
    assert importlib.util.find_spec("cadquery") is None
    assert schema_catalog() == build_catalog()
    assert files("davinci.product").joinpath("resources/tools/inspect_geometry.py").is_file()
    with tempfile.TemporaryDirectory(prefix="davinci-installed-tools-") as folder:
        root = Path(folder) / "workspace"

        def cli(*args):
            p = subprocess.run(
                [sys.executable, "-m", "davinci.product.cli", "--workspace", str(root), *args],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=40,
            )
            assert p.returncode == 0, p.stdout + p.stderr
            return json.loads(p.stdout)["data"]

        cli("init", str(root), "--driver", "external", "--template", "custom")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        (root / "workspace.yaml").write_text(f"storage: local\ndefault_driver: external\nport: {port}\n")
        health = cli("service", "ensure")
        try:
            assert not health["live_available"]
            assert cli("tools", "classes")[0]["class"] == "perforated_plate_v1"
            report = root / "tools.json"
            p = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "davinci.product.tool_walkthrough",
                    "--workspace",
                    str(root),
                    "--report",
                    str(report),
                ],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=600,
            )
            assert p.returncode == 0, p.stdout + p.stderr
            data = json.loads(report.read_text())
            assert [v["status"] for v in data["development"]["versions"]] == [
                "rejected",
                "tested",
                "rejected",
            ]
            assert len(data["reports"]) == 2 and all(
                r["report"]["accepted_candidate_ids"] for r in data["reports"]
            )
            tid = data["development"]["_id"]
            assert cli("tools", "status", tid)["active_version"]
            assert cli("tools", "wait", tid)["phase"] == "tested"
            job = next(j for j in data["development"]["jobs"] if j["kind"] == "invoke" and j["passed"])
            cli("tools", "bundle", tid, job["id"], "--output", str(root / "candidate.json"))
            assert (
                json.loads((root / "candidate.json").read_text())["metadata"]["tool_version_id"]
                == job["version_id"]
            )
            print(
                json.dumps(
                    {
                        "fresh_wheel": True,
                        "host_cad": False,
                        "keyless": True,
                        "native_CAD_helper_checks": True,
                        "independent_mass_reports": 2,
                    }
                )
            )
        finally:
            os.kill(health["started_pid"], signal.SIGTERM)


if __name__ == "__main__":
    main()

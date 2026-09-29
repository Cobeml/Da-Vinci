import argparse
import fcntl
import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import yaml

from davinci.config import Settings
from davinci.product.config import parse_yaml, workspace_settings
from davinci.product.tasks import RESOURCES, SANDBOX, snapshot, template_config


def initialize(root, template):
    root.mkdir(parents=True, exist_ok=True)
    if any((root / n).exists() for n in ("run.yaml", "workspace.yaml")):
        raise ValueError("Workspace configuration already exists; choose a new directory")
    (root / "run.yaml").write_text(yaml.safe_dump(template_config(template), sort_keys=False))
    (root / "workspace.yaml").write_text(
        "storage: local\nport: 8741\nmodel: gpt-6-astra\npricing_model: gpt-6-astra\n# Conservative accounting estimates, USD per million tokens. Verify for your account.\ninput_usd_per_million: 20\noutput_usd_per_million: 75\ndaily_budget_usd: 50\n"
    )
    (root / ".gitignore").write_text(".env\n.davinci/\n")
    if template == "custom":
        shutil.copytree(str(RESOURCES.joinpath("templates/custom")), root / "task")
    print(
        f"Created {root}. Edit run.yaml, set OPENAI_API_KEY, then run davinci setup --template {template} and davinci serve."
    )


def setup(root, template):
    destination = root / ".davinci" / "docker"
    destination.mkdir(parents=True, exist_ok=True)
    # Curated build context excludes keys, beta features and public demo assets.
    names = [
        "Dockerfile",
        "Dockerfile.vtol",
        "requirements.lock",
        "build.py",
        "evaluate.py",
        "integrate.py",
        "families.py",
        "invoke.py",
        "adapt.py",
    ]
    for name in names:
        (destination / name).write_bytes(SANDBOX.joinpath(name).read_bytes())
    (destination / "ui").mkdir(exist_ok=True)
    for name in ("package.json", "package-lock.json", "check.cjs"):
        (destination / "ui" / name).write_bytes(SANDBOX.joinpath("ui/" + name).read_bytes())
    subprocess.run(["docker", "build", "-t", "da-vinci-cad:local", str(destination)], check=True)
    if template == "vtol":
        subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(destination / "Dockerfile.vtol"),
                "-t",
                "da-vinci-vtol:local",
                str(destination),
            ],
            check=True,
        )


def main():
    parser = argparse.ArgumentParser(prog="davinci", description="Local CAD optimization workspace")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument("--template", choices=["sensor", "gripper", "vtol", "custom"], default="sensor")
    for name in ("validate", "run"):
        command = sub.add_parser(name)
        command.add_argument("yaml", type=Path)
    prep = sub.add_parser("setup")
    prep.add_argument("--template", choices=["sensor", "gripper", "vtol", "custom"], default="sensor")
    sub.add_parser("doctor")
    serve = sub.add_parser("serve")
    serve.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    try:
        if args.command == "init":
            initialize(args.directory, args.template)
        elif args.command == "validate":
            c = parse_yaml(args.yaml.read_text())
            t = snapshot(c, root)
            print(
                json.dumps({"valid": True, "task_version": t["version"], "metrics": t["metrics"]}, indent=2)
            )
        elif args.command == "setup":
            setup(root, args.template)
        elif args.command == "doctor":
            options = workspace_settings(root)
            credentials = Settings(_env_file=root / ".env")
            results = {
                "python": sys.version.split()[0],
                "git": bool(shutil.which("git")),
                "docker": False,
                "openai_key_configured": bool(credentials.openai_api_key),
                "storage": options.storage,
                "atlas_configured": bool(credentials.mongodb_uri),
                "ui_bundled": RESOURCES.parent.joinpath("static/index.html").is_file(),
            }
            try:
                results["docker"] = (
                    subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
                )
            except (OSError, subprocess.SubprocessError):
                pass
            if (root / "run.yaml").exists():
                config = parse_yaml((root / "run.yaml").read_text())
                task = snapshot(config, root)
                try:
                    results["task_image"] = (
                        subprocess.run(
                            ["docker", "image", "inspect", task["image"]], capture_output=True, timeout=10
                        ).returncode
                        == 0
                    )
                except (OSError, subprocess.SubprocessError):
                    results["task_image"] = False
            print(json.dumps(results, indent=2))
            if not results["git"]:
                print("Install Git to archive source snapshots.")
            if not results["docker"]:
                print("Install/start Docker Engine, or enable Docker Desktop integration in WSL2.")
            if results.get("task_image") is False:
                print("Run davinci setup --template " + config.task.template)
            if not results["openai_key_configured"]:
                print("Set OPENAI_API_KEY in the environment or workspace .env for live runs.")
        elif args.command == "run":
            options = workspace_settings(root)
            content = args.yaml.read_text()
            snapshot(parse_yaml(content), root)
            data = json.dumps({"yaml": content}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{options.port}/api/v1/runs",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.load(response)
            except urllib.error.HTTPError as exc:
                raise ValueError(json.load(exc).get("detail", "Start failed")) from None
            except urllib.error.URLError:
                raise ValueError("Start davinci serve in this workspace first") from None
            print(f"Run {result['id']}: http://127.0.0.1:{options.port}/object/?id={result['object_id']}")
        elif args.command == "serve":
            import uvicorn

            from davinci.product.api import create_app

            root.mkdir(parents=True, exist_ok=True)
            (root / ".davinci").mkdir(exist_ok=True)
            with (root / ".davinci" / "server.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError("A workspace server is already running") from None
                app = create_app(root)
                port = app.state.engine.options.port
                print(f"Da Vinci: http://127.0.0.1:{port}")
                if not args.no_browser:
                    timer = threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}"))
                    timer.daemon = True
                    timer.start()
                uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Da Vinci: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

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


def initialize(root, template, driver="managed"):
    root.mkdir(parents=True, exist_ok=True)
    if any((root / n).exists() for n in ("run.yaml", "workspace.yaml")):
        raise ValueError("Workspace configuration already exists; choose a new directory")
    (root / "run.yaml").write_text(yaml.safe_dump(template_config(template), sort_keys=False))
    (root / "workspace.yaml").write_text(
        f"default_driver: {driver}\n"
        "storage: local\nport: 8741\nmodel: gpt-6-astra\npricing_model: gpt-6-astra\n# Conservative accounting estimates, USD per million tokens. Verify for your account.\ninput_usd_per_million: 20\noutput_usd_per_million: 75\ndaily_budget_usd: 50\n"
    )
    (root / ".gitignore").write_text(".env\n.davinci/\n")
    if template == "custom":
        shutil.copytree(str(RESOURCES.joinpath("templates/custom")), root / "task")
    if driver == "external":
        shutil.copytree(str(RESOURCES.joinpath("external")), root / "external")
        (root / "AGENTS.md").write_text(RESOURCES.joinpath("external/AGENT.md").read_text())
        (root / "experiment.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "object": {"slug": "my-part", "name": "My part"},
                    "description": "Describe the engineering request",
                    "driver": "external",
                    "mode": "live",
                    "actor": "coding-agent",
                    "operation_id": "open-1",
                },
                indent=2,
            )
        )
        from davinci.product.external_cli import output

        output(
            {
                "workspace": str(root.resolve()),
                "driver": driver,
                "model_key_required": False,
                "next_actions": [
                    "edit experiment.json",
                    "davinci service ensure",
                    "davinci external open --file experiment.json",
                ],
            }
        )
    else:
        print(
            f"Created {root}. Set OPENAI_API_KEY, run davinci setup --template {template}, then davinci service ensure. Use davinci managed request --help for natural-language authoring, or edit run.yaml for the legacy task route."
        )


def setup(root, template):
    destination = root / ".davinci" / "docker"
    destination.mkdir(parents=True, exist_ok=True)
    # Curated build context excludes keys, beta features and public demo assets.
    names = [
        "Dockerfile",
        "Dockerfile.vtol",
        "Dockerfile.structural",
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
    if template == "structural":
        subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(destination / "Dockerfile.structural"),
                "-t",
                "da-vinci-structural:local",
                str(destination),
            ],
            check=True,
        )


class ProtocolParser(argparse.ArgumentParser):
    def error(self, message):
        from davinci.product.external_cli import output

        output({"error": message, "exit_code": 2}, ok=False)
        raise SystemExit(2)


def main():
    parser = ProtocolParser(prog="davinci", description="Local CAD optimization workspace")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument("--driver", choices=["external", "managed"], default="managed")
    init.add_argument("--template", choices=["sensor", "gripper", "vtol", "custom"], default="sensor")
    for name in ("validate", "run"):
        command = sub.add_parser(name)
        command.add_argument("yaml", type=Path)
    prep = sub.add_parser("setup")
    prep.add_argument(
        "--template", choices=["sensor", "gripper", "vtol", "custom", "structural"], default="sensor"
    )
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--driver", choices=["external", "managed"])
    serve = sub.add_parser("serve")
    serve.add_argument("--no-browser", action="store_true")
    from davinci.product.external_cli import add_commands

    add_commands(sub)
    from davinci.product.memory_cli import add_commands as memory_commands

    memory_commands(sub)
    from davinci.product.managed_cli import add_commands as managed_commands

    managed_commands(sub)
    from davinci.product.transfer_cli import add_commands as transfer_commands

    transfer_commands(sub)
    from davinci.product.tool_cli import add_commands as tool_commands

    tool_commands(sub)
    args = parser.parse_args()
    root = args.workspace.resolve()
    try:
        if args.command in ("external", "service", "memory", "managed", "experiment", "tools"):
            from davinci.product.client import ClientError
            from davinci.product.external_cli import output, run

            if args.command == "experiment":
                from davinci.product.transfer_cli import run
            if args.command == "managed":
                from davinci.product.managed_cli import run
            if args.command == "memory":
                from davinci.product.memory_cli import run
            if args.command == "tools":
                from davinci.product.tool_cli import run
            try:
                data, code = run(args, root)
                output(data, ok=code == 0)
                if code:
                    raise SystemExit(code)
            except ClientError as exc:
                output({"error": str(exc), "exit_code": exc.code}, ok=False)
                raise SystemExit(exc.code) from None
            except (ValueError, OSError, KeyError) as exc:
                output({"error": str(exc), "exit_code": 2}, ok=False)
                raise SystemExit(2) from None
        elif args.command == "init":
            initialize(args.directory, args.template, args.driver)
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
            driver = args.driver or options.default_driver
            results = {
                "driver": driver,
                "model_key_required": driver == "managed",
                "embedding": options.embedding.model_dump(),
                "project_id": options.project_id,
                "next_actions": ["davinci service ensure"] if driver == "external" else ["davinci serve"],
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
            if driver == "managed" and (root / "run.yaml").exists():
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
            from davinci.product.external_cli import output

            output(results)
        elif args.command == "run":
            options = workspace_settings(root)
            if options.default_driver == "external":
                raise ValueError(
                    "This is an external workspace; use davinci external open/submit/evaluate. The run command is the managed v1 route."
                )
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

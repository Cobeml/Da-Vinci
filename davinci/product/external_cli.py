"""Supported external-agent commands, all mutations sent to the workspace service."""

import base64
import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

from davinci.product.client import Client, ClientError
from davinci.product.contracts import Candidate
from davinci.product.tasks import RESOURCES


def output(data, *, ok=True):
    print(json.dumps({"version": 2, "ok": ok, "data": data}, allow_nan=False, sort_keys=True))


def add_commands(sub):
    service = sub.add_parser("service", help="Start or connect to the one local workspace execution owner")
    service.add_argument("action", choices=["ensure", "status"])
    external = sub.add_parser(
        "external", help="Keyless external-agent workflow over localhost HTTP (JSON output)"
    )
    commands = external.add_subparsers(dest="action", required=True)
    for name in ("schemas", "instructions", "list"):
        commands.add_parser(name)
    create = commands.add_parser("open", help="Open an external experiment from OpenExperiment JSON")
    create.add_argument("--file", type=Path, required=True)
    retrieve = commands.add_parser("experience")
    retrieve.add_argument("query")
    artifact = commands.add_parser("artifact")
    artifact.add_argument("artifact_id")
    artifact.add_argument("--output", type=Path, required=True)
    for name in (
        "status",
        "validate-plan",
        "capabilities",
        "results",
        "report",
        "job",
        "wait",
        "plan",
        "fixture",
        "reference-build",
        "verify",
        "freeze",
        "submit",
        "reflect",
        "evaluate",
        "cancel",
        "resume",
        "finalize",
        "revise",
    ):
        parser = commands.add_parser(name)
        parser.add_argument("experiment_id")
        if name in ("job", "wait"):
            parser.add_argument("job_id")
        if name == "wait":
            parser.add_argument("--timeout", type=float, default=300)
        if name == "report":
            parser.add_argument("--output", type=Path)
        if name in ("plan", "verify", "reflect", "revise"):
            parser.add_argument("--file", type=Path, required=name != "plan")
        if name == "plan":
            parser.add_argument(
                "--task", type=Path, help="Directory with plan.json, runtime.json and evaluate.py"
            )
            parser.add_argument(
                "--image", help="Locally installed Docker image to resolve to its immutable ID"
            )
        if name == "fixture":
            parser.add_argument("--step", type=Path, required=True)
            parser.add_argument("--provenance", required=True)
        if name in ("submit", "reference-build"):
            parser.add_argument("--source", type=Path, required=True)
            parser.add_argument("--parameters", type=Path, required=True)
            parser.add_argument("--title", required=True)
            parser.add_argument("--change", default="")
            if name == "reference-build":
                parser.add_argument("--provenance", required=True)
        if name == "freeze":
            parser.add_argument("--draft-only", action="store_true")
        if name in (
            "plan",
            "fixture",
            "reference-build",
            "verify",
            "freeze",
            "submit",
            "reflect",
            "evaluate",
            "cancel",
            "resume",
            "finalize",
        ):
            parser.add_argument(
                "--operation-id",
                required=True,
                help="Stable idempotency key; reuse only for the same payload",
            )
            parser.add_argument("--actor", help="Defaults to the experiment owner label")
            parser.add_argument("--revision", type=int, help="CAS revision; defaults to a fresh server read")


def read_json(path, *, object_only=True):
    if path.stat().st_size > 2_500_000:
        raise ClientError("JSON input exceeds 2.5 MB", 2)
    value = json.loads(path.read_text())
    if object_only and not isinstance(value, dict):
        raise ClientError("Expected a JSON object: " + str(path), 2)
    return value


def service(root, action):
    client = Client(root)
    try:
        return client.connect()
    except ClientError as exc:
        if action != "ensure" or exc.code != 3:
            raise
    directory = root / ".davinci"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "service-start.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return client.connect()
        except ClientError as exc:
            if exc.code != 3:
                raise
        with (directory / "service.log").open("ab") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "davinci.product.cli",
                    "--workspace",
                    str(root),
                    "serve",
                    "--no-browser",
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                cwd=root,
            )
        for _ in range(100):
            try:
                return {**client.connect(), "started_pid": child.pid}
            except ClientError as exc:
                if exc.code != 3:
                    raise
            if child.poll() is not None:
                raise ClientError("Service failed to start; inspect .davinci/service.log", 3)
            time.sleep(0.1)
        raise ClientError(
            "Service is still starting; inspect .davinci/service.log and retry service status", 3
        )


def task_bundle(folder, client, image=None):
    folder = folder.resolve()
    plan = read_json(folder / "plan.json")
    runtime = read_json(folder / "runtime.json")
    requested = image or runtime["image"]
    runtime["image"] = client.request("GET", "/api/v2/runtimes/resolve?image=" + quote(requested, safe=""))[
        "image"
    ]
    resources = {"evaluate.py": (folder / "evaluate.py").read_text()}
    manifest = (
        read_json(folder / "resources.json", object_only=False)
        if (folder / "resources.json").exists()
        else []
    )
    if not isinstance(manifest, list) or not all(isinstance(name, str) for name in manifest):
        raise ClientError("resources.json must be an array of explicit filenames", 2)
    for name in manifest:
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or path.suffix not in (".py", ".json", ".txt"):
            raise ClientError("Invalid evaluator support resource path", 2)
        resources[name] = path.read_text()
    return {
        "plan": plan,
        "runtime": runtime,
        "evaluator": {
            "resources": resources,
            "provenance": "External custom task: explicit source snapshot from " + folder.name,
        },
    }


def run(args, root):
    if args.command == "service":
        return service(root, args.action), 0
    action = args.action
    if action == "schemas":
        from davinci.product.protocol import schema_catalog

        return schema_catalog(), 0
    if action == "instructions":
        return {"instructions": RESOURCES.joinpath("external/AGENT.md").read_text()}, 0
    client = Client(root)
    client.connect()
    if action == "open":
        body = read_json(args.file)
        if body.get("driver", "external") != "external":
            raise ClientError("external open requires driver=external", 2)
        return client.request("POST", "/api/v2/experiments", body), 0
    if action == "list":
        return client.request("GET", "/api/v2/experiments"), 0
    if action == "experience":
        return client.request("GET", "/api/v2/experience?q=" + quote(args.query)), 0
    if action == "artifact":
        return client.download(args.artifact_id, args.output), 0
    eid = args.experiment_id
    path = "/api/v2/experiments/" + quote(eid, safe="")
    if action == "status":
        return client.status(eid), 0
    if action in ("validate-plan", "capabilities", "results", "report", "job"):
        suffix = {
            "validate-plan": "plan-validation",
            "job": "jobs/" + quote(getattr(args, "job_id", ""), safe=""),
        }.get(action, action)
        data = client.request("GET", path + "/" + suffix)
        if action == "report" and args.output:
            args.output.write_text(json.dumps(data, indent=2) + "\n")
            return {"path": str(args.output.resolve()), "experiment_id": eid}, 0
        return data, 0
    if action == "wait":
        if not 0 <= args.timeout <= 86400:
            raise ClientError("Wait timeout must be between 0 and 86400 seconds", 2)
        data = client.wait(eid, args.job_id, args.timeout)
        return data, 7 if data.get("wait_timed_out") else (0 if data["status"] == "completed" else 6)
    if action == "revise":
        body = read_json(args.file)
        if body.get("driver", "external") != "external" or body.get("parent_experiment_id") != eid:
            raise ClientError(
                "Revision needs driver=external and parent_experiment_id matching the parent", 2
            )
        return client.request("POST", path + "/revisions", body), 0
    payload = {}
    endpoint = action
    if action == "plan":
        if bool(args.task) == bool(args.file):
            raise ClientError("Choose exactly one of --task or --file", 2)
        payload = task_bundle(args.task, client, args.image) if args.task else read_json(args.file)
    elif action in ("verify", "reflect"):
        payload = {"verification": read_json(args.file)} if action == "verify" else read_json(args.file)
        endpoint = "reflections" if action == "reflect" else "verify"
    elif action in ("submit", "reference-build"):
        proposal = Candidate(
            title=args.title,
            change=args.change,
            source=args.source.read_text(),
            parameters=read_json(args.parameters),
            metadata={"source_file": args.source.name, "parameters_file": args.parameters.name},
        ).model_dump()
        payload = (
            {"candidate": proposal}
            if action == "submit"
            else {"reference": {"candidate": proposal, "provenance": args.provenance}}
        )
        endpoint = "candidates" if action == "submit" else "reference-builds"
    elif action == "fixture":
        if args.step.stat().st_size > 32_000_000:
            raise ClientError("Reference STEP exceeds 32 MB", 2)
        payload = {
            "step_base64": base64.b64encode(args.step.read_bytes()).decode(),
            "provenance": args.provenance,
        }
        endpoint = "fixtures"
    elif action == "freeze":
        payload = {"draft_only": args.draft_only}
    return client.mutate(
        eid, endpoint, payload, args.operation_id, actor=args.actor, revision=args.revision
    ), 0

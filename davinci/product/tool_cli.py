"""Thin public client: never writes lifecycle state or executes generated code."""

import json
import time
from pathlib import Path
from urllib.parse import quote

from davinci.product.client import Client, ClientError


def add_commands(sub):
    tools = sub.add_parser("tools", help="Develop, independently check, pin and use CAD helpers")
    commands = tools.add_subparsers(dest="action", required=True)
    for name in ("classes", "list"):
        commands.add_parser(name)
    for name in (
        "open",
        "define",
        "propose",
        "check",
        "promote",
        "rollback",
        "invoke",
        "cancel",
        "pin",
        "generate",
    ):
        p = commands.add_parser(name)
        if name != "open":
            p.add_argument("identity", help="Experiment ID for pin/generate; tool development ID otherwise")
        p.add_argument("--file", type=Path, required=True)
    for name in ("status", "wait", "bundle"):
        p = commands.add_parser(name)
        p.add_argument("identity")
        if name == "wait":
            p.add_argument("--timeout", type=float, default=180)
        if name == "bundle":
            p.add_argument("job_id")
            p.add_argument("--output", type=Path, required=True)


def run(args, root):
    c = Client(root)
    c.connect()
    base = "/api/v2/tools"
    tid = quote(getattr(args, "identity", ""), safe="")
    if args.action in ("classes", "list"):
        return c.request("GET", base + ("/classes" if args.action == "classes" else "")), 0
    if args.action in ("status", "wait"):
        deadline = time.monotonic() + getattr(args, "timeout", 0)
        while True:
            row = c.request("GET", base + "/" + tid)
            if args.action == "status" or row["phase"] not in ("queued", "running"):
                return row, 6 if args.action == "wait" and row["phase"] in ("interrupted", "cancelled") else 0
            if time.monotonic() >= deadline:
                return row, 7
            time.sleep(0.2)
    if args.action == "bundle":
        data = c.request("GET", base + "/" + tid + "/bundles/" + quote(args.job_id, safe=""))
        args.output.write_text(json.dumps(data, indent=2) + "\n")
        return {"path": str(args.output.resolve()), "requires_independent_design_evaluation": True}, 0
    if args.file.stat().st_size > 100_000:
        raise ClientError("Tool command JSON exceeds 100 KB", 2)
    body = json.loads(args.file.read_text())
    if args.action in ("pin", "generate"):
        suffix = "tool-pins" if args.action == "pin" else "tool-proposals"
        return c.request("POST", "/api/v2/experiments/" + tid + "/" + suffix, body), 0
    return c.request("POST", base if args.action == "open" else base + "/" + tid + "/" + args.action, body), 0

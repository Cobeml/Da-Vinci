"""Thin service client shared by managed users and external coding agents."""

import json
from pathlib import Path
from urllib.parse import quote

from davinci.product.client import Client, ClientError


def add_commands(sub):
    memory = sub.add_parser(
        "memory", help="Project-scoped engineering experience; never transferred acceptance"
    )
    commands = memory.add_subparsers(dest="action", required=True)
    search = commands.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--experiment")
    search.add_argument("--context", type=Path)
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--cursor")
    search.add_argument("--reject-incompatible", action="store_true")
    search.add_argument("--include-superseded", action="store_true")
    browse = commands.add_parser("browse")
    browse.add_argument("--cursor", default="")
    browse.add_argument("--limit", type=int, default=50)
    for action in ("inspect", "supersede"):
        parser = commands.add_parser(action)
        parser.add_argument("identity")
        if action == "supersede":
            parser.add_argument("--file", type=Path, required=True)
    for action in ("note", "exact", "import"):
        parser = commands.add_parser(action)
        parser.add_argument("--file", type=Path, required=True)
        if action == "import":
            parser.add_argument("--actor", required=True)
            parser.add_argument("--operation-id", required=True)
    export = commands.add_parser("export")
    export.add_argument("--ids", nargs="+", required=True)
    export.add_argument("--include-artifacts", action="store_true")
    export.add_argument("--output", type=Path, required=True)
    commands.add_parser("indexes")
    reindex = commands.add_parser("reindex")
    reindex.add_argument("--cursor", default="")
    capture = commands.add_parser("capture")
    capture.add_argument("--experiment", required=True)
    capture.add_argument("--result", required=True)


def run(args, root):
    client = Client(root)
    client.connect()
    base = "/api/v2/memory/"

    def read(path):
        if path.stat().st_size > 16_000_000:
            raise ClientError("Memory JSON exceeds 16 MB", 2)
        return json.loads(path.read_text())

    if args.action == "search":
        body = {
            "query": args.query,
            "experiment_id": args.experiment,
            "limit": args.limit,
            "cursor": args.cursor,
            "include_incompatible": not args.reject_incompatible,
            "include_superseded": args.include_superseded,
        }
        if args.context:
            body["applicability"] = read(args.context)
        return client.request("POST", base + "search", body), 0
    if args.action == "inspect":
        return client.request("GET", base + "records/" + quote(args.identity, safe="")), 0
    if args.action == "browse":
        return client.request(
            "GET", base + "records?after_id=" + quote(args.cursor, safe="") + "&limit=" + str(args.limit)
        ), 0
    if args.action == "indexes":
        return client.request("GET", base + "indexes"), 0
    if args.action == "reindex":
        return client.request("POST", base + "reindex", {"after_id": args.cursor}), 0
    if args.action == "capture":
        return client.request(
            "POST", base + "capture", {"experiment_id": args.experiment, "result_id": args.result}
        ), 0
    if args.action == "supersede":
        return client.request(
            "POST", base + "records/" + quote(args.identity, safe="") + "/supersede", read(args.file)
        ), 0
    if args.action == "note":
        return client.request("POST", base + "notes", read(args.file)), 0
    if args.action == "exact":
        return client.request("POST", base + "exact", read(args.file)), 0
    if args.action == "import":
        return client.request(
            "POST",
            base + "import",
            {"actor": args.actor, "operation_id": args.operation_id, "bundle": read(args.file)},
        ), 0
    if args.action == "export":
        bundle = client.request(
            "POST", base + "export", {"ids": args.ids, "include_artifacts": args.include_artifacts}
        )
        args.output.write_text(json.dumps(bundle, indent=2) + "\n")
        return {"path": str(args.output.resolve()), "records": len(bundle["records"])}, 0
    raise ClientError("Unknown memory operation", 2)

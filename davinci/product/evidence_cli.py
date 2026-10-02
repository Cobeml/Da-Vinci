"""Evidence client; cannot insert scores or change evaluation inputs."""

import json
from pathlib import Path
from urllib.parse import quote

from davinci.product.client import Client, ClientError


def add_commands(sub):
    parser = sub.add_parser(
        "evidence", help="Attributed specimen measurements and separate calibration/validation"
    )
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("measure", "calibrate", "validate", "import"):
        p = actions.add_parser(name)
        p.add_argument("--file", type=Path, required=True)
    p = actions.add_parser("inspect")
    p.add_argument("identity")
    p = actions.add_parser("list")
    p.add_argument("--cursor", default="")
    p.add_argument("--limit", type=int, default=50)
    p = actions.add_parser("export")
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--include-artifacts", action="store_true")
    p.add_argument("--output", type=Path, required=True)


def run(args, root):
    c = Client(root)
    c.connect()
    base = "/api/v2/evidence"
    if args.action == "inspect":
        return c.request("GET", base + "/" + quote(args.identity, safe="")), 0
    if args.action == "list":
        return c.request(
            "GET", base + "?after_id=" + quote(args.cursor, safe="") + "&limit=" + str(args.limit)
        ), 0
    if args.action == "export":
        result = c.request(
            "POST", base + "/export", {"ids": args.ids, "include_artifacts": args.include_artifacts}
        )
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        return {"path": str(args.output.resolve()), "records": len(result["records"])}, 0
    if args.file.stat().st_size > 20_000_000:
        raise ClientError("Evidence command exceeds 20MB", 2)
    suffix = {
        "measure": "measurements",
        "calibrate": "calibrations",
        "validate": "validations",
        "import": "import",
    }[args.action]
    return c.request("POST", base + "/" + suffix, json.loads(args.file.read_text())), 0

"""Thin managed-request client; the workspace service owns all execution."""

from urllib.parse import quote

from davinci.product.client import Client, ClientError
from davinci.product.external_cli import read_json


def add_commands(sub):
    from pathlib import Path

    parser = sub.add_parser(
        "managed", help="Author and run a verified experiment from a natural-language request"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("recipes")
    start = commands.add_parser("request")
    start.add_argument("--description", required=True)
    start.add_argument("--object", required=True)
    start.add_argument("--name")
    start.add_argument("--actor", default="user")
    start.add_argument("--operation-id", required=True)
    start.add_argument("--image", default="da-vinci-cad:local")
    start.add_argument("--budget-usd", type=float, default=10)
    start.add_argument("--max-candidates", type=int, default=6)
    start.add_argument("--search", choices=["agent", "coordinate"], default="agent")
    start.add_argument("--existing-experiment")
    start.add_argument("--existing-candidate")
    for action in ("status", "results", "report", "cancel", "resume", "answer"):
        command = commands.add_parser(action)
        command.add_argument("experiment_id")
        if action in ("cancel", "resume", "answer"):
            command.add_argument("--operation-id", required=True)
        if action == "answer":
            command.add_argument(
                "--file", type=Path, required=True, help="JSON question-ID to answer mapping"
            )


def run(args, root):
    client = Client(root)
    client.connect()
    if args.action == "recipes":
        return client.request("GET", "/api/v2/test-recipes"), 0
    if args.action == "request":
        image = client.request("GET", "/api/v2/runtimes/resolve?image=" + quote(args.image, safe=""))["image"]
        body = {
            "object": {"slug": args.object, "name": args.name or args.object},
            "description": args.description,
            "actor": args.actor,
            "operation_id": args.operation_id,
            "runtime": {
                "image": image,
                "solver": "CadQuery + NumPy analytic screening",
                "provenance": "Explicit local runtime " + args.image,
            },
            "budget_usd": args.budget_usd,
            "policy": {
                "max_candidates": args.max_candidates,
                "min_candidates": min(2, args.max_candidates),
                "search": args.search,
            },
            "existing_experiment_id": args.existing_experiment,
            "existing_candidate_id": args.existing_candidate,
        }
        return client.request("POST", "/api/v2/managed-experiments", body), 0
    row = client.status(args.experiment_id)
    if row["driver"] != "managed" or not row.get("managed"):
        raise ClientError("Use an automatic managed experiment", 4)
    path = "/api/v2/experiments/" + quote(args.experiment_id, safe="")
    if args.action == "status":
        return row, 0
    if args.action in ("results", "report"):
        return client.request("GET", path + "/" + args.action), 0
    body = {"actor": row["actor"], "revision": row["revision"], "operation_id": args.operation_id}
    action = args.action
    if action == "answer":
        body["answers"] = read_json(args.file)
        action = "answers"
    return client.request("POST", path + "/" + action, body), 0

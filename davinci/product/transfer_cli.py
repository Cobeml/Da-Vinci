"""Driver-neutral public continuation and ownership operations."""

from urllib.parse import quote

from davinci.product.client import Client


def add_commands(sub):
    group = sub.add_parser("experiment", help="Continue or hand off a frozen experiment")
    actions = group.add_subparsers(dest="action", required=True)
    for name in ("handoff", "continue"):
        p = actions.add_parser(name)
        p.add_argument("experiment_id")
        p.add_argument("--driver", choices=["managed", "external"], required=True)
        p.add_argument("--owner", required=True)
        p.add_argument("--operation-id", required=True)
        p.add_argument("--max-candidates", type=int, default=4)
        if name == "handoff":
            p.add_argument("--reason", required=True)
        else:
            p.add_argument("--candidate", required=True)
            p.add_argument("--focus", default="")
            p.add_argument("--budget-usd", type=float, default=10)


def run(args, root):
    c = Client(root)
    c.connect()
    row = c.status(args.experiment_id)
    body = {
        "actor": row["actor"],
        "revision": row["revision"],
        "operation_id": args.operation_id,
        "driver": args.driver,
        "new_actor": args.owner,
        "policy": {"max_candidates": args.max_candidates, "min_candidates": min(2, args.max_candidates)},
    }
    if args.action == "handoff":
        body["reason"] = args.reason
    else:
        body.update(candidate_id=args.candidate, focus=args.focus, budget_usd=args.budget_usd)
    return c.request(
        "POST", f"/api/v2/experiments/{quote(args.experiment_id, safe='')}/{args.action}", body
    ), 0

"""Read-only shared UI projections; these never create evaluation evidence."""

from davinci.product.lifecycle_api import next_actions


def experiment_view(row):
    # Explicit projection excludes provider configuration, request payloads and internal receipts.
    names = (
        "_id",
        "lifecycle_version",
        "object_id",
        "description",
        "driver",
        "mode",
        "actor",
        "phase",
        "status",
        "revision",
        "created_at",
        "pending_input",
        "plan",
        "suite_id",
        "draft_only",
        "coverage",
        "capabilities",
        "validation_gaps",
        "candidates",
        "results",
        "experiences",
        "report",
        "report_artifact",
        "parent_experiment_id",
        "continuation",
        "handoffs",
        "spent_usd",
        "budget_usd",
        "job",
    )
    result = {k: row[k] for k in names if k in row}
    if result.get("job"):
        result["job"] = {k: v for k, v in result["job"].items() if k != "payload"}
    state = row.get("managed")
    if state:
        result["managed"] = {
            k: state[k]
            for k in (
                "stage",
                "status",
                "questions",
                "answers",
                "experience",
                "error",
                "stop_reason",
                "capability_report",
                "final_result_id",
                "correction_id",
                "iteration",
                "policy",
            )
            if k in state
        }
    result["next_actions"] = next_actions(row)
    return result


def outcome(result, draft=False):
    if draft:
        return "draft"
    if not result:
        return "not_run"
    if result["design_accepted"] and result["evidence_complete"]:
        return "accepted_under_stated_tests"
    statuses = {t["status"] for t in result["tests"]}
    for status in (
        "invalid_setup",
        "numerical_failure",
        "unsupported_capability",
        "not_run",
        "physical_failure",
    ):
        if status in statuses:
            return status
    return "incomplete_evidence"


def project(row):
    objective = row["plan"].get("objective") or {"metric": "", "direction": "minimize", "target": None}
    state = row.get("managed") or {}
    designs = []
    for candidate in row["candidates"]:
        results = [r for r in row["results"] if r["candidate_id"] == candidate["id"]]
        latest = results[-1] if results else None
        metrics = {k: v for t in latest["tests"] for k, v in t["metrics"].items()} if latest else {}
        designs.append(
            {
                "_id": candidate["id"],
                "run_id": row["_id"],
                "iteration": candidate["iteration"],
                "title": candidate["title"],
                "change": candidate["change"],
                "parameters": candidate["parameters"],
                "source": "",
                "source_artifact": candidate["source_artifact"],
                "artifacts": latest["artifacts"] if latest else {},
                "evaluation": {
                    "outcome": outcome(latest, row["draft_only"]),
                    "metrics": metrics,
                    "violations": [],
                },
                "result": latest,
                "results": results,
            }
        )
    accepted = [d for d in designs if d["evaluation"]["outcome"] == "accepted_under_stated_tests"]
    if row["phase"] == "completed" and row.get("report"):
        accepted = [d for d in accepted if d["_id"] in row["report"]["accepted_candidate_ids"]]
    best = (
        min(
            accepted,
            key=lambda d: (
                d["evaluation"]["metrics"].get(objective["metric"], {}).get("value", 0)
                * (1 if objective["direction"] == "minimize" else -1)
            ),
        )
        if accepted
        else None
    )
    view = {
        "_id": row["_id"],
        "status": row["phase"],
        "phase": row["phase"],
        "created_at": row["created_at"],
        "completed_iterations": len(row["results"]),
        "spent_usd": row["spent_usd"],
        "best_id": best["_id"] if best else None,
        "task_version": row.get("suite_id") or "draft",
        "driver": row["driver"],
        "experiment": experiment_view(row),
        "config": {
            "version": 2,
            "object": row["opening"]["object"],
            "task": {"template": "experiment", "description": row["description"]},
            "objective": objective,
            "constraints": [],
            "run": {
                "mode": row["mode"],
                "iterations": state.get("policy", {}).get("max_candidates", 0),
                "budget_usd": row["budget_usd"],
            },
        },
    }
    return view, designs


def detail(engine, object_id):
    obj = engine.store.get("objects", object_id)
    old = engine.detail(object_id) if obj else None
    rows = engine.store.list(
        "runs", {"lifecycle_version": 2, "object_id": object_id, **engine.experience.scope}, limit=10000
    )
    if not rows and old is None:
        raise KeyError(object_id)
    runs, designs = list(old["runs"]) if old else [], list(old["designs"]) if old else []
    for row in rows:
        run, candidates = project(row)
        runs.append(run)
        designs.extend(candidates)
    runs.sort(key=lambda r: (r["created_at"], r["_id"]), reverse=True)
    name = runs[0]["config"]["object"]["name"] if runs else obj["name"]
    return {
        "_id": object_id,
        "name": name,
        "template": runs[0]["config"]["task"]["template"] if runs else obj["template"],
        "runs": runs,
        "designs": designs,
    }


def gallery(engine):
    ids = {o["_id"] for o in engine.store.list("objects", limit=10000)}
    ids.update(
        r["object_id"]
        for r in engine.store.list("runs", {"lifecycle_version": 2, **engine.experience.scope}, limit=10000)
    )
    cards = []
    for oid in sorted(ids):
        item = detail(engine, oid)
        run = item["runs"][0] if item["runs"] else None
        candidates = [d for d in item["designs"] if run and d["run_id"] == run["_id"]]
        preview = next((d for d in candidates if d["_id"] == run.get("best_id")), None) if run else None
        preview = preview or next((d for d in reversed(candidates) if d["artifacts"].get("model.glb")), None)
        cards.append(
            {
                **{k: item[k] for k in ("_id", "name", "template")},
                "run": run,
                "preview": preview,
                "iteration_count": len(item["designs"]),
            }
        )
    return sorted(cards, key=lambda o: (o["run"] or {}).get("created_at", ""), reverse=True)

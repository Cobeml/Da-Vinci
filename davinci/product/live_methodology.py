"""Explicit opt-in, budgeted live-model trials. Never invoked by default tests or CI."""

import argparse
import json
import math
import time
from pathlib import Path

from davinci.product import recipes
from davinci.product.client import Client
from davinci.product.methodology import requirements


def independent_check(row):
    """Predeclared physical contract and algebraic oracle, never model self-assessment."""
    expected = recipes.make_plan(requirements("heldout-a")).model_dump(mode="json")
    actual = row.get("plan") or {}
    issues = []
    for key in ("design_schema", "design_units"):
        if actual.get(key) != expected[key]:
            issues.append(key)

    # Strip editorial provenance only; all quantities, limits and binding rules stay fixed.
    def physical(value):
        if isinstance(value, dict):
            return {
                k: physical(v)
                for k, v in value.items()
                if k
                not in {
                    "description",
                    "provenance",
                    "material_provenance",
                    "input_provenance",
                    "source",
                    "requirements",
                    "applicability",
                    "method",
                }
            }
        if isinstance(value, list):
            return [physical(v) for v in value]
        return value

    for key in ("materials", "interfaces", "tests"):
        if physical(actual.get(key)) != physical(expected[key]):
            issues.append(key)
    results = row.get("results", [])
    final = next((r for r in results if r["id"] == row.get("managed", {}).get("final_result_id")), None)
    oracle_matches = False
    if final and final.get("evidence_complete"):
        try:
            metrics = final["tests"][0]["metrics"]
            p = requirements("heldout-a").inputs
            thickness = metrics["mass_g"]["value"] / (p.length_mm * p.width_mm * p.density_g_mm3)
            values = recipes.metrics(p, thickness)
            oracle_matches = all(
                math.isclose(metrics[k]["value"], v, rel_tol=1e-6, abs_tol=1e-5) for k, v in values.items()
            )
        except (KeyError, IndexError, ZeroDivisionError):
            pass
    return dict(
        contract_mismatches=issues,
        oracle_matches=oracle_matches,
        protocol_accepted=bool(not issues and oracle_matches and final and final["design_accepted"]),
        interpretation="Independent nominal beam comparison only; no general structural validation",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--allow-paid-model-calls", action="store_true")
    p.add_argument("--budget-usd", type=float, required=True)
    p.add_argument("--trials", type=int, default=2)
    p.add_argument("--operation", required=True, help="Unique campaign ID; same ID reuses existing requests")
    p.add_argument(
        "--memory-ids", nargs="*", default=[], help="Predeclared reusable corpus; never held-out answers"
    )
    a = p.parse_args()
    if not a.allow_paid_model_calls or not 0 < a.budget_usd <= 25 or not 1 <= a.trials <= 3:
        p.error("Explicit paid-call opt-in, total budget (0,25] USD, and 1–3 trials required")
    if not a.memory_ids:
        p.error("Specify a frozen reusable memory corpus for the enabled/disabled comparison")
    c = Client(a.workspace)
    health = c.connect()
    if not health["live_available"]:
        raise ValueError("Configure server-side credentials on the ordinary workspace service")
    for identity in a.memory_ids:
        c.request("GET", "/api/v2/memory/records/" + identity)
    image = c.request("GET", "/api/v2/runtimes/resolve?image=da-vinci-cad%3Alocal")["image"]
    a.output.mkdir(parents=True, exist_ok=True)
    per_run = a.budget_usd / (2 * a.trials)
    protocol = dict(
        version=1,
        model=health["model"],
        image=image,
        total_budget_usd=a.budget_usd,
        per_run_budget_usd=per_run,
        trials=a.trials,
        memory_ids=a.memory_ids,
        acceptance="Fixed rectangular-beam analytic recipe; independently checked references and final solver evidence",
        reporting="Retain every failed, uncertain, exhausted and successful trial; no cherry-picking; small trial counts are descriptive",
    )
    (a.output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    for trial in range(a.trials):
        # Alternate order across repetitions; proposals remain live, not fixture answers.
        for arm in ("disabled", "enabled") if trial % 2 == 0 else ("enabled", "disabled"):
            r = requirements("heldout-a")
            description = (
                "Optimize beam mass under the following fixed nominal screening inputs; preserve length, width and root interface. No fatigue/contact certification. "
                + json.dumps(r.inputs.model_dump())
            )
            row = c.request(
                "POST",
                "/api/v2/managed-experiments",
                dict(
                    object={
                        "slug": f"live-heldout-{trial}-{arm}",
                        "name": f"Live held-out trial {trial} {arm}",
                    },
                    description=description,
                    actor="live-benchmark-user",
                    operation_id=f"{a.operation}-{trial}-{arm}",
                    mode="live",
                    budget_usd=per_run,
                    runtime=dict(
                        image=image,
                        solver="CadQuery / NumPy beam",
                        provenance="Explicit live protocol pinned runtime",
                        cpu_cores=1,
                        memory_gb=2,
                        job_seconds=180,
                        compute_seconds=180,
                    ),
                    policy=dict(
                        max_candidates=4, min_candidates=2, max_solver_jobs=30, solver_compute_seconds=6000
                    ),
                    metadata=dict(
                        memory_retrieval=arm, memory_record_ids=a.memory_ids, live_protocol=protocol
                    ),
                ),
            )
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline:
                row = c.status(row["_id"])
                if row["phase"] in ("awaiting_input", "interrupted", "cancelled") or row.get(
                    "managed", {}
                ).get("status") in ("blocked", "completed"):
                    break
                time.sleep(1)
            else:
                row = c.request(
                    "POST",
                    f"/api/v2/experiments/{row['_id']}/cancel",
                    dict(actor=row["actor"], revision=row["revision"], operation_id="protocol-timeout"),
                )
            check = independent_check(row)
            (a.output / f"{trial}-{arm}-independent.json").write_text(json.dumps(check, indent=2) + "\n")
            (a.output / f"{trial}-{arm}.json").write_text(json.dumps(row, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "trial": trial,
                        "arm": arm,
                        "experiment_id": row["_id"],
                        "phase": row["phase"],
                        "spent_usd": row["spent_usd"],
                    }
                ),
                flush=True,
            )
    print(
        "No engineering improvement claim is inferred automatically; compare all trials and independent final evidence."
    )


if __name__ == "__main__":
    main()

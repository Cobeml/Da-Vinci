"""Public HTTP walkthrough. Run with an installed package and a running workspace service.

The external route needs no provider. The managed-fixture route is exercised in
native tests; a live managed handoff is optional and requires configured credentials.
"""

import argparse
import json
from pathlib import Path

from davinci.product.client import Client
from davinci.product.structural.examples import beam_reference, bracket_plan, candidate, quantity


def plan_bundle(image):
    plan = bracket_plan().model_dump(mode="json")
    return {
        "plan": plan,
        "runtime": {
            "image": image,
            "solver": "Gmsh 4.15.2 / CalculiX 2.23 CPU SPOOLES",
            "provenance": "Pinned optional structural runtime",
            "timeout_seconds": 300,
            "cpu_cores": 1,
            "memory_gb": 4,
            "artifact_bytes": 200000000,
            "file_bytes": 64000000,
        },
        "evaluator": {
            "resources": {
                "evaluate.py": "# Host-owned calculix-static adapter; this file is not executed.\n"
            },
            "provenance": "Trusted packaged adapter and independently specified beam references",
        },
    }


def author(client, *, driver="external", operation="structural-example", mode="live"):
    row = client.request(
        "POST",
        "/api/v2/experiments",
        {
            "object": {"slug": "structural-bracket", "name": "Static shelf bracket"},
            "description": "Stiffen a perforated shelf bracket under the frozen uniform 20 N end load; no changes to materials, interfaces or limits.",
            "driver": driver,
            "mode": mode,
            "actor": "structural-author",
            "operation_id": operation,
        },
    )
    eid = row["_id"]

    def post(action, payload, op):
        row = client.status(eid)
        return client.request(
            "POST",
            f"/api/v2/experiments/{eid}/{action}",
            {"actor": row["actor"], "revision": row["revision"], "operation_id": op, **payload},
        )

    def wait(job):
        result = client.wait(eid, job["id"], 900)
        if result["status"] != "completed" or result.get("failures") or result.get("wait_timed_out"):
            raise RuntimeError(f"Inspect failed/incomplete job: {result}")
        return result

    if row["phase"] != "draft":
        return row
    image = client.request("GET", "/api/v2/runtimes/resolve?image=da-vinci-structural%3Alocal")["image"]
    plan = bracket_plan().model_dump(mode="json")
    if driver == "managed":
        # Deterministic/native tests use the public managed author stage; live use needs credentials.
        authored = post("managed/author", {}, "plan")
        if authored["plan"] != plan:
            raise RuntimeError(
                "Managed author returned a different benchmark contract; inspect it before proceeding"
            )
    else:
        post("plan", plan_bundle(image), "plan")
    for variant, thickness in [("beam-thick", 8), ("beam-thin", 4)]:
        reference = post(
            "reference-builds",
            {
                "reference": {
                    "candidate": candidate(variant),
                    "provenance": "Prismatic analytical reference only, before candidate generation",
                }
            },
            "reference-" + variant,
        )
        artifact = wait(reference)["fixture_artifacts"][0]
        expected = beam_reference(thickness)
        units = plan["tests"][0]["metrics"]
        verification = {
            "test_id": "static",
            "fixture_artifact": artifact,
            "expected_status": "pass" if thickness == 8 else "physical_failure",
            "reference_metrics": {
                k: quantity(
                    v,
                    units[k],
                    {"mass_g": "mass", "load_displacement_mm": "length", "gauge_von_mises_mpa": "pressure"}[
                        k
                    ],
                )
                for k, v in expected.items()
            },
            "tolerances": {
                "mass_g": 0.00001,
                "load_displacement_mm": expected["load_displacement_mm"] * 0.06,
                "gauge_von_mises_mpa": expected["gauge_von_mises_mpa"] * 0.15,
            },
            "provenance": "Independent E-B bending + Timoshenko shear; 6 percent deflection / 15 percent gauge-stress allowance for 3D end/Poisson/shear effects; mass from nominal prismatic dimensions. These are reference comparison tolerances, not acceptance-limit changes.",
        }
        wait(post("verify", {"verification": verification}, "verify-" + variant))
    readiness = client.request("GET", f"/api/v2/experiments/{eid}/plan-validation")
    if not readiness["ready_to_freeze"]:
        raise RuntimeError(f"Independent reference verification not complete: {readiness}")
    post("freeze", {}, "freeze")
    return client.status(eid)


def external(client, operation="structural-example"):
    row = author(client, operation=operation)
    eid = row["_id"]
    if row["phase"] == "completed":
        return client.request("GET", f"/api/v2/experiments/{eid}/report")
    for i, variant in enumerate(("bracket-base", "bracket-ribbed")):
        client.mutate(eid, "candidates", {"candidate": candidate(variant)}, f"candidate-{i}")
        job = client.mutate(eid, "evaluate", {}, f"evaluate-{i}")
        result = client.wait(eid, job["id"], 900)
        if result["status"] != "completed" or result.get("wait_timed_out"):
            raise RuntimeError(result)
        measured = client.status(eid)["results"][-1]
        if measured["evidence_complete"] is not True or measured["design_accepted"] != (i == 1):
            raise RuntimeError(f"Unexpected bracket result: {measured}")
        client.mutate(
            eid,
            "reflections",
            {
                "result_id": measured["id"],
                "lesson": "Hypothesis: tapered ribs stiffen the shelf load path at extra mass. Compare measured response under unchanged force, support and gauge; local notch/fatigue strength remains untested.",
            },
            f"reflect-{i}",
        )
    client.mutate(eid, "finalize", {}, "finalize")
    return client.request("GET", f"/api/v2/experiments/{eid}/report")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--operation-id", default="structural-example")
    parser.add_argument("--report", type=Path, default=Path("structural-report.json"))
    args = parser.parse_args()
    client = Client(args.workspace)
    client.connect()
    report = external(client, args.operation_id)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "report": str(args.report.resolve()),
                "experiment_id": report["experiment"]["_id"],
            }
        )
    )


if __name__ == "__main__":
    main()

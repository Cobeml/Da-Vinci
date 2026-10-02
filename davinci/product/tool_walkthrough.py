"""Installed public example: learn a plate helper, reuse it, independently evaluate mass.

No host CAD, private Engine calls, model provider, or database access.
"""

import argparse
import json
import math
import time
from pathlib import Path

from davinci.product.client import Client
from davinci.product.resources.tools.plate_example import BROKEN, MISLEADING, SOURCE
from davinci.product.tool_contracts import PlateArguments
from davinci.product.tool_execution import references

REFERENCE = """import cadquery as cq
def build(p, interfaces):
    plate = cq.Workplane('XY').rect(p['length'],p['width']).extrude(p['thickness'])
    for x,y in p['holes']:
        cutter = cq.Workplane('XY').center(x,y).circle(p['radius']).extrude(p['thickness'])
        plate = plate.cut(cutter)
    return cq.Assembly(plate.translate(p['translation']))
"""

EVALUATOR = """import cadquery as cq
def evaluate(step, request):
    solid=cq.importers.importStep(step).val()
    valid=solid.isValid() and len(solid.Solids())==1
    density=request['materials'][0]['properties']['density']['value']
    return {'test_id':'mass','status':'pass','reason':'ok','applicable':valid,'mesh_valid':True,'bindings':{},
        'metrics':{'mass_g':{'value':float(solid.Volume()*density),'unit':'g','numerical_error':0.000001,'uncertainty':0.0}}}
"""


def plan():
    return {
        "requirements": [
            {
                "id": "mass",
                "description": "Nominal CAD-derived mass at most 12 g",
                "source": "Construction demonstration, no strength requirement",
            }
        ],
        "assumptions": [
            {
                "description": "Only homogeneous nominal mass is evaluated",
                "source": "Explicit example scope",
                "applicability": "Does not establish structural suitability",
            }
        ],
        "materials": [
            {
                "name": "nominal-aluminium",
                "provenance": "Example nominal density, not measurement",
                "properties": {"density": {"value": 0.0027, "unit": "g/mm3", "dimension": "density"}},
            }
        ],
        "interfaces": [],
        "design_schema": PlateArguments.model_json_schema(),
        "design_units": {
            "unit": "1",
            **{k: "mm" for k in ("length", "width", "thickness", "radius", "holes", "translation")},
        },
        "objective": {"metric": "mass_g", "direction": "minimize"},
        "tests": [
            {
                "id": "mass",
                "requirements": ["mass"],
                "capability": "CAD volume times nominal density",
                "applicability": "Positive-volume valid homogeneous solid only; mass measurement, no stress physics",
                "fixed_inputs": {},
                "load_cases": [],
                "metrics": {"mass_g": "g"},
                "accuracy": {
                    "mass_g": {
                        "method": "Analytical plate-minus-cylinder reference comparison",
                        "max_numerical_error": 0.0001,
                        "max_uncertainty": 0,
                    }
                },
                "mesh_rule": "Exact BRep volume; no physical mesh required",
                "criteria": [{"metric": "mass_g", "operator": "<=", "limit": 12, "unit": "g"}],
            }
        ],
    }


def run(workspace, operation="plate-helper-example"):
    client = Client(workspace)
    client.connect()
    image = client.request("GET", "/api/v2/runtimes/resolve?image=da-vinci-cad%3Alocal")["image"]
    runtime = dict(
        image=image,
        solver="CadQuery geometry and nominal mass only",
        provenance="Resolved local image; no model needed",
        cpu_cores=1,
        memory_gb=2,
        timeout_seconds=60,
        job_seconds=120,
        compute_seconds=120,
        artifact_bytes=16_000_000,
        file_bytes=8_000_000,
    )

    def author(suffix):
        row = client.request(
            "POST",
            "/api/v2/experiments",
            dict(
                object={"slug": suffix, "name": suffix},
                description="Create positioned perforated plates; measure nominal mass independently. No strength claim.",
                driver="external",
                mode="live",
                actor="tool-author",
                operation_id=operation + "-" + suffix,
            ),
        )
        eid = row["_id"]
        if row["phase"] != "draft":
            return client.status(eid)
        client.mutate(
            eid,
            "plan",
            dict(
                plan=plan(),
                runtime=runtime,
                evaluator={
                    "resources": {"evaluate.py": EVALUATOR},
                    "provenance": "Independent exported-volume mass calculation",
                },
            ),
            "plan",
        )
        for thickness in (3, 8):
            args = {**references()[0], "thickness": thickness}
            job = client.mutate(
                eid,
                "reference-builds",
                {
                    "reference": {
                        "candidate": {
                            "title": "Independent plate fixture",
                            "source": REFERENCE,
                            "parameters": args,
                        },
                        "provenance": "Rect/extrude plate and individual cylindrical cutters; analytic volume reference",
                    }
                },
                f"build-{thickness}",
            )
            done = client.wait(eid, job["id"], 180)
            if done["status"] != "completed" or not done.get("fixture_artifacts"):
                raise RuntimeError(done)
            expected = (40 * 24 - 2 * math.pi * 2**2) * thickness * 0.0027
            job = client.mutate(
                eid,
                "verify",
                {
                    "verification": {
                        "test_id": "mass",
                        "fixture_artifact": done["fixture_artifacts"][0],
                        "expected_status": "pass" if thickness == 3 else "physical_failure",
                        "reference_metrics": {
                            "mass_g": {"value": expected, "unit": "g", "dimension": "mass"}
                        },
                        "tolerances": {"mass_g": 0.0001},
                        "provenance": "Analytical rectangular-prism minus two cylinders times nominal density",
                    }
                },
                f"verify-{thickness}",
            )
            done = client.wait(eid, job["id"], 180)
            if done["status"] != "completed" or done.get("failures"):
                raise RuntimeError(done)
        return client.mutate(eid, "freeze", {}, "freeze")

    first = author("plate-fixture-a")
    tool = client.request(
        "POST",
        "/api/v2/tools",
        dict(
            actor="tool-author",
            operation_id=operation + "-need",
            experiment_id=first["_id"],
            name="placed-plate",
            need="Repeated off-origin plate construction loses its translation",
            observations=["Symmetric origin-only testing misses translated and asymmetric failures"],
        ),
    )
    tid = tool["_id"]

    def status():
        return client.request("GET", "/api/v2/tools/" + tid)

    def post(action, payload, op):
        current = status()
        return client.request(
            "POST",
            f"/api/v2/tools/{tid}/{action}",
            dict(actor="tool-author", revision=current["revision"], operation_id=op, **payload),
        )

    def wait():
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            row = status()
            if row["phase"] not in ("queued", "running"):
                return row
            time.sleep(0.1)
        raise RuntimeError("Tool job wait timed out; inspect status, do not resubmit blindly")

    post(
        "define",
        dict(
            runtime=runtime,
            applicability="Rectangular mm plates, separated cylindrical through holes; construction only",
        ),
        "define",
    )
    versions = []
    for index, source in enumerate((BROKEN, SOURCE, MISLEADING)):
        row = post(
            "propose",
            dict(
                source=source,
                summary=[
                    "Reproduce lost placement",
                    "Preserve placement",
                    "Misleading mirrored hole placement",
                ][index],
                parent_version=versions[-1] if versions else None,
            ),
            f"propose-{index}",
        )
        vid = row["versions"][-1]["id"]
        versions.append(vid)
        post("check", {"version_id": vid}, f"check-{index}")
        row = wait()
        if row["job"]["passed"] != (index == 1):
            raise RuntimeError(row["job"])
    good = versions[1]
    post(
        "promote",
        dict(version_id=good, reason="Independent placement, volume, topology and hole regressions passed"),
        "promote",
    )
    reports = []
    for i, row in enumerate((first, author("plate-fixture-b"))):
        eid = row["_id"]
        if client.status(eid)["phase"] == "completed":
            reports.append(client.request("GET", f"/api/v2/experiments/{eid}/report"))
            continue
        client.mutate(
            eid,
            "tool-pins",
            dict(development_id=tid, version_id=good, contract_id=status()["contract_id"]),
            "pin-helper",
        )
        post("invoke", dict(experiment_id=eid, arguments=references()[i]), f"invoke-{i}")
        done = wait()["job"]
        if not done["passed"]:
            raise RuntimeError(done)
        candidate = client.request("GET", f"/api/v2/tools/{tid}/bundles/{done['id']}")
        client.mutate(eid, "candidates", {"candidate": candidate}, "candidate")
        job = client.mutate(eid, "evaluate", {}, "evaluate")
        client.wait(eid, job["id"], 180)
        result = client.status(eid)["results"][-1]
        if not result["design_accepted"]:
            raise RuntimeError(result)
        client.mutate(
            eid,
            "reflections",
            dict(
                lesson="Construction and nominal mass checked independently; structural performance remains untested.",
                result_id=result["id"],
            ),
            "reflect",
        )
        client.mutate(eid, "finalize", {}, "finalize")
        reports.append(client.request("GET", f"/api/v2/experiments/{eid}/report"))
    return {
        "development": status(),
        "reports": reports,
        "scope": "CAD construction and nominal mass only; no structural certification",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--operation", default="plate-helper-example")
    parser.add_argument("--report", type=Path, default=Path("tool-report.json"))
    args = parser.parse_args()
    result = run(args.workspace, args.operation)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "development_id": result["development"]["_id"],
                "report": str(args.report.resolve()),
                "independently_evaluated_objects": len(result["reports"]),
            }
        )
    )

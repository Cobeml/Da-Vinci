"""Public, reproducible methodology benchmark. Scripted proposals are not AI quality evidence."""

import argparse
import json
import math
from pathlib import Path

from davinci.models import digest
from davinci.product import recipes
from davinci.product.client import Client, ClientError
from davinci.product.managed_contracts import RequirementsOutput
from davinci.product.structural.examples import beam_reference, quantity
from davinci.product.structural.examples import candidate as bracket_candidate
from davinci.product.structural.walkthrough import plan_bundle

BAD_EVALUATOR = "def evaluate(step, request):\n    return {'passed': True}\n"


def requirements(case):
    data = dict(
        length_mm=40,
        width_mm=20,
        thickness_min_mm=2,
        thickness_max_mm=8,
        force_n=100,
        youngs_mpa=70000,
        density_g_mm3=0.0027,
        stress_limit_mpa=100,
        deflection_limit_mm=0.5,
    )
    if case == "heldout-a":
        data.update(length_mm=50, force_n=90)
    if case == "heldout-b":
        data.update(length_mm=60, width_mm=24)
    return RequirementsOutput.model_validate(
        dict(
            requirements=[
                dict(
                    id="strength",
                    description=f"Preserve root/length/width and support {data['force_n']} N within 100 MPa / 0.5 mm limits",
                    source="Benchmark request v1",
                )
            ],
            assumptions=[
                dict(
                    description="Nominal small-deflection rectangular beam screen",
                    source="Explicit benchmark scope",
                    applicability="No joints, fatigue or contact validation",
                )
            ],
            recipe="rectangular-beam-v1",
            inputs={
                **data,
                "material": "Nominal aluminium",
                "material_provenance": "Benchmark nominal inputs, not measured batch",
                "input_provenance": {k: "Benchmark request v1" for k in data},
                "phenomena": ["mass", "linear_static", "geometry"],
                "material_model": "linear_isotropic",
                "geometry": "rectangular_prismatic_cantilever",
            },
        )
    )


def bundle(case, images):
    if case == "bracket":
        return plan_bundle(images["structural"])
    p = recipes.make_plan(requirements(case)).model_dump(mode="json")
    if case == "unavailable":
        p["tests"][0]["simulation"]["phenomena"].append("fatigue")
        p["tests"][0]["applicability"] = (
            "Requested fatigue lifetime and static response; elastic screening cannot establish fatigue life"
        )
    if case == "capacity":
        p["tests"][0]["simulation"]["estimate"]["memory_mb"] = 1000000
    return dict(
        plan=p,
        evaluator={
            "resources": {"evaluate.py": BAD_EVALUATOR if case == "bad-evaluator" else recipes.EVALUATOR},
            "provenance": "Benchmark independent recipe / intentional faulty evaluator case",
        },
        runtime=dict(
            image=images["cad"],
            solver="CadQuery / NumPy beam screen",
            provenance="Pinned benchmark runtime",
            cpu_cores=1,
            memory_gb=2,
        ),
    )


def proposals(case):
    if case == "bracket":
        return [bracket_candidate(v) for v in ("bracket-base", "bracket-ribbed")]
    p = requirements(case).inputs
    source = recipes.BUILDER.replace("LENGTH", repr(p.length_mm)).replace("WIDTH", repr(p.width_mm))
    good = dict(
        title="Supported revised beam",
        change="Thickness changes; fixed interfaces and test limits retained",
        source=source,
        parameters={"thickness": 4.5},
    )
    if case == "edit":
        return [
            dict(good, title="Existing inspected beam", parameters={"thickness": 8}),
            dict(
                good,
                title="Deliberate regression: shortened beam",
                source=source.replace(repr(p.length_mm), repr(p.length_mm - 5), 1),
            ),
            good,
        ]
    return [dict(good, title="Deliberately insufficient section", parameters={"thickness": 2}), good]


class BenchmarkProvider:
    """Manual managed stages with fixed answers outside the reusable memory corpus."""

    def __init__(self, engine, row):
        if (
            row["driver"] != "managed"
            or row["mode"] != "replay"
            or not row["opening"]["metadata"].get("methodology_fixture")
        ):
            raise ValueError("This server only permits explicit methodology fixture reasoning")
        self.row = row

    def request(self, key, instruction, context):
        case = self.row["opening"]["metadata"]["benchmark_case"]
        if key.startswith("lifecycle-author"):
            return bundle(case, self.row["opening"]["metadata"]["images"])
        if key.startswith("lifecycle-propose"):
            sequence = proposals(case)
            return sequence[min(len(self.row["candidates"]), len(sequence) - 1)]
        if key.startswith("lifecycle-reflect"):
            return {
                "lesson": "Benchmark fixture: preserve frozen requirements, inspect independent evidence; retrieved claims are hypotheses. No autonomous reasoning claim."
            }
        raise ValueError("Unknown deterministic stage")


class Benchmark:
    def __init__(self, client, driver, output, prefix="methodology-v1"):
        self.client, self.driver, self.output, self.prefix = client, driver, Path(output), prefix
        self.output.mkdir(parents=True, exist_ok=True)
        self.images = {
            key: client.request("GET", "/api/v2/runtimes/resolve?image=" + tag)["image"]
            for key, tag in [("cad", "da-vinci-cad%3Alocal")]
        }
        self.artifact_cache = {}

    def open(self, case, arm="enabled", suffix=""):
        return self.client.request(
            "POST",
            "/api/v2/experiments",
            dict(
                object={"slug": case + ("-" + suffix if suffix else ""), "name": case},
                description=f"Benchmark {case}: static engineering request, fixed interfaces and limits; compare bracket cantilever deflection while preserving root geometry. "
                + ("Fatigue requested; no substitute permitted." if case == "unavailable" else ""),
                driver=self.driver,
                mode="replay" if self.driver == "managed" else "live",
                actor="benchmark",
                operation_id=f"{self.prefix}-{self.driver}-{case}-{arm}-{suffix}",
                metadata={
                    "benchmark_case": case,
                    "methodology_fixture": True,
                    "images": self.images,
                    "memory_retrieval": arm,
                    **(
                        {"memory_record_ids": list(self.memory_ids.values())}
                        if hasattr(self, "memory_ids")
                        else {}
                    ),
                },
                budget_usd=1,
            ),
        )

    def post(self, eid, action, payload=None, op=None):
        r = self.client.status(eid)
        return self.client.request(
            "POST",
            f"/api/v2/experiments/{eid}/{action}",
            dict(actor=r["actor"], revision=r["revision"], operation_id=op or action, **(payload or {})),
        )

    def wait(self, eid, job):
        result = self.client.wait(eid, job["id"], 900)
        if result["status"] != "completed" or result.get("wait_timed_out") or result.get("failures"):
            raise RuntimeError(result)
        return result

    def verify(self, row, case):
        eid = row["_id"]
        p = row["plan"]
        fixtures = (
            recipes.fixtures(requirements(case))
            if case != "bracket"
            else [
                dict(
                    candidate=bracket_candidate(v),
                    expected_status="pass" if t == 8 else "physical_failure",
                    values=beam_reference(t),
                )
                for v, t in [("beam-thick", 8), ("beam-thin", 4)]
            ]
        )
        for i, f in enumerate(fixtures):
            job = self.post(
                eid,
                "reference-builds",
                {
                    "reference": {
                        "candidate": f["candidate"],
                        "provenance": "Independent analytical reference, not a design candidate",
                    }
                },
                f"reference-{i}",
            )
            aid = self.wait(eid, job)["fixture_artifacts"][0]
            if case == "bracket":
                units = p["tests"][0]["metrics"]
                verification = dict(
                    test_id="static",
                    fixture_artifact=aid,
                    expected_status=f["expected_status"],
                    reference_metrics={
                        k: quantity(
                            v,
                            units[k],
                            {
                                "mass_g": "mass",
                                "load_displacement_mm": "length",
                                "gauge_von_mises_mpa": "pressure",
                            }[k],
                        )
                        for k, v in f["values"].items()
                    },
                    tolerances={
                        k: 1e-5 if k == "mass_g" else abs(v) * (0.06 if k == "load_displacement_mm" else 0.15)
                        for k, v in f["values"].items()
                    },
                    provenance="Independent beam bending+shear reference; documented 3D comparison tolerances",
                )
            else:
                verification = recipes.verification(p, f, aid)
            self.wait(eid, self.post(eid, "verify", {"verification": verification}, f"verify-{i}"))
        return self.client.status(eid)

    def author(self, row, case, *, freeze=True):
        eid = row["_id"]
        if self.driver == "managed":
            self.post(eid, "managed/author", op="author")
        else:
            self.post(eid, "plan", bundle(case, self.images), "author")
        row = self.client.status(eid)
        if case in ("unavailable", "capacity"):
            return row
        row = self.verify(row, case)
        if freeze:
            self.post(eid, "freeze")
        return self.client.status(eid)

    def summarize(self, row):
        history = row["history"]
        freezes = [i for i, h in enumerate(history) if h["action"] == "freeze"]
        submits = [i for i, h in enumerate(history) if h["action"] == "submit_candidate"]
        tests = row["results"][-1]["tests"] if row["results"] else []
        durations = sum(
            r.get("duration_seconds", 0) for r in [*row["results"], *row["verifications"], *row["fixtures"]]
        )
        coverage = row.get("coverage", {})
        repeated = None
        if len(row["results"]) >= 2:
            a, b = row["results"][-2:]
            pairs = [
                (x["metrics"][k]["value"], y["metrics"][k]["value"])
                for x, y in zip(a["tests"], b["tests"])
                for k in set(x.get("metrics", {})) & set(y.get("metrics", {}))
            ]
            same_inputs = (
                a["source_artifact"] == b["source_artifact"]
                and row["candidates"][-2]["parameters"] == row["candidates"][-1]["parameters"]
            )
            repeated = {
                "same_source_parameters_suite_runtime": same_inputs
                and all(a[k] == b[k] for k in ("suite_id", "runtime_id", "evaluator_id", "execution_id")),
                "max_absolute_metric_difference": max((abs(x - y) for x, y in pairs), default=None),
                "within_tolerance": bool(pairs)
                and all(math.isclose(x, y, rel_tol=1e-8, abs_tol=1e-6) for x, y in pairs),
            }
        return dict(
            experiment_id=row["_id"],
            driver=row["driver"],
            phase=row["phase"],
            suite_id=row.get("suite_id"),
            acceptance_contract_id=digest(
                {k: row.get(k) for k in ("plan", "evaluator", "runtime", "execution_id")}
            ),
            runtime=row.get("runtime"),
            test_before_candidate=bool(
                freezes
                and submits
                and min(submits) > min(freezes)
                and row["verifications"]
                and all(v["at"] <= row["frozen_at"] for v in row["verifications"])
            ),
            coverage_complete=coverage.get("complete", False),
            requirement_count=len(row["plan"]["requirements"]),
            covered_requirements=len(coverage.get("requirement_tests", {})),
            candidate_count=len(row["candidates"]),
            search_iterations=max(0, len(row["candidates"]) - 1),
            final_evidence_complete=bool(row["results"] and row["results"][-1]["evidence_complete"]),
            final_accepted=bool(row["results"] and row["results"][-1]["design_accepted"]),
            final_metrics={k: v for t in tests for k, v in t.get("metrics", {}).items()},
            outcomes=[
                {
                    "accepted": r["design_accepted"],
                    "complete": r["evidence_complete"],
                    "tests": [{k: t[k] for k in ("test_id", "status", "reason")} for t in r["tests"]],
                }
                for r in row["results"]
            ],
            elapsed_solver_seconds=durations,
            allocated_cpu_seconds_upper_bound=durations * row.get("runtime", {}).get("cpu_cores", 1),
            compute_cost_usd=None,
            compute_cost_note="Local compute price not configured; CPU allocation*time is an upper bound, not measured CPU usage",
            model_cost_usd=row.get("spent_usd", 0),
            fixture_reasoning_calls=sum(h["action"].startswith("managed_") for h in history),
            model_tokens=None,
            reproduction=repeated,
            autonomous_reasoning_evaluated=False,
        )

    def exercise(self, row, case):
        print(json.dumps({"driver": self.driver, "case": case, "experiment_id": row["_id"]}), flush=True)
        eid = row["_id"]
        retrieved = self.client.request(
            "GET", f"/api/v2/experience?q=bracket%20cantilever%20deflection&experiment_id={eid}"
        )
        sequence = proposals(case)
        for i, c in enumerate([*sequence, sequence[-1]]):
            if self.driver == "managed":
                self.post(eid, "managed/propose", op=f"candidate-{i}")
            else:
                self.post(eid, "candidates", {"candidate": c}, f"candidate-{i}")
            self.wait(eid, self.post(eid, "evaluate", op=f"evaluate-{i}"))
            if self.driver == "managed":
                self.post(eid, "managed/reflect", op=f"reflect-{i}")
            else:
                self.post(
                    eid,
                    "reflections",
                    {
                        "result_id": self.client.status(eid)["results"][-1]["id"],
                        "lesson": "Scripted benchmark reflection; independently test geometry and keep fixed inputs. No transfer of passing scores.",
                    },
                    f"reflect-{i}",
                )
        self.post(eid, "finalize")
        report = self.client.request("GET", f"/api/v2/experiments/{eid}/report")
        (self.output / (eid + ".json")).write_text(json.dumps(report, indent=2) + "\n")
        result = self.summarize(self.client.status(eid))
        result["retrieved_ids"] = [r["id"] for r in retrieved]
        result["retrieval_applicability"] = {r["id"]: r["applicability_check"] for r in retrieved}
        result["report_file"] = eid + ".json"
        if not all(
            result[k] for k in ("test_before_candidate", "coverage_complete", "final_evidence_complete")
        ):
            raise AssertionError(result)
        if (
            not result["reproduction"]["same_source_parameters_suite_runtime"]
            or not result["reproduction"]["within_tolerance"]
        ):
            raise AssertionError("Fresh repeated evaluation is not reproducible")
        if not any(not r["accepted"] for r in result["outcomes"]):
            raise AssertionError("Deliberately bad candidate was not detected")
        return result

    def assert_freeze_rejected(self, eid):
        try:
            self.post(eid, "freeze", op="assert-freeze-rejected")
        except ClientError as exc:
            if exc.code not in (2, 4):
                raise
        else:
            raise AssertionError("Invalid or unsupported plan was frozen")

    def seed_memory(self):
        library = self.open("library")
        corpus = [
            (
                "useful",
                "Cantilever bracket deflection depends strongly on section depth. Verify the load path, fixed interfaces and mesh convergence independently.",
                ["linear_static"],
                "static",
            ),
            (
                "misleading",
                "Reducing cantilever bracket section depth always reduces deflection; a static result proves vibration reliability.",
                ["linear_static"],
                "static",
            ),
            (
                "incompatible",
                "Use impact rate-dependent polymer response for cantilever bracket deflection.",
                ["impact"],
                "impact",
            ),
        ]
        ids = {}
        for key, claim, phenomena, regime in corpus:
            note = self.client.request(
                "POST",
                "/api/v2/memory/notes",
                dict(
                    actor="benchmark",
                    operation_id=f"{self.prefix}-{self.driver}-corpus-{key}",
                    experiment_id=library["_id"],
                    claim=claim,
                    applicability=dict(
                        domain="mechanical",
                        materials=["Nominal aluminium"],
                        phenomena=phenomena,
                        load_regimes=[regime],
                    ),
                ),
            )
            ids[key] = note["id"]
        return ids

    def run(self, *, structural=True):
        records = []
        if structural:
            self.images["structural"] = self.client.request(
                "GET", "/api/v2/runtimes/resolve?image=da-vinci-structural%3Alocal"
            )["image"]
            records.append(self.exercise(self.author(self.open("bracket"), "bracket"), "bracket"))
        faulty = self.author(self.open("bad-evaluator"), "bad-evaluator", freeze=False)
        failed = self.client.request("GET", f"/api/v2/experiments/{faulty['_id']}/plan-validation")
        if failed["ready_to_freeze"]:
            raise AssertionError("Bad evaluator became freezeable")
        self.assert_freeze_rejected(faulty["_id"])
        # Corrections are linked drafts; independently verified evidence is rerun.
        revision = self.open("edit")["opening"]
        revision["operation_id"] += "-correction"
        revision["parent_experiment_id"] = faulty["_id"]
        revision["description"] = (
            "Correct invalid evaluator response; preserve original physics and regression interfaces. Rerun all references."
        )
        revised = self.client.request("POST", f"/api/v2/experiments/{faulty['_id']}/revisions", revision)
        records.append(self.exercise(self.author(revised, "edit"), "edit"))
        unavailable = []
        for case in ("unavailable", "capacity"):
            row = self.author(self.open(case), case)
            readiness = self.client.request("GET", f"/api/v2/experiments/{row['_id']}/plan-validation")
            unavailable.append(
                dict(
                    case=case,
                    experiment_id=row["_id"],
                    candidates=len(row["candidates"]),
                    capabilities=readiness["capabilities"],
                    blocked=not readiness["ready_to_freeze"],
                )
            )
            self.assert_freeze_rejected(row["_id"])
            if not all(r["status"] == "unavailable" for r in readiness["capabilities"]):
                raise AssertionError(readiness)
        # Freeze a reusable lesson corpus before either held-out task. Only these IDs
        # are counted for retrieval quality; task-specific answers are never seeded.
        ids = self.seed_memory()
        self.memory_ids = ids
        held = []
        for case in ("heldout-a", "heldout-b"):
            arms = {}
            for arm in ("disabled", "enabled"):
                row = self.author(self.open(case, arm), case)
                arms[arm] = self.exercise(row, case)
                records.append(arms[arm])
            enabled = arms["enabled"]
            disabled = arms["disabled"]
            selected = set(enabled["retrieved_ids"])
            held.append(
                dict(
                    task=case,
                    enabled=enabled["experiment_id"],
                    disabled=disabled["experiment_id"],
                    useful_retrieved=ids["useful"] in selected,
                    misleading_retrieved=ids["misleading"] in selected,
                    incompatible_retrieved=ids["incompatible"] in selected,
                    incompatible_flagged=enabled["retrieval_applicability"]
                    .get(ids["incompatible"], {})
                    .get("status")
                    == "incompatible",
                    precision_at_3=int(ids["useful"] in selected) / 3,
                    misleading_suggestions=sum(ids[k] in selected for k in ("misleading", "incompatible")),
                    iteration_delta=enabled["search_iterations"] - disabled["search_iterations"],
                    mass_delta_g=enabled["final_metrics"]["mass_g"]["value"]
                    - disabled["final_metrics"]["mass_g"]["value"],
                    acceptance_lost=disabled["final_accepted"] and not enabled["final_accepted"],
                    policy="Both scripted routes deliberately use the same proposals; this isolates orchestration/retrieval, not reasoning quality",
                )
            )
        from davinci.product.measurement_examples import synthetic_comparison

        observations = synthetic_comparison(
            self.client,
            self.client.status(records[-1]["experiment_id"]),
            operation=f"{self.prefix}-{self.driver}-synthetic",
        )
        positive, negative = observations["validations"]
        assert positive["mae_after"] < positive["mae_before"]
        assert negative["mae_after"] > negative["mae_before"]
        for comparison in held:
            assert comparison["incompatible_flagged"]
        result = dict(
            synthetic_observations=observations,
            version=1,
            benchmark="methodology-v1",
            driver=self.driver,
            images=self.images,
            request_fixture_hash=digest(
                {k: requirements(k).model_dump() for k in ("edit", "heldout-a", "heldout-b")}
            ),
            cases=records,
            unavailable=unavailable,
            bad_evaluator=dict(
                experiment_id=faulty["_id"],
                freeze_rejected=True,
                unmatched_checks=sum(not v["matched"] for v in faulty["verifications"]),
                correction_id=revised["_id"],
                new_evaluator=records[0 if not structural else 1]["suite_id"] is not None,
            ),
            held_out_comparison=held,
            reusable_corpus_ids=ids,
            claims="Deterministic/scripted methodology evidence only. No proven memory-driven engineering improvement; report misleading retrieval and negative comparisons without suppression.",
        )
        (self.output / (self.driver + "-summary.json")).write_text(json.dumps(result, indent=2) + "\n")
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--driver", choices=["external", "managed"], default="external")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--operation", default="methodology-v1")
    p.add_argument(
        "--skip-structural",
        action="store_true",
        help="Explicit partial run; structural capability is not validated",
    )
    a = p.parse_args()
    c = Client(a.workspace)
    c.connect()
    result = Benchmark(c, a.driver, a.output, a.operation).run(structural=not a.skip_structural)
    print(
        json.dumps(
            {
                "driver": a.driver,
                "cases": len(result["cases"]),
                "output": str(a.output),
                "live_model_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()

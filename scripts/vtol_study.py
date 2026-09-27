"""Resumable range campaign: 12 candidates, fixed evaluator, $30 API cap."""

import argparse
import fcntl
import json
import math
import subprocess
from pathlib import Path

from pydantic import ValidationError

from davinci.artifacts import Artifacts, Repository
from davinci.budget import Budget
from davinci.config import Settings
from davinci.memory import Memory
from davinci.models import digest, document, now
from davinci.providers import AstraProvider
from davinci.runner import Runner, SandboxError
from davinci.store import Store
from davinci.vtol import IMAGE, REFERENCE_SOURCE, SANDBOX, SPECIFICATION, evaluate, evaluator_version
from sandbox.vtol_family import BASELINE, BOUNDS
from scripts.gripper_study import Design, Reflection, Utility
from scripts.gripper_study import Study as SharedStudy

ROOT = Path(__file__).resolve().parents[1]
STUDY = "survey-vtol-range-v2"


def score(e, key):
    return e.get("metrics", {}).get(key, {}).get("value", 0)


def protect(e, base):
    for key, code in [("max_speed_m_s", "SPEED_RETENTION"), ("payload_capacity_kg", "PAYLOAD_RETENTION")]:
        if score(e, key) < 0.95 * score(base, key):
            e["violations"].append({"code": code, "message": "Below 95% of baseline capability"})
    if e["violations"]:
        e["outcome"] = "failed"
    return e


class Study:
    def structured(self, key, instructions, context, schema, output_limit=14000):
        try:
            return SharedStudy.structured(self, key, instructions, context, schema, output_limit)
        except ValidationError:
            raw = self.root / (key + ".response.json")
            if not raw.exists():
                raise
            # Preserve truncated/empty evidence; API accounting is already settled.
            attempt = len(list(self.root.glob(key + ".incomplete-*.json")))
            raw.rename(self.root / f"{key}.incomplete-{attempt}.json")
            return SharedStudy.structured(
                self,
                key,
                instructions
                + " Return the required JSON proposal now; the independent evaluator will perform the calculations.",
                context,
                schema,
                32000,
            )

    def __init__(self):
        self.settings = Settings()
        if not self.settings.mongodb_uri or not self.settings.openai_api_key:
            raise ValueError("Atlas/Astra required")
        self.root = self.settings.root / STUDY
        self.root.mkdir(exist_ok=True)
        self.lock = (self.root / "study.lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.store = Store(self.settings.root, self.settings.mongodb_uri, self.settings.mongodb_database)
        self.artifacts = Artifacts(self.settings.root, self.store)
        self.repository = Repository(self.settings.root)
        self.runner = Runner(self.settings)
        self.version = evaluator_version()
        previous = self.store.get("runs", "survey-vtol-range-v1")
        self.prior_spent = previous["spent_usd"] if previous else 0
        self.campaign_cap = 30 - self.prior_spent
        self.store.insert(
            "study_audits",
            document(
                "audit",
                _id="survey-vtol-range-v1-superseded",
                study_id="survey-vtol-range-v1",
                replacement=STUDY,
                status="superseded",
                reason="Straight spars protruded beyond the analyzed airfoil. V2 uses contained tapered spars and variable EI.",
            ),
        )
        self.image = subprocess.check_output(
            ["docker", "image", "inspect", "--format={{.Id}}", IMAGE], text=True
        ).strip()
        self.store.insert(
            "runs",
            document(
                "run",
                _id=STUDY,
                project_id="engineering-demo",
                diagnostic=True,
                mode="live",
                status="study_running",
                budget_usd=self.campaign_cap,
                spent_usd=0,
                revision=0,
                evaluator_version=self.version,
                runtime_image_digest=self.image,
            ),
        )
        run = self.store.get("runs", STUDY)
        if run["evaluator_version"] != self.version or run["runtime_image_digest"] != self.image:
            raise ValueError("Frozen evaluator/image changed; use a new study ID")
        self.provider = AstraProvider(
            self.settings, Budget(self.store, self.settings.davinci_daily_budget_usd), self.store, STUDY
        )
        self.provider.client = self.provider.client.with_options(timeout=600)
        self.memory = Memory(self.store, self.provider.embed, self.version)
        self.store.insert("specifications", {**SPECIFICATION, "evaluator_version": self.version})

    def recall(self):
        vector = self.provider.embed(
            "VTOL range drag hover energy CG trim stability payload speed structural lessons", STUDY
        )
        return list(
            self.store.db.memories.aggregate(
                [
                    {
                        "$vectorSearch": {
                            "index": "memory_vector",
                            "path": "embedding",
                            "queryVector": vector,
                            "numCandidates": 100,
                            "limit": 5,
                            "filter": {
                                "specification_id": SPECIFICATION["_id"],
                                "evaluator_version": self.version,
                            },
                        }
                    },
                    {"$project": {"_id": 1, "summary": 1, "score": {"$meta": "vectorSearchScore"}}},
                ]
            )
        )

    def tool(self, history):
        saved = self.store.get("design_tools", STUDY + "-energy") or self.store.get(
            "design_tools", "survey-vtol-range-v1-energy"
        )
        if saved:
            return saved
        u = self.structured(
            "energy-tool",
            "Write a pure Python run(arguments) utility importing only math. "
            "Inputs: battery_wh, reserve_fraction, overhead_wh, cruise_power_w, speed_m_s. "
            "Output range_km = (battery_wh*(1-reserve_fraction)-overhead_wh)*speed_m_s*3.6/cruise_power_w "
            "and wh_per_km = cruise_power_w/(speed_m_s*3.6). Reject missing/nonfinite values, nonpositive battery/power/speed, "
            "reserve outside [0,1), negative overhead, and overhead >= usable energy. This is a sensitivity calculator, "
            "not a flight simulator. Explain how it helps compare drag versus hover-energy changes.",
            {"history": history},
            Utility,
        )
        checks = []
        for energy, overhead, power, speed in [
            (150, 25, 100, 15),
            (150, 40, 130, 18),
            (135, 25, 100, 15),
            (150, 25, 120, 15),
        ]:
            args = dict(
                battery_wh=energy,
                reserve_fraction=0.2,
                overhead_wh=overhead,
                cruise_power_w=power,
                speed_m_s=speed,
            )
            value = self.runner.invoke(u.source, args)
            assert math.isclose(
                value["range_km"], (energy * 0.8 - overhead) * speed * 3.6 / power, rel_tol=1e-8
            )
            assert math.isclose(value["wh_per_km"], power / (speed * 3.6), rel_tol=1e-8)
            checks.append(dict(arguments=args, result=value, passed=True))
        for field, value in [
            ("speed_m_s", 0),
            ("overhead_wh", 151),
            ("reserve_fraction", 1),
            ("cruise_power_w", -1),
        ]:
            try:
                self.runner.invoke(u.source, {**args, field: value})
            except RuntimeError:
                checks.append(dict(invalid_field=field, passed=True))
            else:
                raise ValueError("Generated tool failed invalid-input test")
        files = {"tool.py": u.source, "explanation.txt": u.explanation}
        record = document(
            "tool",
            _id=STUDY + "-energy",
            study_id=STUDY,
            source=u.source,
            explanation=u.explanation,
            validation=checks,
            source_commit=self.repository.commit(STUDY + "-tool", files),
            bundle_artifact_id=self.artifacts.put(
                self.repository.bundle(files), "tool.json", "application/json"
            ),
        )
        self.store.insert("design_tools", record)
        return record

    def cached_evaluation(self, key, source, parameters, resolution=10):
        path = self.root / (key + "-evaluation.json")
        out = self.root / (key + "-artifacts")
        out.mkdir(exist_ok=True)
        if path.exists():
            return json.loads(path.read_text()), {p.name: p.read_bytes() for p in out.iterdir()}
        result, files = evaluate(self.runner, source, parameters, resolution)
        for name, data in files.items():
            (out / name).write_bytes(data)
        path.write_text(json.dumps(result))
        return result, files

    def run(self, count):
        for index in range(count):
            ident = f"{STUDY}-{index:02d}"
            if self.store.get("design_iterations", ident):
                continue
            records = self.store.list("design_iterations", {"study_id": STUDY})
            history = [
                {k: d[k] for k in ("iteration", "parameters", "change", "reflection")}
                | {
                    "outcome": d["evaluation"]["outcome"],
                    "metrics": d["evaluation"]["metrics"],
                    "violations": d["evaluation"]["violations"],
                    "best_cruise": d["evaluation"].get("performance", {}).get("nominal", {}).get("best"),
                }
                for d in records
            ]
            tool = self.tool(history) if index >= 2 else None
            predictions = []
            if tool:
                passing = [d for d in records if d["evaluation"]["outcome"] == "passed"]
                best = max(passing, key=lambda d: score(d["evaluation"], "range_km"))
                n = best["evaluation"]["performance"]["nominal"]
                b = n["best"]
                for factor in (1.0, 0.9, 1.1):
                    args = dict(
                        battery_wh=150,
                        reserve_fraction=0.2,
                        overhead_wh=n["overhead_wh"],
                        cruise_power_w=b["power_w"] * factor,
                        speed_m_s=b["speed_m_s"],
                    )
                    predictions.append(
                        {"arguments": args, "result": self.runner.invoke(tool["source"], args)}
                    )
            context = dict(
                iteration=index + 1,
                specification=SPECIFICATION,
                baseline=BASELINE,
                bounds=BOUNDS,
                history=history,
                geometry_contract=(SANDBOX / "vtol_family.py").read_text(),
                physics_contract=(SANDBOX / "vtol_physics.py").read_text(),
                reference_source=REFERENCE_SOURCE,
                retrieved_memory=self.recall() if index else [],
                tool_predictions=predictions,
                working_policy=records[-1]["reflection"] if records else {},
            )
            proposal = self.structured(
                f"proposal-{index:02d}",
                "Design a small survey lift-and-cruise VTOL. Return source using the exact reference build wrapper and ALL "
                "documented SI parameters. The wing spar tapers with chord and is checked for containment; its root diameter must be <=10.5% root chord. Its variable stiffness is integrated along the span. Maximize estimated range, keeping .5kg payload and 150Wh fixed; maintain >=95% "
                "baseline speed and payload capacity. Improve fuselage/wing/tail/booms and packaging together. "
                "All-moving tail provides pitch trim. Battery and payload boxes must fit without overlap. "
                "Use real previous failures and best-cruise drag breakdowns; do not invent results or change evaluator. "
                "Favor meaningful geometry alternatives over tiny trims; vary wing efficiency, fuselage shape, structural "
                "mass and CG carefully. Title/description concise. "
                + (
                    "Use BASELINE exactly for the first design."
                    if index == 0
                    else "Correct failures and outperform the best passing design. Static margin must remain 5–20%; moving battery forward increases it."
                ),
                context,
                Design,
                24000,
            )
            print(f"Evaluating {index + 1}: {proposal.title}", flush=True)
            try:
                e, files = self.cached_evaluation(
                    f"candidate-{index:02d}", proposal.source, proposal.parameters
                )
            except ValueError as exc:
                e = dict(
                    outcome="failed",
                    metrics={},
                    violations=[dict(code="INVALID_PARAMETERS", message=str(exc))],
                    fidelity="geometry_rejection",
                )
                files = {}
            except SandboxError as exc:
                # Preserve infrastructure/solver failures as explicit unsupported attempts, not successful estimates.
                e = dict(
                    outcome="unsupported",
                    metrics={},
                    violations=[
                        dict(
                            code="UNSUPPORTED_ANALYSIS",
                            message="CAD/solver did not complete: " + str(exc)[-1200:],
                        )
                    ],
                    fidelity="unsupported",
                )
                files = {}
                # Archive unsupported analysis without inventing performance; it cannot become champion.
            if index == 0 and e["outcome"] != "passed":
                raise ValueError("Baseline failed; stop before optimization")
            if index:
                protect(e, records[0]["evaluation"])
            reflection = self.structured(
                f"reflection-{index:02d}",
                "Review measured aircraft screening results. Return lesson and next_focus, <=400 characters each. "
                "Discuss limiting energy/drag, static margin, structure and protected speed/payload. Never invent measurements.",
                {
                    "proposal": proposal.model_dump(),
                    "metrics": e["metrics"],
                    "violations": e["violations"],
                    "performance": e.get("performance"),
                    "specification": SPECIFICATION,
                },
                Reflection,
                6000,
            )
            bundle = {
                "candidate.py": proposal.source,
                "parameters.json": json.dumps(proposal.parameters),
                "context.json": json.dumps(context),
                "policy.json": reflection.model_dump_json(),
            }
            artifacts = {
                name: self.artifacts.put(
                    data, name, "model/gltf-binary" if name.endswith("glb") else "application/step"
                )
                for name, data in files.items()
            }
            record = document(
                "design",
                _id=ident,
                study_id=STUDY,
                iteration=index + 1,
                title=proposal.title[:70],
                change=proposal.change[:400],
                source=proposal.source,
                parameters=proposal.parameters,
                evaluation=e,
                reflection=reflection.model_dump(),
                source_commit=self.repository.commit(ident, bundle),
                source_artifact_id=self.artifacts.put(
                    self.repository.bundle(bundle), "source.json", "application/json"
                ),
                artifacts=artifacts,
                tool_id=tool["_id"] if tool else None,
                tool_predictions=predictions,
                retrieved_memory=context["retrieved_memory"],
                evaluator_version=self.version,
                runtime_image_digest=self.image,
                generator=self.settings.openai_model,
            )
            self.store.insert("design_iterations", record)
            self.memory.remember(
                dict(
                    _id=ident,
                    run_id=STUDY,
                    project_id="engineering-demo",
                    subsystem="vtol",
                    specification_id=SPECIFICATION["_id"],
                    evaluator_version=self.version,
                    parameters=proposal.parameters,
                    fingerprint=digest(proposal.parameters),
                ),
                {"_id": ident + "-evaluation", **e},
            )
            print(
                json.dumps(
                    {
                        "iteration": index + 1,
                        "outcome": e["outcome"],
                        "metrics": e["metrics"],
                        "violations": e["violations"],
                    }
                ),
                flush=True,
            )
            self.export()
        self.validate_finalists()
        self.store.update("runs", STUDY, {"status": "completed", "finished_at": now()})
        self.export()

    def validate_finalists(self):
        records = self.store.list("design_iterations", {"study_id": STUDY})
        base = records[0]
        finalists = sorted(
            [d for d in records if d["evaluation"]["outcome"] == "passed"],
            key=lambda d: score(d["evaluation"], "range_km"),
            reverse=True,
        )[:3]
        validations = {}
        for d in {d["_id"]: d for d in [base, *finalists]}.values():
            medium, _ = self.cached_evaluation(d["_id"] + "-r14", d["source"], d["parameters"], 14)
            fine, _ = self.cached_evaluation(d["_id"] + "-r18", d["source"], d["parameters"], 18)
            errors = {
                key: abs(score(fine, key) / score(medium, key) - 1)
                for key in ("range_km", "max_speed_m_s")
                if score(medium, key)
            }
            errors["drag"] = abs(
                fine["performance"]["nominal"]["best"]["drag_n"]
                / medium["performance"]["nominal"]["best"]["drag_n"]
                - 1
            )
            validations[d["_id"]] = dict(
                evaluation=fine, relative_changes=errors, converged=all(v < 0.03 for v in errors.values())
            )
        (self.root / "validation.json").write_text(json.dumps(validations, indent=2))
        self.store.insert(
            "study_validations",
            document("validation", _id=STUDY, evaluator_version=self.version, validations=validations),
        )

    def export(self):
        records = self.store.list("design_iterations", {"study_id": STUDY})
        public = ROOT / "web/public/models/vtol" / STUDY
        public.mkdir(parents=True, exist_ok=True)
        designs = []
        for d in records:
            assets = {}
            for name, ident in d["artifacts"].items():
                target = f"{d['iteration']:02d}-" + name
                (public / target).write_bytes(self.artifacts.read(ident))
                assets[name] = "/models/vtol/" + STUDY + "/" + target
            (public / f"{d['iteration']:02d}.py").write_text(d["source"])
            designs.append(
                {
                    k: d[k]
                    for k in (
                        "_id",
                        "iteration",
                        "title",
                        "change",
                        "parameters",
                        "evaluation",
                        "reflection",
                        "tool_id",
                        "retrieved_memory",
                        "source_commit",
                        "generator",
                    )
                }
                | {"assets": assets}
            )
        passed = [d for d in designs if d["evaluation"]["outcome"] == "passed"]
        best = max(passed, key=lambda d: score(d["evaluation"], "range_km")) if passed else None
        base = designs[0] if designs else None
        improvement = (
            (score(best["evaluation"], "range_km") / score(base["evaluation"], "range_km") - 1) * 100
            if best and base
            else 0
        )
        validation = self.store.get("study_validations", STUDY)
        publishable = False
        if validation and best:
            vb = validation["validations"].get(base["_id"])
            eligible = []
            for d in passed:
                v = validation["validations"].get(d["_id"])
                if not v or not v["converged"] or not vb["converged"]:
                    continue
                e = protect(json.loads(json.dumps(v["evaluation"])), vb["evaluation"])
                adverse = e["performance"]["scenarios"]["combined_adverse"]
                ba = vb["evaluation"]["performance"]["scenarios"]["combined_adverse"]
                if (
                    e["outcome"] == "passed"
                    and not adverse["violations"]
                    and not ba["violations"]
                    and score(e, "range_km") >= 1.1 * score(vb["evaluation"], "range_km")
                    and adverse["range_km"] > ba["range_km"]
                ):
                    eligible.append(d)
            if eligible:
                best = max(
                    eligible,
                    key=lambda d: score(validation["validations"][d["_id"]]["evaluation"], "range_km"),
                )
                publishable = True
                improvement = (
                    score(best["evaluation"], "range_km") / score(base["evaluation"], "range_km") - 1
                ) * 100
        tool = self.store.get("design_tools", STUDY + "-energy") or self.store.get(
            "design_tools", "survey-vtol-range-v1-energy"
        )
        manifest = dict(
            study_id=STUDY,
            generated_at=now(),
            specification=SPECIFICATION,
            designs=designs,
            best_id=best["_id"] if best else None,
            improvement_percent=improvement,
            publishable=publishable,
            validation=validation,
            spent_usd=self.prior_spent + self.store.get("runs", STUDY)["spent_usd"],
            current_cohort_spent_usd=self.store.get("runs", STUDY)["spent_usd"],
            superseded_cohort_spent_usd=self.prior_spent,
            tool={k: v for k, v in (tool or {}).items() if k not in ("source", "bundle_artifact_id")},
        )
        (ROOT / "web/data/vtol-gallery.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(
            f"Archived {len(designs)} designs; range change {improvement:.1f}%; publishable {publishable}",
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=12, choices=range(1, 13))
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    try:
        study = Study()
        study.export() if args.export_only else study.run(args.count)
    except Exception as exc:
        print(json.dumps({"status": "stopped", "error_type": type(exc).__name__}), flush=True)
        # Never print connection exception messages: they can contain connection strings.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

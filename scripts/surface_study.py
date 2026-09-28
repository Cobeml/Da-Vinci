"""Resumable $60 matched VTOL surface-tool experiment, with isolated Atlas memory."""

import argparse
import copy
import fcntl
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from davinci.artifacts import Artifacts, Repository
from davinci.budget import Budget, BudgetExceeded
from davinci.config import Settings
from davinci.memory import Memory
from davinci.models import digest, document, now
from davinci.providers import AstraProvider
from davinci.runner import Runner, SandboxError
from davinci.store import Store
from davinci.surface import FILES, IMAGE, SANDBOX, crosscheck, evaluate, evaluator_version, image_digest, tool
from sandbox.surface_geometry import SHAPE_BOUNDS, validate
from sandbox.vtol_family import BOUNDS

STUDY = "survey-vtol-cst-v1"
ROOT = Path(__file__).resolve().parents[1]
ARMS = ("control", "surface_tools")


def metric(e, key):
    return e.get("metrics", {}).get(key, {}).get("value", 0)


def public_evaluation(e):
    """Keep full solver tables in the archive, not in the browser hydration payload."""
    result = {k: v for k, v in e.items() if k not in ("components", "performance")}
    if "performance" in e:
        p = e["performance"]
        result["performance"] = {
            "nominal": {k: v for k, v in p["nominal"].items() if k != "curve"},
            "scenarios": p["scenarios"],
            "direct_audit": {
                k: v
                for k, v in (p.get("direct_audit") or {}).items()
                if k in ("CL", "CD", "Cm", "min_confidence", "surrogate_errors")
            },
            "benchmark_audits": p.get("benchmark_audits", {}),
        }
    return result


def tool_def(name, description, properties, required):
    return dict(
        type="function",
        name=name,
        description=description,
        strict=False,
        parameters=dict(type="object", properties=properties, required=required, additionalProperties=False),
    )


def definitions(arm):
    obj = {"type": "object"}
    string = {"type": "string"}
    defs = [
        tool_def(
            "edit_geometry",
            "Edit current geometry; returns actual STEP/GLB preview and constraints. "
            "Edits can contain dimensions, shape, root/tip CST objects, thickness_scale, camber_scale. "
            "A failed edit leaves current geometry unchanged.",
            {"edits": obj},
            ["edits"],
        ),
        tool_def(
            "submit_design",
            "Submit the current previewed geometry. No further edits after submission.",
            {"title": string, "change": string, "lesson": string, "next_focus": string},
            ["title", "change", "lesson", "next_focus"],
        ),
    ]
    if arm != "control":
        defs += [
            tool_def(
                "analyze_sections",
                "Analyze current root and tip airfoils at up to 30 operating points. "
                "Each condition has reynolds (100k–1.5M) and alpha_deg (-8–14).",
                {"conditions": {"type": "array", "items": obj}},
                ["conditions"],
            ),
            tool_def(
                "optimize_sections",
                "Numerically optimize CST coefficients; applies the returned section to root and tip. "
                "Targets: reynolds (150k–800k), lift_coefficient (.3–.9), min_thickness (.11–.16). "
                "Full geometry preview must still pass; section drag is not whole-aircraft range.",
                {"targets": obj},
                ["targets"],
            ),
        ]
    return defs


class Study:
    def __init__(self, amend_preflight=False):
        self.settings = Settings()
        if not self.settings.mongodb_uri or not self.settings.openai_api_key:
            raise ValueError("Live credentials required")
        self.root = self.settings.root / STUDY
        self.root.mkdir(exist_ok=True)
        self.lock = (self.root / "study.lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.store = Store(self.settings.root, self.settings.mongodb_uri, self.settings.mongodb_database)
        self.runner = Runner(self.settings)
        self.artifacts = Artifacts(self.settings.root, self.store)
        self.repository = Repository(self.settings.root)
        self.version = evaluator_version()
        self.image = subprocess.check_output(
            ["docker", "image", "inspect", "--format={{.Id}}", IMAGE], text=True
        ).strip()
        self.seed = json.loads((self.root / "seed.json").read_text())
        validate(self.seed)
        freeze = {
            "evaluator_version": self.version,
            "runtime_image_digest": self.image,
            "seed_digest": digest(self.seed),
        }
        self.store.insert(
            "surface_studies", document("study", _id=STUDY, **freeze, status="preparing", budget_usd=60)
        )
        existing = self.store.get("surface_studies", STUDY)
        if any(existing[k] != v for k, v in freeze.items()):
            if not amend_preflight or self.records():
                raise ValueError("Frozen seed/evaluator/image changed; use a new study ID")
            # Pilot-only defects may be repaired before the matched experiment.
            # Preserve every earlier response and all spending; never rescore an arm.
            archive = self.root / ("preflight-" + existing["evaluator_version"])
            archive.mkdir(exist_ok=True)
            for path in self.root.glob("pilot*.json"):
                path.rename(archive / path.name)
            history = existing.get("preflight_amendments", []) + [
                {
                    "at": now(),
                    "previous": {k: existing[k] for k in freeze},
                    "reason": "Repair pilot fairing failure and nonlinear audit memory use before any scored designs",
                }
            ]
            self.store.update("surface_studies", STUDY, {**freeze, "preflight_amendments": history})
            for arm in ("pilot", *ARMS):
                self.store.update("runs", STUDY + "-" + arm, freeze)
        for arm, cap in [("pilot", 6), ("control", 27), ("surface_tools", 27)]:
            self.store.insert(
                "runs",
                document(
                    "run",
                    _id=STUDY + "-" + arm,
                    project_id="engineering-demo",
                    diagnostic=True,
                    mode="live",
                    status="study_running",
                    spent_usd=0,
                    budget_usd=cap,
                    revision=0,
                    **freeze,
                ),
            )
        # The explicitly approved campaign cap is split across three disjoint run ledgers.
        ledger = self.store.get("budgets", "budget-global") or {}
        prior = sum(ledger.get("days", {}).values())
        self.budget = Budget(self.store, max(self.settings.davinci_daily_budget_usd, prior + 60))

    def provider(self, arm):
        p = AstraProvider(self.settings, self.budget, self.store, STUDY + "-" + arm)
        p.client = p.client.with_options(timeout=600)
        return p

    def spent(self, arm):
        return self.store.get("runs", STUDY + "-" + arm)["spent_usd"]

    def preview(self, geometry):
        folder = (
            self.root
            / "previews"
            / digest({"geometry": geometry, "version": self.version, "image": self.image})
        )
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / "result.json").exists():
            return json.loads((folder / "result.json").read_text()), {
                p.name: p.read_bytes() for p in folder.iterdir() if p.name != "result.json"
            }
        result, files = tool(self.runner, "preview", {"geometry": geometry})
        for name, data in files.items():
            (folder / name).write_bytes(data)
        (folder / "result.json").write_text(json.dumps(result))
        return result, files

    def cached_evaluation(self, geometry, resolution=6, nonlinear=False):
        if evaluator_version() != self.version or image_digest() != self.image:
            raise ValueError("Frozen seed/evaluator/image changed; use a new study ID")
        key = digest(
            dict(
                geometry=geometry,
                resolution=resolution,
                nonlinear=nonlinear,
                version=self.version,
                image=self.image,
            )
        )
        folder = self.root / "evaluations" / key
        folder.mkdir(parents=True, exist_ok=True)
        saved = folder / "result.json"
        if saved.exists():
            return json.loads(saved.read_text()), {
                p.name: p.read_bytes() for p in folder.iterdir() if p.name != "result.json"
            }
        prepared = self.root / ("evaluate" + ("-nonlinear" if nonlinear else "") + "-" + str(resolution))
        if (prepared / "result.json").exists():
            e = json.loads((prepared / "result.json").read_text())
            expected = dict(
                geometry_digest=digest(geometry),
                evaluator_version=self.version,
                image_digest=self.image,
                resolution=resolution,
                nonlinear=nonlinear,
            )
            if e.get("execution") == expected:
                files = {
                    p.name: p.read_bytes()
                    for p in prepared.iterdir()
                    if p.name in ("model.step", "model.glb", "internal.glb")
                }
                for name, data in files.items():
                    (folder / name).write_bytes(data)
                saved.write_text(json.dumps(e, allow_nan=False))
                return e, files
        try:
            e, files = evaluate(self.runner, geometry, resolution, nonlinear)
        except (ValueError, SandboxError) as exc:
            e = dict(
                outcome="failed",
                metrics={},
                violations=[{"code": "BUILD_OR_SOLVER_FAILED", "message": str(exc)[-1800:]}],
                fidelity="unsupported_geometry_or_flow",
            )
            files = {}
        for name, data in files.items():
            (folder / name).write_bytes(data)
        saved.write_text(json.dumps(e, allow_nan=False))
        return e, files

    def recall(self, arm, provider):
        vector = provider.embed(
            "VTOL range airfoil trim drag structural failure improvement lessons", STUDY + "-" + arm
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
                            "limit": 4,
                            "filter": {
                                "specification_id": STUDY + "-" + arm,
                                "evaluator_version": self.version,
                            },
                        }
                    },
                    {"$project": {"_id": 1, "summary": 1, "score": {"$meta": "vectorSearchScore"}}},
                ]
            )
        )

    def propose(self, arm, key, geometry, context, pilot_task=None):
        path = self.root / (key + ".json")
        if path.exists():
            return json.loads(path.read_text())
        provider = self.provider("pilot" if pilot_task else arm)
        current = copy.deepcopy(geometry)
        inputs = [
            {
                "role": "user",
                "content": json.dumps(
                    dict(
                        context=context,
                        current_geometry=current,
                        dimension_bounds=BOUNDS,
                        shape_bounds=SHAPE_BOUNDS,
                        task=pilot_task,
                    )
                ),
            }
        ]
        instructions = (
            "You are the VTOL CAD engineer. Optimize estimated cruise range at fixed 150Wh battery and .5kg payload. "
            "Use actual tools to edit geometry and submit_design before six responses end. Aim for >=95% seed speed and payload. "
            "You can make multiple related edits in one edit call. Each edit is incremental from current geometry. "
            "Honor failures and archive useful lessons, never invent measurements. Tools return valid STEP previews, not flight certification. "
            "Dimensions are metres, twist degrees; CST coefficients dimensionless. Keep airfoil thickness 10.5–18%, camber <=6%. "
            "Body shaping has conservative empirical drag; there is no assumed fairing interference benefit. "
            "The aircraft is conventional lift-and-cruise, hollow enclosed body with four lift rotors and a cruise prop. "
            "At most six responses. Prefer 1–3 useful tool calls and then submission; do not spend all rounds analyzing. "
            + (
                "CONTROL ARM: edit_geometry accepts only dimensions. Airfoils and shape controls remain at seed values. "
                if arm == "control"
                else "SURFACE ARM: use CST section tools and wing shaping where they improve performance, while keeping spars contained. "
            )
            + (
                "This is an interface pilot: complete the supplied task, do not optimize the whole aircraft."
                if pilot_task
                else ""
            )
        )
        calls = []
        for round_number in range(6):
            response_file = self.root / (key + f"-response-{round_number}.json")
            if response_file.exists():
                items = json.loads(response_file.read_text())
            else:
                print(f"Astra {key} tool round {round_number + 1}", flush=True)
                response = provider._response(
                    output_limit=6000,
                    reasoning_effort="high",
                    instructions=instructions,
                    input=inputs,
                    tools=definitions(arm),
                    parallel_tool_calls=False,
                    tool_choice={"type": "function", "name": "submit_design"}
                    if round_number == 5
                    else "required",
                )
                items = [o.model_dump(mode="json", exclude_none=True) for o in response.output]
                response_file.write_text(json.dumps(items))
            inputs.extend(items)
            functions = [o for o in items if o["type"] == "function_call"]
            for call in functions:
                name = call["name"]
                started = time.monotonic()
                try:
                    args = json.loads(call["arguments"])
                    if name == "submit_design":
                        required = {"title", "change", "lesson", "next_focus"}
                        if set(args) != required or any(
                            not isinstance(args[k], str) or not args[k].strip() for k in required
                        ):
                            raise ValueError(
                                "Submission needs nonempty title, change, lesson and next_focus strings"
                            )
                        args = {
                            k: args[k][:limit]
                            for k, limit in [
                                ("title", 70),
                                ("change", 400),
                                ("lesson", 1000),
                                ("next_focus", 500),
                            ]
                        }
                        self.preview(current)
                        result = dict(geometry=current, **args, calls=calls)
                        path.write_text(json.dumps(result, indent=2))
                        return result
                    if name == "edit_geometry":
                        if arm == "control" and set(args["edits"]) != {"dimensions"}:
                            raise ValueError("Control arm may edit dimensions only")
                        r, _ = tool(self.runner, "edit", {"geometry": current, "edits": args["edits"]})
                        preview, artifacts = self.preview(r["geometry"])
                        current = r["geometry"]
                        result = {
                            "geometry": current,
                            "geometry_id": digest(current),
                            "preview_artifact_id": self.artifacts.put(
                                artifacts["model.glb"], "preview.glb", "model/gltf-binary"
                            ),
                            "sections": preview["sections"],
                            "valid_solids": preview["valid_solids"],
                        }
                    elif name == "analyze_sections" and arm != "control":
                        result, _ = tool(self.runner, "analyze", {"geometry": current, **args})
                    elif name == "optimize_sections" and arm != "control":
                        r, _ = tool(self.runner, "optimize", {"geometry": current, **args})
                        _, artifacts = self.preview(r["geometry"])
                        current = r["geometry"]
                        result = r
                        result["geometry_id"] = digest(current)
                        result["preview_artifact_id"] = self.artifacts.put(
                            artifacts["model.glb"], "preview.glb", "model/gltf-binary"
                        )
                    else:
                        raise ValueError("Unknown or unavailable tool")
                    result["ok"] = True
                except (ValueError, SandboxError, KeyError, TypeError) as exc:
                    result = {
                        "ok": False,
                        "error": str(exc)[-1400:],
                        "repair": "Fix the identified constraint; current geometry is unchanged.",
                    }
                calls.append(
                    dict(
                        name=name,
                        arguments=call["arguments"],
                        result=result,
                        seconds=time.monotonic() - started,
                    )
                )
                inputs.append(
                    dict(type="function_call_output", call_id=call["call_id"], output=json.dumps(result))
                )
                (self.root / (key + "-calls.json")).write_text(json.dumps(calls, indent=2))
        raise ValueError("Agent did not submit a design within six responses")

    def pilot(self):
        saved = self.root / "pilot.json"
        if saved.exists():
            result = json.loads(saved.read_text())
            if not result["passed"]:
                raise ValueError("Pilot failed; campaign is disabled")
            return result
        tasks = [
            "Increase airfoil thickness slightly using edit_geometry and submit a valid STEP design.",
            "Set the middle chord factor to 1.02 while preserving the three-section wing and submit a valid STEP design.",
            "First call edit_geometry with thickness_scale=0.1 to exercise validation. Then repair it with thickness_scale=1.02 and submit.",
        ]
        results = []
        for i, task in enumerate(tasks):
            proposal = self.propose("surface_tools", f"pilot-{i}", self.seed, {}, task)
            calls = proposal["calls"]
            passed = any(c["name"] == "edit_geometry" and c["result"]["ok"] for c in calls)
            if i == 0:
                passed = passed and proposal["geometry"]["root"] != self.seed["root"]
            if i == 1:
                passed = passed and proposal["geometry"]["shape"]["mid_chord_factor"] == 1.02
            if i == 2:
                passed = passed and any(not c["result"]["ok"] for c in calls)
            results.append(dict(task=task, passed=passed, calls=calls))
        result = dict(passed=all(x["passed"] for x in results), tasks=results, spent_usd=self.spent("pilot"))
        saved.write_text(json.dumps(result, indent=2))
        self.store.insert("study_pilots", document("pilot", _id=STUDY + "-" + self.version, **result))
        if not result["passed"]:
            raise ValueError("Pilot failed; campaign is disabled")
        files = {name: (SANDBOX / name).read_text() for name in FILES if name.startswith("surface_")}
        self.store.insert(
            "design_tools",
            document(
                "tool",
                _id=STUDY + "-surface-tools",
                study_id=STUDY,
                evaluator_version=self.version,
                source_commit=self.repository.commit(STUDY + "-surface-tools", files),
                validation=result,
                interfaces=definitions("surface_tools"),
            ),
        )
        return result

    def record(self, arm, index, proposal):
        ident = f"{STUDY}-{arm}-{index:02d}"
        e, files = self.cached_evaluation(proposal["geometry"])
        bundle = {
            "geometry.json": json.dumps(proposal["geometry"]),
            "policy.json": json.dumps({k: proposal[k] for k in ("lesson", "next_focus")}),
            "calls.json": json.dumps(proposal.get("calls", [])),
        }
        record = document(
            "design",
            _id=ident,
            study_id=STUDY,
            arm=arm,
            iteration=index + 1,
            geometry=proposal["geometry"],
            title=proposal["title"],
            change=proposal["change"],
            reflection={k: proposal[k] for k in ("lesson", "next_focus")},
            evaluation=e,
            calls=proposal.get("calls", []),
            generator=self.settings.openai_model if index else "shared_engineering_seed",
            evaluator_version=self.version,
            source_commit=self.repository.commit(ident, bundle),
            artifacts={
                name: self.artifacts.put(
                    data, name, "model/gltf-binary" if name.endswith("glb") else "application/step"
                )
                for name, data in files.items()
            },
        )
        self.store.insert("design_iterations", record)
        if index:
            provider = self.provider(arm)
            Memory(self.store, provider.embed, self.version).remember(
                dict(
                    _id=ident,
                    run_id=STUDY + "-" + arm,
                    project_id="engineering-demo",
                    subsystem="vtol_surface",
                    specification_id=STUDY + "-" + arm,
                    evaluator_version=self.version,
                    parameters=proposal["geometry"],
                    fingerprint=digest(proposal["geometry"]),
                ),
                dict(_id=ident + "-evaluation", **e),
            )
        print(
            json.dumps(
                dict(
                    arm=arm,
                    iteration=index + 1,
                    outcome=e["outcome"],
                    range_km=metric(e, "range_km"),
                    violations=e["violations"],
                )
            ),
            flush=True,
        )
        self.export()

    def records(self, arm=None):
        return sorted(
            self.store.list("design_iterations", {"study_id": STUDY, **({"arm": arm} if arm else {})}),
            key=lambda d: (d["iteration"], d["arm"]),
        )

    def run(self, count):
        baseline, _ = self.cached_evaluation(self.seed)
        if baseline["outcome"] != "passed":
            raise ValueError("Common baseline must pass before paid campaign")
        self.pilot()
        limited = False
        for index in range(count):
            # Reserve enough room for both next proposals before starting a paired round.
            missing = any(
                not self.store.get("design_iterations", f"{STUDY}-{arm}-{index:02d}") for arm in ARMS
            )
            if index and missing and any(27 - self.spent(arm) < 3 for arm in ARMS):
                self.store.update("surface_studies", STUDY, {"status": "budget_limited"})
                limited = True
                break
            for arm in ARMS:
                if self.store.get("design_iterations", f"{STUDY}-{arm}-{index:02d}"):
                    continue
                if index == 0:
                    proposal = dict(
                        geometry=self.seed,
                        title="Common streamlined baseline",
                        change="Shared enclosed body and fixed NACA-derived sections.",
                        lesson="Both arms start from identical geometry and physics.",
                        next_focus="Improve range while retaining speed and payload.",
                        calls=[],
                    )
                else:
                    records = self.records(arm)
                    passing = [d for d in records if d["evaluation"]["outcome"] == "passed"]
                    best = max(passing, key=lambda d: metric(d["evaluation"], "range_km"))
                    history = [
                        {k: d[k] for k in ("iteration", "title", "change", "reflection", "geometry")}
                        | {
                            "metrics": d["evaluation"]["metrics"],
                            "violations": d["evaluation"]["violations"],
                            "best_cruise": d["evaluation"]
                            .get("performance", {})
                            .get("nominal", {})
                            .get("best"),
                        }
                        for d in records[-5:]
                    ]
                    context = dict(
                        iteration=index + 1,
                        history=history,
                        baseline_metrics=baseline["metrics"],
                        retrieved_memory=self.recall(arm, self.provider(arm)),
                    )
                    proposal = self.propose(arm, f"{arm}-{index:02d}", best["geometry"], context)
                self.record(arm, index, proposal)
        self.validate_finalists()
        self.store.update(
            "surface_studies",
            STUDY,
            {"status": "budget_limited" if limited else "completed", "finished_at": now()},
        )
        for arm in ("pilot", *ARMS):
            self.store.update(
                "runs",
                STUDY + "-" + arm,
                {"status": "budget_exhausted" if limited else "completed", "finished_at": now()},
            )
        self.export()

    def validate_finalists(self):
        validation = {}
        for arm in ARMS:
            rows = self.records(arm)
            if not rows:
                continue
            finalists = sorted(
                [d for d in rows if d["evaluation"]["outcome"] == "passed"],
                key=lambda d: metric(d["evaluation"], "range_km"),
                reverse=True,
            )[:3]
            for d in {d["_id"]: d for d in [rows[0], *finalists]}.values():
                print(f"Nonlinear refinement: {d['_id']}", flush=True)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    medium_job = pool.submit(self.cached_evaluation, d["geometry"], 8, True)
                    fine_job = pool.submit(self.cached_evaluation, d["geometry"], 12, True)
                    medium, _ = medium_job.result()
                    fine, _ = fine_job.result()
                r0, r1 = metric(medium, "range_km"), metric(fine, "range_km")
                change = abs(r1 / r0 - 1) if r0 else None
                check = {"passed": False, "reason": "No supported optimum"}
                audit = fine.get("performance", {}).get("direct_audit")
                if audit:
                    target = self.root / (digest(d["geometry"]) + "-xfoil.json")
                    if target.exists():
                        check = json.loads(target.read_text())
                    else:
                        try:
                            check = crosscheck(self.runner, d["geometry"], audit)
                        except SandboxError:
                            check = {"passed": False, "reason": "XFOIL failed or timed out"}
                        target.write_text(json.dumps(check))
                validation[d["_id"]] = dict(
                    evaluation=fine,
                    relative_range_change=change,
                    section_crosscheck=check,
                    converged=change is not None
                    and change <= 0.02
                    and medium["outcome"] == "passed"
                    and fine["outcome"] == "passed"
                    and check["passed"],
                )
                (self.root / "validation.json").write_text(json.dumps(validation, indent=2))
        self.store.insert(
            "study_validations",
            document("validation", _id=STUDY, validations=validation, evaluator_version=self.version),
        )

    def export(self):
        public = ROOT / "web/public/models/vtol" / STUDY
        public.mkdir(parents=True, exist_ok=True)
        rows = []
        for d in self.records():
            assets = {}
            for name, ident in d["artifacts"].items():
                target = f"{d['arm']}-{d['iteration']:02d}-{name}"
                path = public / target
                if not path.exists():
                    path.write_bytes(self.artifacts.read(ident))
                assets[name] = "/models/vtol/" + STUDY + "/" + target
            rows.append(
                {k: v for k, v in d.items() if k not in ("artifacts", "calls", "evaluation")}
                | {
                    "evaluation": public_evaluation(d["evaluation"]),
                    "assets": assets,
                    "tool_calls": len(d.get("calls", [])),
                    "tool_failures": sum(not x["result"]["ok"] for x in d.get("calls", [])),
                    "tool_seconds": sum(x["seconds"] for x in d.get("calls", [])),
                    "numerical_evaluations": sum(
                        x["result"].get("numerical_evaluations", 0) for x in d.get("calls", [])
                    ),
                }
            )
        saved = self.store.get("study_validations", STUDY)
        validation = saved["validations"] if saved else {}
        eligible = {
            arm: [d for d in rows if d["arm"] == arm and validation.get(d["_id"], {}).get("converged")]
            for arm in ARMS
        }
        winner = None
        if all(eligible.values()):
            control = max(
                eligible["control"], key=lambda d: metric(validation[d["_id"]]["evaluation"], "range_km")
            )
            base = next(d for d in rows if d["arm"] == "control" and d["iteration"] == 1)
            vb = validation.get(base["_id"], {})
            for d in sorted(
                eligible["surface_tools"],
                key=lambda d: metric(validation[d["_id"]]["evaluation"], "range_km"),
                reverse=True,
            ):
                e = validation[d["_id"]]["evaluation"]
                b = vb.get("evaluation", {})
                c = validation[control["_id"]]["evaluation"]
                adverse = e.get("performance", {}).get("scenarios", {}).get("combined_adverse", {})
                ab = b.get("performance", {}).get("scenarios", {}).get("combined_adverse", {})
                ac = c.get("performance", {}).get("scenarios", {}).get("combined_adverse", {})
                if (
                    vb.get("converged")
                    and metric(e, "range_km") >= 1.05 * max(metric(b, "range_km"), metric(c, "range_km"))
                    and all(
                        metric(e, k) >= 0.95 * metric(b, k) for k in ("max_speed_m_s", "payload_capacity_kg")
                    )
                    and not any(v.get("violations", ["missing"]) for v in (adverse, ab, ac))
                    and adverse.get("range_km", 0) > max(ab.get("range_km", 0), ac.get("range_km", 0))
                ):
                    winner = d["_id"]
                    break
        manifest = dict(
            study_id=STUDY,
            generated_at=now(),
            designs=rows,
            validation={
                k: {**v, "evaluation": public_evaluation(v["evaluation"])} for k, v in validation.items()
            },
            publishable=bool(winner),
            best_id=winner,
            spent_usd=sum(self.spent(a) for a in ("pilot", *ARMS)),
            spending={a: self.spent(a) for a in ("pilot", *ARMS)},
            status=self.store.get("surface_studies", STUDY)["status"],
            evaluator_version=self.version,
            budget_usd=60,
        )
        (ROOT / "web/data/surface-gallery.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=12, choices=range(1, 13))
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--amend-preflight",
        action="store_true",
        help="Archive and repair a failed pilot; forbidden after any scored design",
    )
    args = parser.parse_args()
    try:
        study = Study(amend_preflight=args.amend_preflight)
        if args.export_only:
            study.export()
        elif args.pilot_only:
            study.pilot()
        elif args.validate_only:
            study.validate_finalists()
            study.export()
        else:
            study.run(args.count)
    except Exception as exc:
        # Never expose exceptions containing credentials or connection strings.
        print(json.dumps({"status": "stopped", "error_type": type(exc).__name__}), flush=True)
        if isinstance(exc, BudgetExceeded):
            print("Campaign budget cannot cover the next request.", flush=True)
        elif isinstance(exc, ValueError) and str(exc).startswith(
            ("Frozen seed/", "Common baseline ", "Pilot failed;", "Agent did not ")
        ):
            print(str(exc)[:200], flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

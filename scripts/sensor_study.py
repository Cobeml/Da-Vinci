"""Bounded live Astra sensor study. Resume by ID; preserve every evaluated attempt.

Dedicated study collections avoid feeding a new geometry family into plate/wing workers.
Uses the existing Atlas ledger, budget, Vector Search, GridFS and Git artifact repository.
"""

import argparse
import fcntl
import json
import math
from pathlib import Path

from pydantic import BaseModel, Field

from davinci.artifacts import Artifacts, Repository
from davinci.budget import Budget
from davinci.config import Settings
from davinci.memory import Memory
from davinci.models import digest, document, now
from davinci.providers import AstraProvider
from davinci.runner import Runner
from davinci.sensor import REFERENCE_SOURCE, SANDBOX, SPECIFICATION, evaluate, evaluator_version
from davinci.store import Store

ROOT = Path(__file__).resolve().parents[1]
STUDY = "sensor-cradle-study-v1"


class Design(BaseModel):
    title: str = Field(max_length=48)
    change: str = Field(max_length=180)
    source: str = Field(max_length=16000)
    parameters: dict[str, float]
    lesson: str = Field(max_length=260)


class Utility(BaseModel):
    source: str = Field(max_length=12000)
    lesson: str = Field(max_length=260)
    target_deflection_mm: float = Field(ge=.3, le=.65)


class Study:
    def __init__(self):
        self.settings = Settings()  # SDK use only; never display settings or environment contents.
        if not self.settings.mongodb_uri or not self.settings.openai_api_key:
            raise ValueError("Atlas and Astra configuration required")
        self.root = self.settings.root / STUDY
        self.root.mkdir(exist_ok=True)
        self.lock = (self.root / "study.lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.store = Store(self.settings.root, self.settings.mongodb_uri, self.settings.mongodb_database)
        self.artifacts = Artifacts(self.settings.root, self.store)
        self.repository = Repository(self.settings.root)
        self.runner = Runner(self.settings)
        self.version = evaluator_version()
        self.store.insert("runs", document("run", _id=STUDY, project_id="uas-demo", diagnostic=True,
                                          mode="live", status="study_running", budget_usd=3,
                                          spent_usd=0, revision=0, evaluator_version=self.version))
        self.provider = AstraProvider(self.settings, Budget(self.store, self.settings.davinci_daily_budget_usd),
                                      self.store, STUDY)
        self.memory = Memory(self.store, self.provider.embed, self.version)
        self.store.insert("specifications", {**SPECIFICATION, "evaluator_version": self.version})

    def structured(self, key, instructions, context, schema):
        path = self.root / (key + ".json")
        if path.exists():
            return schema.model_validate_json(path.read_text())
        raw = self.root / (key + ".response.json")
        if not raw.exists():
            response = self.provider._response(
                instructions=instructions,
                input=json.dumps(context),
                text={"format": {"type": "json_schema", "name": schema.__name__,
                                 "strict": False, "schema": schema.model_json_schema()}},
            )
            raw.write_text(response.output_text)
        content = json.loads(raw.read_text())
        # Display-only text limits never modify source, geometry, or measurements.
        for name, length in (("title", 48), ("change", 180), ("lesson", 260)):
            if name in content and isinstance(content[name], str):
                content[name] = content[name][:length]
        result = schema.model_validate(content)
        path.write_text(result.model_dump_json(indent=2))
        return result

    def tool(self, history):
        existing = self.store.get("design_tools", STUDY + "-wall-tool")
        if existing:
            return existing
        result = self.structured("utility", (
            "Write a reusable Python utility run(arguments), no I/O. Return source, lesson, target_deflection_mm. "
            "It predicts minimum wall thickness for a two-wall PA12 cradle. Arguments: load_n (TOTAL force shared "
            "by two walls), height_mm, effective_width_mm, youngs_modulus_mpa, max_deflection_mm. "
            "Use I=b*t^3/12 and delta=(load_n/2)*height^3/(3*E*I). Return {minimum_wall_mm: number}. "
            "Validate positive finite inputs. No imports except math. Learn from measured history; target deflection "
            "must lie between 0.3 and 0.65 mm. Keep the physical evaluator unchanged. Plain descriptive lesson."
        ), {"history": history, "specification": SPECIFICATION}, Utility)
        checks = []
        for width, delta in ((88, .65), (28, .65), (40, .5), (22, .4)):
            args = {"load_n": 20, "height_mm": 35, "effective_width_mm": width,
                    "youngs_modulus_mpa": 1700, "max_deflection_mm": delta}
            actual = self.runner.invoke(result.source, args)["minimum_wall_mm"]
            expected = (2 * 20 * 35**3 / (1700 * width * delta)) ** (1 / 3)
            assert math.isclose(actual, expected, rel_tol=1e-8)
            checks.append({"arguments": args, "actual": actual, "expected": expected, "passed": True})
        try:
            self.runner.invoke(result.source, {"load_n": 0, "height_mm": 35, "effective_width_mm": 28,
                                               "youngs_modulus_mpa": 1700, "max_deflection_mm": .65})
        except RuntimeError:
            checks.append({"name": "nonpositive input rejected", "passed": True})
        else:
            raise ValueError("Generated tool accepted invalid input")
        files = {"tool.py": result.source, "policy.json": json.dumps({
            "target_deflection_mm": result.target_deflection_mm, "lesson": result.lesson,
        })}
        commit = self.repository.commit(STUDY + "-tool", files)
        record = document("tool", _id=STUDY + "-wall-tool", study_id=STUDY,
                          source=result.source, source_commit=commit, validation=checks,
                          target_deflection_mm=result.target_deflection_mm, lesson=result.lesson,
                          bundle_artifact_id=self.artifacts.put(self.repository.bundle(files), "tool.json", "application/json"))
        self.store.insert("design_tools", record)
        print("Generated wall-thickness tool: five independent checks passed", flush=True)
        return record

    def recall(self):
        vector = self.provider.embed("sensor cradle mass wall deflection cutouts failures and passing designs", STUDY)
        records = list(self.store.db.memories.aggregate([
            {"$vectorSearch": {"index": "memory_vector", "path": "embedding", "queryVector": vector,
                               "numCandidates": 100, "limit": 6,
                               "filter": {"specification_id": SPECIFICATION["_id"], "evaluator_version": self.version}}},
            {"$project": {"_id": 1, "summary": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]))
        return records

    def run(self, count):
        for index in range(count):
            id = f"{STUDY}-{index:02d}"
            if self.store.get("design_iterations", id):
                continue
            history = self.store.list("design_iterations", {"study_id": STUDY})
            summary = [{k: r[k] for k in ("iteration", "parameters", "evaluation", "change", "lesson")} for r in history]
            tool, suggestions = None, []
            if index >= 2:
                tool = self.tool(summary)
                for window in (30, 40, 50, 60, 66):
                    result = self.runner.invoke(tool["source"], {
                        "load_n": 20, "height_mm": 35, "effective_width_mm": 88 - window,
                        "youngs_modulus_mpa": 1700, "max_deflection_mm": tool["target_deflection_mm"],
                    })
                    suggestions.append({"window_mm": window, **result})
                self.store.event(STUDY, "study_tool_invoked", "Invoked saved thickness helper", iteration=index)
            context = {
                "specification": SPECIFICATION, "geometry_contract": (SANDBOX / "sensor_family.py").read_text(),
                "reference_source": REFERENCE_SOURCE, "iteration": index + 1, "history": summary,
                "retrieved_memory": self.recall() if index else [],
                "working_policy": {"lesson": tool["lesson"], "target_deflection_mm": tool["target_deflection_mm"]}
                if tool else {"lesson": "Establish a conservative baseline, then remove unnecessary material"},
                "executed_tool_predictions": suggestions,
            }
            directions = (
                "First design: establish a solid, conservative reference with base_mm=6, wall_mm=6, "
                "window_style=0, window_mm=0, base_slots=0, gusset_mm=0."
                if index == 0 else
                "Reduce mass relative to the best passing predecessor. Explore a visibly different pocket/rib layout "
                "when useful: open windows, split triangular windows, base slots and gussets. "
                "Use measured feedback; preserve useful changes and correct failures. Avoid identical geometry."
            )
            if index >= 6:
                directions += (
                    " This is a deliberate topology comparison after convergence, not another fractional wall trim. "
                    "Require window_style=2 (two triangular windows with a diagonal rib), "
                    + ("base_slots=3 and gusset_mm=12. " if index == 6 else "base_slots=2 and gusset_mm=6. ")
                    + "Choose window size and wall/base thickness to minimize mass in that topology. "
                    "Keep existing best design if this alternative is heavier; do not claim improvement unless measured."
                )
            proposal = self.structured(f"proposal-{index:02d}", (
                "You are a CAD agent optimizing a drone sensor cradle. Return actual executable CadQuery source "
                "with build(parameters, interfaces)->cadquery.Assembly plus parameters, a short descriptive title, "
                "one-sentence change and a lesson for subsequent attempts. Use the supplied build_cradle helper "
                "to preserve the independently evaluated family. Parameters are base_mm, wall_mm, window_mm, "
                "window_style, base_slots, gusset_mm. The geometry helper is available as sensor_family. "
                "Never invent measurements. Minimize STEP mass subject to max deflection 0.65 mm and stress 28 MPa. "
                "Wall screen ignores rib stiffness credit and uses width=88-window_mm (or 88 for solid walls), "
                "height=35 mm, I=width*wall_mm^3/12, load per wall=10 N, E=1700 MPa. "
                "Keep four mounting holes and pivot interface. " + directions
            ), context, Design)
            print(f"Evaluating {index + 1}: {proposal.title}", flush=True)
            evaluation, outputs = evaluate(self.runner, proposal.source, proposal.parameters)
            files = {"candidate.py": proposal.source, "parameters.json": json.dumps(proposal.parameters),
                     "context.json": json.dumps(context), "policy.json": json.dumps({"lesson": proposal.lesson})}
            commit = self.repository.commit(id, files)
            artifact_ids = {name: self.artifacts.put(data, name, "model/gltf-binary" if name.endswith("glb") else "application/step")
                            for name, data in outputs.items()}
            source_id = self.artifacts.put(self.repository.bundle(files), "source.json", "application/json")
            record = document("design", _id=id, study_id=STUDY, iteration=index + 1,
                              title=proposal.title, change=proposal.change, lesson=proposal.lesson,
                              parameters=proposal.parameters, evaluation=evaluation, source_commit=commit,
                              source=proposal.source, source_artifact_id=source_id, artifacts=artifact_ids,
                              tool_id=tool["_id"] if tool else None, tool_predictions=suggestions,
                              retrieved_memory=context["retrieved_memory"], evaluator_version=self.version,
                              runtime_image_digest=self.runner.image_digest(), generator=self.settings.openai_model)
            self.store.insert("design_iterations", record)
            candidate = {"_id": id, "run_id": STUDY, "project_id": "uas-demo", "subsystem": "sensor_cradle",
                         "specification_id": SPECIFICATION["_id"], "evaluator_version": self.version,
                         "fingerprint": digest(proposal.parameters), "parameters": proposal.parameters}
            self.memory.remember(candidate, {"_id": id + "-evaluation", **evaluation})
            (self.root / f"iteration-{index:02d}.json").write_text(json.dumps(record, indent=2))
            print(f"{evaluation['outcome']}: {evaluation['metrics']['mass_g']['value']:.2f} g, "
                  f"{evaluation['metrics']['deflection_mm']['value']:.3f} mm", flush=True)
        self.export()
        self.store.update("runs", STUDY, {"status": "completed", "finished_at": now()})

    def export(self):
        records = self.store.list("design_iterations", {"study_id": STUDY})
        public = ROOT / "web/public/models/sensor"
        public.mkdir(parents=True, exist_ok=True)
        data = ROOT / "web/data"
        data.mkdir(exist_ok=True)
        designs = []
        for record in records:
            names = {}
            for filename, artifact_id in record["artifacts"].items():
                target = f"{record['iteration']:02d}." + filename.split(".")[-1]
                payload = self.artifacts.read(artifact_id)
                (public / target).write_bytes(payload)
                names[filename] = "/models/sensor/" + target
            (public / f"{record['iteration']:02d}.py").write_text(record["source"])
            designs.append({**{k: record[k] for k in (
                "_id", "iteration", "title", "change", "lesson", "parameters", "evaluation",
                "source_commit", "tool_id", "generator", "evaluator_version", "retrieved_memory",
            )}, "model_url": names["model.glb"], "step_url": names["model.step"],
                "source_url": f"/models/sensor/{record['iteration']:02d}.py"})
        manifest = {"study_id": STUDY, "generated_at": now(), "specification": SPECIFICATION,
                    "designs": designs, "spent_usd": self.store.get("runs", STUDY)["spent_usd"],
                    "tool": {k: v for k, v in (self.store.get("design_tools", STUDY + "-wall-tool") or {}).items()
                             if k not in ("source", "bundle_artifact_id")},
                    "execution": "bounded Python study; Atlas archive and vector memory; isolated CAD evaluation"}
        (data / "sensor-gallery.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Exported {len(designs)} models; recorded usage ${manifest['spent_usd']:.4f}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=6, choices=range(1, 9))
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    try:
        study = Study()
        study.export() if args.export_only else study.run(args.count)
    except Exception as exc:
        # Raw provider/database errors can contain credentials. Preserve type only.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

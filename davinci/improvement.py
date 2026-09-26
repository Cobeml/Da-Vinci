import json
import math

from davinci.models import digest, document
from davinci.templates import INITIAL_ORCHESTRATOR, INITIAL_POLICY, INITIAL_UI


class Improvements:
    def __init__(self, store, artifacts, repository, runner):
        self.store, self.artifacts, self.repository, self.runner = store, artifacts, repository, runner

    def initialize(self):
        files = {
            "orchestrator.py": INITIAL_ORCHESTRATOR,
            "policy.json": json.dumps(INITIAL_POLICY),
            "PolicyNote.tsx": INITIAL_UI,
        }
        release = {
            **document("release"),
            "_id": "release-baseline",
            "files": files,
            "status": "active",
            "predecessor_id": None,
            "summary": "Initial screening policy",
            "validation": [],
            "tool_version_ids": [],
        }
        if not self.store.get("releases", release["_id"]):
            release["source_commit"] = self.repository.commit(release["_id"], files)
            release["bundle_artifact_id"] = self.artifacts.put(
                self.repository.bundle(files), "release.json", "application/json"
            )
            self.store.insert("releases", release)
        self.store.insert("pointers", {"_id": "active-release", "release_id": release["_id"], "revision": 0})

    def active(self):
        return self.store.get("releases", self.store.get("pointers", "active-release")["release_id"])

    def create_tool(self, source, summary, run_id, evaluation_id):
        id = "tool-area-" + digest(source)[:16]
        prior = self.store.get("tools", id)
        if prior:
            return prior
        tests = []
        cases = [
            ({"dimensions_m": [2, 3, 4], "direction": [1, 0, 0]}, 12),
            ({"dimensions_m": [2, 3, 4], "direction": [0, 1, 0]}, 8),
            ({"dimensions_m": [2, 3, 4], "direction": [0, 0, -2]}, 6),
            ({"dimensions_m": [2, 3, 4], "direction": [1, 1, 0]}, 20 / math.sqrt(2)),
        ]
        try:
            for args, expected in cases:
                output = self.runner.invoke(source, args)
                passed = (
                    math.isclose(output["projected_area_m2"], expected, rel_tol=1e-8)
                    and output["fidelity"] == "bounding_box_proxy"
                )
                tests.append({"arguments": args, "expected": expected, "actual": output, "passed": passed})
            try:
                self.runner.invoke(source, {"dimensions_m": [1, 1, 1], "direction": [0, 0, 0]})
                tests.append({"name": "zero direction rejected", "passed": False})
            except RuntimeError:
                tests.append({"name": "zero direction rejected", "passed": True})
        except Exception as exc:
            tests.append({"name": "execution", "passed": False, "error": str(exc)[:1000]})
        status = "active" if tests and all(t["passed"] for t in tests) else "rejected"
        commit = self.repository.commit(id, {"tool.py": source})
        tool = {
            **document("tool"),
            "_id": id,
            "project_id": "uas-demo",
            "name": "directional_projected_area",
            "source": source,
            "source_commit": commit,
            "version": id,
            "status": status,
            "summary": summary,
            "entrypoint": "tool:run",
            "motivation": evaluation_id,
            "run_id": run_id,
            "validation": tests,
            "runtime_image": self.runner.settings.davinci_sandbox_image,
            "input_schema": {
                "type": "object",
                "required": ["dimensions_m", "direction"],
                "properties": {
                    key: {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number"}}
                    for key in ("dimensions_m", "direction")
                },
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "required": ["projected_area_m2", "fidelity"],
                "properties": {
                    "projected_area_m2": {"type": "number", "minimum": 0},
                    "fidelity": {"const": "bounding_box_proxy"},
                },
                "additionalProperties": False,
            },
            "limitations": "Bounding-box area proxy only; does not predict drag",
            "execution": {"timeout_seconds": 60, "network": False},
        }
        tool["bundle_artifact_id"] = self.artifacts.put(
            self.repository.bundle({"tool.py": source}), "tool.json", "application/json"
        )
        self.store.insert("tools", tool)
        self.store.event(
            run_id, "tool_" + status, f"Reusable tool {status}: directional projected area", tool_id=id
        )
        return tool

    def invoke_tool(self, id, arguments, run_id=None):
        from jsonschema import validate

        tool = self.store.get("tools", id)
        if not tool or tool["status"] != "active":
            raise ValueError("Tool version is not active")
        validate(arguments, tool["input_schema"])
        result = self.runner.invoke(tool["source"], arguments)
        validate(result, tool["output_schema"])
        self.store.event(
            run_id,
            "tool_invoked",
            "Executed archived utility",
            tool_id=id,
            arguments=arguments,
            result=result,
        )
        return result

    def propose_release(self, patch, run_id, evaluation_id):
        current = self.active()
        allowed = {"orchestrator.py", "policy.json", "PolicyNote.tsx"}
        if not patch.files or not set(patch.files).issubset(allowed):
            raise ValueError("Patch must target editable orchestration, policy or UI files")
        if any(len(value) > 40000 for value in patch.files.values()):
            raise ValueError("Patch exceeds source limit")
        files = {**current["files"], **patch.files}
        id = "release-" + digest(files)[:16]
        if self.store.get("releases", id):
            return self.store.get("releases", id)
        checks, ui = [], None
        try:
            policy = json.loads(files["policy.json"])
            assert 2.5 <= policy["minimum_mount_thickness_mm"] <= 6
            assert 1.5 <= policy["minimum_hinge_gap_mm"] <= 5
            cases = [{"subsystem": "structural", "parameters": {"thickness_mm": v}} for v in (1.5, 3, 6)]
            cases += [
                {
                    "subsystem": "aerodynamic",
                    "parameters": {"hinge_gap_mm": v, "span_mm": 600, "flap_fraction": 0.25},
                }
                for v in (0.2, 2, 4)
            ]
            results = self.runner.adapt(files, cases)
            assert len(results) == len(cases)
            for case, result in zip(cases, results):
                key, minimum = (
                    ("thickness_mm", 2.5) if case["subsystem"] == "structural" else ("hinge_gap_mm", 1.5)
                )
                original = case["parameters"]
                valid = set(result) == set(original) and minimum <= result[key] <= max(
                    original[key],
                    policy["minimum_mount_thickness_mm"]
                    if key == "thickness_mm"
                    else policy["minimum_hinge_gap_mm"],
                )
                valid = valid and all(result[k] == original[k] for k in original if k != key)
                checks.append({"name": f"adapt {case['subsystem']} {original[key]}", "passed": valid})
            rendered, _, _ = self.runner.execute(
                "/opt/ui/check.cjs",
                {"PolicyNote.tsx": files["PolicyNote.tsx"]},
                timeout=30,
                executable="node",
            )
            ui = rendered["note.html"]
            checks.append({"name": "React component compiles and renders", "passed": bool(ui)})
            # Genuine CAD canary of the motivating failure after adaptation.
            from davinci.models import SPECIFICATION
            from davinci.templates import MOUNT_SOURCE, WING_SOURCE

            for case, result, source in (
                (cases[0], results[0], MOUNT_SOURCE),
                (cases[3], results[3], WING_SOURCE),
            ):
                evaluation, _, _ = self.runner.evaluate(source, result, case["subsystem"], SPECIFICATION)
                checks.append(
                    {
                        "name": f"{case['subsystem']} geometry canary",
                        "passed": evaluation["outcome"] == "passed",
                        "violations": evaluation["violations"],
                    }
                )
        except Exception as exc:
            checks.append({"name": "candidate execution", "passed": False, "error": str(exc)[:1000]})
        passing = bool(checks) and all(c["passed"] for c in checks)
        release = {
            **document("release"),
            "_id": id,
            "files": files,
            "status": "validated" if passing else "rejected",
            "run_id": run_id,
            "predecessor_id": current["_id"],
            "summary": patch.summary,
            "motivation": evaluation_id,
            "validation": checks,
            "source_commit": self.repository.commit(id, files),
            "tool_version_ids": [t["_id"] for t in self.store.list("tools", {"status": "active"})],
        }
        release["bundle_artifact_id"] = self.artifacts.put(
            self.repository.bundle(files), "release.json", "application/json"
        )
        if ui:
            release["ui_artifact_id"] = self.artifacts.put(ui, "note.html", "text/html")
        self.store.insert("releases", release)
        self.store.event(
            run_id,
            "release_" + release["status"],
            "Harness patch " + release["status"],
            release_id=id,
            checks=checks,
        )
        return release

    def activate(self, release_id, run_id):
        release = self.store.get("releases", release_id)
        if not release or release["status"] != "validated":
            return False
        result = self.store.update(
            "pointers",
            "active-release",
            {"release_id": release_id},
            {"release_id": release["predecessor_id"]},
        )
        if result:
            self.store.event(
                run_id,
                "release_activated",
                "Validated harness activated at round boundary",
                release_id=release_id,
            )
        return bool(result)

    def rollback(self, release_id, run_id, reason):
        release = self.store.get("releases", release_id)
        if release and release["predecessor_id"]:
            changed = self.store.update(
                "pointers",
                "active-release",
                {"release_id": release["predecessor_id"]},
                {"release_id": release_id},
            )
            if changed:
                self.store.event(run_id, "release_rolled_back", reason, release_id=release_id)
            return bool(changed)
        return False

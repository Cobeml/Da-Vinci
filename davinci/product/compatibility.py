"""Explicit v1 adapter. Old records are never upgraded to test-first evidence."""

import json

from davinci.errors import safe_error
from davinci.models import digest, document
from davinci.product.tasks import score_evaluation
from davinci.runner import SandboxError


def legacy_view(run):
    return {
        **run,
        "lifecycle_version": 1,
        "driver": run.get("driver", "managed"),
        "mode": run.get("mode", run.get("config", {}).get("run", {}).get("mode", "replay")),
        "guarantees": "legacy-unverified-coverage",
        "test_first_verified": False,
    }


def identities(task, config, image):
    # A builder edit changes the legacy task hash, but never these suite inputs.
    evaluator = {
        k: v for k, v in task.items() if k not in ("source", "baseline", "version", "source_version")
    }
    plan = {
        "specification": task["specification"],
        "constraints": config.model_dump()["constraints"],
        "objective": config.model_dump()["objective"],
        "parameters_schema": task["parameters_schema"],
    }
    ids = {"plan_id": digest(plan), "evaluator_id": digest(evaluator), "runtime_id": digest(image)}
    return {**ids, "suite_id": digest(ids), "guarantees": "legacy-unverified-coverage"}


class LegacyAdapter:
    """Existing managed loop delegates persistence/execution to this compatibility boundary.

    Legacy fixed-family evaluations retain their original semantics and UI shape.
    They deliberately cannot supply verification evidence for a v2 experiment.
    """

    def __init__(self, engine):
        self.engine = engine
        self.store = engine.store

    def submit(self, run, candidate):
        self.store.insert("candidates", candidate)
        commit = self.engine.repository.commit(
            candidate["_id"],
            {
                "build.py": candidate["source"],
                "parameters.json": json.dumps(candidate["parameters"]),
                "run.yaml": run["original_yaml"],
            },
        )
        self.store.update("candidates", candidate["_id"], {"source_commit": commit})
        self.store.event(
            run["_id"], "candidate_created", "CAD proposal archived", candidate_id=candidate["_id"]
        )

    def evaluate(self, run, config, task, candidate, evaluate):
        self.engine.ensure_running(run["_id"])
        self.store.update("runs", run["_id"], {"phase": "evaluating"})
        try:
            result, artifacts = evaluate(
                self.engine.runner,
                task,
                candidate["parameters"],
                candidate["source"],
                run["runtime_image_digest"],
            )
            result = score_evaluation(task, config, result)
        except Exception as exc:
            self.engine.ensure_running(run["_id"])
            if isinstance(exc, (SandboxError, ValueError, KeyError)) or type(exc).__module__.startswith(
                "jsonschema"
            ):
                result = {
                    "outcome": "failed",
                    "metrics": {},
                    "violations": [{"code": "BUILD_OR_EVALUATION", "message": safe_error(exc)}],
                    "fidelity": "not_evaluated",
                }
                artifacts = {}
            else:
                raise
        cid = candidate["_id"]
        refs = {
            name: self.engine.artifacts.put(
                data, name, "model/gltf-binary" if name.endswith(".glb") else "application/step"
            )
            for name, data in artifacts.items()
            if name.endswith((".step", ".glb"))
        }
        self.store.update("candidates", cid, {"artifacts": refs})
        evaluation = document(
            "evaluation", _id="evaluation-" + cid, run_id=run["_id"], candidate_id=cid, **result
        )
        if config.task.template == "vtol" and candidate["iteration"]:
            base = self.store.get("evaluations", "evaluation-" + run["_id"] + "-000")
            for key in ("max_speed_m_s", "payload_capacity_kg"):
                bv, value = (
                    base["metrics"].get(key, {}).get("value"),
                    evaluation["metrics"].get(key, {}).get("value"),
                )
                if bv is None or value is None or value < 0.95 * bv:
                    evaluation["violations"].append(
                        {
                            "code": "CAPABILITY_RETENTION",
                            "message": f"{key} below 95% of baseline or unavailable",
                        }
                    )
                    evaluation["outcome"] = "failed"
        self.store.insert("evaluations", evaluation)
        self.store.event(
            run["_id"],
            "evaluation_completed",
            "Evaluation archived",
            candidate_id=cid,
            outcome=evaluation["outcome"],
        )
        return evaluation

    def reflect(self, policy):
        # A legacy model's lesson is an unverified hypothesis, not a physical score.
        self.store.insert("policies", {**policy, "support": "hypothesis"})

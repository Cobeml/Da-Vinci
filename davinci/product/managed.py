"""Thin reasoning adapter over Lifecycle; no separate execution or acceptance loop."""

from davinci.product.contracts import Candidate, Command
from davinci.product.lifecycle import Conflict


class ManagedDriver:
    def __init__(self, engine):
        self.engine = engine
        self.lifecycle = engine.lifecycle

    def advance(self, eid, command, stage):
        """Author a draft, propose under a frozen suite, or reflect on measured evidence.

        Verification, freezing, execution and reporting use the same lifecycle API
        as external agents. A caller can chain these without approval round-trips.
        """
        allowed = {"author": {"draft"}, "propose": {"frozen", "reflected"}, "reflect": {"evaluated"}}
        if stage not in allowed:
            raise ValueError("Unknown managed stage")
        row, cmd, sig, done = self.lifecycle._begin(eid, command, "managed_" + stage, None, allowed[stage])
        if row["driver"] != "managed":
            raise Conflict("External experiments cannot invoke a managed provider")
        if done:
            return row
        if row["mode"] == "live" and not self.engine.credentials.openai_api_key:
            raise ValueError("Managed live reasoning requires configured model credentials")
        provider = self.engine.provider_type(self.engine, row)
        # Claim the same slot and revision before any potentially paid request.
        job = {
            "id": "managed-" + cmd.operation_id,
            "owner": cmd.actor,
            "operation_id": cmd.operation_id,
            "status": "running",
        }
        self.lifecycle._execution_claim(row, cmd, sig, "managed_" + stage, job)
        try:
            context = {
                "description": row["description"],
                "plan": row["plan"],
                "experience": self.lifecycle.retrieve(row["description"], experiment_id=eid),
                "memory_policy": "Cross-task suggestions are hypotheses unless explicitly supported observations. Check applicability and source evidence; imported claims are not locally reproduced. No passing score transfers. Define and verify this task's own tests.",
                "candidates": row["candidates"][-3:],
                "results": row["results"][-3:],
            }
            if stage == "author":
                from davinci.product.contracts import Evaluator, Plan, Runtime

                context["schemas"] = {
                    "plan": Plan.model_json_schema(),
                    "evaluator": Evaluator.model_json_schema(),
                    "runtime": Runtime.model_json_schema(),
                }
                from davinci.product.adapters import catalog

                context["simulation_adapters"] = catalog()
                instruction = (
                    "Declare simulation adapter, supported physics/material/fidelity, CAD/solver units, structured planar interface regions, and required final evidence for every new test. "
                    "Only shipped scoped adapters are available; do not invent a generic structural/dynamics solver. "
                    "Use unsupported requirements to request missing capabilities, never silently substitute a preliminary screen. "
                    "Author an engineering test plan before any candidate. Return plan, evaluator, runtime. "
                    "Mark missing critical engineering requirements resolved=false; never invent user loads or material data. "
                    "Evaluator/runtime may be null until configured. Do not create candidate geometry. "
                    "Use explicit units, coverage, uncertainty, numerical accuracy and independent reference fixtures."
                )
            elif stage == "propose":
                context["schema"] = Candidate.model_json_schema()
                instruction = "Return a candidate matching the schema. Only edit the design; the frozen test plan is immutable."
            else:
                instruction = "Return lesson (string). State hypotheses and limits. Do not relax tests or claim cross-task acceptance."
            answer = provider.request("lifecycle-" + stage + "-" + cmd.operation_id, instruction, context)
            finished = self.lifecycle._finish(eid, job["id"], {"phase": row["phase"]})
            if finished["phase"] == "cancelled":
                return finished
            next_cmd = Command(
                actor=cmd.actor, revision=finished["revision"], operation_id="apply-" + cmd.operation_id
            )
            if stage == "author":
                return self.lifecycle.update_plan(
                    eid, next_cmd, answer["plan"], answer.get("evaluator"), answer.get("runtime")
                )
            if stage == "propose":
                return self.lifecycle.submit_candidate(eid, next_cmd, answer)
            return self.lifecycle.reflect(
                eid, next_cmd, lesson=answer["lesson"], result_id=row["results"][-1]["id"]
            )
        except Exception:
            # Never auto-repeat uncertain/malformed reasoning. Provider archives requests/spend.
            request_id = f"{eid}:lifecycle-{stage}-{cmd.operation_id}"
            self.engine.store.update("requests", request_id, {"status": "uncertain"}, {"status": "completed"})
            current = self.lifecycle.get(eid)
            if current.get("job", {}).get("status") == "running":
                self.lifecycle._finish(eid, job["id"], {"phase": "interrupted", "resume_phase": row["phase"]})
            elif current["phase"] == row["phase"] and current.get("job", {}).get("id") == job["id"]:
                self.engine.store.update(
                    "runs",
                    eid,
                    {
                        "phase": "interrupted",
                        "status": "paused",
                        "resume_phase": row["phase"],
                        "revision": current["revision"] + 1,
                    },
                    {"revision": current["revision"]},
                )
            raise
        finally:
            self.engine.release(eid)

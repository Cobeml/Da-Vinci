"""Public test-first MuJoCo route; use --driver managed only with the explicit fixture server."""

import argparse
import json
import math
from pathlib import Path

from davinci.models import digest
from davinci.product.client import Client, ClientError
from davinci.product.mechanism.examples import bundle, candidate

VARIANTS = ("solid", "ambiguous", "misplaced", "pocketed", "pocketed")


class MechanismProvider:
    """Deterministic fixture reasoning; never constructs a generation/embedding provider."""

    def __init__(self, engine, row):
        if (
            row["driver"] != "managed"
            or row["mode"] != "replay"
            or not row["opening"]["metadata"].get("mechanism_fixture")
        ):
            raise ValueError("Only explicit managed mechanism fixtures permitted")
        self.row = row

    def request(self, key, instruction, context):
        if key.startswith("lifecycle-author"):
            return bundle(self.row["opening"]["metadata"]["image"])
        if key.startswith("lifecycle-propose"):
            return candidate(VARIANTS[min(len(self.row["candidates"]), len(VARIANTS) - 1)])
        if key.startswith("lifecycle-reflect"):
            return {
                "lesson": "Fixture hypothesis: removing interior mass improves force-limited tracking; validate independent CAD inertia, contacts and fixed interfaces. No strength inference."
            }
        raise ValueError("Unsupported fixture stage")


class MechanismBenchmark:
    def __init__(self, client, driver, output, prefix="mechanism-v1"):
        self.client, self.driver, self.output, self.prefix = client, driver, Path(output), prefix
        self.output.mkdir(parents=True, exist_ok=True)
        self.image = client.request("GET", "/api/v2/runtimes/resolve?image=da-vinci-mujoco%3Alocal")["image"]

    def open(self, suffix=""):
        return self.client.request(
            "POST",
            "/api/v2/experiments",
            dict(
                object={"slug": "rigid-carriage" + suffix, "name": "Rigid vertical carriage" + suffix},
                description="Lift a rigid carriage by 30 mm using a 0.4 N motor under gravity; preserve the guide/stop and reduce mass. No stress/fatigue claim.",
                actor="mechanism-author",
                operation_id=self.prefix + "-" + self.driver + suffix,
                driver=self.driver,
                mode="replay" if self.driver == "managed" else "live",
                metadata={"mechanism_fixture": True, "image": self.image},
            ),
        )

    def post(self, eid, action, payload=None, operation=None):
        row = self.client.status(eid)
        return self.client.request(
            "POST",
            f"/api/v2/experiments/{eid}/{action}",
            dict(
                actor=row["actor"],
                revision=row["revision"],
                operation_id=operation or action,
                **(payload or {}),
            ),
        )

    def wait(self, eid, job):
        result = self.client.wait(eid, job["id"], 900)
        if result["status"] != "completed" or result.get("failures") or result.get("wait_timed_out"):
            raise RuntimeError(result)
        return result

    def run(self, **ignored):
        row = self.open()
        eid = row["_id"]
        print(json.dumps({"driver": self.driver, "experiment_id": eid}), flush=True)
        if self.driver == "managed":
            self.post(eid, "managed/author")
        else:
            self.post(eid, "plan", bundle(self.image))
        for variant, expected, mass, error in [
            ("solid", "physical_failure", 64.8, 0.05),
            ("reference-light", "pass", 19.44, 0.0),
        ]:
            job = self.post(
                eid,
                "reference-builds",
                {
                    "reference": {
                        "candidate": candidate(variant),
                        "provenance": "Independent nominal box reference before design generation",
                    }
                },
                "reference-" + variant,
            )
            aid = self.wait(eid, job)["fixture_artifacts"][0]
            job = self.post(
                eid,
                "verify",
                {
                    "verification": dict(
                        test_id="mechanism",
                        fixture_artifact=aid,
                        expected_status=expected,
                        reference_metrics={
                            "mass_g": dict(value=mass, unit="g", dimension="mass"),
                            "tracking_error_m": dict(value=error, unit="m", dimension="length"),
                            "settled_penetration_m": dict(value=0.0, unit="m", dimension="length"),
                            "equilibrium_error_n": dict(value=0.0, unit="N", dimension="force"),
                            "peak_actuation_n": dict(value=0.2, unit="N", dimension="force"),
                        },
                        tolerances={
                            "mass_g": 1e-5,
                            "tracking_error_m": 0.0002,
                            "settled_penetration_m": 0.0005,
                            "equilibrium_error_n": 0.00001,
                            "peak_actuation_n": 0.200001,
                        },
                        provenance="Independent box mass and static force balance: heavy motor cannot oppose weight, so q=-initial_gap; light gravity-compensated target q=0.03. Contact penetration must lie within 0.5 mm; equilibrium residual within 1e-5 N. Peak actuation reference is the independently specified interval [0,0.4] N (center 0.2, half-width 0.200001), not a measured answer. Internal analytic motion/conservation and settled contact checks also mandatory.",
                    )
                },
                "verify-" + variant,
            )
            self.wait(eid, job)
        self.post(eid, "freeze")
        suite = self.client.status(eid)["suite_id"]
        expected_status = ["physical_failure", "invalid_setup", "invalid_setup", "pass", "pass"]
        for i, variant in enumerate(VARIANTS):
            if self.driver == "managed":
                self.post(eid, "managed/propose", operation=f"candidate-{i}")
            else:
                self.post(eid, "candidates", {"candidate": candidate(variant)}, f"candidate-{i}")
            self.wait(eid, self.post(eid, "evaluate", operation=f"evaluate-{i}"))
            row = self.client.status(eid)
            result = row["results"][-1]
            assert row["suite_id"] == suite and result["tests"][0]["status"] == expected_status[i], result
            assert result["design_accepted"] == (i >= 3)
            assert result["evidence_complete"] == (i not in (1, 2))
            if self.driver == "managed":
                self.post(eid, "managed/reflect", operation=f"reflection-{i}")
            else:
                self.post(
                    eid,
                    "reflections",
                    dict(
                        result_id=result["id"],
                        lesson="External hypothesis: reduce carriage mass under unchanged force/trajectory limits; invalid bindings require geometry correction, not relaxed interfaces.",
                    ),
                    f"reflection-{i}",
                )
        self.post(eid, "finalize")
        row = self.client.status(eid)
        report = self.client.request("GET", f"/api/v2/experiments/{eid}/report")
        (self.output / (eid + ".json")).write_text(json.dumps(report, indent=2) + "\n")
        history = [h["action"] for h in row["history"]]
        assert history.index("freeze") < history.index("submit_candidate")
        assert all(v["matched"] and v["at"] <= row["frozen_at"] for v in row["verifications"])
        a, b = row["results"][-2:]
        for key, v in a["tests"][0]["metrics"].items():
            assert math.isclose(
                v["value"], b["tests"][0]["metrics"][key]["value"], rel_tol=1e-8, abs_tol=1e-8
            )
        unavailable = self.open("-unsupported")
        other = unavailable["_id"]
        payload = bundle(self.image)
        payload["plan"]["tests"][0]["simulation"]["phenomena"].append("fatigue")
        # An explicitly unsupported request remains a draft, never a cheaper dynamics substitute.
        self.post(other, "plan", payload)
        readiness = self.client.request("GET", f"/api/v2/experiments/{other}/plan-validation")
        assert not readiness["ready_to_freeze"] and not self.client.status(other)["candidates"]
        try:
            self.post(other, "freeze")
        except ClientError as exc:
            assert exc.code in (2, 4)
        else:
            raise AssertionError("Unsupported physics was accepted")
        result = dict(
            version=1,
            driver=self.driver,
            image=self.image,
            paid_calls=0,
            reasoning="Scripted external / deterministic managed fixture; not autonomous reasoning evidence",
            cases=[
                dict(
                    experiment_id=eid,
                    suite_id=suite,
                    acceptance_contract_id=digest(
                        {k: row[k] for k in ("plan", "evaluator", "runtime", "execution_id")}
                    ),
                    final_metrics=b["tests"][0]["metrics"],
                    final_accepted=b["design_accepted"],
                    test_before_candidate=True,
                    evidence_complete=b["evidence_complete"],
                    outcomes=[
                        dict(
                            status=r["tests"][0]["status"],
                            metrics=r["tests"][0]["metrics"],
                            accepted=r["design_accepted"],
                            complete=r["evidence_complete"],
                        )
                        for r in row["results"]
                    ],
                    repeated_final_metrics=True,
                    report_file=eid + ".json",
                )
            ],
            unavailable=readiness,
        )
        (self.output / "mechanism-summary.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("mechanism-evidence"))
    p.add_argument("--driver", choices=["external", "managed"], default="external")
    p.add_argument("--operation", default="mechanism-v1")
    a = p.parse_args()
    c = Client(a.workspace)
    c.connect()
    result = MechanismBenchmark(c, a.driver, a.output, a.operation).run()
    print(
        json.dumps(
            {
                "experiment_id": result["cases"][0]["experiment_id"],
                "accepted": result["cases"][0]["final_accepted"],
            }
        )
    )


if __name__ == "__main__":
    main()

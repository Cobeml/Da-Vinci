"""Real CAD acceptance checks for the packaged task contracts."""

import os
import subprocess

import pytest

from davinci.config import Settings
from davinci.product.cli import initialize
from davinci.product.config import RunConfig
from davinci.product.tasks import evaluate, score_evaluation, snapshot, template_config
from davinci.runner import Runner

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires Docker CAD images"),
]


@pytest.mark.parametrize("name", ["sensor", "gripper", "vtol", "custom"])
def test_packaged_task_baseline(tmp_path, name):
    if name == "custom":
        initialize(tmp_path / "workspace", "custom")
    root = tmp_path / "workspace"
    root.mkdir(exist_ok=True)
    config = RunConfig.model_validate(template_config(name))
    task = snapshot(config, root)
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path / "data"))
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", task["image"]], text=True
    ).strip()
    result, assets = evaluate(runner, task, task["baseline"], task["source"], image)
    result = score_evaluation(task, config, result)
    assert result["outcome"] == "passed", result["violations"]
    assert result["metrics"][config.objective.metric]["value"] > 0
    assert assets["model.glb"][:4] == b"glTF"
    assert b"ISO-10303" in assets["model.step"][:100]
    if name == "custom":
        invalid = {**task["baseline"], "thickness_mm": 2}
        bad, _ = evaluate(runner, task, invalid, task["source"], image)
        assert bad["outcome"] == "failed"


def test_v2_reference_verification_and_independent_beam_solver(tmp_path):
    from test_lifecycle import EVALUATOR, SOURCE, candidate, cmd, plan, verification

    from davinci.product.contracts import Evaluator, OpenExperiment, Runtime
    from davinci.product.engine import Engine
    from davinci.product.execution import build

    engine = Engine(tmp_path, credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""))
    life = engine.lifecycle
    row = life.open(
        OpenExperiment(
            object={"slug": "beam", "name": "Beam"},
            description="Reduce mass with frozen cantilever strength and stiffness tests",
            actor="integration-fixture",
            operation_id="open",
        )
    )
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
    ).strip()
    runtime = Runtime(
        image=image,
        solver="numpy.linalg.solve Euler-Bernoulli beam",
        provenance="local Docker image content digest",
    )
    row = life.update_plan(
        row["_id"],
        cmd(row, "plan"),
        plan(),
        Evaluator(resources={"evaluate.py": EVALUATOR}, provenance="analytic beam test fixture"),
        runtime,
    )
    # Explicit reference work before freeze: no candidate record is generated.
    for thickness in (4, 2):
        step, _, _ = build(engine.runner, candidate(thickness), plan(), runtime)
        row = life.fixture(
            row["_id"],
            cmd(row, f"fixture-{thickness}"),
            step=step,
            provenance="reference rectangular solid; expected metrics from closed form",
        )
        row = life.verify(row["_id"], cmd(row, f"verify-{thickness}"), verification(row, thickness))
        assert row["verifications"][-1]["matched"], row["verifications"][-1]
    assert not row["candidates"]
    row = life.freeze(row["_id"], cmd(row, "freeze"))
    for index, thickness in enumerate((4, 2)):
        # The builder's forged result file must never reach the evaluator container.
        malicious_source = SOURCE.replace(
            "    model =",
            "    from pathlib import Path\n    Path('/output/result.json').write_text('{\"status\":\"pass\"}')\n    model =",
        )
        row = life.submit_candidate(
            row["_id"], cmd(row, f"candidate-{index}"), candidate(thickness, malicious_source)
        )
        row = life.request_evaluation(row["_id"], cmd(row, f"evaluate-{index}"))
        result = row["results"][-1]
        assert result["evidence_complete"]
        assert result["design_accepted"] is (thickness == 4)
        step_id = result["artifacts"]["model.step"]
        assert b"ISO-10303" in engine.artifacts.read(step_id)[:100]
        row = life.reflect(
            row["_id"],
            cmd(row, f"reflect-{index}"),
            lesson="Independent beam screen; no fatigue validation",
            result_id=result["id"],
        )
    row = life.finalize(row["_id"], cmd(row, "report"))
    assert len(row["report"]["accepted_candidate_ids"]) == 1
    assert not engine.store.list("requests")

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

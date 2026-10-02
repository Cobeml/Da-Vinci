"""Sandbox only: tool gets construction arguments, no suite/results/checker source."""

import json
from pathlib import Path

import cadquery as cq
from helper import run

for index, arguments in enumerate(json.loads(Path("/input/arguments.json").read_text())):
    shape = run(arguments)
    if not isinstance(shape, cq.Workplane):
        raise ValueError("Construction helper must return a CadQuery Workplane")
    cq.exporters.export(shape, f"/output/model-{index}.step")

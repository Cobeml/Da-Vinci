# Da Vinci user guide

Da Vinci is a Python package with a localhost interface for iterative CAD optimization. Define a task, objective, and constraints in YAML; inspect generated models and measured results; continue from an earlier design.

- [Install and run](quickstart.md)
- [YAML and workspace settings](configuration.md)
- [Using the workspace](workspace.md)
- [Custom engineering tasks](custom-tasks.md)
- [How improvement works](architecture.md)
- [MongoDB Atlas for Scalable Model Improvement](atlas.md)
- [Development and release](development.md)

The sensor mount, gripper, and VTOL templates are engineering examples with fixed geometry families and screening evaluators. A custom adapter can apply the workflow to other physical engineering tasks. Quantitative claims are limited by the adapter's physical model and tests.

# Da Vinci user guide

Da Vinci is a Python package with a localhost interface for iterative CAD engineering. An external coding agent or the built-in agent supplies reasoning; the same harness verifies and freezes tests, executes CAD and simulation, and preserves evidence. SQLite and local artifacts work without a cloud database.

## Choose your workflow

- **External agent:** your coding agent authors requirements, tests, CAD and reflections through public CLI/HTTP operations. Da Vinci needs no model API key. Start with [installation](quickstart.md), then the [external walkthrough](external-agents.md).
- **Built-in agent:** supply a description and configure model credentials on the server. The harness asks for missing engineering inputs and proceeds through verified tests and bounded iterations. See [managed requests](managed-requests.md).
- **Advanced tasks:** keep using [YAML and custom Python tasks](custom-tasks.md). Historical v1 runs retain their original evidence; they are not retroactively test-first validated.

Automatic request-to-test authoring currently supports rectangular cantilever analytic screening. Optional structural and mechanism adapters have separate, narrow validated scopes. The [capability matrix](capability-matrix.md) distinguishes implementation, executed checks and unavailable physics.

## Documentation

<!-- documentation-navigation -->
### Start here

- [Install and run](quickstart.md)
- [External coding agent · keyless](external-agents.md)
- [Built-in agent · start with a description](managed-requests.md)
- [Advanced YAML and custom tasks](custom-tasks.md)

### Workflow

- [How improvement works](architecture.md)
- [Requirements, verification and frozen tests](lifecycle.md)
- [Workspace, continuation and recovery](workspace.md)
- [Complete journeys and driver handoff](product-journeys.md)

### Simulation

- [Capabilities, resources and evidence](simulation-adapters.md)
- [Gmsh / CalculiX solid structures](structural-simulation.md)
- [MuJoCo rigid slider](mechanism-simulation.md)

### Learning and evidence

- [Scoped experience and retrieval](memory.md)
- [Tested, versioned CAD helpers](tool-learning.md)
- [Attributed measurements and calibration](measurements.md)
- [Benchmarks and limitations](methodology.md)
- [Capability and evidence matrix](capability-matrix.md)

### Operations

- [Workspace and run settings](configuration.md)
- [MongoDB Atlas for Scalable Model Improvement](atlas.md)
- [Development and release](development.md)

### Technical records

- [Historical MVP validation](validation.md)
- [Lifecycle implementation record](implementation-lifecycle.md)
- [External route implementation record](implementation-external.md)
- [Simulation implementation record](implementation-simulation.md)
- [Memory implementation record](implementation-memory.md)
- [Managed route implementation record](implementation-managed.md)
- [Product parity implementation record](implementation-product-parity.md)
- [Structural implementation record](implementation-structural.md)
- [Tool learning implementation record](implementation-tool-learning.md)
- [Methodology implementation record](implementation-methodology.md)
- [Mechanism implementation record](implementation-mechanism.md)
- [Website and documentation implementation record](implementation-website.md)
<!-- /documentation-navigation -->

No laboratory measurements or autonomous memory benefit are established by the new methodology fixtures. See [benchmark evidence and limits](methodology.md).

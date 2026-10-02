# Da Vinci user guide

Da Vinci is a Python package with a localhost interface for iterative CAD engineering. An external coding agent or the built-in agent supplies reasoning; the same harness verifies and freezes tests, executes CAD and simulation, and preserves evidence. SQLite and local artifacts work without a cloud database.

## Choose your workflow

- **External agent:** your coding agent authors requirements, tests, CAD and reflections through public CLI/HTTP operations. Da Vinci needs no model API key. Start with [installation](quickstart.md), then the [external walkthrough](external-agents.md).
- **Built-in agent:** supply a description and configure model credentials on the server. The harness asks for missing engineering inputs and proceeds through verified tests and bounded iterations. See [managed requests](managed-requests.md).
- **Advanced tasks:** keep using [YAML and custom Python tasks](custom-tasks.md). Historical v1 runs retain their original evidence; they are not retroactively test-first validated.

Automatic request-to-test authoring currently supports rectangular cantilever analytic screening. Optional structural and mechanism adapters have separate, narrow validated scopes. The [capability matrix](capability-matrix.md) distinguishes implementation, executed checks and unavailable physics.

## Documentation

<!-- documentation-navigation -->

No laboratory measurements or autonomous memory benefit are established by the new methodology fixtures. See [benchmark evidence and limits](methodology.md).

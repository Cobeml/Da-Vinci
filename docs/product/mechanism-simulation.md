# Optional MuJoCo rigid-slider simulation

`mujoco-slider` is a CPU adapter for a **two-body vertical carriage with an ideal prismatic guide and frictionless normal stop contact**. It measures rigid-body motion, actuation and contact under a declared scenario. It supplies no structural stress, deformation, fatigue, wear, thermal or fluid evidence. A lighter moving part may track better and still be structurally unsuitable.

## Install and discover

Use the normal installed package and workspace service. No MuJoCo Python dependency is added to the default host installation; the solver is in an explicitly installed Docker image.

```bash
davinci init slider-workspace --driver external --template custom
cd slider-workspace
davinci setup --template mujoco
davinci external adapters
davinci external schemas
davinci service ensure
python -m davinci.product.mechanism.walkthrough --workspace . --output mechanism-evidence
```

Setup first builds the existing CadQuery base and then `da-vinci-mujoco:local`. MuJoCo **3.4.0** and the tested additional dependency versions are pinned in `sandbox/Dockerfile.mujoco`; each experiment resolves the resulting image SHA-256 identity. The validated runtime is Linux x86-64 native CPU. No GPU, MJX, Warp, remote provisioning or browser rendering runtime is implied by discovery. Normal CPU/RAM/disk/time/artifact limits and cancellation apply.

Open the existing localhost UI at the workspace's configured port. The object gallery and experiment page display the assembly CAD, iterations, outcomes, coverage, capability limits and downloadable artifacts. The existing 3D viewer is a static CAD inspection view; simulated motion is recorded in CSV rather than a new playback UI. Discovery makes the adapter available to external/manual managed plans; automatic natural-language task authoring still has its existing narrower recipe coverage.

## Frozen public contract

The installed `SliderSettings` JSON schema defines fixed bodies, material assignments, body binding interfaces, frame convention, mass/inertia derivation, collision approximation, guide, actuator, contact, trajectories, timestep and convergence limits. It is nested in `test.fixed_inputs.mechanism`, separate from editable candidate parameters.

The assembly has exactly two valid separate STEP solids. A test-owned semantic region selects the base top; another selects the carriage bottom. Both must be horizontal, oriented, full rectangular faces with the declared location and extent. The host independently inspects the STEP and rejects missing/ambiguous selections. The solver reimports it and resolves each face to exactly one distinct solid. CAD labels, candidate hints and face indices are not trusted bindings.

The base must fill its box envelope. The carriage may have internal/top pockets while keeping a full rectangular bottom face. Its vertical swept envelope must fit inside the base footprint with a 1 mm margin, and the initial gap must be 5–50 mm. Body extents must be 0.5–500 mm. Sideways motion, oblique contact, multiple bodies/joints, through-holes in the contact plane, general concave contact and finite-guide compliance are unsupported.

Mass and center of mass come from actual CAD volume integrals and the frozen homogeneous density. The full COM inertia tensor comes from OpenCascade volume properties. Conversion is explicit: mm→m by 1e-3, volume by 1e-9 and the geometric inertia integral by 1e-15 before multiplication by kg/m³ density. Each body frame uses CAD world axes at its measured COM; the collision envelope has an explicit COM-relative offset. Compiled MuJoCo mass and reconstructed inertia are checked against these integrals. Independently specified box-subtraction references test volume, COM and inertia for the pocketed part. The reported `mass_g` metric is **moving carriage mass**, not total assembly mass.

The guide allows only world-z translation; rotation and horizontal translation are ideally constrained. There is no guide damping, friction, compliance or actuator electrical model. The motor applies a clipped gravity-compensated PD force: `clip(m*g + kp*(target-q) - kd*qdot, 0, force_limit)`. The target ramps linearly then holds. A separate settle scenario resets the original CAD pose/zero velocity, turns actuation off and lets gravity bring the carriage onto the stop. The body geometry, material density, controller, scenarios, loads and numerical requirements are frozen together.

Collision geometry uses axis-aligned box envelopes. Pockets are filled for collision only; their removed volume still changes mass/COM/inertia. This approximation is restricted to the verified flat-bottom vertical contact path, where the envelope bottom coincides with the actual contact face. It is not an approximation for objects entering cavities. Contact is frictionless (`condim=1`, zero friction) with fixed `solref=(0.01,1)` and `solimp=(0.95,0.99,0.001)`. These parameters describe numerical soft contact, not measured surface properties or restitution.

MuJoCo documents local frames, explicit inertial parameters, joint DOFs and soft-contact modeling in its [3.4.0 modeling guide](https://mujoco.readthedocs.io/en/3.4.0/modeling.html) and [MJCF XML reference](https://mujoco.readthedocs.io/en/3.4.0/XMLreference.html). The adapter uses the native bindings described in the [official Python documentation](https://mujoco.readthedocs.io/en/3.4.0/python.html). It does not send candidate-authored MJCF or Python evaluators to the solver; only the pinned packaged adapter writes the deck.

## Independent checks, accuracy and resources

Before a suite can freeze, the walkthrough verifies deliberately passing/failing reference CAD against independent nominal box masses and stationary force-balance predictions. Candidate evaluation additionally requires:

- Positive physical mass/inertia, valid two-body topology and independent binding checks. The compiled model must have one coordinate, one velocity and one actuator.
- Constant-force motion against `q=F*t²/(2m)`. The reference tolerance is `0.51*a*T*dt + 1e-12 m`, covering the known first-order time-discretization offset rather than an arbitrary percentage.
- Kinetic-energy conservation in an unforced, gravity-free, contact-free translation reference (relative tolerance 1e-9 or 1e-12 J). Energy conservation is not asserted for actuated or dissipative contact trajectories.
- Settled normal force balancing weight within the larger of 0.001 N or 1%, vertical speed below 0.0001 m/s, and no positive stop gap above 0.0001 m. Forces are summed over all active normal contacts.
- Three timesteps, each half the previous. Both successive comparisons must meet 0.1 mm sampled-trajectory position and 0.002 N peak-actuation differences. The example starts at **0.25 ms**, then 0.125 and 0.0625 ms. A 1 ms start demonstrably fails the same position contract and is retained as a numerical-failure test.

The final acceptance metrics are carriage mass, final lift tracking error, maximum penetration during the final 0.2 s of settling, settled mean-force equilibrium residual and peak actuation. Contact impulses/impact peak forces are **not** validated acceptance quantities. CSV samples preserve time, position, velocity, actuation, summed normal force and penetration; they are bounded to roughly 2000 rows per trajectory. Timestep checks compare these sampled trajectories, not a rigorous continuous-time error norm.

The example declares a nominal model allowance of 0.1 mm for position/penetration and 0.001 N for forces; it is not calibrated manufacturing/contact uncertainty or a probabilistic bound. Hard limits account for those allowances through the existing score service. Missing convergence, numerical warnings, incomplete artifacts or invalid bindings cannot produce acceptance. No cheaper physics is substituted.

Preflight estimates depend on duration/timestep: two scenarios and three levels require about `14*duration/dt` steps, plus references/CAD import. The adapter rejects understated estimates and workloads above 80,000 finest-level steps per scenario. Initial budgets are one CPU core, 768 MB estimated RAM, 32 MB disk and a conservative step-throughput time estimate. Actual steps, elapsed time and process peak RSS are retained in `solver-resources.json`, separate from host-owned resource limits/logs. Estimates do not prove adequacy.

## Reproduce both public routes

From the repository, this uses the existing service/worker with an explicit deterministic managed fixture:

```bash
uv run davinci setup --template mujoco
uv run python scripts/run_methodology_benchmark.py --suite mechanism \
  --workspace runtime/mechanism-new --output runtime/mechanism-new-results
uv run python scripts/required_native.py --mechanism
```

The benchmark runs external then managed against the same physical contract. Each route verifies references, freezes, submits a failing solid carriage, two invalid-binding candidates, a pocketed revision, and a fresh repeated final candidate/evaluation. An explicitly requested fatigue test remains unavailable without candidate generation. Final reports and source, STEP/GLB, MJCF, material attribution, assembly bindings, trajectories, numerical references, convergence, uncertainty, timing and logs stay in the normal artifact store. XML artifacts download as attachments; they are not rendered in the trusted browser origin.

For the installed managed-fixture journey, start a dedicated fixture workspace in terminal one:

```bash
python -m davinci.product.benchmark_server --fixture mechanism --workspace ./fixture-workspace
```

Then, in terminal two:

```bash
python -m davinci.product.mechanism.walkthrough --workspace ./fixture-workspace \
  --driver managed --output ./managed-mechanism-evidence
```

The same walkthrough with `--driver external` works with the ordinary `davinci service ensure` service and no credentials. The fixture server is solely an explicit test configuration of the existing Engine; it never calls the generation/embedding API, even if a key exists in the environment. Use a new workspace or unique operation ID for a new campaign. Inspect partial jobs before resuming; never delete evidence to bypass ownership/revision guards.

The recorded demonstration reduced moving mass from 64.8 g to 30.5856 g (52.8%) while changing a failed nominal lift into a pass under the same actuator limit. This improvement comes from scripted proposals and has no structural-strength implication.

See the [implementation/evidence record](implementation-mechanism.md) for actual results and tested commands. Scripted proposals and deterministic reasoning prove lifecycle behavior and adapter evidence within this scope, not autonomous engineering quality or physical laboratory validation. Fluid, fatigue, thermal and other new domain packages are deferred until they have their own concrete task, adapter scope and independent reference suite.

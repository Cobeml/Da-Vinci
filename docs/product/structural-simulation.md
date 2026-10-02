# Optional Gmsh / CalculiX static solids

`calculix-static` is an optional, CPU-only simulation adapter in `davinci.product.structural`. It uses the existing experiment lifecycle, job worker, immutable plans, sandbox, artifact manifest, local SQLite storage and optional Atlas/GridFS. Discovery and plan authoring import no Gmsh, CalculiX or NumPy on the host. No provider, model credential, embedding or cloud service is needed for external execution.

## Tested runtime and official references

The runtime uses **Gmsh 4.15.2**, **CalculiX 2.23**, and the serial **SPOOLES 2.2** solver on Linux amd64. `sandbox/Dockerfile.structural` extends the repository's CAD image, whose Dockerfile/base digest and Python dependency lock remain unchanged. CalculiX and SPOOLES source downloads are SHA-256 pinned; Gmsh is version pinned. Every experiment resolves the finished image to its immutable image ID and retains it with the software probe and execution-source identity. OS packages follow the base distribution at build time, so independently rebuilt image IDs can differ; there is no claim of bit-for-bit reproducible builds.

Official documentation used for this implementation:

- [Gmsh reference manual](https://gmsh.info/doc/texinfo/): OpenCASCADE STEP import, `Mesh.SecondOrderLinear`, tetrahedron/triangle ordering, `getElementQualities` and mesh API. The adapter checks geometric midpoint positions after converting the Gmsh tetra10 ordering to CalculiX ordering.
- [CalculiX official distribution and documentation](https://www.dhondt.de/), specifically the [2.23 HTML manual archive](https://www.dhondt.de/ccx_2.23.htm.tar.bz2): C3D10 (four integration points), `*STATIC`, `*ELASTIC`, `*CLOAD`, `*NODE PRINT` and `*EL PRINT`. Nodal RF includes external forces; the adapter reads reactions only on clamped nodes with no applied loads.
- [CalculiX 2.23 installation instructions](https://www.dhondt.de/ccx_2.23.README.INSTALL) and [official source](https://www.dhondt.de/ccx_2.23.src.tar.bz2). The provided binary requires obsolete `libgfortran.so.4`; setup compiles source against the current Fortran runtime instead. Build flags and the upstream-documented SPOOLES Tree makefile correction are explicit in the Dockerfile.
- [SPOOLES official distribution](https://www.netlib.org/linalg/spooles/spooles.2.2.html): serial sparse factorization. GPU/remote execution is not required or provisioned.

## Exact supported scope

- One valid, positive-volume, connected solid imported from the **actual exported STEP**. Parts can have holes, ribs, tapers, changes of section and fillets; no comparison with a reconstructed baseline is used. Features must be resolvable by the declared mesh and pass topology, quality, volume and convergence checks. Assemblies, touching-only pieces and disconnected meshes are rejected.
- One homogeneous, isotropic, linear-elastic material. Positive Young's modulus and density; Poisson ratio from 0 through 0.45. Material properties and their source are required in the frozen plan. No plasticity, near-incompressibility, anisotropy, thermal effects, fatigue, contact, dynamics, fracture or buckling qualification is implemented.
- Full translational clamps on one or more independently resolved **planar** faces, plus one disjoint planar face carrying a specified uniform resultant force in global XYZ. No point forces, applied moments, gravity, displacement-controlled loading, bolt/contact compliance or partial/sliding supports. Each load case is a separate declared test; there is no automatic superposition or load-envelope substitution.
- Straight-sided quadratic **C3D10** tetrahedra with positive Jacobians, checked midpoint ordering, minimum signed inverse-condition quality and face-connected topology. Curved boundaries are faceted; geometric volume error relative to the CAD is bounded and retained.
- CAD and solver lengths are explicitly mm, forces N, stress/modulus MPa. Material inputs can use supported convertible units. Density converts from g/mm³ to tonne/mm³ for the N-mm-s solver system. Mass is measured CAD volume times density; solver mass and mesh volume are independently compared to mesh geometry and density. Declared candidate thickness, volume, material hints or scores do not supply evidence.
- The declared small-displacement/span and maximum principal-strain limits are checked from the computed field. Exceeding them returns unsupported physics, not acceptance under a nonlinear model. Their defaults are 2% of the maximum bounding-box span and 1% strain; a task may tighten them. These checks do not establish resistance to buckling.

## Frozen setup and semantic binding

Use `SimulationSpec.adapter="calculix-static"`, `fidelity="converged_linear_solid"`, `material_model="linear_isotropic"`, and explicitly requested `mass` / `linear_static` phenomena. All five evidence categories are required. The discoverable `StructuralSettings` JSON schema defines `test.fixed_inputs.structural`; unknown fields fail local validation.

The setup names the material, clamp interfaces, load interface, load-case ID, stress gauge, mesh policy, equilibrium tolerance, applicability limits and uncertainty allowance. The load case must provide the dimensioned `force_x`, `force_y`, `force_z` quantities. The plan retains material provenance, requirements, independent verification records, hard thresholds and design variables separately.

Before meshing, a separate trusted CadQuery/OCP inspection checks interface position, outward orientation, extent and expected selection count. Gmsh reimport must agree with those geometric descriptors and with the independently measured solid volume. Mesh boundary triangles are checked against tetrahedral adjacency, actual outward normals, area and area-weighted centers. CAD face indices and builder labels are never carried forward as identities. Missing/ambiguous regions or overlapping load/clamp nodes are invalid setup.

The reference cases validate rectangular load/clamp faces. Curved outlines or holes on those faces can fail the strict area check when faceted; supporting such interfaces requires applicable reference verification and sufficient geometric resolution. Varied features elsewhere in the solid do not need to match a baseline.

Uniform traction is integrated with quadratic triangle shape functions: zero corner weights and area/3 on each midside node. The assembled nodal loads must reproduce the prescribed resultant and moment. The constrained rigid-body matrix must have rank six, and the volume mesh must be connected through shared faces. Actual reaction force and moment must balance the load within the frozen tolerance (default 0.1%).

The host selects the trusted structural runner and deck writer. `Evaluator.resources` retains a provenance placeholder to preserve the shared contract, but its executable content is **not run** for this adapter. Neither candidate code nor authored evaluator code can replace the structural measurements, solver deck, settings or host scoring.

## Stress, convergence and uncertainty

Three acceptance metrics are supported:

| Metric | Definition |
| --- | --- |
| `mass_g` | Independently measured CAD volume × supplied homogeneous density |
| `load_displacement_mm` | Area-weighted loaded-face displacement projected along the resultant force |
| `gauge_von_mises_mpa` | Volume-weighted mean von Mises stress at integration points within a predeclared spatial box |

The stress box and its physical justification precede candidate generation. The **whole box** must remain outside a declared exclusion band around every idealized support/load plane. Peaks are retained in the convergence record and full stress field, but they are not silently discarded from an otherwise peak-stress criterion. This adapter does not offer a peak-yield/fatigue criterion. A gauge-mean pass cannot establish the strength of a notch, rib termination, clamp or load edge.

Refinement uses the frozen initial size, factor, number of levels, quality and node/element limits. At least three levels with increasing element/node counts are needed; repeated identical meshes cannot establish convergence. **Two consecutive changes** must meet the declared relative/absolute tolerance for displacement, gauge stress and sampled gauge volume. Reported numerical error is twice the maximum of the two changes. This is an empirical convergence diagnostic, not a Richardson extrapolation or guaranteed error bound. Accuracy fields can reject a result even after relative convergence. Exhausted refinement returns numerical failure/incomplete evidence; it never selects the most favorable unconverged mesh.

The uncertainty field is a task-declared allowance with a required explanation; the bracket example uses 5% for nominal-model quantities. It is not a probabilistic confidence interval or a bound on manufacturing variability, actual mounting stiffness or uncertain loads. Host acceptance uses conservative value + numerical-error + uncertainty for upper limits. Hard requirements, optional objective targets and search stopping remain separate.

## Resources and evidence

The same network-disabled, unprivileged, read-only Docker sandbox and existing CPU/RAM/time/compute/output limits apply. Each mesh archives actual element/node counts and quality, an updated topology-dependent memory/time estimate, observed wall time and separate process/solver peak RSS values. These estimates are explicitly uncertain; successful resource admission is not proof of adequate resolution. The solver scratch area is bounded tmpfs. Stable output files are copied to the flat artifact directory; this avoids races with the runner's path/symlink checks.

Evidence includes source and STEP, physical region definitions, independent and mesh bindings, each `.msh` and `.inp`, solver `.dat`, displacement/stress CSV fields, Gmsh/solver logs, nominal material provenance and unit conversions, resource observations, convergence and uncertainty. Existing manifests retain checksums and suite/evaluator/runtime/source identities. Failures preserve available bounded evidence; cancellation during a solve can retain the CAD/mesh/deck/log without a completed field table. Corruption, artifact omissions, cancellation and unavailable physics cannot produce acceptance.

## Reference checks and varied-feature example

References are specified independently of solver output:

- Uniform axial extension of a prismatic solid with Poisson ratio zero: `u=FL/(EA)`, stress `F/A`, mass `rho*V`. The 0.1% comparison tolerance covers text-output precision and numerical operations while being much smaller than the design margins. Zero Poisson ratio removes the clamped-end lateral-contraction boundary layer and produces an exact constant-strain continuum solution.
- 60 × 20 mm cantilevers, thickness 4 and 8 mm, transverse 20 N. Displacement reference is Euler–Bernoulli bending plus the Timoshenko shear term with rectangular-section factor 5/6. Tolerances are 6% for displacement and 15% for fixed-gauge mean bending stress. These deliberately allow the differences between beam theory and a 3D elastic clamp/traction solution, including Poisson/end effects and shear in von Mises stress; they are not solver error guarantees or acceptance-limit changes. Exact prismatic mass tolerance is 1e-5 g.
- The thin beam physically fails the same 0.1 mm deflection limit that the thick reference passes. Positive and negative references must verify before suite freeze.
- A nontrivial shelf bracket has a 60 × 20 × 4 mm shelf, 30 mm mounting wall and two through holes. Its revision adds two tapered ribs; shelf thickness, holes, mounting plane, load, material, acceptance limits, gauge and refinement policy remain fixed. The adapter evaluates the new STEP directly.

The development four-level bracket study correctly failed convergence. The verified example declares a five-level budget before freeze, preserving the 3.5% two-step convergence rule and all engineering limits. See the [implementation record](implementation-structural.md) for measured results and executed checks. Neither reference agreement nor bracket acceptance is general manufacturing or real-world certification.

## Installed use and both drivers

From an installed wheel (no host solver extras):

```bash
davinci init structural-workspace --driver external --template custom
cd structural-workspace
davinci setup --template structural
davinci external adapters
davinci service ensure
python -m davinci.product.structural.walkthrough --workspace . --report structural-report.json
```

The walkthrough uses public HTTP operations, builds reference-only fixtures, verifies the two analytical comparisons, freezes, evaluates a failing bracket and supported ribbed revision, records hypotheses and exports the report. The shared browser displays both models, actual outcomes, uncertainty, capabilities and artifact downloads. Inspect/download individual evidence with the existing external CLI. Cancellation/resume, linked evaluator corrections and final report checks use the existing lifecycle.

For another geometry, an external agent authors its own plan/source bundles using the same public operations and `StructuralSettings`; it must independently verify applicable references before freeze. Do not edit the benchmark plan after seeing a candidate result. Fixes to frozen evaluator/runtime/setup create linked revisions and require new verification/evidence.

Native tests also run public managed author/proposal/reflection operations using a deterministic provider, independently verify/freeze the same physical contract and evaluate both bracket designs. Independently verified suites have different verification/probe provenance and suite IDs even with matching plan/evaluator/runtime identities. A second check continues the external run with the managed automatic adoption workflow, preserving the exact suite ID, reevaluating the failing seed, proposing the ribbed design and performing a final independent rerun. Managed and external metrics must agree within 1e-7 absolute or 1e-8 relative for identical source, suite and runtime. A model fixture is orchestration evidence; all reported physics comes from real meshing/solving. No paid model call is needed for these tests.

The current automatic natural-language authoring recipe remains the analytic rectangular beam. This package does not claim to automatically turn an arbitrary structural description into verified boundary conditions. An external author may hand a verified frozen structural suite to the existing managed adoption workflow for design iteration, with configured server-side credentials; threshold/setup changes remain prohibited. No live-model capability claim is made by the fixture test.

From a checkout:

```bash
uv run pytest tests/product/test_structural.py -m 'not integration' -q
uv run davinci setup --template structural
uv run python scripts/required_native.py --structural
```

The structural CI job explicitly builds this optional runtime and fails if required tests or images are missing or skipped. Default host installation and fast tests do not install a solver. Legacy screen formulas, archived studies and historical results remain unchanged. The new trusted adapter sources change execution identity; old frozen v2 suites stay inspectable but need linked revisions to execute under changed code. No database migration is required.

"""Trusted sandbox-only Gmsh/CalculiX execution. Never imports candidate/evaluator code."""

import csv
import itertools
import json
import math
import os
import resource
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import gmsh
import numpy as np

OUT = Path("/output")
# Gmsh tetra10 edges: 12,23,31,14,34,24; CCX: 12,23,31,14,24,34.
CCX_ORDER = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]
CCX_EDGES = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]


class Rejected(Exception):
    def __init__(self, status, reason, message):
        self.status, self.reason = status, reason
        super().__init__(message)


def require(condition, message, status="invalid_setup", reason="invalid_geometry"):
    if not condition:
        raise Rejected(status, reason, message)


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, allow_nan=False))


def faces_for_interfaces(request):
    """Re-resolve current OCC faces using independent prechecked geometric descriptors."""
    selected = {}
    for interface in request["interfaces"]:
        name = interface["id"]
        target = request["validated_bindings"][name]["matches"][0]
        matches = []
        for _, tag in gmsh.model.getEntities(2):
            if gmsh.model.getType(2, tag) != "Plane":
                continue
            center = np.array(gmsh.model.occ.getCenterOfMass(2, tag))
            bb = np.array(gmsh.model.getBoundingBox(2, tag))
            ext = bb[3:] - bb[:3]
            area = gmsh.model.occ.getMass(2, tag)
            tol = interface["tolerance"] + 1e-6
            if (
                np.all(np.abs(center - target["center"]) <= tol)
                and np.all(np.abs(ext - target["extent"]) <= 2 * tol)
                and abs(area - target["area"]) <= max(1e-6, area * 1e-7)
            ):
                matches.append(tag)
        require(len(matches) == 1, f"{name}: missing or ambiguous reimported face", reason="invalid_binding")
        selected[name] = matches[0]
    require(
        len(set(selected.values())) == len(selected), "Physical interfaces overlap", reason="invalid_binding"
    )
    return selected


def mesh(request, level, h, selected, cad_volume):
    settings = request["structural"]["settings"]
    policy = settings["mesh"]
    gmsh.model.mesh.clear()
    gmsh.option.setNumber("Mesh.MeshSizeMin", h)
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 16)
    gmsh.option.setNumber("Mesh.ElementOrder", 1)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.mesh.generate(3)
    gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
    gmsh.model.mesh.setOrder(2)
    gmsh.write(str(OUT / f"level-{level}.msh"))
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    coords = np.array(coords).reshape(-1, 3)
    index = {int(tag): i for i, tag in enumerate(node_tags)}
    types, tags, nodes = gmsh.model.mesh.getElements(3)
    require(list(types) == [11], "Only Gmsh tetra10 elements supported")
    elements = np.array(nodes[0], dtype=int).reshape(-1, 10)[:, CCX_ORDER]
    element_ids = np.array(tags[0], dtype=int)
    require(
        len(coords) <= policy["max_nodes"] and len(elements) <= policy["max_elements"],
        "Refined mesh exceeds declared node/element budget",
        "not_run",
        "resource_exhaustion",
    )
    xyz = coords[np.array([[index[int(n)] for n in e] for e in elements])]
    determinants = np.linalg.det(np.stack([xyz[:, j] - xyz[:, 0] for j in (1, 2, 3)], axis=2))
    require(np.all(determinants > 1e-12), "Inverted or degenerate tetrahedron")
    for i, (a, b) in enumerate(CCX_EDGES):
        require(
            np.allclose(xyz[:, i + 4], (xyz[:, a] + xyz[:, b]) / 2, rtol=0, atol=1e-7),
            "C3D10 edge ordering or straight-edge midpoint mismatch",
        )
    quality = gmsh.model.mesh.getElementQualities(element_ids, "minSICN")
    require(
        min(quality) >= policy["min_quality"],
        "Mesh quality below frozen threshold",
        "numerical_failure",
        "missing_evidence",
    )
    volumes = determinants / 6
    volume_error = abs(float(sum(volumes)) - cad_volume) / cad_volume
    require(
        volume_error <= policy["max_volume_error"],
        "Mesh volume inconsistent with CAD volume",
        "numerical_failure",
        "missing_evidence",
    )
    # Connectivity by shared faces, not merely coincident points/edges.
    boundaries, adjacent = {}, [[] for _ in elements]
    for i, e in enumerate(elements):
        for opposite in range(4):
            key = tuple(sorted(int(e[k]) for k in range(4) if k != opposite))
            boundaries.setdefault(key, []).append((i, int(e[opposite])))
    for owners in boundaries.values():
        require(len(owners) <= 2, "Nonmanifold tetrahedral mesh")
        if len(owners) == 2:
            a, b = owners[0][0], owners[1][0]
            adjacent[a].append(b)
            adjacent[b].append(a)
    visited, todo = set(), [0]
    while todo:
        i = todo.pop()
        if i not in visited:
            visited.add(i)
            todo.extend(j for j in adjacent[i] if j not in visited)
    require(len(visited) == len(elements), "Mesh has disconnected components")
    used = {int(n) for e in elements for n in e}
    require(used == set(index), "Unconnected nodes in mesh")
    bound, weights, load_area = {}, {}, 0.0
    interfaces = {i["id"]: i for i in request["interfaces"]}
    for name, tag in selected.items():
        ts, _, ns = gmsh.model.mesh.getElements(2, tag)
        require(list(ts) == [9], "Interface must mesh into quadratic triangles", reason="invalid_binding")
        triangles = np.array(ns[0], dtype=int).reshape(-1, 6)
        face_nodes = set()
        normal = np.array(interfaces[name]["region"]["normal"], float)
        normal /= np.linalg.norm(normal)
        areas, centers = [], []
        for tri in triangles:
            points = coords[[index[int(n)] for n in tri[:3]]]
            key = tuple(sorted(int(n) for n in tri[:3]))
            owners = boundaries.get(key, [])
            require(len(owners) == 1, "Selected interface is not a boundary", reason="invalid_binding")
            n = np.cross(points[1] - points[0], points[2] - points[0])
            area = np.linalg.norm(n) / 2
            require(area > 1e-12, "Degenerate load/support triangle", reason="invalid_binding")
            if np.dot(n, coords[index[owners[0][1]]] - points[0]) > 0:
                n = -n
            require(
                float(np.dot(n / np.linalg.norm(n), normal))
                >= math.cos(math.radians(interfaces[name]["region"]["normal_tolerance_degrees"])),
                "Selected face has wrong outward orientation",
                reason="invalid_binding",
            )
            for k, (a, b) in enumerate([(0, 1), (1, 2), (2, 0)]):
                require(
                    np.allclose(coords[index[int(tri[3 + k])]], (points[a] + points[b]) / 2, atol=1e-7),
                    "Triangle6 node ordering invalid",
                )
            areas.append(area)
            centers.append(points.mean(axis=0))
            face_nodes.update(int(n) for n in tri)
            if name == settings["load_interface"]:
                # Exact integral of quadratic triangle shape functions: corners=0, edges=A/3.
                for node in tri[3:]:
                    weights[int(node)] = weights.get(int(node), 0.0) + area / 3
        total = float(sum(areas))
        expected = request["validated_bindings"][name]["matches"][0]
        require(
            abs(total - expected["area"]) <= total * 1e-5,
            "Interface mesh area mismatch",
            reason="invalid_binding",
        )
        center = np.average(centers, axis=0, weights=areas)
        require(
            np.allclose(center, expected["center"], rtol=0, atol=1e-5),
            "Interface mesh location mismatch",
            reason="invalid_binding",
        )
        bound[name] = {
            "nodes": sorted(face_nodes),
            "area_mm2": total,
            "center_mm": center.tolist(),
            "normal": normal.tolist(),
        }
        if name == settings["load_interface"]:
            load_area = total
    clamps = set(n for name in settings["clamped_interfaces"] for n in bound[name]["nodes"])
    require(
        not clamps.intersection(bound[settings["load_interface"]]["nodes"]),
        "Load and clamp share nodes",
        reason="invalid_binding",
    )
    # Rank of constrained rigid-body displacement matrix must be six.
    origin = coords.mean(axis=0)
    span = max(np.ptp(coords, axis=0))
    rigid = []
    for n in sorted(clamps):
        x, y, z = (coords[index[n]] - origin) / span
        rigid.extend([[1, 0, 0, 0, z, -y], [0, 1, 0, -z, 0, x], [0, 0, 1, y, -x, 0]])
    require(
        np.linalg.matrix_rank(rigid, tol=1e-9) == 6, "Unrestrained rigid body mode", reason="invalid_binding"
    )
    force = np.array(request["structural"]["force_n"])
    loads = {n: force * w / load_area for n, w in weights.items()}
    resultant = sum(loads.values())
    moment = sum(np.cross(coords[index[n]], f) for n, f in loads.items())
    expected_moment = np.cross(bound[settings["load_interface"]]["center_mm"], force)
    require(
        np.allclose(resultant, force, atol=1e-8, rtol=1e-9)
        and np.allclose(moment, expected_moment, atol=1e-7, rtol=1e-9),
        "Equivalent traction does not preserve total force/moment",
        reason="invalid_binding",
    )
    gauge = settings["stress_region"]
    # Entire fixed gauge box must be separated from each idealized BC plane.
    corners = np.array(list(itertools.product(*zip(gauge["lower_mm"], gauge["upper_mm"]))))
    for face in bound.values():
        distances = (corners - np.array(face["center_mm"])) @ np.array(face["normal"])
        require(
            not (min(distances) <= 0 <= max(distances))
            and min(abs(distances)) >= gauge["exclusion_distance_mm"],
            "Stress gauge intersects the declared support/load exclusion band",
            reason="invalid_binding",
        )
    write(
        f"level-{level}-bindings.json",
        {
            "regions": bound,
            "rigid_body_rank": 6,
            "force_n": resultant.tolist(),
            "moment_n_mm": moment.tolist(),
            "consistent_triangle_loads": True,
        },
    )
    stats = {
        "level": level,
        "size_mm": h,
        "nodes": len(coords),
        "elements": len(elements),
        "min_quality": float(min(quality)),
        "mesh_volume_mm3": float(sum(volumes)),
        "cad_volume_mm3": cad_volume,
        "volume_relative_error": volume_error,
        "components": 1,
    }
    # Empirical provisioning estimate, NOT a solver adequacy proof. Hard limits remain enforced externally.
    stats["estimated_memory_mb"] = 256 + len(coords) * 0.03 + len(elements) * 0.01
    stats["estimated_seconds"] = 2 + len(coords) ** 1.4 / 80000
    stats["estimate_uncertainty"] = (
        "SPOOLES fill depends on topology; estimate may be low by several-fold; cgroup remains authoritative"
    )
    write(f"level-{level}-resources.json", stats)
    require(
        stats["estimated_memory_mb"] <= request["runtime_limits"]["memory_gb"] * 1024,
        "Post-mesh RAM estimate exceeds job limit",
        "not_run",
        "resource_exhaustion",
    )
    return node_tags, coords, index, elements, element_ids, volumes, clamps, loads, weights, load_area, stats


def deck(request, level, data):
    tags, xyz, index, elements, ids, volumes, clamps, loads, weights, area, stats = data
    mat = request["structural"]["material"]
    lines = ["*HEADING", "Da Vinci trusted linear elastic static solid", "*NODE,NSET=ALLN"]
    lines += [f"{int(n)}," + ",".join(f"{v:.12g}" for v in p) for n, p in zip(tags, xyz)]
    lines += ["*ELEMENT,TYPE=C3D10,ELSET=SOLID"]
    lines += [f"{int(e)}," + ",".join(str(int(n)) for n in nodes) for e, nodes in zip(ids, elements)]
    lines += ["*NSET,NSET=CLAMP"]
    clamp = sorted(clamps)
    lines += [",".join(str(n) for n in clamp[i : i + 12]) for i in range(0, len(clamp), 12)]
    lines += [
        "*MATERIAL,NAME=MAT",
        "*ELASTIC",
        f"{mat['young_mpa']:.12g},{mat['poisson']:.12g}",
        "*DENSITY",
        f"{mat['density_g_mm3'] / 1e6:.12g}",
        "*SOLID SECTION,ELSET=SOLID,MATERIAL=MAT",
        "*BOUNDARY",
        "CLAMP,1,3",
        "*STEP",
        "*STATIC,SOLVER=SPOOLES",
        "*CLOAD",
    ]
    lines += [f"{n},{j + 1},{f:.12g}" for n, force in sorted(loads.items()) for j, f in enumerate(force) if f]
    lines += [
        "*NODE PRINT,NSET=ALLN,GLOBAL=YES",
        "U",
        "*NODE PRINT,NSET=CLAMP,GLOBAL=YES",
        "RF",
        "*EL PRINT,ELSET=SOLID,GLOBAL=YES",
        "S,E,COORD,EVOL,EMAS",
        "*END STEP",
    ]
    path = OUT / f"level-{level}.inp"
    path.write_text("\n".join(lines) + "\n")
    return path


def dat_tables(path):
    tables, active = {}, None
    headers = {
        "displacements": "u",
        "forces": "rf",
        "stresses": "s",
        "strains": "e",
        "global coordinates": "coord",
        "volume": "volume",
        "mass": "mass",
    }
    for line in path.read_text().splitlines():
        text = line.strip().lower()
        hit = next((v for k, v in headers.items() if text.startswith(k + " (")), None)
        if hit:
            active = hit
            tables.setdefault(hit, [])
        elif active and text:
            values = text.split()
            if values[0].isdigit():
                tables[active].append([float(v.replace("d", "e")) for v in values])
            elif not text.startswith(("node", "element", "integ")):
                active = None
    return {k: np.array(v) for k, v in tables.items()}


def results(request, data, tables, level):
    tags, xyz, index, elements, ids, volumes, clamps, loads, weights, area, stats = data
    settings = request["structural"]["settings"]
    require(
        set(tables) == {"u", "rf", "s", "e", "coord", "volume", "mass"},
        "Missing solver result tables",
        "numerical_failure",
        "missing_evidence",
    )
    require(
        all(np.isfinite(t).all() for t in tables.values()),
        "Nonfinite solver result",
        "numerical_failure",
        "solver_error",
    )
    for k, width, count in [
        ("u", 4, len(tags)),
        ("rf", 4, len(clamps)),
        ("s", 8, 4 * len(ids)),
        ("e", 8, 4 * len(ids)),
        ("coord", 5, 4 * len(ids)),
        ("volume", 2, len(ids)),
        ("mass", 8, len(ids)),
    ]:
        require(
            tables[k].shape == (count, width),
            f"Incomplete {k} table",
            "numerical_failure",
            "missing_evidence",
        )
    expected_volumes = dict(zip((int(e) for e in ids), volumes))
    for key in ("mass", "volume"):
        require(
            {int(row[0]) for row in tables[key]} == set(expected_volumes),
            "Solver mass/volume element identities incomplete",
            "numerical_failure",
            "missing_evidence",
        )
    for row in tables["volume"]:
        require(
            int(row[0]) in expected_volumes
            and np.isclose(row[1], expected_volumes[int(row[0])], rtol=2e-6, atol=1e-9),
            "Solver volume differs from independently computed tetrahedron volume",
            "numerical_failure",
            "solver_error",
        )
    solver_mass_g = float(sum(tables["mass"][:, 1])) * 1e6
    expected_mass_g = float(sum(volumes)) * request["structural"]["material"]["density_g_mm3"]
    require(
        np.isclose(solver_mass_g, expected_mass_g, rtol=2e-6, atol=1e-8),
        "Solver mass/density inconsistent with meshed STEP",
        "numerical_failure",
        "solver_error",
    )
    stats["solver_mass_g"] = solver_mass_g
    u = {int(t[0]): t[1:] for t in tables["u"]}
    reactions = {int(t[0]): t[1:] for t in tables["rf"]}
    require(
        set(u) == set(index) and set(reactions) == clamps,
        "Solver node identities differ",
        "numerical_failure",
        "missing_evidence",
    )
    require(
        max(np.linalg.norm(u[n]) for n in clamps) < 1e-10,
        "Prescribed clamps violated",
        "numerical_failure",
        "solver_error",
    )
    applied = sum(loads.values())
    react = sum(reactions.values())
    applied_m = sum(np.cross(xyz[index[n]], f) for n, f in loads.items())
    react_m = sum(np.cross(xyz[index[n]], f) for n, f in reactions.items())
    span = max(np.ptp(xyz, axis=0))
    residual = np.linalg.norm(react + applied) / np.linalg.norm(applied)
    moment_residual = np.linalg.norm(react_m + applied_m) / (np.linalg.norm(applied) * span)
    require(
        max(residual, moment_residual) <= settings["equilibrium_tolerance"],
        "Force/moment reaction balance failed",
        "numerical_failure",
        "solver_error",
    )
    keys = [(int(e), ip) for e in ids for ip in range(1, 5)]
    expected = set(keys)
    rows = {}
    for k in ("s", "e", "coord"):
        rows[k] = {(int(t[0]), int(t[1])): t[2:] for t in tables[k]}
        require(
            set(rows[k]) == expected,
            "Integration point identities incomplete",
            "numerical_failure",
            "missing_evidence",
        )
    stress = np.array([rows["s"][k] for k in keys])
    strain = np.array([rows["e"][k] for k in keys])
    points = np.array([rows["coord"][k] for k in keys])
    # Small-strain gate uses principal strains, not a selected component.
    tensors = np.zeros((len(strain), 3, 3))
    tensors[:, 0, 0], tensors[:, 1, 1], tensors[:, 2, 2] = strain[:, :3].T
    for j, (a, b) in enumerate([(0, 1), (0, 2), (1, 2)]):
        tensors[:, a, b] = tensors[:, b, a] = strain[:, 3 + j]
    max_strain = float(np.max(np.abs(np.linalg.eigvalsh(tensors))))
    max_displacement = max(np.linalg.norm(v) for v in u.values())
    require(
        max_displacement / span <= settings["max_displacement_span_ratio"]
        and max_strain <= settings["max_strain"],
        "Computed response exceeds declared linear small-deformation scope",
        "unsupported_capability",
        "unsupported_physics",
    )
    vm = np.sqrt(
        (
            (stress[:, 0] - stress[:, 1]) ** 2
            + (stress[:, 1] - stress[:, 2]) ** 2
            + (stress[:, 2] - stress[:, 0]) ** 2
        )
        / 2
        + 3 * np.sum(stress[:, 3:] ** 2, axis=1)
    )
    gauge = settings["stress_region"]
    mask = np.all(points >= gauge["lower_mm"], axis=1) & np.all(points <= gauge["upper_mm"], axis=1)
    require(
        np.count_nonzero(mask) >= 16,
        "Stress gauge has insufficient integration points",
        "numerical_failure",
        "missing_evidence",
    )
    integration_volumes = np.repeat(volumes / 4, 4)
    stress_mean = float(np.average(vm[mask], weights=integration_volumes[mask]))
    direction = applied / np.linalg.norm(applied)
    displacement = sum(w * float(np.dot(u[n], direction)) for n, w in weights.items()) / area
    require(
        displacement > 0,
        "Negative compliance indicates invalid solution",
        "numerical_failure",
        "solver_error",
    )
    with (OUT / f"level-{level}-displacement.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(["node", "x_mm", "y_mm", "z_mm", "ux_mm", "uy_mm", "uz_mm"])
        writer.writerows([int(n), *xyz[index[int(n)]], *u[int(n)]] for n in tags)
    with (OUT / f"level-{level}-stress.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "element",
                "ip",
                "x_mm",
                "y_mm",
                "z_mm",
                "sxx_mpa",
                "syy_mpa",
                "szz_mpa",
                "sxy_mpa",
                "sxz_mpa",
                "syz_mpa",
                "von_mises_mpa",
                "in_gauge",
            ]
        )
        writer.writerows(
            [*k, *p, *s, float(v), bool(m)] for k, p, s, v, m in zip(keys, points, stress, vm, mask)
        )
    return {
        **stats,
        "load_displacement_mm": displacement,
        "gauge_von_mises_mpa": stress_mean,
        "gauge_volume_mm3": float(sum(integration_volumes[mask])),
        "gauge_points": int(sum(mask)),
        "peak_von_mises_mpa_diagnostic_only": float(max(vm)),
        "max_principal_strain": max_strain,
        "max_displacement_mm": float(max_displacement),
        "reaction_n": react.tolist(),
        "reaction_moment_n_mm": react_m.tolist(),
        "reaction_relative_residual": float(residual),
        "moment_relative_residual": float(moment_residual),
    }


def execute(request):
    config = request["structural"]
    settings, material = config["settings"], config["material"]
    write(
        "material.json",
        {
            **config["material_source"],
            "converted": material,
            "solver_density_tonne_mm3": material["density_g_mm3"] / 1e6,
            "unit_system": "N, mm, MPa, tonne, s",
        },
    )
    write("regions.json", {"interfaces": request["interfaces"], "stress_region": settings["stress_region"]})
    write(
        "uncertainty.json",
        {
            "relative_allowance": settings["relative_uncertainty"],
            "basis": settings["uncertainty_basis"],
            "certified_bound": False,
        },
    )
    gmsh.initialize()
    gmsh.logger.start()
    history = []
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        gmsh.model.occ.importShapes("/input/model.step")
        gmsh.model.occ.synchronize()
        solids = gmsh.model.getEntities(3)
        require(
            len(solids) == 1 and request["measured_geometry"]["solids"] == 1,
            "Exactly one connected CAD solid required",
        )
        cad_volume = gmsh.model.occ.getMass(3, solids[0][1])
        require(
            cad_volume > 0
            and abs(cad_volume - request["measured_geometry"]["volume"]) <= max(1e-6, cad_volume * 1e-7),
            "Independent CAD volume mismatch",
        )
        selected = faces_for_interfaces(request)
        policy, errors = settings["mesh"], {}
        for level in range(policy["max_levels"]):
            started = time.monotonic()
            data = mesh(
                request, level, policy["initial_size_mm"] * policy["factor"] ** level, selected, cad_volume
            )
            if history:
                require(
                    data[-1]["elements"] > history[-1]["elements"]
                    and data[-1]["nodes"] > history[-1]["nodes"],
                    "Requested refinement did not produce a finer mesh; repeated meshes cannot establish convergence",
                    "numerical_failure",
                    "missing_evidence",
                )
            path = deck(request, level, data)
            # Keep solver scratch out of the monitored flat artifact directory. Never rename
            # output paths while Runner is checking them; publish only stable regular files.
            with tempfile.TemporaryDirectory(prefix="ccx-", dir="/tmp") as work:
                shutil.copyfile(path, Path(work) / path.name)
                with (OUT / f"level-{level}-solver.log").open("w") as log:
                    run = subprocess.run(
                        ["ccx", "-i", path.stem],
                        cwd=work,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env={
                            **os.environ,
                            "OMP_NUM_THREADS": "1",
                            "CCX_NPROC_RESULTS": "1",
                            "CCX_NPROC_EQUATION_SOLVER": "1",
                        },
                    )
                for artifact in Path(work).iterdir():
                    require(
                        artifact.is_file() and not artifact.is_symlink(),
                        "Invalid solver output path",
                        "numerical_failure",
                        "solver_error",
                    )
                    if artifact.suffix == ".inp":
                        continue
                    name = (
                        artifact.name if artifact.suffix == ".dat" else f"level-{level}-{artifact.name}.log"
                    )
                    shutil.copyfile(artifact, OUT / name)
            text = (OUT / f"level-{level}-solver.log").read_text()
            require(
                run.returncode == 0 and "*ERROR" not in text.upper(),
                "CalculiX execution failed; inspect solver log",
                "numerical_failure",
                "solver_error",
            )
            result = results(request, data, dat_tables(path.with_suffix(".dat")), level)
            result["seconds"] = time.monotonic() - started
            result["peak_solver_rss_kb"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            history.append(result)
            converged = False
            if len(history) >= 3:
                checks = []
                for metric, floor in [
                    ("load_displacement_mm", policy["displacement_floor_mm"]),
                    ("gauge_von_mises_mpa", policy["stress_floor_mpa"]),
                    ("gauge_volume_mm3", 1e-6),
                ]:
                    changes = [abs(history[i][metric] - history[i - 1][metric]) for i in (-1, -2)]
                    errors[metric] = 2 * max(changes)
                    checks.append(
                        max(changes) <= max(floor, policy["relative_tolerance"] * abs(result[metric]))
                    )
                converged = all(checks)
            write(
                "convergence.json",
                {
                    "converged": converged,
                    "rule": policy,
                    "error_estimate": "twice maximum of last two absolute differences; empirical, not rigorous",
                    "errors": errors,
                    "levels": history,
                },
            )
            if converged:
                metrics = {
                    "mass_g": {
                        "value": cad_volume * material["density_g_mm3"],
                        "unit": "g",
                        "numerical_error": cad_volume * material["density_g_mm3"] * 1e-7,
                        "uncertainty": cad_volume
                        * material["density_g_mm3"]
                        * settings["relative_uncertainty"],
                    }
                }
                for name, unit in [("load_displacement_mm", "mm"), ("gauge_von_mises_mpa", "MPa")]:
                    metrics[name] = {
                        "value": result[name],
                        "unit": unit,
                        "numerical_error": errors[name],
                        "uncertainty": abs(result[name]) * settings["relative_uncertainty"],
                    }
                return {
                    "test_id": request["test"]["id"],
                    "status": "pass",
                    "reason": "ok",
                    "mesh_valid": True,
                    "applicable": True,
                    "metrics": metrics,
                }
        raise Rejected(
            "numerical_failure",
            "missing_evidence",
            "Declared mesh convergence not established within refinement budget",
        )
    finally:
        (OUT / "gmsh.log").write_text("\n".join(gmsh.logger.get()))
        gmsh.logger.stop()
        gmsh.finalize()


def main():
    request = json.loads(Path("/input/request.json").read_text())
    start = time.monotonic()
    try:
        result = execute(request)
    except Rejected as exc:
        result = {
            "test_id": request["test"]["id"],
            "status": exc.status,
            "reason": exc.reason,
            "message": str(exc),
        }
    except Exception as exc:
        result = {
            "test_id": request["test"]["id"],
            "status": "numerical_failure",
            "reason": "solver_error",
            "message": type(exc).__name__ + ": " + str(exc),
        }
    write(
        "structural-resources.json",
        {
            "seconds": time.monotonic() - start,
            "process_peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "children_peak_rss_kb": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            "memory_measurement": "separate process maxima, not summed concurrent peak",
            "gmsh": gmsh.__version__,
            "calculix": "2.23",
            "backend": "CPU SPOOLES",
        },
    )
    write("result.json", result)


if __name__ == "__main__":
    main()

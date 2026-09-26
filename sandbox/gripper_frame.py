"""Linear 3D Euler-Bernoulli frame screen; units N, mm, MPa.

Ribs lie in XZ; rectangular sections are depth along global Y and width
in the XZ plane. Nodes have [ux,uy,uz,rx,ry,rz]. Ideal rigid joints.
"""
import math

import numpy as np


def element(a, b, width, depth, modulus=69000.0, poisson=.33):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    length = float(np.linalg.norm(b - a))
    if length <= 0 or min(width, depth, modulus) <= 0:
        raise ValueError("Invalid member")
    ex = (b - a) / length
    ey = np.array([0., 1., 0.])
    if abs(float(ex @ ey)) > 1e-8:
        raise ValueError("Members must lie in XZ")
    ez = np.cross(ex, ey)
    rotation = np.array([ex, ey, ez])
    transform = np.zeros((12, 12))
    for i in range(4):
        transform[3*i:3*i+3, 3*i:3*i+3] = rotation
    area = width * depth
    iy, iz = depth * width**3 / 12, width * depth**3 / 12
    big, small = max(width, depth), min(width, depth)
    torsion = big * small**3 * (1/3 - .21 * small / big * (1 - small**4 / (12 * big**4)))
    k = np.zeros((12, 12))
    for i, j, stiffness in ((0, 6, modulus*area/length),
                             (3, 9, modulus/(2*(1+poisson))*torsion/length)):
        k[i, i] += stiffness
        k[j, j] += stiffness
        k[i, j] -= stiffness
        k[j, i] -= stiffness
    # Local y translation with z rotation; local z with negative y rotation.
    for indices, inertia, sign in (([1, 5, 7, 11], iz, 1), ([2, 4, 8, 10], iy, -1)):
        L = length
        block = modulus * inertia / L**3 * np.array([
            [12, sign*6*L, -12, sign*6*L],
            [sign*6*L, 4*L*L, -sign*6*L, 2*L*L],
            [-12, -sign*6*L, 12, -sign*6*L],
            [sign*6*L, 2*L*L, -sign*6*L, 4*L*L],
        ])
        k[np.ix_(indices, indices)] += block
    return k, transform, length, area, iy, iz


def solve(nodes, edges, depth, load, fixed=(0, 1), tip=2, modulus=69000.0):
    points = [[x, 0, z] for x, z in nodes]
    count = len(nodes) * 6
    stiffness = np.zeros((count, count))
    elements = []
    for a, b, width in edges:
        a, b = int(a), int(b)
        k, t, length, area, iy, iz = element(points[a], points[b], width, depth, modulus)
        indices = list(range(a*6, a*6+6)) + list(range(b*6, b*6+6))
        stiffness[np.ix_(indices, indices)] += t.T @ k @ t
        elements.append((indices, k, t, length, area, iy, iz, width))
    free = [i for i in range(count) if i // 6 not in fixed]
    force = np.zeros(count)
    force[tip*6:tip*6+3] = load
    displacement = np.zeros(count)
    reduced = stiffness[np.ix_(free, free)]
    if np.linalg.cond(reduced) > 1e13:
        raise ValueError("Unstable frame")
    displacement[free] = np.linalg.solve(reduced, force[free])
    members = []
    for indices, k, t, length, area, iy, iz, width in elements:
        f = k @ t @ displacement[indices]
        axial = abs(float(f[0])) / area
        bending = max(abs(float(f[4])), abs(float(f[10]))) * width / (2*iy)
        bending += max(abs(float(f[5])), abs(float(f[11]))) * depth / (2*iz)
        # Nominal normal stress only; no torsional/shear or joint stress credit.
        stress = axial + bending
        compression = max(float(f[0]), 0)
        euler = math.pi**2 * modulus * min(iy, iz) / length**2
        members.append({"stress_mpa": stress, "compression_n": compression,
                        "buckling_factor": min(1e6, euler / max(compression, 1e-6))})
    tip_u = displacement[tip*6:tip*6+3]
    residual = stiffness @ displacement - force
    return {"deflection_mm": float(np.linalg.norm(tip_u)),
            "stress_mpa": max(m["stress_mpa"] for m in members),
            "buckling_factor": min(m["buckling_factor"] for m in members),
            "tip_displacement_mm": tip_u.tolist(),
            "displacements": displacement.reshape(-1, 6)[:, :3].tolist(),
            "members": members,
            "free_residual_n": float(np.max(np.abs(residual[free])))}

"""Independent matching of inspected STEP faces against fixed physical interfaces."""

import math

from davinci.product.units import convert


def bind_regions(interfaces, faces, cad_unit="mm"):
    bindings = {}
    evidence = {}
    for interface in interfaces:
        rule = interface.region
        if rule is None:
            raise ValueError(f"Missing structured region rule: {interface.id}")
        scale = convert(1, cad_unit, interface.unit, "length")
        norm = math.sqrt(sum(v * v for v in rule.normal))
        normal = [v / norm for v in rule.normal]
        matches = []
        for face in faces:
            if face["kind"] != "PLANE":
                continue
            center, extent = ([v * scale for v in face[key]] for key in ("center", "extent"))
            dot = sum(a * b for a, b in zip(normal, face["normal"]))
            if (
                all(
                    abs(a - b) <= t + interface.tolerance
                    for a, b, t in zip(center, rule.center, rule.center_tolerance)
                )
                and dot >= math.cos(math.radians(rule.normal_tolerance_degrees))
                and all(
                    a - interface.tolerance <= v <= b + interface.tolerance
                    for v, a, b in zip(extent, rule.extent_min, rule.extent_max)
                )
            ):
                matches.append(face)
        valid = len(matches) == rule.expected_count
        bindings[interface.id] = valid
        evidence[interface.id] = {
            "valid": valid,
            "expected_count": rule.expected_count,
            "observed_count": len(matches),
            "matches": matches,
            "rule": rule.model_dump(),
            "unit": interface.unit,
        }
    return bindings, evidence

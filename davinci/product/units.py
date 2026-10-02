"""Explicit dimensional conversions for supported engineering quantities, no guessing."""

import math

# dimension, SI scale. Deliberately finite vocabulary; unknown units fail closed.
UNITS = {
    "1": ("dimensionless", 1),
    "ratio": ("dimensionless", 1),
    "mm": ("length", 0.001),
    "cm": ("length", 0.01),
    "m": ("length", 1),
    "km": ("length", 1000),
    "mm2": ("area", 1e-6),
    "m2": ("area", 1),
    "mm3": ("volume", 1e-9),
    "cm3": ("volume", 1e-6),
    "cm³": ("volume", 1e-6),
    "m3": ("volume", 1),
    "g": ("mass", 0.001),
    "kg": ("mass", 1),
    "N": ("force", 1),
    "kN": ("force", 1000),
    "Pa": ("pressure", 1),
    "MPa": ("pressure", 1e6),
    "GPa": ("pressure", 1e9),
    "kg/m3": ("density", 1),
    "g/mm3": ("density", 1e6),
    "s": ("time", 1),
    "min": ("time", 60),
    "h": ("time", 3600),
    "m/s2": ("acceleration", 1),
    "kg*m2": ("inertia", 1),
    "N*m": ("torque", 1),
    "m/s": ("velocity", 1),
    "km/h": ("velocity", 1 / 3.6),
    "W": ("power", 1),
    "kW": ("power", 1000),
    "J": ("energy", 1),
    "Wh": ("energy", 3600),
    "rad": ("angle", 1),
    "deg": ("angle", math.pi / 180),
}


def validate_unit(unit, dimension=None):
    if unit not in UNITS or (dimension is not None and UNITS[unit][0] != dimension):
        raise ValueError(f"Unsupported unit/dimension: {unit} / {dimension}")
    return UNITS[unit]


def convert(value, source, target, dimension=None):
    dim, scale = validate_unit(source, dimension)
    _, other = validate_unit(target, dim)
    if not math.isfinite(value):
        raise ValueError("Quantity must be finite")
    return value * scale / other


def validate_plan_units(plan):
    for requirement in plan.requirements:
        if requirement.quantity:
            validate_unit(requirement.quantity.unit, requirement.quantity.dimension)
    for material in plan.materials:
        for quantity in material.properties.values():
            validate_unit(quantity.unit, quantity.dimension)
    for test in plan.tests:
        for case in test.load_cases:
            for quantity in case.quantities.values():
                validate_unit(quantity.unit, quantity.dimension)
        for unit in test.metrics.values():
            validate_unit(unit)
    for interface in plan.interfaces:
        validate_unit(interface.unit, "length")
    for unit in plan.design_units.values():
        validate_unit(unit)

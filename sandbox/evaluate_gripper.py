"""Trusted evaluation of STEP and graph; no import of agent-authored code."""
import json
from pathlib import Path

import cadquery as cq
from gripper_family import BASE_Z, parts, validate
from gripper_frame import solve

request = json.loads(Path('/input/request.json').read_text())
p, spec = request['parameters'], request['specification']
validate(p)
solids = cq.importers.importStep('/input/model.step').solids().vals()
reference = parts(p)
violations = []


def fail(code, message):
    violations.append({'code': code, 'message': message})


actual = {}
for solid in solids:
    name = 'base' if solid.BoundingBox().xlen > 200 else ('right' if solid.Center().x > 0 else 'left')
    if name in actual or not solid.isValid():
        fail('INVALID_SOLID', 'Expected three distinct valid solids')
    actual[name] = solid
if len(solids) != 3 or set(actual) != set(reference):
    raise ValueError('Expected base and two jaw solids')
residual = 0
for name, ref in reference.items():
    shape = ref.val()
    mismatch = shape.cut(actual[name]).Volume() + actual[name].cut(shape).Volume()
    residual += mismatch
if residual > .1:
    fail('UNSUPPORTED_GEOMETRY', 'STEP differs from the independently supported graph and interfaces')

collision_volume, min_clearance = 0., 1e6
samples = []
for gap in range(20, 61, 5):
    right = actual['right'].translate(((gap-60)/2, 0, 0))
    left = actual['left'].translate((-(gap-60)/2, 0, 0))
    volumes, distances = [], []
    for a, b in ((actual['base'], right), (actual['base'], left), (right, left)):
        volumes.append(a.intersect(b).Volume())
        distances.append(a.distance(b))
    # Two endpoint gauges model 20/60 mm samples; touching pads is permitted.
    if gap in (20, 60):
        gauge = cq.Workplane('XY').box(gap, 20, 18).translate((0, 0, BASE_Z+70)).val()
        volumes.extend((right.intersect(gauge).Volume(), left.intersect(gauge).Volume()))
    sample = {'gap_mm': gap, 'collision_mm3': max(volumes), 'clearance_mm': min(distances)}
    samples.append(sample)
    collision_volume = max(collision_volume, sample['collision_mm3'])
    min_clearance = min(min_clearance, sample['clearance_mm'])
if collision_volume > .01:
    fail('TRAVEL_COLLISION', 'Parts or sample gauge intersect during travel')
if min_clearance < spec['min_clearance_mm'] - 1e-6:
    fail('GUIDE_CLEARANCE', 'Minimum running clearance is too small')

cases = []
for name, load in spec['load_cases'].items():
    try:
        result = solve(p['nodes'], p['edges'], p['depth_mm'], load, modulus=spec['youngs_modulus_mpa'])
        cases.append({'name': name, 'load_n': load, **result})
    except (ValueError, ArithmeticError):
        fail('UNSTABLE_FRAME', 'Frame has an unsupported mechanism')
        break
stress = max((x['stress_mpa'] for x in cases), default=1e6)
deflection = max((x['deflection_mm'] for x in cases), default=1e6)
buckling = min((x['buckling_factor'] for x in cases), default=0)
if stress > spec['allowable_stress_mpa']:
    fail('STRESS_LIMIT', 'Nominal frame stress exceeds 80 MPa')
if deflection > spec['max_deflection_mm']:
    fail('DEFLECTION_LIMIT', 'Tip displacement exceeds 0.25 mm')
if buckling < spec['min_buckling_factor']:
    fail('BUCKLING_LIMIT', 'Pinned-member Euler buckling factor is below 2')
mass = sum(actual[n].Volume() for n in ('left', 'right')) * spec['density_g_mm3']
total = sum(s.Volume() for s in solids) * spec['density_g_mm3']
metrics = {
    'mass_g': {'value': mass, 'unit': 'g', 'fidelity': 'STEP_volume_moving_pair'},
    'total_mass_g': {'value': total, 'unit': 'g', 'fidelity': 'STEP_volume_three_parts'},
    'stress_mpa': {'value': stress, 'unit': 'MPa', 'fidelity': 'linear_3d_frame'},
    'deflection_mm': {'value': deflection, 'unit': 'mm', 'fidelity': 'linear_3d_frame'},
    'buckling_factor': {'value': buckling, 'unit': 'ratio', 'fidelity': 'Euler_pinned_member'},
    'clearance_mm': {'value': min_clearance, 'unit': 'mm', 'fidelity': 'BRep_distance'},
    'travel_mm': {'value': 40, 'unit': 'mm', 'fidelity': 'BRep_9_positions'},
}
assembly = cq.Assembly(name='gripper')
for name, solid in actual.items():
    color = cq.Color(*((.65, .70, .65) if name == 'base' else (.9, .4, .14)))
    assembly.add(solid, name=name, color=color)
    single = cq.Assembly(name=name)
    single.add(solid, name=name+'_solid', color=color)
    single.export('/output/'+name+'.glb')
assembly.export('/output/model.glb')
Path('/output/result.json').write_text(json.dumps({
    'outcome': 'passed' if not violations else 'failed', 'metrics': metrics,
    'violations': violations, 'fidelity': 'linear_3d_frame_and_BRep_travel',
    'reference_residual_mm3': residual, 'load_cases': cases, 'travel_samples': samples,
    'limitations': 'Nominal aluminium; rigid beam joints and fixed carriage roots. Normal stress only; no local joint, shear, torsional stress, fatigue or bearing analysis. External actuator and friction pads not designed.',
}, allow_nan=False))

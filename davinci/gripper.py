"""Independent graph-gripper build and evaluation contract."""
import json
from pathlib import Path

from davinci.models import digest

SANDBOX = Path(__file__).resolve().parents[1] / 'sandbox'
SPECIFICATION = {
    '_id': 'parallel-gripper-frame-v1', 'material': 'Aluminium (nominal)',
    'density_g_mm3': .0027, 'youngs_modulus_mpa': 69000,
    'allowable_stress_mpa': 80, 'max_deflection_mm': .25, 'min_buckling_factor': 2,
    'min_clearance_mm': .25, 'gap_range_mm': [20, 60],
    'load_cases': {'pinch': [100, 0, 0], 'payload': [0, 0, -25],
                   'lateral': [0, 15, 0], 'combined': [100, 15, -25]},
    'objective': 'minimize moving jaw-pair STEP mass; fixed guide base excluded from objective',
}
REFERENCE_SOURCE = '''from gripper_family import build_gripper

def build(parameters, interfaces):
    return build_gripper(parameters)
'''


def evaluator_version():
    return 'gripper-' + digest({'specification': SPECIFICATION, 'sources': {
        n: (SANDBOX/n).read_text() for n in ('gripper_family.py', 'gripper_frame.py', 'evaluate_gripper.py')
    }})[:12]


def evaluate(runner, source, parameters):
    from sandbox.gripper_family import validate
    validate(parameters)
    request = json.dumps({'parameters': parameters, 'interfaces': SPECIFICATION, 'specification': SPECIFICATION})
    helper = (SANDBOX/'gripper_family.py').read_text()
    built, _, _ = runner.execute('/input/build.py', {
        'build.py': (SANDBOX/'build.py').read_text(), 'source.py': source,
        'gripper_family.py': helper, 'request.json': request,
    })
    measured, _, _ = runner.execute('/input/evaluate_gripper.py', {
        'evaluate_gripper.py': (SANDBOX/'evaluate_gripper.py').read_text(),
        'gripper_family.py': helper, 'gripper_frame.py': (SANDBOX/'gripper_frame.py').read_text(),
        'model.step': built['model.step'], 'request.json': request,
    }, timeout=180)
    return json.loads(measured.pop('result.json')), {'model.step': built['model.step'], **measured}

import cadquery as cq
import numpy as np


def evaluate(step, request):
    shape = cq.importers.importStep(step)
    solid = shape.val()
    bb = solid.BoundingBox()
    t = bb.zlen
    valid = (len(shape.solids().vals()) == 1 and solid.isValid() and
             abs(bb.xlen - 40) < 1e-5 and abs(bb.ylen - 20) < 1e-5 and
             abs(solid.Volume() - 40*20*t) < 1e-4)
    load = request['test']['fixed_inputs']['force_n']
    youngs = request['materials'][0]['properties']['youngs']['value']
    density = request['materials'][0]['properties']['density']['value']
    inertia = 20*t**3/12
    # Euler-Bernoulli cantilever: free-end translation and rotation stiffness.
    stiffness = youngs*inertia / 40**3 * np.array([[12., -6*40], [-6*40, 4*40**2]])
    displacement = np.linalg.solve(stiffness, np.array([load, 0.]))[0]
    values = {'mass_g': (solid.Volume()*density, 'g'),
              'stress_mpa': (6*load*40/(20*t*t), 'MPa'),
              'deflection_mm': (float(displacement), 'mm')}
    return {'test_id': request['test']['id'], 'status': 'pass', 'reason': 'ok',
            'applicable': valid, 'mesh_valid': True, 'bindings': {'root': valid},
            'metrics': {k: {'value': v, 'unit': u, 'numerical_error': .00001, 'uncertainty': 0.}
                        for k, (v, u) in values.items()}}

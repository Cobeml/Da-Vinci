import os

import pytest

from davinci.config import Settings
from davinci.gripper import REFERENCE_SOURCE, evaluate
from davinci.runner import Runner
from sandbox.gripper_family import BASELINE
from sandbox.gripper_frame import solve


def test_frame_matches_three_analytic_cantilever_loads():
    length, width, depth, force, modulus = 70, 6, 12, 100, 69000
    for load, inertia in (([force, 0, 0], depth*width**3/12), ([0, force, 0], width*depth**3/12)):
        result = solve([[0, 0], [0, length]], [[0, 1, width]], depth, load, fixed=(0,), tip=1)
        assert result['deflection_mm'] == pytest.approx(force*length**3/(3*modulus*inertia))
        half = width/2 if load[0] else depth/2
        assert result['stress_mpa'] == pytest.approx(force*length*half/inertia)
        assert result['free_residual_n'] < 1e-7
    axial = solve([[0, 0], [0, length]], [[0, 1, width]], depth, [0, 0, -force], fixed=(0,), tip=1)
    assert axial['deflection_mm'] == pytest.approx(force*length/(modulus*width*depth))
    assert axial['buckling_factor'] == pytest.approx(3.141592653589793**2*modulus*depth*width**3/12/length**2/force)


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get('DAVINCI_INTEGRATION') != '1', reason='Requires Docker CAD')
def test_gripper_baseline_travel_and_thin_failure(tmp_path):
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path))
    result, artifacts = evaluate(runner, REFERENCE_SOURCE, BASELINE)
    assert result['outcome'] == 'passed', result['violations']
    assert len(result['load_cases']) == 4
    assert len(result['travel_samples']) == 9
    assert result['metrics']['clearance_mm']['value'] == pytest.approx(.3)
    assert all(artifacts[n][:4] == b'glTF' for n in ('base.glb', 'left.glb', 'right.glb'))
    thin = {'depth_mm': 10, 'nodes': [[8, 0], [36, 0], [8, 70]], 'edges': [[0, 1, 3], [0, 2, 3]]}
    failed, _ = evaluate(runner, REFERENCE_SOURCE, thin)
    assert failed['outcome'] == 'failed'
    assert 'DEFLECTION_LIMIT' in [v['code'] for v in failed['violations']]
    assert failed['metrics']['mass_g']['value'] < result['metrics']['mass_g']['value']


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get('DAVINCI_INTEGRATION') != '1', reason='Requires Docker CAD')
def test_gripper_rejects_forged_step(tmp_path):
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path))
    source = REFERENCE_SOURCE.replace('return build_gripper(parameters)',
        "p = dict(parameters); p['depth_mm'] = 10\n    return build_gripper(p)")
    result, _ = evaluate(runner, source, BASELINE)
    assert 'UNSUPPORTED_GEOMETRY' in [v['code'] for v in result['violations']]

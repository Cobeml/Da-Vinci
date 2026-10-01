"""Run from an initialized external workspace after `davinci service ensure`.

No Engine, Store, host CAD dependency, model credentials, or private API calls.
"""

import json
from pathlib import Path

from davinci.product.client import Client


def run(workspace):
    client = Client(workspace)
    client.connect()
    folder = Path(workspace) / 'external'
    request = json.loads((Path(workspace) / 'experiment.json').read_text())
    request['description'] = 'Find a beam that supports a 100 N tip load; compare mass without relaxing stress or stiffness tests.'
    row = client.request('POST', '/api/v2/experiments', request)
    eid = row['_id']
    memory = client.request('GET', '/api/v2/experience?q=cantilever%20beam')
    if row['phase'] == 'completed':
        return client.request('GET', f'/api/v2/experiments/{eid}/report')
    runtime = json.loads((folder / 'runtime.json').read_text())
    runtime['image'] = client.request('GET', '/api/v2/runtimes/resolve?image=da-vinci-cad%3Alocal')['image']
    plan = json.loads((folder / 'plan.json').read_text())
    row = client.mutate(eid, 'plan', {'plan': plan, 'runtime': runtime,
        'evaluator': {'resources': {'evaluate.py': (folder / 'evaluate.py').read_text()},
                      'provenance': 'Packaged nominal beam example with closed-form reference values'}}, 'plan-1')
    def candidate(thickness):
        return {'title': f'{thickness} mm cantilever beam', 'source': (folder / 'build.py').read_text(),
                'parameters': {'thickness': thickness}, 'metadata': {'source_file': 'build.py', 'author': request['actor']}}
    def wait(job):
        finished = client.wait(eid, job['id'])
        if finished['status'] != 'completed' or finished.get('wait_timed_out') or finished.get('failures'):
            raise RuntimeError(f'Inspect job {job["id"]}: {finished}')
        return finished
    for thickness in (4, 2):
        job = client.mutate(eid, 'reference-builds', {'reference': {'candidate': candidate(thickness),
            'provenance': 'Rectangular reference beam; closed-form expected mass/stress/deflection'}}, f'reference-{thickness}')
        artifact = wait(job)['fixture_artifacts'][0]
        # Expected values come from the specified reference geometry and closed form,
        # not from the evaluator's measured output.
        expected = {'mass_g': 40*20*thickness*.0027, 'stress_mpa': 6*100*40/(20*thickness**2),
                    'deflection_mm': 100*40**3/(3*70000*(20*thickness**3/12))}
        verification = {'test_id': 'beam', 'fixture_artifact': artifact,
            'expected_status': 'pass' if thickness == 4 else 'physical_failure',
            'reference_metrics': {k: {'value': v, 'unit': plan['tests'][0]['metrics'][k], 'dimension': 'reference quantity'}
                                  for k, v in expected.items()},
            'tolerances': {k: .0001 for k in expected}, 'provenance': 'Independent closed-form cantilever values'}
        wait(client.mutate(eid, 'verify', {'verification': verification}, f'verify-{thickness}'))
    readiness = client.request('GET', f'/api/v2/experiments/{eid}/plan-validation')
    if not readiness['ready_to_freeze']:
        raise RuntimeError(f'Plan needs work: {readiness}')
    client.mutate(eid, 'freeze', {}, 'freeze')
    for index, thickness in enumerate((2, 4)):
        client.mutate(eid, 'candidates', {'candidate': candidate(thickness)}, f'candidate-{index}')
        wait(client.mutate(eid, 'evaluate', {}, f'evaluate-{index}'))
        measured = client.request('GET', f'/api/v2/experiments/{eid}/results')['results'][-1]
        if measured['design_accepted'] != (thickness == 4):
            raise RuntimeError(f'Unexpected independent result: {measured}')
        client.download(measured['artifacts']['model.step'], folder / f'candidate-{index}.step')
        client.mutate(eid, 'reflections', {'lesson': 'The thin beam fails frozen limits; test a thicker section.' if index == 0
            else 'The thicker beam passes this nominal linear screen. Fatigue and joint details remain untested.',
            'result_id': measured['id']}, f'reflect-{index}')
    client.mutate(eid, 'finalize', {}, 'finalize')
    report = client.request('GET', f'/api/v2/experiments/{eid}/report')
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return {'experiment_id': eid, 'retrieved_experiences': len(memory), 'report': report['report'],
            'report_path': str(folder / 'report.json')}


if __name__ == '__main__':
    print(json.dumps(run(Path.cwd()), indent=2))

"""Astra graph-gripper study; resumable, independently evaluated and capped at $25."""
import argparse
import fcntl
import json
import math
from pathlib import Path

from pydantic import BaseModel

from davinci.artifacts import Artifacts, Repository
from davinci.budget import Budget
from davinci.config import Settings
from davinci.gripper import REFERENCE_SOURCE, SANDBOX, SPECIFICATION, evaluate, evaluator_version
from davinci.memory import Memory
from davinci.models import digest, document, now
from davinci.providers import AstraProvider
from davinci.runner import Runner
from davinci.store import Store
from sandbox.gripper_family import BASELINE

ROOT = Path(__file__).resolve().parents[1]
STUDY = 'parallel-gripper-study-v1'


class Design(BaseModel):
    title: str
    change: str
    source: str
    parameters: dict


class Reflection(BaseModel):
    lesson: str
    next_focus: str


class Utility(BaseModel):
    source: str
    explanation: str


class Study:
    def __init__(self):
        self.settings = Settings()
        if not self.settings.mongodb_uri or not self.settings.openai_api_key:
            raise ValueError('Live Atlas and Astra configuration required')
        self.root = self.settings.root / STUDY
        self.root.mkdir(exist_ok=True)
        self.lock = (self.root/'study.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.store = Store(self.settings.root, self.settings.mongodb_uri, self.settings.mongodb_database)
        self.artifacts = Artifacts(self.settings.root, self.store)
        self.repository = Repository(self.settings.root)
        self.runner = Runner(self.settings)
        self.version = evaluator_version()
        self.store.insert('runs', document('run', _id=STUDY, project_id='engineering-demo', diagnostic=True,
                          mode='live', status='study_running', budget_usd=25, spent_usd=0, revision=0,
                          evaluator_version=self.version))
        if self.store.get('runs', STUDY)['evaluator_version'] != self.version:
            raise ValueError('Frozen evaluator changed; use a new study ID')
        self.provider = AstraProvider(self.settings, Budget(self.store, self.settings.davinci_daily_budget_usd),
                                      self.store, STUDY)
        self.provider.client = self.provider.client.with_options(timeout=600)
        self.memory = Memory(self.store, self.provider.embed, self.version)
        self.store.insert('specifications', {**SPECIFICATION, 'evaluator_version': self.version})

    def structured(self, key, instructions, context, schema, output_limit=14000):
        saved = self.root/(key+'.json')
        if saved.exists():
            return schema.model_validate_json(saved.read_text())
        raw = self.root/(key+'.response.json')
        if not raw.exists():
            print('Astra high reasoning: '+key, flush=True)
            response = self.provider._response(
                output_limit=output_limit, reasoning_effort='high', instructions=instructions,
                input=json.dumps(context),
                text={'format': {'type': 'json_schema', 'name': schema.__name__,
                                 'strict': False, 'schema': schema.model_json_schema()}},
            )
            raw.write_text(response.output_text)
        value = schema.model_validate_json(raw.read_text())
        saved.write_text(value.model_dump_json(indent=2))
        return value

    def tool(self, history):
        existing = self.store.get('design_tools', STUDY+'-sizing')
        if existing:
            return existing
        result = self.structured('sizing-tool',
            'Write a reusable pure Python utility run(arguments). It sizes a rectangular cantilever in the bending '
            'plane, returning minimum_width_mm. Inputs: force_n, length_mm, depth_mm, modulus_mpa, '
            'allowable_stress_mpa, max_deflection_mm. I=depth*width^3/12; delta=F*L^3/(3*E*I); '
            'sigma=6*F*L/(depth*width^2). Return the maximum required width from the two constraints. '
            'Reject missing, nonfinite and nonpositive inputs. Import only math; no I/O. '
            'This is a preliminary member sizing tool, not the trusted multi-member frame evaluator. '
            'Explain how to use it in light of history without claiming it certifies whole-frame behavior.',
            {'history': history}, Utility)
        checks = []
        for force, length, depth in ((100, 70, 24), (40, 35, 12), (15, 60, 10), (120, 25, 18)):
            args = {'force_n': force, 'length_mm': length, 'depth_mm': depth,
                    'modulus_mpa': 69000, 'allowable_stress_mpa': 80, 'max_deflection_mm': .25}
            actual = self.runner.invoke(result.source, args)['minimum_width_mm']
            expected = max((4*force*length**3/(69000*depth*.25))**(1/3), math.sqrt(6*force*length/(depth*80)))
            if not math.isclose(actual, expected, rel_tol=1e-8):
                raise ValueError('Sizing tool failed independent numeric validation')
            checks.append({'arguments': args, 'actual': actual, 'expected': expected, 'passed': True})
        for value in (0, -1):
            try:
                self.runner.invoke(result.source, {**args, 'force_n': value})
            except RuntimeError:
                checks.append({'invalid_force_n': value, 'passed': True})
            else:
                raise ValueError('Sizing tool accepted nonpositive load')
        files = {'tool.py': result.source, 'explanation.txt': result.explanation}
        record = document('tool', _id=STUDY+'-sizing', study_id=STUDY, source=result.source,
                          explanation=result.explanation, validation=checks,
                          source_commit=self.repository.commit(STUDY+'-tool', files),
                          bundle_artifact_id=self.artifacts.put(self.repository.bundle(files), 'tool.json', 'application/json'))
        self.store.insert('design_tools', record)
        print('Member sizing tool passed six checks', flush=True)
        return record

    def recall(self):
        vector = self.provider.embed('parallel gripper rib frame stress displacement buckling mass design lessons', STUDY)
        return list(self.store.db.memories.aggregate([
            {'$vectorSearch': {'index': 'memory_vector', 'path': 'embedding', 'queryVector': vector,
             'numCandidates': 100, 'limit': 5,
             'filter': {'specification_id': SPECIFICATION['_id'], 'evaluator_version': self.version}}},
            {'$project': {'_id': 1, 'summary': 1, 'score': {'$meta': 'vectorSearchScore'}}},
        ]))

    def run(self, count):
        for index in range(count):
            id = f'{STUDY}-{index:02d}'
            if self.store.get('design_iterations', id):
                continue
            records = self.store.list('design_iterations', {'study_id': STUDY})
            history = [{k: d[k] for k in ('iteration', 'parameters', 'change', 'reflection')} |
                       {'evaluation': {k: d['evaluation'][k] for k in ('outcome', 'metrics', 'violations')}}
                       for d in records]
            tool, predictions = None, []
            if index >= 2:
                tool = self.tool(history)
                for depth in (10, 16, 24):
                    for length in (35, 70):
                        args = {'force_n': 100, 'length_mm': length, 'depth_mm': depth,
                                'modulus_mpa': 69000, 'allowable_stress_mpa': 80, 'max_deflection_mm': .25}
                        predictions.append({**args, **self.runner.invoke(tool['source'], args)})
            context = {'iteration': index+1, 'specification': SPECIFICATION, 'history': history,
                       'geometry_contract': (SANDBOX/'gripper_family.py').read_text(),
                       'frame_evaluator': (SANDBOX/'gripper_frame.py').read_text(),
                       'reference_source': REFERENCE_SOURCE, 'baseline': BASELINE,
                       'retrieved_memory': self.recall() if index else [],
                       'executed_tool_predictions': predictions,
                       'working_policy': records[-1]['reflection'] if records else {}}
            instructions = (
                'You design the rib topology of two opposed robotic gripper fingers. Return an executable '
                'build(parameters, interfaces) that calls gripper_family.build_gripper(parameters), and the '
                'parameters {depth_mm,nodes,edges}. Geometry is a genuine graph: choose intermediate node '
                'locations, connectivity and individual rib widths, not just a global scale. Root nodes 0/1 '
                'and tip node 2 are fixed. This is nominal aluminium with 4 independent frame load cases. '
                'Minimize moving jaw pair STEP mass, passing stress<=80MPa, deflection<=0.25mm and '
                'Euler buckling factor>=2. Preserve the fixed carriage, pad and running clearances. '
                'Use the supplied geometry contract exactly; do not invent measurements. '
                'Prefer meaningful structural alternatives to tiny fractional trims. Read actual failed loads '
                'and member stresses from history. The tool gives cantilever screening, not certification. '
                'Use short descriptive title and one-sentence change. '
                + ('This first attempt MUST use the exact supplied conservative baseline parameters.' if index == 0 else
                   'Try to improve the best passing design while exploring a different efficient load path. '
                   'If previous attempt failed, address its constraint violations explicitly.')
            )
            proposal = self.structured(f'proposal-{index:02d}', instructions, context, Design)
            print(f'Evaluating {index+1}: {proposal.title}', flush=True)
            try:
                evaluation, outputs = evaluate(self.runner, proposal.source, proposal.parameters)
            except (ValueError, RuntimeError) as exc:
                # Sandbox has no secrets. Limit diagnostic feedback to generated geometry failures.
                evaluation = {'outcome': 'failed', 'metrics': {}, 'fidelity': 'build_failure',
                              'violations': [{'code': 'BUILD_FAILED', 'message': str(exc)[-1600:]}]}
                outputs = {}
            reflection = self.structured(f'reflection-{index:02d}',
                'You are the independent design-review agent. Reflect on measured CAD/frame results. '
                'State a short concrete lesson and next_focus for the next graph design. Prioritize correcting '
                'failures and meaningful topology changes over tiny trims. Do not invent success or measurements. '
                'Explain which members or load case control when relevant. Keep each field under 300 characters.',
                {'proposal': proposal.model_dump(), 'evaluation': evaluation, 'history': history,
                 'specification': SPECIFICATION, 'geometry_contract': (SANDBOX/'gripper_family.py').read_text()},
                Reflection, 6000)
            files = {'candidate.py': proposal.source, 'parameters.json': json.dumps(proposal.parameters),
                     'context.json': json.dumps(context), 'policy.json': reflection.model_dump_json()}
            artifact_ids = {name: self.artifacts.put(payload, name, 'model/gltf-binary' if name.endswith('glb') else 'application/step')
                            for name, payload in outputs.items()}
            record = document('design', _id=id, study_id=STUDY, iteration=index+1,
                title=proposal.title[:64], change=proposal.change[:280], parameters=proposal.parameters,
                source=proposal.source, source_commit=self.repository.commit(id, files),
                source_artifact_id=self.artifacts.put(self.repository.bundle(files), 'source.json', 'application/json'),
                evaluation=evaluation, artifacts=artifact_ids, reflection=reflection.model_dump(),
                tool_id=tool['_id'] if tool else None, tool_predictions=predictions,
                retrieved_memory=context['retrieved_memory'], evaluator_version=self.version,
                runtime_image_digest=self.runner.image_digest(), generator=self.settings.openai_model)
            self.store.insert('design_iterations', record)
            self.memory.remember({'_id': id, 'run_id': STUDY, 'project_id': 'engineering-demo',
                'subsystem': 'parallel_gripper', 'specification_id': SPECIFICATION['_id'],
                'evaluator_version': self.version, 'parameters': proposal.parameters,
                'fingerprint': digest(proposal.parameters)}, {'_id': id+'-evaluation', **evaluation})
            (self.root/f'iteration-{index:02d}.json').write_text(json.dumps(record, indent=2))
            print(json.dumps({'iteration': index+1, 'outcome': evaluation['outcome'],
                  'metrics': {k: v['value'] for k, v in evaluation['metrics'].items()},
                  'violations': [v['code'] for v in evaluation['violations']]}), flush=True)
            self.export()
        self.store.update('runs', STUDY, {'status': 'completed', 'finished_at': now()})

    def export(self):
        records = self.store.list('design_iterations', {'study_id': STUDY})
        public = ROOT/'web/public/models/gripper'
        public.mkdir(parents=True, exist_ok=True)
        designs = []
        for record in records:
            urls = {}
            for filename, artifact_id in record['artifacts'].items():
                target = f"{record['iteration']:02d}-"+filename
                (public/target).write_bytes(self.artifacts.read(artifact_id))
                urls[filename] = '/models/gripper/'+target
            (public/f"{record['iteration']:02d}.py").write_text(record['source'])
            designs.append({k: record[k] for k in ('_id', 'iteration', 'title', 'change', 'parameters',
                'evaluation', 'reflection', 'tool_id', 'source_commit', 'retrieved_memory', 'generator')} |
                {'assets': urls})
        passed = [d for d in designs if d['evaluation']['outcome'] == 'passed']
        base = designs[0]['evaluation']['metrics'].get('mass_g', {}).get('value') if designs else None
        best = min(passed, key=lambda d: d['evaluation']['metrics']['mass_g']['value']) if passed else None
        reduction = 100*(1-best['evaluation']['metrics']['mass_g']['value']/base) if best and base else 0
        tool = self.store.get('design_tools', STUDY+'-sizing')
        manifest = {'study_id': STUDY, 'generated_at': now(), 'specification': SPECIFICATION,
                    'designs': designs, 'best_id': best['_id'] if best else None,
                    'reduction_percent': reduction, 'publishable': bool(base and reduction >= 15),
                    'spent_usd': self.store.get('runs', STUDY)['spent_usd'],
                    'tool': {k: v for k, v in (tool or {}).items() if k not in ('source', 'bundle_artifact_id')}}
        (ROOT/'web/data/gripper-gallery.json').write_text(json.dumps(manifest, indent=2)+'\n')
        print(f"Archived {len(designs)} attempts, reduction {reduction:.1f}%, usage ${manifest['spent_usd']:.3f}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=8, choices=range(1, 11))
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    try:
        study = Study()
        study.export() if args.export_only else study.run(args.count)
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

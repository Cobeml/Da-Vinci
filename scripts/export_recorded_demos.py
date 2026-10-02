"""Publish an allowlisted, checksummed view of existing local evidence; never execute CAD.

Reads archives through SQLite read-only connections, not the product worker. Default
inputs are the explicitly reviewed structural and mechanism validation archives.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    'structural': ('Structural bracket', 'runtime/structural-validation', 'experiment-9c7b5d0f81356828be38c062'),
    'mechanism': ('Vertical slider', 'runtime/mechanism-installed-archive', 'experiment-21f2c5cf7fb3005044376ff6'),
}
ALLOWED = {'model.step', 'model.glb', 'bindings.json', 'assembly-bindings.json', 'convergence.json',
           'uncertainty.json', 'reference-checks.json', 'material-source.json', 'lift-2.csv'}
LIMIT = 32_000_000


def encode(data):
    return (json.dumps(data, indent=2, allow_nan=False) + '\n').encode()


def export_case(slug, archive, destination):
    name, _, experiment_id = CASES[slug]
    db = sqlite3.connect(f'{(archive / ".davinci/ledger.sqlite3").resolve().as_uri()}?mode=ro', uri=True)
    def record(collection, identity):
        row = db.execute('SELECT body FROM documents WHERE collection=? AND id=?', (collection, identity)).fetchone()
        if not row:
            raise ValueError(f'Missing {collection} record: {identity}')
        return json.loads(row[0])
    e = record('runs', experiment_id)
    out = destination / slug
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    total = 0
    def publish(data, filename, source=None):
        nonlocal total
        total += len(data)
        if total > 100_000_000:
            raise ValueError('Public bundle quota exceeded')
        sha = hashlib.sha256(data).hexdigest()
        url = f'/studies/{slug}/{filename}'
        (out / filename).write_bytes(data)
        files[url] = {'sha256': sha, 'bytes': len(data), 'source_artifact': source}
        return url
    def artifact(identity):
        r = record('artifacts', identity)
        checksum = r['sha256']
        if not re.fullmatch('[a-f0-9]{64}', checksum) or r['size'] > LIMIT:
            raise ValueError('Unsafe artifact identity or size')
        p = archive / '.davinci/artifacts' / checksum
        if p.is_symlink() or not p.is_file() or p.stat().st_size != r['size']:
            raise ValueError('Missing, unsafe or incorrectly sized artifact')
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError('Corrupted artifact')
        return data
    candidates = {c['id']: c for c in e['candidates']}
    iterations = []
    for index, r in enumerate(e['results']):
        c = candidates[r['candidate_id']]
        assets = {}
        trajectory = []
        # Exclude arbitrary metadata, logs, source text, workspace paths and configuration.
        for logical, identity in r['artifacts'].items():
            base = logical.rsplit('/', 1)[-1]
            if base not in ALLOWED or logical.startswith('preview/'):
                continue
            data = artifact(identity)
            if base.endswith('.glb') and not data.startswith(b'glTF'):
                raise ValueError('Invalid GLB')
            if base.endswith('.step') and b'ISO-10303-21' not in data[:128]:
                raise ValueError('Invalid STEP')
            if base.endswith('.json'):
                json.loads(data)
            safe_name = f'{index + 1}-{logical.replace("/", "-")}'
            if not re.fullmatch('[a-zA-Z0-9_.-]+', safe_name):
                raise ValueError('Unsafe public artifact name')
            assets[logical] = publish(data, safe_name, identity)
            if base == 'lift-2.csv':
                rows = list(csv.DictReader(io.StringIO(data.decode())))
                selected = rows[::max(1, len(rows)//200)]
                if selected[-1] != rows[-1]:
                    selected.append(rows[-1])
                trajectory = [[float(row['time_s']), float(row['q_m'])*1000] for row in selected]
        tests = [{k: t[k] for k in ('test_id', 'status', 'reason', 'message', 'metrics') if k in t} for t in r['tests']]
        iterations.append({
            'id': c['id'], 'iteration': index + 1, 'title': c['title'], 'change': c['change'],
            'candidate_version': r['candidate_version'], 'source_artifact': r['source_artifact'],
            'result_id': r['id'], 'suite_id': r['suite_id'], 'runtime_id': r['runtime_id'],
            'execution_id': r['execution_id'], 'accepted': r['design_accepted'],
            'evidence_complete': r['evidence_complete'], 'objective_target_attained': r['objective_target_attained'],
            'duration_seconds': r['duration_seconds'], 'tests': tests, 'assets': assets, 'trajectory': trajectory,
        })
    # Both routes are published as curated metrics, not a dump of their workspace records.
    comparison = json.loads((ROOT / f'docs/product/{slug}-results.json').read_text())
    # Drop archive locations; only documented evidence and route comparisons are public.
    comparison = {k: v for k, v in comparison.items() if k not in {'workspace', 'artifact_archive'}}
    comparison_url = publish(encode(comparison), 'route-comparison.json')
    case = {
        'version': 1, 'slug': slug, 'name': name, 'experiment_id': e['_id'],
        'description': e['description'], 'reasoning': 'Scripted external agent / deterministic managed fixture',
        'suite_id': e['suite_id'], 'runtime': {k: e['runtime'][k] for k in ('image', 'solver', 'backend', 'cpu_cores')},
        'coverage': e['coverage'], 'assumptions': e['plan']['assumptions'],
        'tests': e['plan']['tests'], 'iterations': iterations,
        'report': e['report'], 'comparison_url': comparison_url,
        'publication': 'Curated recorded evidence; no autonomous reasoning or laboratory validation claim.',
    }
    case['report_url'] = f'/studies/{slug}/report.json'
    case['manifest_url'] = f'/studies/{slug}/manifest.json'
    publish(encode(case), 'report.json')
    (out / 'manifest.json').write_bytes(encode({'version': 1, 'experiment_id': e['_id'], 'suite_id': e['suite_id'], 'files': files}))
    db.close()
    return case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'web/public/studies')
    args = parser.parse_args()
    for slug, (_, archive, _) in CASES.items():
        case = export_case(slug, args.archive_root / archive, args.output)
        print(f'{slug}: {len(case["iterations"])} recorded evaluations exported')


if __name__ == '__main__':
    main()

"""Public evidence contract; does not need a private archive or execute solvers."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_published_native_evidence_integrity_and_scope():
    for slug, count in [('structural', 2), ('mechanism', 5)]:
        directory = ROOT / 'web/public/studies' / slug
        manifest = json.loads((directory / 'manifest.json').read_text())
        report = json.loads((directory / 'report.json').read_text())
        assert report['suite_id'] == manifest['suite_id']
        assert len(report['iterations']) == count
        assert report['iterations'][0]['tests'][0]['status'] == 'physical_failure'
        assert not report['iterations'][0]['accepted']
        assert report['iterations'][-1]['accepted']
        assert report['iterations'][-1]['evidence_complete']
        assert 'Scripted' in report['reasoning']
        for item in report['iterations']:
            assert item['suite_id'] == report['suite_id']
            for url in item['assets'].values():
                assert url in manifest['files']
            if any(t['status'] == 'invalid_setup' for t in item['tests']):
                assert not item['accepted'] and not item['evidence_complete']
        for url, info in manifest['files'].items():
            assert url.startswith(f'/studies/{slug}/') and '..' not in url
            data = (ROOT / 'web/public' / url.lstrip('/')).read_bytes()
            assert len(data) == info['bytes']
            assert hashlib.sha256(data).hexdigest() == info['sha256']
            assert not url.endswith(('.sqlite3', '.log', '.yaml', '.env'))


def test_published_reports_match_preserved_reference_metrics():
    structural = json.loads((ROOT / 'web/public/studies/structural/report.json').read_text())
    reference = json.loads((ROOT / 'docs/product/structural-results.json').read_text())
    for actual, expected in zip(structural['iterations'], reference['routes']['external'], strict=True):
        assert actual['tests'][0]['metrics'] == expected['metrics']
        assert actual['accepted'] == expected['accepted']
    mechanism = json.loads((ROOT / 'web/public/studies/mechanism/report.json').read_text())
    reference = json.loads((ROOT / 'docs/product/mechanism-results.json').read_text())
    case = next(r for r in reference['runs'] if r['driver'] == 'external')['cases'][0]
    assert mechanism['iterations'][-1]['tests'][0]['metrics'] == case['final_metrics']

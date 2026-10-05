"""Progress claims must match evidence, route resolution and generated reporting."""
import json
import subprocess
import sys
from pathlib import Path

from app.api.compatibility_reads import RETIRED_READS
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
LEDGER = json.loads((ROOT/'docs/development-plan-progress.json').read_text())


def test_fixed_plan_scope_and_evidence_references():
    assert LEDGER['schema_version'] == 1
    assert [g['id'] for g in LEDGER['groups']] == list(range(1, 8))
    assert [len(g['milestones']) for g in LEDGER['groups']] == [10, 4, 5, 6, 5, 5, 6]
    for group in LEDGER['groups']:
        ids = [m['id'] for m in group['milestones']]
        assert len(ids) == len(set(ids))
        for m in group['milestones']:
            assert type(m['complete']) is bool
            if m['complete']:
                assert m['evidence'], (group['id'], m['id'])
            for path in m['evidence']:
                assert (ROOT/path).is_file(), path


def test_completed_compatibility_families_are_resolved_and_cover_all_tombstones():
    retired = {path for path, _, _ in RETIRED_READS}
    registered = {r.path for r in app.routes if 'GET' in (getattr(r, 'methods', None) or set())}
    milestones = LEDGER['groups'][0]['milestones']
    candidate_paths = [path for m in milestones for path in m.get('routes', [])]
    assert len(candidate_paths) == len(set(candidate_paths)) == 53
    assert set(candidate_paths) <= registered
    resolved = set()
    for m in milestones:
        bounded = m.get('bounded_evidence', {})
        assert set(bounded) <= set(m.get('routes', []))
        for path, evidence in bounded.items():
            assert path in registered and evidence, (m['id'], path)
            assert all((ROOT/ref).is_file() for ref in evidence)
            assert any(ref.startswith('backend/tests/') for ref in evidence)
        if m['complete']:
            for path in m.get('routes', []):
                assert path in retired or path in bounded, (m['id'], path)
                if path in retired:
                    resolved.add(path)
    assert resolved == retired  # New tombstones cannot silently escape the progress ledger.
    if milestones[-1]['complete']:
        assert all(m['complete'] for m in milestones[:-1])


def test_plan_report_is_reproducible_and_document_table_is_current():
    report = ROOT/'scripts/report_development_plan_progress.py'
    checked = subprocess.run([sys.executable, str(report), '--check'], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    output = subprocess.run([sys.executable, str(report)], check=True, capture_output=True, text=True).stdout
    # Completion counts can advance without freezing today's percentages in tests.
    for group in LEDGER['groups']:
        assert f"| {group['id']}. {group['name']} |" in output
    assert len(output.strip().splitlines()) == 9
    assert '34/44' not in output  # This report is separate from roadmap item accounting.

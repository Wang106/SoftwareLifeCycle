"""CI must fail closed on incomplete evidence and non-disposable databases."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'scripts/ci/check_backend_report.py'


@pytest.mark.parametrize('cases', [
    '',
    '<testcase classname="tests.test_auth" name="ok"/>',
    '<testcase classname="tests.test_command_postgres" name="bad"><failure/></testcase>',
    '<testcase classname="tests.test_command_postgres" name="bad"><error/></testcase>',
    '<testcase classname="tests.test_command_postgres" name="bad"><skipped/></testcase>',
])
def test_report_cli_rejects_empty_missing_pg_or_unsuccessful_evidence(tmp_path, cases):
    path = tmp_path / 'report.xml'
    path.write_text('<testsuites><testsuite>'+cases+'</testsuite></testsuites>')
    result = subprocess.run([sys.executable, str(REPORT), str(path)], capture_output=True, text=True)
    assert result.returncode != 0 and 'Invalid backend evidence' in result.stderr


@pytest.mark.parametrize('content', ['not XML', '<testsuites>'])
def test_report_cli_rejects_broken_xml(tmp_path, content):
    path = tmp_path / 'report.xml'; path.write_text(content)
    assert subprocess.run([sys.executable, str(REPORT), str(path)], capture_output=True).returncode != 0


def test_report_cli_requires_an_existing_report(tmp_path):
    assert subprocess.run([sys.executable, str(REPORT), str(tmp_path/'missing.xml')], capture_output=True).returncode != 0
    assert subprocess.run([sys.executable, str(REPORT)], capture_output=True).returncode != 0


def test_report_cli_accepts_successful_sqlite_and_postgres_evidence(tmp_path):
    path = tmp_path / 'report.xml'
    path.write_text('<testsuites><testsuite><testcase classname="tests.test_auth" name="ok"/>'
        '<testcase classname="tests.test_command_postgres" name="ok"/></testsuite></testsuites>')
    result = subprocess.run([sys.executable, str(REPORT), str(path)], capture_output=True, text=True)
    assert result.returncode == 0 and '2 passed, 1 PostgreSQL-module cases, no skips' in result.stdout


@pytest.mark.parametrize('url', [
    'postgresql+psycopg://localhost/company',
    'postgresql+psycopg://public.example/software_lifecycle_ci',
    'postgresql+psycopg://localhost/software_lifecycle_ci?options=-csearch_path=public',
    'sqlite:///software_lifecycle_ci',
])
def test_migration_check_rejects_non_disposable_target_before_connection(monkeypatch, url):
    spec = importlib.util.spec_from_file_location('ci_migrations', ROOT/'scripts/ci/check_migrations.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setenv('TEST_POSTGRES_URL', url)
    monkeypatch.setattr(module, 'create_engine', lambda *args, **kwargs: pytest.fail('rejected target must never connect'))
    with pytest.raises(ValueError, match='loopback software_lifecycle_ci'):
        module.check_migrations()

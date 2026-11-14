"""Mock-only staging schema compatibility. No HTTP requests are made."""
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def checker():
    spec = importlib.util.spec_from_file_location('staging_schema_check', ROOT / 'scripts/check_staging.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_staging_current_schema_uses_existing_readonly_checks():
    module = checker()
    responses = [io.StringIO(json.dumps(dict(status='ready', database_revision=Settings().required_db_revision))),
        io.StringIO('{}'), io.StringIO('{}'), io.StringIO('{}'),
        HTTPError('https://synthetic.invalid',403,'synthetic',{},io.BytesIO(b'{"detail":"read_only_mode"}'))]
    with patch.object(module, 'urlopen', side_effect=responses) as request:
        module.check('https://synthetic.invalid')
    assert request.call_count == 5


@pytest.mark.parametrize('revision', ['0022_acceptance_history', '0029_changeover_batch_history'])
def test_staging_rejects_legacy_schema_before_further_requests(revision):
    module = checker()
    with patch.object(module, 'urlopen', return_value=io.StringIO(json.dumps(dict(status='ready', database_revision=revision)))) as request:
        with pytest.raises(RuntimeError, match='API or migration not ready'):
            module.check('https://synthetic.invalid')
    request.assert_called_once_with('https://synthetic.invalid/health/ready', timeout=10)

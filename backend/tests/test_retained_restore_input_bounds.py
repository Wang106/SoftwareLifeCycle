"""Actual-module input gates; existing retained integration covers native restore."""
from pathlib import Path

import pytest

from app.ops import postgresql_backup_restore as backup
from app.ops import retained_synthetic_restore as recovery


@pytest.mark.parametrize('kind', ['archive', 'manifest', 'baseline'])
def test_oversized_package_never_creates_target(tmp_path, monkeypatch, kind):
    paths = {name: tmp_path / name for name in ('archive', 'manifest', 'baseline')}
    for path in paths.values():
        path.write_bytes(b'{}')
    limit = recovery.MAX_ARCHIVE_BYTES if kind == 'archive' else recovery.MAX_JSON_BYTES
    # Sparse synthetic input exercises production constants without a large allocation.
    with paths[kind].open('wb') as stream:
        stream.truncate(limit + 1)
    writes = []
    monkeypatch.setattr(backup, 'create_owned_database', lambda *args: writes.append(args))
    monkeypatch.setattr(backup, 'require_absent', lambda *args: pytest.fail('invalid inputs reached database'))
    output = tmp_path / 'new-evidence'
    with pytest.raises(backup.RehearsalError, match='limit'):
        recovery.recover(repo_root=Path(__file__).resolve().parents[2],
                         admin_url='postgresql+psycopg://synthetic:synthetic@127.0.0.1:5432/synthetic_ci',
                         archive=paths['archive'], manifest_path=paths['manifest'],
                         baseline_path=paths['baseline'], evidence_dir=output,
                         trusted_own_synthetic=True, run_id='abcdef012345')
    assert not writes
    assert not output.exists()
    assert paths[kind].stat().st_size == limit + 1


def test_actual_archive_validation_rejects_growth_with_bounded_reads(tmp_path, monkeypatch):
    from test_retained_synthetic_restore import package

    archive, manifest, baseline = package(tmp_path, monkeypatch)
    monkeypatch.setattr(recovery, 'MAX_ARCHIVE_BYTES', 32)
    original_open = Path.open
    requests, returned = [], []

    class GrowingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size):
            if not requests:
                with original_open(archive, 'ab') as writer:
                    writer.write(b'x' * 100)
            requests.append(size)
            data = self.stream.read(size)
            returned.append(len(data))
            return data

    def growing_open(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return GrowingReader(stream) if path == archive and mode == 'rb' else stream

    monkeypatch.setattr(Path, 'open', growing_open)
    monkeypatch.setattr(backup, '_native', lambda *args: pytest.fail('oversized archive reached native catalog'))
    with pytest.raises(backup.RehearsalError, match='size limit'):
        recovery.validate_package(None, archive, manifest, baseline)
    assert requests == [33]
    assert sum(returned) == 33

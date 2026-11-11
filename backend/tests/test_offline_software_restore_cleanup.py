"""Directory cleanup must finish once without retrying uncertain close outcomes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'software_restore_cleanup', ROOT / 'scripts/offline_software_restore_rehearsal.py')
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


class SoftwareCleanupTests(unittest.TestCase):
    def check_closes(self, failures):
        run = object.__new__(restore.Rehearsal)
        run.fds = [101, 102, 103, 104]
        order = list(reversed(run.fds))
        errors = {index: OSError(f'private close detail {index}') for index in failures}
        attempts = []

        def close(fd):
            index = len(attempts)
            attempts.append(fd)
            if index in errors:
                raise errors[index]

        with patch.object(restore.os, 'close', side_effect=close):
            if errors:
                with self.assertRaises(OSError) as raised:
                    run.close()
                self.assertIs(raised.exception, errors[min(errors)])
            else:
                run.close()
            self.assertEqual(attempts, order)
            self.assertEqual(run.fds, [])
            run.close()
            self.assertEqual(attempts, order)

    def test_first_error_still_attempts_all_once(self):
        self.check_closes([0])

    def test_middle_error_still_attempts_all_once(self):
        self.check_closes([1])

    def test_multiple_errors_preserve_first(self):
        self.check_closes([0, 2, 3])

    def test_last_error_leaves_no_registered_descriptors(self):
        self.check_closes([3])

    def test_success_and_second_cleanup_do_not_repeat(self):
        self.check_closes([])

    def test_empty_cleanup_does_not_close(self):
        run = object.__new__(restore.Rehearsal)
        run.fds = []
        with patch.object(restore.os, 'close') as close:
            run.close()
            run.close()
        close.assert_not_called()

    def test_real_descriptors_closed_before_error_are_not_retried(self):
        real_close = os.close
        with tempfile.TemporaryDirectory() as root:
            run = object.__new__(restore.Rehearsal)
            run.fds = []
            attempted = []
            pending = set()
            error = OSError('synthetic post-close failure')
            try:
                for _ in range(4):
                    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                    run.fds.append(fd)
                    pending.add(fd)
                order = list(reversed(run.fds))

                def close(fd):
                    attempted.append(fd)
                    real_close(fd)
                    pending.remove(fd)
                    if len(attempted) == 1:
                        raise error

                with patch.object(restore.os, 'close', side_effect=close):
                    with self.assertRaises(OSError) as raised:
                        run.close()
                    self.assertIs(raised.exception, error)
                    self.assertEqual(attempted, order)
                    self.assertEqual(run.fds, [])
                    run.close()
                    self.assertEqual(attempted, order)
                self.assertFalse(pending)
                for fd in order:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
            finally:
                # Only descriptors never passed to real_close remain owned here.
                for fd in pending:
                    real_close(fd)

    def test_cli_cleanup_failure_is_nonzero_and_redacted(self):
        run = restore.Rehearsal()
        root = Path('/tmp') / run.run_id
        real_close = os.close
        pending = set()
        attempts = []
        stdout, stderr = io.StringIO(), io.StringIO()
        private = 'PRIVATE_EXCEPTION_PATH_TOKEN'
        original_close = run.close

        def cleanup():
            order = list(reversed(run.fds))
            pending.update(order)

            def close(fd):
                attempts.append(fd)
                real_close(fd)
                pending.remove(fd)
                if len(attempts) in (1, 3):
                    raise OSError(private)

            with patch.object(restore.os, 'close', side_effect=close):
                try:
                    original_close()
                finally:
                    self.assertEqual(attempts, order)

        try:
            with patch.object(restore, 'Rehearsal', return_value=run), \
                    patch.object(run, 'close', side_effect=cleanup), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = restore.main([])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(stdout.getvalue()), {
                'scope': 'SYNTHETIC_ONLY', 'status': 'BLOCKED',
                'reason': 'REHEARSAL_FAILED', 'run_id': run.run_id})
            self.assertNotIn(private, stdout.getvalue() + stderr.getvalue())
            self.assertEqual(stderr.getvalue(), '')
            self.assertEqual(run.fds, [])
            self.assertFalse(pending)
            original_close()
            self.assertEqual(len(attempts), 5)
            # Cleanup never removes retained synthetic evidence.
            self.assertTrue((root / 'result.json').is_file())
        finally:
            for fd in pending:
                real_close(fd)
            # Before main starts, construction can already have owned fds.
            if not attempts:
                original_close()
            shutil.rmtree(root)


if __name__ == '__main__':
    unittest.main()

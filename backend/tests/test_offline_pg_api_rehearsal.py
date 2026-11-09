"""Pure mocks only; never bind a listener, start API, connect PG or execute DDL."""
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/offline_pg_api_rehearsal.py'
URL = 'postgresql+psycopg://slc_ci:synthetic@127.0.0.1:5432/software_lifecycle_ci'
NS = 'ci_catalog_' + 'a' * 32
CI = {'GITHUB_ACTIONS': 'true', 'CI': 'true', 'GITHUB_REPOSITORY': 'Wang106/SoftwareLifeCycle'}


class APIRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'new API process harness missing')
        spec = importlib.util.spec_from_file_location('api_rehearsal', SCRIPT)
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)

    def test_ci_environment_guard_rejects_before_side_effects(self):
        for env in ({}, dict(CI, CI='false'), dict(CI, PGHOSTADDR='remote'), dict(CI, PGOPTIONS='')):
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(self.m.RehearsalError): self.m.validate_ci()

    def test_url_exact_scope_and_readonly_options(self):
        value = self.m.scoped_url(URL, NS)
        self.assertIn('default_transaction_read_only', value)
        self.assertIn(NS, value)
        self.assertNotIn('public', value)
        for bad in (URL.replace('127.0.0.1', 'elsewhere'), URL + '?options=x',
                    URL.replace('slc_ci:', 'other:'), URL.replace(':5432', ':5433'), URL + '#x'):
            with self.assertRaises(self.m.RehearsalError): self.m.scoped_url(bad, NS)

    def test_namespace_rejects_public_or_arbitrary_names(self):
        for ns in ('public', 'ci_catalog_a', 'ci_api_' + 'a'*31, NS + ';DROP', 'pg_temp'):
            with self.assertRaises(self.m.RehearsalError): self.m.scoped_url(URL, ns)

    def test_environment_is_explicit_and_disabled(self):
        with mock.patch.dict(os.environ, dict(CI, DATABASE_URL='SECRET', AUTH_MODE='oidc', PYTHONPATH='SECRET'), clear=True):
            env = self.m.child_environment(URL, NS)
        self.assertEqual(env['READ_ONLY_MODE'], 'true')
        self.assertEqual(env['AUTH_MODE'], 'disabled')
        self.assertEqual(env['SEED_ON_STARTUP'], 'false')
        self.assertEqual(env['ADMIN_OPERATOR_ENABLED'], 'false')
        self.assertNotIn('PYTHONPATH', env)
        self.assertNotIn('SECRET', json.dumps(env))

    def test_request_is_loopback_bounded_and_no_redirect_follow(self):
        api = self.m.APIProcess(URL, NS)
        api.port = 12345; api.deadline = self.m.time.monotonic() + 10
        api.process = mock.Mock(); api.process.poll.return_value = None
        response = mock.Mock(status=302); response.read.return_value = b'redirect'
        client = mock.Mock(); client.getresponse.return_value = response
        with mock.patch.object(self.m.http.client, 'HTTPConnection', return_value=client) as constructor:
            status, body = api.request('GET', '/health/live')
        self.assertEqual(status, 302); self.assertEqual(body, b'redirect')
        self.assertEqual(constructor.call_args.args, ('127.0.0.1', 12345))
        response.read.assert_called_once_with(self.m.MAX_RESPONSE + 1)
        client.close.assert_called_once()

    def test_unknown_request_and_oversize_fail_closed(self):
        api = self.m.APIProcess(URL, NS); api.port=12345; api.deadline=self.m.time.monotonic()+10
        api.process=mock.Mock(); api.process.poll.return_value=None
        with self.assertRaises(self.m.RehearsalError): api.request('GET', 'https://example.com')
        response=mock.Mock(status=200); response.read.return_value=b'x'*(self.m.MAX_RESPONSE+1)
        client=mock.Mock(); client.getresponse.return_value=response
        with mock.patch.object(self.m.http.client, 'HTTPConnection', return_value=client):
            with self.assertRaises(self.m.RehearsalError): api.request('GET','/health/live')
        client.close.assert_called_once()

    def test_deadline_and_early_exit_do_not_contact_http(self):
        api=self.m.APIProcess(URL,NS); api.deadline=0; api.process=mock.Mock()
        with mock.patch.object(self.m.http.client,'HTTPConnection') as client:
            with self.assertRaises(self.m.RehearsalError): api.request('GET','/health/live')
            client.assert_not_called()

    def test_owned_process_graceful_shutdown(self):
        api=self.m.APIProcess(URL,NS); process=mock.Mock(); process.poll.return_value=None
        process.wait.return_value=0; api.process=process
        api.stop()
        process.terminate.assert_called_once(); process.kill.assert_not_called()
        self.assertIsNone(api.process)

    def test_shutdown_timeout_is_failure_even_after_kill(self):
        api=self.m.APIProcess(URL,NS); process=mock.Mock(); process.poll.return_value=None
        process.wait.side_effect=[self.m.subprocess.TimeoutExpired('fixed',5),0]; api.process=process
        with self.assertRaises(self.m.RehearsalError): api.stop()
        process.terminate.assert_called_once(); process.kill.assert_called_once()

    def test_bootstrap_is_fixed_single_worker_and_not_entrypoint(self):
        self.assertIn('uvicorn.run',self.m.BOOTSTRAP)
        self.assertIn('fd=',self.m.BOOTSTRAP)
        self.assertIn('workers=1',self.m.BOOTSTRAP)
        self.assertNotIn('alembic',self.m.BOOTSTRAP)
        self.assertNotIn('seed',self.m.BOOTSTRAP)

    def test_json_decoder_is_bounded_and_strict(self):
        self.assertEqual(self.m.json_body(b'{"status":"ok"}'), {'status':'ok'})
        for body in (b'{"x":1,"x":2}', b'null', b'[]', b'{"x":NaN}', b'bad SECRET'):
            with self.assertRaises(self.m.RehearsalError) as error:self.m.json_body(body)
            self.assertNotIn('SECRET',str(error.exception))

    def test_start_passes_owned_bound_fd_and_empty_cwd(self):
        listener=mock.MagicMock(); listener.__enter__.return_value=listener
        listener.getsockname.return_value=('127.0.0.1',12345); listener.fileno.return_value=77
        process=mock.Mock(); process.poll.return_value=None; process.wait.return_value=0
        with mock.patch.dict(os.environ,CI,clear=True), mock.patch.object(self.m.socket,'socket',return_value=listener), mock.patch.object(self.m.subprocess,'Popen',return_value=process) as popen, mock.patch.object(self.m.APIProcess,'request',return_value=(200,b'{"status":"ok"}')):
            with self.m.APIProcess(URL,NS): pass
        listener.bind.assert_called_once_with(('127.0.0.1',0))
        call=popen.call_args
        self.assertEqual(call.kwargs['pass_fds'],(77,))
        self.assertTrue(call.kwargs['close_fds'])
        self.assertEqual(call.args[0][-1],'77')
        self.assertNotEqual(call.kwargs['cwd'],str(self.m.BACKEND))
        self.assertEqual(call.kwargs['env']['READ_ONLY_MODE'],'true')
        self.assertEqual(call.kwargs['stdout'],self.m.subprocess.DEVNULL)

    def test_startup_bad_response_stops_only_owned_process(self):
        listener=mock.MagicMock(); listener.__enter__.return_value=listener
        listener.getsockname.return_value=('127.0.0.1',12345); listener.fileno.return_value=77
        process=mock.Mock(); process.poll.return_value=None; process.wait.return_value=0
        with mock.patch.dict(os.environ,CI,clear=True), mock.patch.object(self.m.socket,'socket',return_value=listener), mock.patch.object(self.m.subprocess,'Popen',return_value=process), mock.patch.object(self.m.APIProcess,'request',return_value=(302,b'redirect')):
            with self.assertRaises(self.m.RehearsalError):
                with self.m.APIProcess(URL,NS): pass
        process.terminate.assert_called_once(); process.kill.assert_not_called()

    def test_invalid_ci_never_binds_or_spawns(self):
        with mock.patch.dict(os.environ,{},clear=True), mock.patch.object(self.m.socket,'socket') as bind, mock.patch.object(self.m.subprocess,'Popen') as spawn:
            with self.assertRaises(self.m.RehearsalError):
                with self.m.APIProcess(URL,NS): pass
            bind.assert_not_called(); spawn.assert_not_called()

    def test_real_test_scope_is_two_prepared_cases_without_permission_changes(self):
        import ast
        text=(ROOT/'backend/tests/test_pg_api_rehearsal_postgres.py').read_text()
        parsed=ast.parse(text)
        names=[node.name for node in parsed.body if isinstance(node,ast.FunctionDef) and node.name.startswith('test_')]
        self.assertEqual(len(names),2)
        for prohibited in ('GRANT ', 'REVOKE ', 'create_all(', 'command.stamp', 'docker ', 'CREATE ROLE'):
            self.assertNotIn(prohibited,text)
        self.assertIn('owned_catalog_schema',text)
        self.assertIn('found != (oid, True)',text)
        self.assertIn('process.request',text)

    def test_http_deadline_rejects_existing_timer(self):
        with mock.patch.object(self.m.signal,'getitimer',return_value=(5.0,0.0)), mock.patch.object(self.m.signal,'setitimer') as setter:
            with self.assertRaises(self.m.RehearsalError):
                with self.m.http_deadline(1): pass
            setter.assert_not_called()

    def test_http_deadline_restores_handler_on_exception(self):
        sentinel=object()
        with mock.patch.object(self.m.signal,'getitimer',return_value=(0.0,0.0)), mock.patch.object(self.m.signal,'getsignal',return_value=sentinel), mock.patch.object(self.m.signal,'signal') as handler, mock.patch.object(self.m.signal,'setitimer') as timer:
            with self.assertRaises(RuntimeError):
                with self.m.http_deadline(1): raise RuntimeError('test')
            self.assertEqual(handler.call_args.args,(self.m.signal.SIGALRM,sentinel))
            self.assertEqual(timer.call_args.args,(self.m.signal.ITIMER_REAL,0))
            self.assertIn(mock.call(self.m.signal.ITIMER_REAL,1),timer.call_args_list)

    def test_http_deadline_handler_raises_timeout(self):
        with mock.patch.object(self.m.signal,'getitimer',return_value=(0.0,0.0)), mock.patch.object(self.m.signal,'getsignal',return_value=None), mock.patch.object(self.m.signal,'signal') as handler, mock.patch.object(self.m.signal,'setitimer'):
            with self.m.http_deadline(1):
                callback=handler.call_args.args[1]
                with self.assertRaises(TimeoutError): callback(0,None)

    def test_startup_interrupt_cleans_owned_process_and_preserves_interrupt(self):
        listener=mock.MagicMock(); listener.__enter__.return_value=listener
        listener.getsockname.return_value=('127.0.0.1',12345); listener.fileno.return_value=77
        process=mock.Mock(); process.poll.return_value=None; process.wait.return_value=0
        with mock.patch.dict(os.environ,CI,clear=True), mock.patch.object(self.m.socket,'socket',return_value=listener), mock.patch.object(self.m.subprocess,'Popen',return_value=process), mock.patch.object(self.m.APIProcess,'request',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                with self.m.APIProcess(URL,NS): pass
        process.terminate.assert_called_once(); process.kill.assert_not_called()

    def test_startup_system_exit_cleans_owned_process_and_preserves_exit(self):
        listener=mock.MagicMock(); listener.__enter__.return_value=listener
        listener.getsockname.return_value=('127.0.0.1',12345); listener.fileno.return_value=77
        process=mock.Mock(); process.poll.return_value=None; process.wait.return_value=0
        with mock.patch.dict(os.environ,CI,clear=True), mock.patch.object(self.m.socket,'socket',return_value=listener), mock.patch.object(self.m.subprocess,'Popen',return_value=process), mock.patch.object(self.m.APIProcess,'request',side_effect=SystemExit(2)):
            with self.assertRaises(SystemExit) as error:
                with self.m.APIProcess(URL,NS): pass
            self.assertEqual(error.exception.code,2)
        process.terminate.assert_called_once()

    def test_http_timer_cancel_failure_still_restores_handler(self):
        previous=object()
        with mock.patch.object(self.m.signal,'getitimer',return_value=(0.0,0.0)), mock.patch.object(self.m.signal,'getsignal',return_value=previous), mock.patch.object(self.m.signal,'signal') as handler, mock.patch.object(self.m.signal,'setitimer',side_effect=[None,OSError('SECRET')]) as timer:
            with self.assertRaises(self.m.RehearsalError) as error:
                with self.m.http_deadline(1): pass
            self.assertEqual(handler.call_args.args,(self.m.signal.SIGALRM,previous))
            self.assertEqual(timer.call_count,2)
            self.assertNotIn('SECRET',str(error.exception))

    def test_http_handler_restore_failure_is_fixed_failure_without_retry(self):
        with mock.patch.object(self.m.signal,'getitimer',return_value=(0.0,0.0)), mock.patch.object(self.m.signal,'getsignal',return_value=None), mock.patch.object(self.m.signal,'signal',side_effect=[None,OSError('SECRET')]) as handler, mock.patch.object(self.m.signal,'setitimer') as timer:
            with self.assertRaises(self.m.RehearsalError) as error:
                with self.m.http_deadline(1): pass
            self.assertEqual(handler.call_count,2)
            self.assertEqual(timer.call_args.args,(self.m.signal.ITIMER_REAL,0))
            self.assertNotIn('SECRET',str(error.exception))

    def test_import_has_no_execution_entrypoint(self):
        source=SCRIPT.read_text()
        self.assertNotIn("if __name__",source)
        self.assertNotIn('create_engine',source)
        self.assertNotIn('psycopg.connect',source)


if __name__ == '__main__': unittest.main()

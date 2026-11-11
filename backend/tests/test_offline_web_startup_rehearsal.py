"""Only fake Docker/process/HTTP transports; never start a container or server."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_web_startup_rehearsal as web
import offline_api_startup_rehearsal as api
from test_offline_api_startup_rehearsal import IMAGE, COMMIT, CID, TOKEN, raw, container_document, image_document


def web_image():
    value = image_document()
    value[0]['Config']['Env'] = ['PATH=/usr/local/bin:/usr/bin:/bin', 'NODE_VERSION=22.23.4', 'YARN_VERSION=1.22.22']
    return value


def web_container(c, running=False):
    value = container_document(c, running)
    item = value[0]
    item.update(Path=web.NODE, Args=web.NEXT_ARGS)
    item['Config'].update(Entrypoint=[web.NODE], Cmd=web.NEXT_ARGS)
    item['Config']['Labels'] = {web.LABEL: TOKEN, 'org.opencontainers.image.revision': COMMIT}
    return value


class WebStartupTests(unittest.TestCase):
    def make(self, root, child=Mock()):
        return web.Container(root, child, TOKEN, IMAGE, COMMIT, web.verify_image(raw(web_image()), IMAGE, COMMIT))

    def test_default_help_and_missing_trust_are_noop(self):
        for args, code in (([], 2), (['--help'], 0), (['--run', '--image-id', IMAGE, '--source-commit', COMMIT], 2)):
            with patch.object(web, 'run_rehearsal') as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(web.main(args), code)
            run.assert_not_called()

    def test_explicit_gate_exact_inputs_once(self):
        with patch.object(web, 'run_rehearsal', return_value=({}, 2)) as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(web.main(['--run', '--trusted-local-image', '--image-id', IMAGE, '--source-commit', COMMIT]), 2)
        run.assert_called_once_with(IMAGE, COMMIT)

    def test_image_rejects_mismatch_and_unsafe_configuration(self):
        self.assertEqual(web.verify_image(raw(web_image()), IMAGE, COMMIT)['NODE_VERSION'], '22.23.4')
        for path, value in [(('Id',), 'sha256:' + 'e'*64), (('Architecture',), 'arm64'),
                (('Config','Labels','org.opencontainers.image.revision'), 'e'*40),
                (('Config','User'), '0'), (('Config','Volumes'), {'/app': {}}),
                (('Config','Env'), ['NODE_VERSION=22.23.4', 'API_BASE_URL=https://private']),
                (('Config','Env'), ['NODE_VERSION=22.23.4', 'NODE_VERSION=22.23.4'])]:
            doc = web_image(); node = doc[0]
            for p in path[:-1]: node = node[p]
            node[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(web.Blocked): web.verify_image(raw(doc), IMAGE, COMMIT)

    def test_fixed_isolation_and_disabled_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = self.make(Path(tmp)); args = c.create_args()
        for item in ['--network=none', '--pull=never', '--read-only', '--user=65532:65532',
                     '--cap-drop=ALL', '--security-opt=no-new-privileges', '--log-driver=none']:
            self.assertIn(item, args)
        self.assertEqual(args[-len(web.NEXT_ARGS)-1:], [IMAGE, *web.NEXT_ARGS])
        for gate in web.GATES: self.assertIn(gate + '=disabled', args)
        self.assertNotIn('--publish', args); self.assertNotIn('--volume', args)
        self.assertNotIn('DATABASE_URL', web.ENVIRONMENT)

    def test_identity_and_running_exit_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = self.make(Path(tmp)); c.cid = CID
            c.verify_identity(raw(web_container(c, True)), True)
            for path, value in [(('HostConfig','NetworkMode'), 'host'), (('HostConfig','ReadonlyRootfs'), False),
                    (('Path',), '/bin/sh'), (('Config','Cmd'), ['other']),
                    (('Config','Labels',web.LABEL), 'e'*32), (('State','Running'), False),
                    (('State','Pid'), 333), (('HostConfig','PortBindings'), {'3000/tcp':[{}]})]:
                doc = web_container(c, True); node = doc[0]
                for p in path[:-1]: node=node[p]
                node[path[-1]]=value
                with self.subTest(path=path), self.assertRaises(web.Blocked): c.verify_identity(raw(doc), True)

    def test_uses_existing_custody_without_name_lookup_or_repeat_removal(self):
        self.assertIs(web.Container.cleanup, api.Container.cleanup)
        self.assertIs(web.Container.create, api.Container.create)
        with tempfile.TemporaryDirectory() as tmp:
            child = Mock(return_value=(1,b'private'))
            c = self.make(Path(tmp), child); c.cid=CID; c.attempted=True
            with patch.object(c,'inspect'):
                with self.assertRaisesRegex(web.Blocked,'CLEANUP_UNCERTAIN'): c.cleanup()
                with self.assertRaisesRegex(web.Blocked,'CLEANUP_UNCERTAIN'): c.cleanup()
            child.assert_called_once_with(['rm','--force',CID], limit=1024)

    def test_probe_receipt_no_false_success(self):
        for case in web.CASES:
            web.verify_probe(case,0,raw({'case':case,'passed':True}))
            for code, data in [(2,raw({'case':case,'passed':True})),(0,raw({'case':case,'passed':1})),
                               (0,b'{'),(0,raw({'case':case,'passed':True,'html':'private'}))]:
                with self.assertRaises(web.Blocked): web.verify_probe(case,code,data)

# This evaluates the exact in-container program with fake filesystem, HTTP and
# timers. Node itself is local; it never listens or requests a real destination.
NODE_HARNESS = r'''
const vm=require('node:vm'), {EventEmitter}=require('node:events');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
let output='', code=0, options=null, timer=null;
const status='Uid:\t65532 65532 65532 65532\nGid:\t65532 65532 65532 65532\n'+
 ['CapInh','CapPrm','CapEff','CapBnd','CapAmb'].map(k=>k+':\t0000000000000000\n').join('')+
 'NoNewPrivs:\t1\nSeccomp:\t2\n';
const files={'/proc/1/cmdline':'next-server (v16.4.2)\0\0', '/proc/1/status':status,
 '/proc/net/tcp':'header\n0: 0100007F:0BB8 00000000:0000 0A\n', '/proc/net/tcp6':'header\n', ...(input.files||{})};
const positions={};let closes=0;
const fakeFs={openSync:p=>{positions[p]=0;return p;},closeSync:()=>{closes++;},readlinkSync:()=>input.exe||'/usr/local/bin/node',
 readSync:(p,b,offset,length)=>{const data=Buffer.from(files[p]);const position=positions[p];
 const count=Math.min(data.length-position,length,(typeof input.readChunk==='object' ? input.readChunk[p] : input.readChunk)||65537);
 data.copy(b,offset,position,position+count);positions[p]+=count;return count;}};
const fakeHttp={request:(o,callback)=>{options=o;const req=new EventEmitter();req.destroy=()=>{};
 req.end=()=>{if(input.timeout){timer();return;} if(input.requestError){req.emit('error',new Error('PRIVATE'));return;}
 const res=new EventEmitter();res.headers=input.headers;res.statusCode=input.status;res.complete=input.complete!==false;
 callback(res);if(input.abort){res.emit('aborted');return;}
 const body=Buffer.from(input.body||'');res.emit('data',body);res.emit('end');};return req;}};
const context={require:name=>{if(name==='node:fs')return fakeFs;if(name==='node:http')return fakeHttp;throw Error('unexpected');},
 Buffer,TextDecoder,process:{argv:['node',input.case],stdout:{write:s=>output+=s},exit:c=>{code=c;throw Error('exit');}},
 setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{}};
try{vm.runInNewContext(input.program,context,{timeout:1500});}catch{if(!code)code=99;}
process.stdout.write(JSON.stringify({code,output,options,closes,positions}));
'''


class WebProgramTests(unittest.TestCase):
    def run_program(self, case='dashboard_unavailable', **overrides):
        import subprocess
        data = {'program':web.PROBE_PROGRAM, 'case':case, 'status':200,
                'headers':{'content-type':'text/html; charset=utf-8'}, 'body':self.html(), **overrides}
        result = subprocess.run(['node','-e',NODE_HARNESS], input=json.dumps(data).encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True)
        return json.loads(result.stdout)

    def html(self):
        return ('<!DOCTYPE html><html><body><h1>Lifecycle Dashboard</h1></body></html>'
                '<div hidden><p>Dashboard data unavailable. Try reading again later.</p>'
                '<p>Current release data unavailable</p><p>Recent activity unavailable</p>'
                '<p>Live dashboard unavailable</p><a>Read dashboard again</a></div>')

    def test_complete_streamed_server_html_and_fixed_destination(self):
        value=self.run_program()
        self.assertEqual(value['code'],0); self.assertEqual(json.loads(value['output']),{'case':'dashboard_unavailable','passed':True})
        options=value['options']; self.assertEqual((options['host'],options['port'],options['path'],options['method']),('127.0.0.1',3000,'/','GET'))
        self.assertFalse(options['agent']);self.assertEqual(options['headers']['Cookie'],'slc_language=en')

    def test_complete_markup_not_just_script_strings(self):
        for body in [self.html().replace('Recent activity unavailable','No activity records available.'),
                '<!DOCTYPE html><html><h1>Lifecycle Dashboard</h1><script>'+self.html()+'</script></html>',
                self.html().replace('</html>',''), '<html>'+self.html()[15:]]:
            with self.subTest(body=body[:50]):self.assertEqual(self.run_program(body=body)['code'],2)

    def test_timeout_truncation_redirect_encoding_abort_and_response_bound(self):
        for changes in [{'timeout':True},{'requestError':True},{'complete':False},{'abort':True},
                {'headers':{'content-type':'text/html','location':'https://PRIVATE'}},
                {'headers':{'content-type':'text/html','content-encoding':'gzip'}},
                {'headers':{'content-type':'text/html','content-length':'1'}},
                {'body':'x'*1048577},{'status':500}]:
            with self.subTest(changes=list(changes)):
                value=self.run_program(**changes);self.assertEqual(value['code'],2);self.assertEqual(value['output'],'')

    def test_disabled_login_is_post_503_and_no_redirect_or_cookie(self):
        headers={'content-type':'application/json','cache-control':'private, no-store','pragma':'no-cache',
                 'vary':'RSC, Cookie','referrer-policy':'no-referrer','x-content-type-options':'nosniff'}
        params={'status':503,'headers':headers,'body':'{"error":"login_not_configured"}'}
        value=self.run_program('login_disabled',**params);self.assertEqual(value['code'],0)
        self.assertEqual(value['options']['method'],'POST');self.assertEqual(value['options']['path'],'/auth/login')
        for update in [{'status':200},{'body':'{"error":"login_not_configured","error":"login_not_configured"}'},
                       {'headers':headers|{'set-cookie':['PRIVATE']}},{'headers':headers|{'location':'PRIVATE'}}]:
            self.assertEqual(self.run_program('login_disabled',**(params|update))['code'],2)

    def test_fragmented_proc_reads_reach_eof_and_close_each_file(self):
        for chunk in (1, 7, 31):
            value=self.run_program('process',readChunk=chunk)
            self.assertEqual(value['code'],0);self.assertEqual(value['closes'],4)
    def test_late_wildcard_listener_cannot_hide_after_valid_first_read(self):
        # Valid-looking first chunk cannot conceal a second wildcard listener.
        prefix='header\n0: 0100007F:0BB8 00000000:0000 0A\n'
        value=self.run_program('process',readChunk={'/proc/net/tcp':len(prefix)},files={
            '/proc/net/tcp':prefix+'1: 00000000:0BB8 00000000:0000 0A\n'})
        self.assertEqual(value['code'],2);self.assertEqual(value['output'],'')
        self.assertEqual(value['positions']['/proc/net/tcp'],len(prefix)+len('1: 00000000:0BB8 00000000:0000 0A\n'))

    def test_proc_exact_cap_eof_and_one_byte_overflow_always_close(self):
        title='next-server (v16.4.2)'
        at_cap=title+'\0'*(65536-len(title))
        value=self.run_program('process',files={'/proc/1/cmdline':at_cap},readChunk=127)
        self.assertEqual(value['code'],0);self.assertEqual(value['closes'],4)
        value=self.run_program('process',files={'/proc/1/cmdline':at_cap+'\0'},readChunk=127)
        self.assertEqual(value['code'],2);self.assertEqual(value['closes'],1)
        self.assertEqual(value['positions']['/proc/1/cmdline'],65537)

    def test_actual_next_title_node_identity_and_only_loopback_listener(self):
        self.assertEqual(self.run_program('process')['code'],0)
        for changes in [{'exe':'/bin/sh'}, {'files':{'/proc/1/cmdline':'node next start\0'}},
                {'files':{'/proc/net/tcp':'header\n0: 00000000:0BB8 00000000:0000 0A\n'}},
                {'files':{'/proc/net/tcp6':'header\n0: 00000000000000000000000000000000:0BB8 x 0A\n'}},
                {'files':{'/proc/1/status':'Uid: 0 0 0 0\n'}},
                {'files':{'/proc/1/cmdline':'x'*65537}}]:
            with self.subTest(changes=changes.keys()):self.assertEqual(self.run_program('process',**changes)['code'],2)


class WebCoordinatorTests(unittest.TestCase):
    def run_fake(self, *, failure=None, cleanup_failure=False):
        child = Mock(side_effect=[(0,raw({'OSType':'linux','Architecture':'amd64'})),(0,raw(web_image()))])
        c=Mock();c.attempted=True;c.cleaned=False
        def clean():
            if cleanup_failure: raise web.Blocked('CLEANUP_UNCERTAIN')
            c.cleaned=True
        c.cleanup.side_effect=clean
        def execute(name):
            if failure: raise web.Blocked(failure)
            return 0,raw({'case':name,'passed':True})
        c.execute.side_effect=execute
        with patch.object(web,'prepare_runtime',return_value=({},'/fake/docker')), patch.object(web,'run_child',child), \
                patch.object(web,'Container',return_value=c), patch.object(web.shutil,'rmtree') as remove:
            value,code=web.run_rehearsal(IMAGE,COMMIT)
        return value,code,c,remove

    def test_success_requires_all_probes_final_process_and_cleanup(self):
        value,code,c,_=self.run_fake()
        self.assertEqual(code,0);self.assertEqual(value['cases_passed'],2);self.assertTrue(value['container_removed'])
        self.assertFalse(value['browser_hydration']);self.assertFalse(value['api_integration']);self.assertFalse(value['offline_acceptance'])
        self.assertEqual([call.args[0] for call in c.execute.call_args_list],[*web.CASES,'process'])
        c.cleanup.assert_called_once()

    def test_timeout_and_cleanup_uncertainty_never_report_success(self):
        for failure,uncertain in [('COMMAND_TIMEOUT',False),('COMMAND_OUTPUT_LIMIT',False),(None,True)]:
            value,code,c,remove=self.run_fake(failure=failure,cleanup_failure=uncertain)
            self.assertEqual(code,2);self.assertEqual(value['status'],'BLOCKED')
            self.assertEqual(value['container_removed'],not uncertain)
            if uncertain:remove.assert_not_called()
            self.assertNotIn('image_id',value);c.cleanup.assert_called_once()

    def test_source_mismatch_stops_before_docker(self):
        with patch.object(web,'prepare_runtime',side_effect=web.Blocked('SOURCE_MISMATCH')),patch.object(web,'run_child') as child:
            result,code=web.run_rehearsal(IMAGE,COMMIT)
        self.assertEqual(code,2);self.assertEqual(result['reason'],'SOURCE_MISMATCH');child.assert_not_called()

    def test_bounded_exec_and_startup_polling(self):
        with tempfile.TemporaryDirectory() as tmp:
            child=Mock(return_value=(2,b''));c=web.Container(Path(tmp),child,TOKEN,IMAGE,COMMIT,{})
            c.cid=CID
            with patch.object(c,'inspect'),patch.object(web.time,'sleep'):
                with self.assertRaisesRegex(web.Blocked,'STARTUP_TIMEOUT'):c.process_ready()
            self.assertEqual(child.call_count,20)
            for call in child.call_args_list:
                self.assertEqual(call.kwargs,{'limit':4096,'timeout':25})

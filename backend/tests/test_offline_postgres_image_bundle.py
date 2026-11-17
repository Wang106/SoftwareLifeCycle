"""Non-runnable synthetic archives and mocked processes only; no Docker runtime."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import offline_postgres_image_bundle as m
except ModuleNotFoundError:
    m = None
COMMIT = 'a' * 40


def tar_bytes(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        for name, raw in entries:
            info = tarfile.TarInfo(name); info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    return output.getvalue()


class PostgresBundleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'missing independent PostgreSQL image bundle capability')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.dest = self.root / 'handoff'
        self.layers = [tar_bytes([('NON_RUNNABLE_TEXT', b'synthetic fixture ' + bytes([n]))]) for n in range(2)]
        self.config = {'architecture':'amd64', 'os':'linux', 'created':'2026-11-05T07:30:43.99618368Z', 'config': {
            'Env':['PGDATA=/var/lib/postgresql/data'], 'Entrypoint':['docker-entrypoint.sh'],
            'Cmd':['postgres'], 'Volumes':{'/var/lib/postgresql/data':{}}},
            'rootfs':{'type':'layers', 'diff_ids':['sha256:'+hashlib.sha256(x).hexdigest() for x in self.layers]}}
        self.raw_config = json.dumps(self.config).encode()
        self.image_id = 'sha256:' + hashlib.sha256(self.raw_config).hexdigest()
        for name,value in [('IMAGE_ID',self.image_id),('CONFIG_SIZE',len(self.raw_config)),('LAYER_COUNT',2)]:
            active = patch.object(m,name,value); active.start(); self.addCleanup(active.stop)
        self.make_archive()

    def make_archive(self, sources=False, extra=(), mutate=None):
        config_name = ('blobs/sha256/' if sources else '') + self.image_id[7:] + ('' if sources else '.json')
        layer_names = [('blobs/sha256/'+value[7:]) if sources else (str(i+1)*64+'/layer.tar')
                       for i,value in enumerate(self.config['rootfs']['diff_ids'])]
        record = {'Config':config_name,'RepoTags':None,'Layers':layer_names}
        if sources:
            record['LayerSources']={value:{'mediaType':'application/vnd.oci.image.layer.v1.tar',
                'digest':value,'size':len(raw)} for value,raw in zip(self.config['rootfs']['diff_ids'],self.layers)}
        if mutate: mutate(record)
        self.entries = [(config_name,self.raw_config),*zip(layer_names,self.layers),
                        ('manifest.json',json.dumps([record]).encode()),*extra]
        self.archive = tar_bytes(self.entries)

    def modern_archive(self, mutate_helper=None, mutate_manifest=None, mutate_index=None):
        self.make_archive(sources=True)
        descriptors=[{'mediaType':'application/vnd.oci.image.layer.v1.tar','digest':digest,'size':len(raw)}
                     for digest,raw in zip(self.config['rootfs']['diff_ids'],self.layers)]
        generated={'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json',
                   'config':{'mediaType':'application/vnd.oci.image.config.v1+json','digest':self.image_id,'size':len(self.raw_config)},
                   'layers':descriptors}
        if mutate_manifest:mutate_manifest(generated)
        raw=json.dumps(generated).encode();digest=hashlib.sha256(raw).hexdigest()
        index={'schemaVersion':2,'mediaType':'application/vnd.oci.image.index.v1+json',
               'manifests':[{'mediaType':'application/vnd.oci.image.manifest.v1+json','digest':'sha256:'+digest,'size':len(raw)}]}
        if mutate_index:mutate_index(index)
        self.entries += [('blobs/sha256/'+digest,raw),('index.json',json.dumps(index).encode()),
                         ('oci-layout',b'{"imageLayoutVersion":"1.0.0"}')]
        parent=''
        for i in range(len(self.layers)):
            ident=hashlib.sha256(('synthetic non-runnable id '+str(i)).encode()).hexdigest()
            helper={'id':ident,'created':'1970-01-01T00:00:00Z','os':'linux',
                    'container_config':{'Hostname':'','Domainname':'','User':'','Image':'','WorkingDir':'',
                        'AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'OpenStdin':False,'StdinOnce':False,
                        'Env':None,'Cmd':None,'Volumes':None,'Entrypoint':None,'OnBuild':None,'Labels':None}}
            if parent:helper['parent']=parent
            if i==len(self.layers)-1:
                helper.update(created=self.config['created'],architecture='amd64',
                              config={**helper['container_config'],**self.config['config']})
            if mutate_helper:mutate_helper(i,helper)
            raw=json.dumps(helper).encode()
            self.entries.append(('blobs/sha256/'+hashlib.sha256(raw).hexdigest(),raw));parent=ident
        self.archive=tar_bytes(self.entries)

    def export(self):
        def save(file, env):
            self.assertEqual(set(env), {'PATH','HOME','LANG','DOCKER_CONFIG'})
            self.assertEqual(list(Path(env['DOCKER_CONFIG']).iterdir()), [])
            m.base.write_bytes(file,self.archive); file.written()
        with patch.object(m,'source_binding') as source, patch.object(m,'inspect_local_image') as inspect, \
             patch.object(m,'save_image',side_effect=save) as saved, \
             patch.object(m.os,'fstatvfs',return_value=type('Space',(),{'f_bavail':32*1024**3,'f_frsize':1})()):
            result = m.run(COMMIT,self.dest)
            self.assertGreaterEqual(source.call_count,2); inspect.assert_called_once(); saved.assert_called_once()
            return result

    def verify(self,result):
        return m.verify_bundle(self.dest,expected_commit=COMMIT,expected_manifest_sha256=result['manifest_sha256'])

    def test_legacy_roundtrip_readonly_no_process(self):
        result=self.export()
        self.assertEqual(result['status'],m.EXPORTED)
        before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.dest.iterdir()}
        with patch('subprocess.Popen',side_effect=AssertionError),patch.object(m,'source_binding',side_effect=AssertionError):
            self.assertEqual(self.verify(result)['status'],m.VERIFIED)
        self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.dest.iterdir()})
        self.assertEqual(set(before),m.FILES|{'COMPLETE'})
        self.assertEqual(self.dest.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in self.dest.iterdir()))

    def test_layersources_roundtrip(self):
        self.make_archive(sources=True);self.verify(self.export())

    def test_defaults_help_and_import_have_no_runtime(self):
        with patch('subprocess.Popen',side_effect=AssertionError),contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main([]),2)
            with self.assertRaises(SystemExit) as error:m.main(['--help'])
            self.assertEqual(error.exception.code,0)
            self.assertEqual(m.main(['export','--expected-commit',COMMIT,'--destination',str(self.dest)]),2)
        self.assertFalse(self.dest.exists())

    def test_external_expectations_required(self):
        result=self.export()
        for commit,digest in [('b'*40,result['manifest_sha256']),(COMMIT,'f'*64),(None,None),(True,False)]:
            with self.subTest(commit=commit),self.assertRaises(m.base.BundleError):
                m.verify_bundle(self.dest,expected_commit=commit,expected_manifest_sha256=digest)

    def test_unknown_payload_duplicates_and_traversal_fail(self):
        for extra in [('secret.txt',b'secret'),('../escape',b'x'),('/absolute',b'x'),('manifest.json',b'[]'),('a\\b',b'x')]:
            with self.subTest(extra=extra):
                self.make_archive(extra=[extra])
                with self.assertRaises(m.base.BundleError):self.export()
                self.assertFalse((self.dest/'COMPLETE').exists());self.dest=self.root/('next'+str(len(list(self.root.iterdir()))))

    def test_tags_and_unreviewed_manifest_fields_fail(self):
        for key,value in [('RepoTags',['evil:latest']),('RepoTags',{}),('Extra',True),('Layers',[]),('Config','config.json')]:
            with self.subTest(key=key):
                self.make_archive(mutate=lambda x:x.update({key:value}))
                with self.assertRaises(m.base.BundleError):self.export()
                self.assertFalse((self.dest/'COMPLETE').exists());self.dest=self.root/('next'+str(len(list(self.root.iterdir()))))

    def test_order_and_descriptor_integrity_fail(self):
        mutations=[lambda r:r['Layers'].reverse(),lambda r:r['LayerSources'][next(iter(r['LayerSources']))].update(size=True),
                   lambda r:r['LayerSources'][next(iter(r['LayerSources']))].update(mediaType='application/vnd.oci.image.layer.v1.tar+gzip'),
                   lambda r:r['LayerSources'][next(iter(r['LayerSources']))].update(urls=['https://invalid'])]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.make_archive(sources=True,mutate=mutate)
                with self.assertRaises(m.base.BundleError):self.export()
                self.dest=self.root/('next'+str(len(list(self.root.iterdir()))))

    def test_fixed_original_config_not_reserialized(self):
        self.raw_config=b' '+self.raw_config;self.make_archive()
        with self.assertRaises(m.base.BundleError):self.export()

    def test_inner_layer_must_be_tar_even_legacy(self):
        self.layers[0]=b'not a tar'
        self.config['rootfs']['diff_ids'][0]='sha256:'+hashlib.sha256(self.layers[0]).hexdigest()
        self.raw_config=json.dumps(self.config).encode();self.image_id='sha256:'+hashlib.sha256(self.raw_config).hexdigest()
        with patch.object(m,'IMAGE_ID',self.image_id),patch.object(m,'CONFIG_SIZE',len(self.raw_config)):
            self.make_archive()
            with self.assertRaises(m.base.BundleError):self.export()

    def test_special_outer_and_trailing_garbage_fail(self):
        for kind in [tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.FIFOTYPE,tarfile.CHRTYPE]:
            output=io.BytesIO()
            with tarfile.open(fileobj=output,mode='w') as tf:
                info=tarfile.TarInfo('special');info.type=kind;info.linkname='target';tf.addfile(info)
            self.archive=output.getvalue()
            with self.subTest(kind=kind),self.assertRaises(m.base.BundleError):self.export()
            self.dest=self.root/('next'+str(len(list(self.root.iterdir()))))
        self.make_archive();self.archive+=b'x'*512
        with self.assertRaises(m.base.BundleError):self.export()

    def test_files_links_extra_or_marker_rejected(self):
        result=self.export();(self.dest/'unknown').write_text('x')
        with self.assertRaises(m.base.BundleError):self.verify(result)
        (self.dest/'unknown').unlink();os.link(self.dest/'manifest.json',self.root/'link')
        with self.assertRaises(m.base.BundleError):self.verify(result)
        (self.root/'link').unlink();(self.dest/'COMPLETE').write_bytes(b'not complete')
        with self.assertRaises(m.base.BundleError):self.verify(result)

    def test_destination_collision_and_symlink_refused_before_daemon(self):
        self.dest.mkdir()
        with patch.object(m,'inspect_local_image',side_effect=AssertionError),self.assertRaises(m.base.BundleError):m.run(COMMIT,self.dest)
        link=self.root/'link';link.symlink_to(self.dest,target_is_directory=True)
        with patch.object(m,'inspect_local_image',side_effect=AssertionError),self.assertRaises(m.base.BundleError):m.run(COMMIT,link/'bundle')

    def test_no_marker_on_payload_failure(self):
        with patch.object(m,'verify_files',side_effect=RuntimeError('SECRET')):
            with self.assertRaises(m.base.BundleError) as error:self.export()
        self.assertNotIn('SECRET',str(error.exception));self.assertFalse((self.dest/'COMPLETE').exists())

    def test_no_marker_on_payload_close_failure(self):
        original=m.base.Descriptor.close
        def close(handle):
            target=os.readlink('/proc/self/fd/'+str(handle.fd)) if handle.fd is not None else ''
            original(handle)
            if target==str(self.dest/'postgres.tar'):raise OSError('SECRET')
        with patch.object(m.base.Descriptor,'close',close),self.assertRaises(m.base.BundleError):self.export()
        self.assertFalse((self.dest/'COMPLETE').exists())

    def test_final_marker_close_failure_is_uncertain(self):
        original=m.base.Descriptor.close
        def close(handle):
            target=os.readlink('/proc/self/fd/'+str(handle.fd)) if handle.fd is not None else ''
            original(handle)
            if target==str(self.dest/'COMPLETE'):raise OSError('SECRET')
        with patch.object(m.base.Descriptor,'close',close),self.assertRaises(m.base.BundleError) as error:self.export()
        self.assertEqual(error.exception.code,'BUNDLE_COMPLETION_UNCERTAIN');self.assertIsNotNone(error.exception.receipt)

    def test_final_stdout_failure_reports_uncertain(self):
        result={'status':m.EXPORTED,'source_commit':COMMIT,'manifest_sha256':'b'*64}
        class Broken(io.StringIO):
            def write(self,_):raise BrokenPipeError('SECRET')
        err=io.StringIO()
        with patch.object(m,'run',return_value=result),contextlib.redirect_stdout(Broken()),contextlib.redirect_stderr(err):
            self.assertEqual(m.main(['export','--run','--expected-commit',COMMIT,'--destination',str(self.dest)]),2)
        self.assertIn('BUNDLE_COMPLETION_UNCERTAIN',err.getvalue());self.assertNotIn('SECRET',err.getvalue())

    def test_successful_export_stdout_systemexit_preserves_uncertain_receipt(self):
        result={'status':m.EXPORTED,'source_commit':COMMIT,'manifest_sha256':'b'*64}
        class Exiting(io.StringIO):
            def write(self,_):raise SystemExit(17)
        err=io.StringIO()
        with patch.object(m,'run',return_value=result),contextlib.redirect_stdout(Exiting()),contextlib.redirect_stderr(err):
            self.assertEqual(m.main(['export','--run','--expected-commit',COMMIT,'--destination',str(self.dest)]),2)
        self.assertIn('BUNDLE_COMPLETION_UNCERTAIN',err.getvalue())
        self.assertIn(COMMIT,err.getvalue());self.assertIn('b'*64,err.getvalue())

    def test_help_systemexit_is_propagated_without_uncertain_receipt(self):
        err=io.StringIO()
        with patch('subprocess.Popen',side_effect=AssertionError),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as error:m.main(['--help'])
        self.assertEqual(error.exception.code,0);self.assertEqual(err.getvalue(),'')

    def test_export_systemexit_without_completed_receipt_is_propagated(self):
        err=io.StringIO()
        with patch.object(m,'run',side_effect=SystemExit(17)),contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as error:
                m.main(['export','--run','--expected-commit',COMMIT,'--destination',str(self.dest)])
        self.assertEqual(error.exception.code,17);self.assertEqual(err.getvalue(),'')

    def test_verify_stdout_systemexit_does_not_claim_export_uncertain(self):
        result={'status':m.VERIFIED,'source_commit':COMMIT,'manifest_sha256':'b'*64}
        class Exiting(io.StringIO):
            def write(self,_):raise SystemExit(19)
        err=io.StringIO()
        with patch.object(m,'verify_bundle',return_value=result),contextlib.redirect_stdout(Exiting()),contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as error:
                m.main(['verify','--expected-commit',COMMIT,'--directory',str(self.dest),'--expected-manifest-sha256','b'*64])
        self.assertEqual(error.exception.code,19);self.assertEqual(err.getvalue(),'')

    def test_inspection_requires_fixed_id_repository_and_platform(self):
        good=[{'Id':self.image_id,'RepoDigests':[m.REFERENCE],'Os':'linux','Architecture':'amd64'}]
        for key,value in [('Id','sha256:'+'b'*64),('RepoDigests',[]),('RepoDigests',[m.REFERENCE+'x']),('Os','windows'),('Architecture','arm64'),('Variant','v8')]:
            bad=copy.deepcopy(good);bad[0][key]=value
            with self.subTest(key=key),patch.object(m,'command',return_value=json.dumps(bad).encode()),patch.object(m.shutil,'which',return_value='/usr/bin/docker'),self.assertRaises(m.base.BundleError):m.inspect_local_image({})
        with patch.object(m,'command',return_value=json.dumps(good).encode()) as cmd,patch.object(m.shutil,'which',return_value='/usr/bin/docker'):
            m.inspect_local_image({});self.assertEqual(cmd.call_args.args[0][-3:],['image','inspect',self.image_id])

    def test_existing_timer_is_not_overwritten(self):
        with patch.object(m.signal,'getitimer',return_value=(10.0,0.0)),patch.object(m.signal,'setitimer') as timer,self.assertRaises(m.base.BundleError):
            with m.bounded(1):pass
        timer.assert_not_called()

    def test_empty_readonly_command_output_is_valid(self):
        reader,writer=os.pipe();os.close(writer)
        class Process:
            stdout=os.fdopen(reader,'rb');returncode=0
            def wait(self,**_):return 0
        with patch.object(m.subprocess,'Popen',return_value=Process()):
            self.assertEqual(m.command(['mock-git'],{}),b'')

    def test_source_binding_works_as_main_without_import_alias(self):
        names=sorted('scripts/'+name+'.py' for name in m.SOURCES)
        def command(args,_env,**_kwargs):
            if 'rev-parse' in args:return (COMMIT+'\n').encode()
            if 'status' in args:return b''
            if 'ls-tree' in args:
                return b''.join(('100644 blob '+str(i)*40+'\t'+name+'\0').encode() for i,name in enumerate(names,1))
            if 'cat-file' in args:return (ROOT/names[int(args[-1][0])-1]).read_bytes()
            self.fail('unexpected command')
        with patch.dict(sys.modules,{},clear=False),patch.object(m,'command',side_effect=command),patch.object(m.shutil,'which',return_value='/usr/bin/git'):
            sys.modules.pop('offline_postgres_image_bundle')
            m.source_binding(COMMIT)

    def test_moby_utc_oci_helpers_roundtrip(self):
        self.modern_archive();self.verify(self.export())

    def test_moby_helper_extra_fields_or_altered_values_fail(self):
        changes=[('secret','PRIVATE'),('container_config',{}),('created','1970-01-01T01:00:00+01:00'),
                 ('parent','f'*64),('os','windows'),('id',True)]
        for key,value in changes:
            with self.subTest(key=key):
                self.modern_archive(mutate_helper=lambda i,x:x.update({key:value}) if i==0 else None)
                with self.assertRaises(m.base.BundleError):self.export()
                self.dest=self.root/('next'+str(len(list(self.root.iterdir()))))

    def test_moby_helper_complete_single_chain_required(self):
        self.modern_archive();self.entries=self.entries[:-1];self.archive=tar_bytes(self.entries)
        with self.assertRaises(m.base.BundleError):self.export()
        self.dest=self.root/'again'
        self.modern_archive(mutate_helper=lambda i,x:x.pop('parent',None) if i==1 else None)
        with self.assertRaises(m.base.BundleError):self.export()

    def test_moby_oci_manifest_is_not_upstream_gzip_manifest(self):
        def mutate(value):value['layers'][0]['mediaType']+=' +gzip'
        self.modern_archive(mutate_manifest=mutate)
        with self.assertRaises(m.base.BundleError):self.export()

    def test_moby_oci_annotations_urls_and_types_rejected(self):
        changes=[lambda x:x['manifests'][0].update(annotations={'name':'private'}),
                 lambda x:x.update(schemaVersion=True),lambda x:x['manifests'][0].update(size=True),
                 lambda x:x['manifests'][0].update(urls=['https://invalid'])]
        for change in changes:
            with self.subTest(change=change):
                self.modern_archive(mutate_index=change)
                with self.assertRaises(m.base.BundleError):self.export()
                self.dest=self.root/('next'+str(len(list(self.root.iterdir()))))

    def test_moby_oci_helper_blob_name_hash_is_verified(self):
        self.modern_archive();name,raw=self.entries[-1];self.entries[-1]=(name,b' '+raw);self.archive=tar_bytes(self.entries)
        with self.assertRaises(m.base.BundleError):self.export()

    def test_no_unknown_oci_sidecar_or_helpers_in_minimal_profile(self):
        self.make_archive(sources=True,extra=[('oci-layout',b'{"imageLayoutVersion":"1.0.0"}')])
        with self.assertRaises(m.base.BundleError):self.export()

    def test_archive_directory_ancestors_only(self):
        self.make_archive(sources=True)
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w') as tf:
            for name in ['blobs','blobs/sha256']:
                info=tarfile.TarInfo(name);info.type=tarfile.DIRTYPE;tf.addfile(info)
            for name,raw in self.entries:
                info=tarfile.TarInfo(name);info.size=len(raw);tf.addfile(info,io.BytesIO(raw))
        self.archive=output.getvalue();self.verify(self.export())
        self.dest=self.root/'bad'
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w') as tf:
            info=tarfile.TarInfo('unrelated');info.type=tarfile.DIRTYPE;tf.addfile(info)
            for name,raw in self.entries:
                info=tarfile.TarInfo(name);info.size=len(raw);tf.addfile(info,io.BytesIO(raw))
        self.archive=output.getvalue()
        with self.assertRaises(m.base.BundleError):self.export()

    def test_duplicate_json_keys_rejected(self):
        self.entries=[(name,b'[{"Config":"x","Config":"y","RepoTags":null,"Layers":[]}]' if name=='manifest.json' else raw)
                      for name,raw in self.entries];self.archive=tar_bytes(self.entries)
        with self.assertRaises(m.base.BundleError):self.export()

    def test_free_space_checked_before_daemon(self):
        with patch.object(m,'source_binding'),patch.object(m,'inspect_local_image') as inspect, \
             patch.object(m.os,'fstatvfs',return_value=type('Space',(),{'f_bavail':1,'f_frsize':1})()),self.assertRaises(m.base.BundleError):
            m.run(COMMIT,self.dest)
        inspect.assert_not_called();self.assertFalse(self.dest.exists())

    def test_no_marker_on_save_failure_and_no_retry(self):
        with patch.object(m,'source_binding'),patch.object(m,'inspect_local_image'), \
             patch.object(m,'save_image',side_effect=TimeoutError('SECRET')) as save,self.assertRaises(m.base.BundleError):
            m.run(COMMIT,self.dest)
        save.assert_called_once();self.assertFalse((self.dest/'COMPLETE').exists())

    def test_inherited_docker_overrides_rejected(self):
        for key in m.FORBIDDEN_ENV:
            with self.subTest(key=key),patch.dict(os.environ,{key:'SECRET'}),patch.object(m,'source_binding') as source,self.assertRaises(m.base.BundleError):
                m.run(COMMIT,self.dest)
            source.assert_not_called()

    def test_save_command_is_fixed_id_only(self):
        with patch.object(m,'command') as command,patch.object(m.shutil,'which',return_value='/usr/bin/docker'):
            marker=object();m.save_image(marker,{'DOCKER_CONFIG':'/private'})
            self.assertEqual(command.call_args.args[0],['/usr/bin/docker','--host=unix:///var/run/docker.sock','image','save',self.image_id])
            self.assertIs(command.call_args.kwargs['sink'],marker)

    def test_fsync_before_marker_failure_never_completes(self):
        with patch.object(m.os,'fsync',side_effect=OSError('SECRET')),self.assertRaises(m.base.BundleError):self.export()
        self.assertFalse((self.dest/'COMPLETE').exists())

    def test_post_marker_directory_fsync_is_uncertain(self):
        original=m.os.fsync
        def sync(fd):
            if (self.dest/'COMPLETE').exists() and os.readlink('/proc/self/fd/'+str(fd))==str(self.dest):raise OSError('SECRET')
            return original(fd)
        with patch.object(m.os,'fsync',side_effect=sync),self.assertRaises(m.base.BundleError) as error:self.export()
        self.assertEqual(error.exception.code,'BUNDLE_COMPLETION_UNCERTAIN')

    def test_interruption_during_verification_never_completes(self):
        previous=signal.getsignal(signal.SIGTERM)
        with patch.object(m,'verify_files',side_effect=KeyboardInterrupt),self.assertRaises(m.base.BundleError):self.export()
        self.assertFalse((self.dest/'COMPLETE').exists());self.assertEqual(signal.getsignal(signal.SIGTERM),previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))

    def test_readonly_verifier_rejects_symlink_and_fifo(self):
        result=self.export();path=self.dest/'evidence.json';saved=path.read_bytes();path.unlink()
        target=self.root/'evidence';target.write_bytes(saved);path.symlink_to(target)
        with self.assertRaises(m.base.BundleError):self.verify(result)
        path.unlink();os.mkfifo(path)
        with self.assertRaises(m.base.BundleError):self.verify(result)

    def test_outer_budget_exhaustion_fails_closed(self):
        with patch.object(m.base,'MAX_OUTER_HEADERS',1),self.assertRaises(m.base.BundleError):self.export()

    def test_tool_binding_rejects_dirty_head_and_missing_source(self):
        for value in [b' M scripts/offline_postgres_image_bundle.py\n',b'?? unexpected\n']:
            def command(args,_env,**_kwargs):return (COMMIT+'\n').encode() if 'rev-parse' in args else value
            with self.subTest(value=value),patch.object(m,'command',side_effect=command),patch.object(m.shutil,'which',return_value='/usr/bin/git'),self.assertRaises(m.base.BundleError):m.source_binding(COMMIT)

    def test_official_contract_constants_are_fixed(self):
        source=(ROOT/'scripts/offline_postgres_image_bundle.py').read_text()
        self.assertIn("IMAGE_ID = 'sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f'",source)
        self.assertIn('CONFIG_SIZE = 10133',source);self.assertIn('LAYER_COUNT = 14',source)
        self.assertIn('5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e',source)

    def test_each_legacy_helper_is_limited_to_16_kib(self):
        self.modern_archive();name,raw=self.entries[-1];raw=b' '*16384+raw
        self.entries[-1]=('blobs/sha256/'+hashlib.sha256(raw).hexdigest(),raw)
        self.archive=tar_bytes(self.entries)
        with self.assertRaises(m.base.BundleError):self.export()

    def test_process_output_capacity_and_cleanup_are_bounded(self):
        reader,writer=os.pipe();os.write(writer,b'overflow');os.close(writer)
        class Process:
            stdout=os.fdopen(reader,'rb');returncode=None;pid=123456789
            def wait(self,**_):self.returncode=-9;return self.returncode
        with patch.object(m.subprocess,'Popen',return_value=Process()) as spawned,patch.object(m.os,'killpg') as killed,self.assertRaises(m.base.BundleError):
            m.command(['mock'],{},limit=2)
        spawned.assert_called_once();killed.assert_called_once_with(123456789,signal.SIGKILL)

    def test_empty_save_output_rejected(self):
        reader,writer=os.pipe();os.close(writer)
        class Process:
            stdout=os.fdopen(reader,'rb');returncode=0
            def wait(self,**_):return 0
        with patch.object(m.subprocess,'Popen',return_value=Process()),self.assertRaises(m.base.BundleError):
            m.command(['mock-save'],{},sink=object())

    def test_source_commit_and_manifest_types_are_exact(self):
        result=self.export();manifest=json.loads((self.dest/'manifest.json').read_bytes())
        for key,value in [('source_commit',True),('format','other'),('contract',{}),('image',{'archive':'postgres.tar','size':True,'sha256':'a'*64})]:
            bad=copy.deepcopy(manifest);bad[key]=value;raw=json.dumps(bad).encode();(self.dest/'manifest.json').write_bytes(raw)
            with self.subTest(key=key),self.assertRaises(m.base.BundleError):
                m.verify_bundle(self.dest,expected_commit=COMMIT,expected_manifest_sha256=hashlib.sha256(raw).hexdigest())

    def test_same_inode_content_change_rejected(self):
        result=self.export();original=m.archive_gate
        def changed(file,item):
            raw=(self.dest/'postgres.tar').read_bytes()
            with (self.dest/'postgres.tar').open('r+b') as stream:stream.write(raw)
            return original(file,item)
        with patch.object(m,'archive_gate',side_effect=changed),self.assertRaises(m.base.BundleError):self.verify(result)

    def test_unknown_options_are_redacted(self):
        err=io.StringIO()
        with contextlib.redirect_stderr(err):self.assertEqual(m.main(['export','--secret','PASSWORD']),2)
        self.assertNotIn('PASSWORD',err.getvalue());self.assertNotIn('--secret',err.getvalue())

    def test_import_executes_no_process(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('postgres_import_probe',ROOT/'scripts/offline_postgres_image_bundle.py')
        module=importlib.util.module_from_spec(spec)
        with patch('subprocess.Popen',side_effect=AssertionError):spec.loader.exec_module(module)

    def test_marker_creation_interrupt_preserves_uncertain_outcome(self):
        original=m.base.File
        def create(directory,name,stack,**kwargs):
            file=original(directory,name,stack,**kwargs)
            if name=='COMPLETE' and kwargs.get('create'):raise KeyboardInterrupt()
            return file
        with patch.object(m.base,'File',side_effect=create),self.assertRaises(m.base.BundleError) as error:self.export()
        self.assertEqual(error.exception.code,'BUNDLE_COMPLETION_UNCERTAIN')
        self.assertTrue((self.dest/'COMPLETE').exists())

    def test_original_application_gate_unchanged(self):
        self.assertEqual(m.base.FILES,frozenset({'api.tar','web.tar','manifest.json','evidence.json'}))
        raw=(ROOT/'scripts/offline_readonly_preflight.py').read_text()
        self.assertIn('image revision label mismatch',raw);self.assertIn('image-declared writable volumes refused',raw)


class CurrentPostgresHandoffTests(unittest.TestCase):
    def test_fixed_contract_matches_current_rehearsal_without_runtime_import(self):
        import ast
        def constants(path):
            result={}
            for node in ast.parse(path.read_text()).body:
                if isinstance(node,ast.Assign):
                    for name in node.targets:
                        if isinstance(name,ast.Name) and name.id in ('PG_IMAGE','PG_ID','REFERENCE','IMAGE_ID'):
                            result[name.id]=ast.literal_eval(node.value)
            return result
        original=constants(ROOT/'scripts/offline_migration_database_rehearsal.py')
        candidate=constants(ROOT/'scripts/offline_postgres_image_bundle.py')
        self.assertEqual(candidate['REFERENCE'],original['PG_IMAGE'])
        self.assertEqual(candidate['IMAGE_ID'],original['PG_ID'])

    def test_real_clean_git_source_binding_and_dirty_refusal(self):
        import subprocess
        with tempfile.TemporaryDirectory() as location:
            root=Path(location);scripts=root/'scripts';scripts.mkdir()
            for name in m.SOURCES:
                (scripts/(name+'.py')).write_bytes((ROOT/'scripts'/(name+'.py')).read_bytes())
            env={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,
                 'GIT_AUTHOR_NAME':'Synthetic','GIT_AUTHOR_EMAIL':'test@example.invalid',
                 'GIT_COMMITTER_NAME':'Synthetic','GIT_COMMITTER_EMAIL':'test@example.invalid'}
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,env=env,stderr=subprocess.DEVNULL)
            git('init','-q');git('add','scripts')
            git('-c','commit.gpgsign=false','commit','-qm','Synthetic tool binding')
            commit=git('rev-parse','HEAD').decode().strip()
            with patch.object(m,'ROOT',root),patch.object(m,'__file__',str(scripts/'offline_postgres_image_bundle.py')), \
                 patch.object(m.base,'__file__',str(scripts/'offline_image_bundle.py')), \
                 patch.object(m.base.preflight,'__file__',str(scripts/'offline_readonly_preflight.py')):
                m.source_binding(commit)
                (scripts/'offline_image_bundle.py').write_text('uncommitted change')
                with self.assertRaises(m.base.BundleError):m.source_binding(commit)

    def test_short_success_receipt_reports_uncertain_without_retry(self):
        class Short:
            def write(self,value): return max(0,len(value)-1)
            def flush(self): pass
        receipt={'status':m.EXPORTED,'source_commit':COMMIT,'manifest_sha256':'b'*64}
        errors=io.StringIO()
        with patch.object(m,'run',return_value=receipt) as run, \
             patch.object(m.sys,'stdout',Short()),contextlib.redirect_stderr(errors):
            result=m.main(['export','--run','--expected-commit',COMMIT,'--destination','/unused'])
        self.assertEqual(result,2)
        run.assert_called_once()
        self.assertIn('BUNDLE_COMPLETION_UNCERTAIN',errors.getvalue())
        self.assertIn('b'*64,errors.getvalue())

    def test_abbreviated_execution_options_rejected_before_export(self):
        with patch.object(m,'run') as run,contextlib.redirect_stderr(io.StringIO()):
            result=m.main(['export','--run','--expected-comm',COMMIT,'--dest','/unused'])
        self.assertEqual(result,2)
        run.assert_not_called()

    def test_broken_diagnostic_stream_still_returns_failure(self):
        class Broken:
            def write(self,value): raise OSError('PRIVATE_DIAGNOSTIC')
            def flush(self): raise OSError('PRIVATE_DIAGNOSTIC')
        with patch.object(m.sys,'stderr',Broken()):
            self.assertEqual(m.main(['invalid']),2)


if __name__=='__main__':unittest.main()

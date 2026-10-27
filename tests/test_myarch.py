"""Offline contract tests; every temporary write stays under this repository."""
import contextlib
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
from myarch import common, audit, snapshot, plan, engine, validation, discovery, resources

REAL_ROOT=common.ROOT


class Isolated(unittest.TestCase):
    def setUp(self):
        (REAL_ROOT/'tests/.tmp').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=REAL_ROOT/'tests/.tmp')
        self.root=Path(self.temp.name)
        self.home=self.root/'fixture-home'
        self.config=self.home/'.config'
        self.config.mkdir(parents=True)
        self.stack=contextlib.ExitStack()
        self.stack.enter_context(patch.dict(os.environ, {'PATH':'/usr/bin', 'HOME':str(self.home)}, clear=True))
        for mod in [common,audit,snapshot,plan,engine,validation,discovery,resources]:
            for attr,value in [('ROOT',self.root),('HOME',self.home),('CONFIG',self.config)]:
                if hasattr(mod,attr):
                    self.stack.enter_context(patch.object(mod,attr,value))
        for p in (REAL_ROOT/'config/profiles').glob('*.json'):
            common.atomic_bytes(self.root/'config/profiles'/p.name,p.read_bytes())
        common.atomic_bytes(self.root/'config/policy.json',(REAL_ROOT/'config/policy.json').read_bytes())

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def make_capture(self):
        p=self.config/'foot/foot.ini';p.parent.mkdir();p.write_text('font=Example\n')
        item={**common.record_file(p),'restore':'portable_candidate','risks':[]}
        common.atomic_json(self.root/'manifests/dotfiles.json',{'entries':[item],'include_graph':[]})
        data=snapshot.capture()
        return snapshot.load_snapshot(data['id'])

    def fake_query(self,argv,*args,**kwargs):
        output={('pacman','-Q'):'foot 1.0\nfish 1.0\n',('pacman','-Qeq'):'foot\nfish\n',
                ('pacman','-Qmq'):'fish\n',('pacman','-Qdtq'):'',('pacman','-Qg'):'',
                ('pacman','-Sl'):'extra foot 1.1\n',('pacman-conf','--repo-list'):'core\nextra\n'}
        return {'status':'ok','returncode':0,'argv':argv,'stdout':output.get(tuple(argv),'')}

    def test_secret_detection(self):
        for name in ['.env','fish_variables','id_ed25519','auth.json','history.txt','credentials.ini']:
            self.assertTrue(common.sensitive(name),name)
        for value in [b'password = "supersecret"',b'export API_KEY=abc123456789',b'-----BEGIN OPENSSH PRIVATE KEY-----',b'https://u:pass@example.com']:
            self.assertTrue(common.sensitive('config',value),value)
        self.assertFalse(common.sensitive('config',b'font=JetBrains Mono\n'))

    def test_relative_and_blob_boundaries(self):
        for path in ['/etc/passwd','../escape','config/../../escape','config//a','.','config/./a']:
            with self.assertRaises(ValueError):snapshot.safe_relative(path)
        with self.assertRaises(ValueError):snapshot.blob_path('../escape')

    def test_capture_exact_and_tamper_detection(self):
        snap=self.make_capture()
        self.assertEqual(snapshot.verify(snap),[])
        e=snap['entries'][0]
        self.assertEqual(snapshot.blob_path(e['sha256']).read_bytes(),b'font=Example\n')
        snapshot.blob_path(e['sha256']).write_bytes(b'tampered')
        self.assertTrue(snapshot.verify(snap))

    def test_capture_metadata_tampering_rejected(self):
        snap=self.make_capture()
        snap['entries'][0]['restore']='malicious_change'
        common.atomic_json(self.root/'dotfiles/snapshots'/f"{snap['id']}.json",snap)
        with self.assertRaisesRegex(ValueError,'metadata checksum'):
            snapshot.load_snapshot(snap['id'])

    def test_private_wallpaper_capture_and_staging(self):
        snap=self.make_capture()
        image=self.home/'Pictures/current.png';image.parent.mkdir();image.write_bytes(b'PNG fake test fixture')
        link=self.home/'.local/state/caelestia/wallpaper/current';link.parent.mkdir(parents=True);link.symlink_to(image)
        common.atomic_json(self.root/'manifests/applications.json',{'sddm':{}})
        with patch.object(snapshot,'now',return_value='2030-01-01T00:00:00+00:00'):
            result=snapshot.capture()
        captured=snapshot.load_snapshot(result['id'])
        wallpaper=next(r for r in captured['resources'] if r['kind']=='current_wallpaper')
        self.assertEqual(wallpaper['restore'],'manual_reference_only')
        tx=engine.stage(captured['id'])
        asset=wallpaper
        dest=Path(tx['reference_assets'])/asset['sha256']/asset['name']
        self.assertEqual(dest.read_bytes(),image.read_bytes())

    def test_changed_source_not_captured(self):
        snap=self.make_capture()
        (self.config/'foot/foot.ini').write_text('font=Changed\n')
        with patch.object(snapshot,'now',return_value='2030-01-01T00:00:00+00:00'):
            captured=snapshot.capture()
        self.assertEqual(captured['captured'],0)
        self.assertEqual(captured['excluded'][0]['reason'],'changed_since_audit_or_unsafe')

    def test_source_symlink_not_captured(self):
        p=self.config/'safe.ini';p.symlink_to(self.config/'missing')
        self.assertEqual(common.record_file(p)['status'],'symlink_manual')

    def test_config_dependency_parser_does_not_execute(self):
        hypr=self.config/'hypr';hypr.mkdir()
        marker=self.root/'executed'
        (hypr/'hyprland.conf').write_text(f'$base = {hypr}\nsource = $base/monitor.conf\nexec-once = touch {marker}\n')
        (hypr/'monitor.conf').write_text('monitor = DP-1,1920x1080@144,0x0,1\n')
        result=audit.Audit().configurations()
        self.assertFalse(marker.exists())
        self.assertEqual(result['include_graph'][0]['status'],'resolved')
        parent=next(e for e in result['entries'] if e['source'].endswith('/hyprland.conf'))
        self.assertEqual(parent['restore'],'manual_review')

    def test_profile_deduplication_and_cycles(self):
        cats,_,_,info=plan.profiles(['desktop','laptop','desktop'])
        self.assertEqual(cats,{'desktop'})
        self.assertEqual(len(info),2)
        common.atomic_json(self.root/'config/profiles/a.json',{'extends':['b']})
        common.atomic_json(self.root/'config/profiles/b.json',{'extends':['a']})
        with self.assertRaises(ValueError):plan.profiles(['a'])
        with self.assertRaises(ValueError):plan.profiles(['../../escape'])

    def test_foreign_not_assumed_aur(self):
        with patch.object(audit,'run',side_effect=self.fake_query):
            data=audit.Audit().pacman()
        fish=next(p for p in data['packages'] if p['name']=='fish')
        self.assertEqual(fish['origin'],'foreign_unverified')
        self.assertEqual(fish['restore'],'manual_source_review')

    def test_source_host_guard_before_any_mutation(self):
        plan.source_guard()
        with self.assertRaisesRegex(ValueError,'source computer'):
            engine.apply()

    def test_symlink_destination_rejected(self):
        snap=self.make_capture();base=self.root/'staging/test/home';base.mkdir(parents=True)
        (base/'.config').symlink_to(self.config,target_is_directory=True)
        tx=engine.new_transaction('stage',snap['id'],base,base/'.config')
        with self.assertRaisesRegex(ValueError,'Symlink'):
            engine.deploy(snap['entries'],tx,False)
        self.assertEqual((self.config/'foot/foot.ini').read_text(),'font=Example\n')

    def test_stage_idempotent_backup_and_rollback(self):
        snap=self.make_capture()
        home=self.root/'staging/test/home';dest=home/'.config/foot/foot.ini'
        dest.parent.mkdir(parents=True);dest.write_text('original\n');dest.chmod(0o640)
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        engine.deploy(snap['entries'],tx,False)
        self.assertEqual(dest.read_text(),'font=Example\n')
        engine.deploy(snap['entries'],tx,False)
        self.assertEqual(len(tx['files']),1)
        result=engine.rollback(tx['id'])
        self.assertEqual(result['status'],'Rolled back')
        self.assertEqual(dest.read_text(),'original\n')
        self.assertEqual(dest.stat().st_mode & 0o777,0o640)

    def test_rollback_preserves_post_install_user_edits(self):
        snap=self.make_capture()
        tx=engine.stage(snap['id'])
        dest=Path(tx['config'])/'foot/foot.ini';dest.write_text('user edit\n')
        with self.assertRaisesRegex(ValueError,'changed after deployment'):
            engine.rollback(tx['id'])
        self.assertEqual(dest.read_text(),'user edit\n')

    def test_resume_after_interrupted_atomic_write(self):
        snap=self.make_capture();home=self.root/'staging/test/home'
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        original=engine.write_target
        def crash(*args):
            original(*args)
            raise KeyboardInterrupt()
        with patch.object(engine,'write_target',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):engine.deploy(snap['entries'],tx,False)
        self.assertEqual(next(iter(tx['files'].values()))['status'],'Installing')
        engine.deploy(snap['entries'],tx,False)
        self.assertEqual(next(iter(tx['files'].values()))['status'],'Installed')
        self.assertEqual(engine.rollback(tx['id'])['status'],'Rolled back')

    def test_resume_rejects_subsequent_edits(self):
        snap=self.make_capture();home=self.root/'staging/test/home'
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        engine.deploy(snap['entries'],tx,False)
        (home/'.config/foot/foot.ini').write_text('edited')
        with self.assertRaisesRegex(ValueError,'changed'):
            engine.deploy(snap['entries'],tx,False)

    def test_plan_repository_qualification_and_manual_hardware(self):
        snap=self.make_capture()
        def pkg(name,compat='portable',origin='repository_available_not_install_origin'):
            return {'name':name,'version':'1','category':'desktop','installation_reason':'explicit',
                    'compatibility':compat,'origin':origin,'evidence':'fixture','dependencies':[]}
        common.atomic_json(self.root/'manifests/packages.json',{'packages':[pkg('foot'),pkg('nvidia','nvidia_manual'),pkg('foreign',origin='foreign_unverified')]})
        def q(argv,*a,**kw):
            if argv==['pacman','-Q']:return {'status':'ok','stdout':''}
            if argv==['pacman','-Sl']:return {'status':'ok','stdout':'blackarch foot 99\nextra foot 2\n'}
            return {'status':'ok','stdout':''}
        with patch.object(plan,'run',side_effect=q):p=plan.make_plan(['desktop'],snap['id'])
        actions={a.get('name'):a for a in p['actions'] if a['kind']=='package'}
        self.assertEqual(actions['foot']['target'],'extra/foot')
        self.assertEqual(actions['nvidia']['status'],'Requires manual action')
        self.assertEqual(actions['foreign']['status'],'Requires manual action')
        self.assertEqual(plan.load_plan(p['id']),p)
        p['actions'][0]['name']='injected'
        common.atomic_json(self.root/'state/plans'/f"{p['id']}.json",p)
        with self.assertRaisesRegex(ValueError,'checksum'):plan.load_plan(p['id'])

    def test_bundle_and_checksum_failure(self):
        snap=self.make_capture();plan.source_guard()
        result=engine.backup_bundle(snap['id'])
        self.assertTrue(engine.check_bundle(result['bundle'])['valid'])
        bundle=Path(result['bundle'])
        first=next(iter(common.read_json(bundle/'bundle.json')['files']))
        (bundle/first).write_bytes(b'bad')
        self.assertFalse(engine.check_bundle(bundle)['valid'])

    def test_lock_conflict(self):
        with engine.project_lock():
            with self.assertRaisesRegex(ValueError,'Another'):
                with engine.project_lock():pass

    def test_interrupted_rollback_can_resume(self):
        snap=self.make_capture();home=self.root/'staging/test/home'
        dest=home/'.config/foot/foot.ini';dest.parent.mkdir(parents=True);dest.write_text('before')
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        engine.deploy(snap['entries'],tx,False)
        original=engine.write_target
        def crash(*args):
            original(*args)
            raise KeyboardInterrupt()
        with patch.object(engine,'write_target',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):engine.rollback(tx['id'])
        self.assertEqual(engine.rollback(tx['id'])['status'],'Rolled back')
        self.assertEqual(dest.read_text(),'before')

    def test_bundle_import_into_fresh_inventory(self):
        snap=self.make_capture();plan.source_guard()
        bundle=engine.backup_bundle(snap['id'])['bundle']
        for p in (self.root/'dotfiles').rglob('*'):
            if p.is_file():p.unlink()
        for p in (self.root/'manifests').glob('*.json'):p.unlink()
        # A real bundle includes package inventory; provide a minimal one for the fixture.
        meta=common.read_json(Path(bundle)/'bundle.json')
        raw=b'{"packages": []}\n'
        common.atomic_bytes(Path(bundle)/'manifests/packages.json',raw)
        meta['files']['manifests/packages.json']=common.digest(raw)
        common.atomic_json(Path(bundle)/'bundle.json',meta)
        result=engine.import_bundle(bundle)
        self.assertEqual(result['capture'],snap['id'])
        self.assertEqual(snapshot.verify(snapshot.load_snapshot(snap['id'])),[])

    def test_bundle_import_refuses_code_path(self):
        snap=self.make_capture();plan.source_guard()
        base=Path(engine.backup_bundle(snap['id'])['bundle'])
        meta=common.read_json(base/'bundle.json')
        common.atomic_bytes(base/'installer.sh',b'evil')
        meta['files']['installer.sh']=common.digest(b'evil')
        common.atomic_json(base/'bundle.json',meta)
        with self.assertRaisesRegex(ValueError,'Unexpected path'):
            engine.import_bundle(base)

    def test_live_engine_with_mock_package_manager(self):
        snap=self.make_capture()
        common.atomic_json(self.root/'manifests/packages.json',{'packages':[
            {'name':'foot','version':'1','category':'desktop','installation_reason':'explicit',
             'compatibility':'portable','origin':'repository_available_not_install_origin',
             'evidence':'fixture','dependencies':[]}]})
        installed={}
        def query(argv,*a,**kw):
            raw=''
            if argv==['pacman','-Q']:raw=''.join(k+' '+v+'\n' for k,v in installed.items())
            if argv==['pacman','-Sl']:raw='extra foot 2\n'
            return {'status':'ok','stdout':raw}
        with patch.object(plan,'run',side_effect=query):
            p=plan.make_plan(['desktop'],snap['id'])
            def install(argv,**kwargs):
                self.assertEqual(argv,['bash',str(self.root/'modules/packages.sh'),'extra/foot'])
                installed['foot']='2'
                return type('Result',(),{'returncode':0})()
            with patch.object(engine,'require_destination_host'), patch.object(engine,'run',return_value={'status':'ok','stdout':'extra\n'}), patch.object(engine.subprocess,'run',side_effect=install) as command:
                tx=engine.apply(p['id'])
                self.assertEqual(tx['packages']['status'],'Installed')
                command.assert_called_once()

    def test_permission_only_changes_and_rollback_conflict(self):
        snap=self.make_capture();home=self.root/'staging/test/home'
        dest=home/'.config/foot/foot.ini';dest.parent.mkdir(parents=True)
        dest.write_bytes(snapshot.blob_path(snap['entries'][0]['sha256']).read_bytes())
        dest.chmod(0o600)
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        engine.deploy(snap['entries'],tx,False)
        self.assertEqual(dest.stat().st_mode & 0o777,snap['entries'][0]['mode'])
        dest.chmod(0o640)
        with self.assertRaisesRegex(ValueError,'changed after deployment'):
            engine.rollback(tx['id'])
        self.assertEqual(dest.stat().st_mode & 0o777,0o640)

    def test_stage_cannot_escape_project(self):
        snap=self.make_capture()
        with self.assertRaises(ValueError):engine.stage(snap['id'],self.home/'overwrite')


if __name__=='__main__':unittest.main()

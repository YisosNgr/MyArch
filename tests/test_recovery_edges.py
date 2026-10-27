"""Failure injection at durable boundaries, using project-local fixtures only."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_myarch as fixtures
from myarch import common, engine, plan, snapshot, validation


class RecoveryEdges(unittest.TestCase):
    setUp=fixtures.Isolated.setUp
    tearDown=fixtures.Isolated.tearDown
    make_capture=fixtures.Isolated.make_capture

    def target(self):
        home=self.root/'staging/recovery/home'
        return home,home/'.config/foot/foot.ini'

    def planned(self):
        snap=self.make_capture()
        common.atomic_json(self.root/'manifests/packages.json',{'packages':[
            {'name':'foot','version':'1','category':'desktop','installation_reason':'explicit',
             'compatibility':'portable','origin':'repository_available_not_install_origin',
             'evidence':'fixture','dependencies':[]}]})
        installed={}
        def query(argv,*args,**kwargs):
            raw=''
            if argv==['pacman','-Q']:raw=''.join(k+' '+v+'\n' for k,v in installed.items())
            if argv==['pacman','-Sl']:raw='extra foot 2\n'
            return {'status':'ok','stdout':raw}
        self.stack.enter_context(patch.object(plan,'run',side_effect=query))
        self.stack.enter_context(patch.object(engine,'require_destination_host'))
        self.stack.enter_context(patch.object(engine,'run',return_value={'status':'ok','stdout':'extra\n'}))
        return snap,plan.make_plan(['desktop'],snap['id']),installed

    def test_rollback_after_crash_before_new_file_write(self):
        snap=self.make_capture();home,dest=self.target()
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        with patch.object(engine,'write_target',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):engine.deploy(snap['entries'],tx,False)
        result=engine.rollback(tx['id'])
        self.assertEqual(result['status'],'Rolled back')
        self.assertFalse(dest.exists())

    def test_rollback_after_crash_before_existing_file_write(self):
        snap=self.make_capture();home,dest=self.target()
        dest.parent.mkdir(parents=True);dest.write_text('original')
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        with patch.object(engine,'write_target',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):engine.deploy(snap['entries'],tx,False)
        self.assertEqual(engine.rollback(tx['id'])['status'],'Rolled back')
        self.assertEqual(dest.read_text(),'original')

    def test_resume_preserves_permission_edits_after_backup(self):
        snap=self.make_capture();home,dest=self.target()
        dest.parent.mkdir(parents=True);dest.write_text('original');dest.chmod(0o600)
        tx=engine.new_transaction('stage',snap['id'],home,home/'.config')
        with patch.object(engine,'write_target',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):engine.deploy(snap['entries'],tx,False)
        dest.chmod(0o640)
        with self.assertRaisesRegex(ValueError,'changed after backup'):
            engine.deploy(snap['entries'],tx,False)
        self.assertEqual(dest.read_text(),'original')
        self.assertEqual(dest.stat().st_mode & 0o777,0o640)

    def test_resume_checks_completed_files_before_package_mutation(self):
        snap,p,installed=self.planned()
        tx=engine.new_transaction('apply',p['id'],self.home,self.config)
        engine.deploy(snap['entries'],tx,False)
        (self.config/'foot/foot.ini').write_text('user edit')
        def worker(*a,**kw):
            installed['foot']='2'
            return type('Result',(),{'returncode':0})()
        with patch.object(engine.subprocess,'run',side_effect=worker) as command:
            with self.assertRaisesRegex(ValueError,'changed'):
                engine.apply(p['id'],tx['id'])
            self.assertEqual(command.call_count,0)

    def test_failed_package_transaction_has_failed_status(self):
        snap,p,_=self.planned()
        with patch.object(engine.subprocess,'run',return_value=type('Result',(),{'returncode':1})()):
            with self.assertRaises(ValueError):engine.apply(p['id'])
        tx=common.read_json(next((self.root/'state/transactions').glob('*.json')))
        self.assertEqual(tx['packages']['status'],'Failed')

    def test_retry_failed_upgrade_even_if_root_was_installed(self):
        snap,p,installed=self.planned()
        def incomplete(*a,**kw):
            installed['foot']='2'
            return type('Result',(),{'returncode':1})()
        with patch.object(engine.subprocess,'run',side_effect=incomplete):
            with self.assertRaises(ValueError):engine.apply(p['id'])
        tx=common.read_json(next((self.root/'state/transactions').glob('*.json')))
        with patch.object(engine.subprocess,'run',return_value=type('Result',(),{'returncode':0})()) as command:
            result=engine.apply(p['id'],tx['id'])
            command.assert_called_once()
        self.assertEqual(result['packages']['status'],'Installed')

    def test_bundle_missing_file_reports_invalid(self):
        snap=self.make_capture();plan.source_guard()
        base=Path(engine.backup_bundle(snap['id'])['bundle'])
        meta=common.read_json(base/'bundle.json')
        first=next(iter(meta['files']));(base/first).unlink()
        self.assertFalse(engine.check_bundle(base)['valid'])

    def test_import_invalid_snapshot_leaves_fresh_checkout_untouched(self):
        snap=self.make_capture();plan.source_guard()
        common.atomic_json(self.root/'manifests/packages.json',{'packages':[]})
        base=Path(engine.backup_bundle(snap['id'])['bundle'])
        rel='dotfiles/snapshots/'+snap['id']+'.json'
        data=common.read_json(base/rel);data['entries'][0]['mode']=0
        common.atomic_json(base/rel,data)
        meta=common.read_json(base/'bundle.json');meta['files'][rel]=common.digest((base/rel).read_bytes())
        common.atomic_json(base/'bundle.json',meta)
        for root in ['dotfiles','manifests']:
            for p in (self.root/root).rglob('*'):
                if p.is_file():p.unlink()
        (self.root/'state/source-host.json').unlink()
        with self.assertRaises(ValueError):engine.import_bundle(base)
        self.assertFalse((self.root/'state/source-host.json').exists())
        self.assertFalse(any((self.root/'manifests').glob('*.json')))

    def test_validate_rejects_plan_from_different_home(self):
        snap,p,_=self.planned()
        with patch.object(plan,'HOME',self.root/'other-home'):
            with self.assertRaisesRegex(ValueError,'destination'):
                validation.validate(snap['id'],p['id'])

    def test_snapshot_rejects_invalid_permission_mode(self):
        snap=self.make_capture();snap['entries'][0]['mode']=-1
        self.assertTrue(snapshot.verify(snap))

    def test_apply_cannot_resume_a_partially_rolled_back_transaction(self):
        snap,p,_=self.planned()
        tx=engine.new_transaction('apply',p['id'],self.home,self.config)
        engine.deploy(snap['entries'],tx,False)
        tx['status']='Rolling back';engine.save(tx)
        with patch.object(engine.subprocess,'run') as worker:
            with self.assertRaisesRegex(ValueError,'partially rolled-back'):
                engine.apply(p['id'],tx['id'])
            self.assertEqual(worker.call_count,0)

    def test_missing_bundle_object_does_not_import_anything(self):
        snap=self.make_capture();plan.source_guard()
        common.atomic_json(self.root/'manifests/packages.json',{'packages':[]})
        base=Path(engine.backup_bundle(snap['id'])['bundle'])
        meta=common.read_json(base/'bundle.json')
        key='dotfiles/objects/'+snap['entries'][0]['sha256']
        del meta['files'][key];common.atomic_json(base/'bundle.json',meta)
        for p in (self.root/'dotfiles').rglob('*'):
            if p.is_file():p.unlink()
        (self.root/'state/source-host.json').unlink()
        with self.assertRaises(ValueError):engine.import_bundle(base)
        self.assertFalse((self.root/'state/source-host.json').exists())

    def test_resource_names_and_sizes_are_checked(self):
        from myarch import resources
        data=b'reference';sha=common.digest(data)
        common.atomic_bytes(resources.resource_path(sha),data)
        for name,size in [('',len(data)),('../escape',len(data)),('file\nname',len(data)),('image',999)]:
            with self.subTest(name=name,size=size):
                self.assertTrue(resources.verify_resources([{'name':name,'sha256':sha,'size':size}]))

    def test_project_json_rejects_duplicate_keys(self):
        p=self.root/'duplicate.json';p.write_text('{"id": "first", "id": "second"}')
        with self.assertRaisesRegex(ValueError,'Duplicate JSON key'):common.read_json(p)

    def test_parent_and_child_snapshot_destinations_are_rejected(self):
        import copy
        snap=self.make_capture();other=copy.deepcopy(snap['entries'][0])
        other['path']=snap['entries'][0]['path']+'/child';snap['entries'].append(other)
        self.assertTrue(snapshot.verify(snap))

    def test_external_applications_remain_visible_in_the_full_plan(self):
        snap,p,_=self.planned()
        common.atomic_json(self.root/'manifests/applications.json',{'inventory':[
            {'manager':'flatpak','kind':'app','name':'org.example.Editor','scope':'user','version':'1'},
            {'manager':'npm','inventory':'{"dependencies":{"example":{"version":"1"}}}'}]})
        full=plan.make_plan(['full'],snap['id'])
        external=[a for a in full['actions'] if a['kind']=='application']
        self.assertEqual(len(external),2)
        self.assertTrue(all(a['status']=='Requires manual action' for a in external))

    def test_invalid_profile_types_fail_with_a_clear_error(self):
        for key,value in [('extends','desktop'),('categories',3),('dotfiles',[None]),('only_packages',None),('hardware_review','false')]:
            with self.subTest(key=key):
                common.atomic_json(self.root/'config/profiles/invalid.json',{key:value})
                with self.assertRaisesRegex(ValueError,'Profile invalid'):
                    plan.profiles(['invalid'])

    def test_invalid_repository_policy_fails_before_target_queries(self):
        snap,p,_=self.planned()
        common.atomic_json(self.root/'config/policy.json',{'trusted_repositories':'extra'})
        with patch.object(plan,'run') as query:
            with self.assertRaisesRegex(ValueError,'trusted_repositories'):
                plan.make_plan(['desktop'],snap['id'])
            self.assertEqual(query.call_count,0)

    def test_failed_package_classification_is_not_an_empty_inventory(self):
        from myarch import audit
        def query(argv,*args,**kwargs):
            if argv==['pacman','-Q']:
                return {'argv':argv,'status':'ok','returncode':0,'stdout':'foot 1.0\n'}
            return {'argv':argv,'status':'unavailable','returncode':None,'stdout':''}
        with patch.object(audit,'run',side_effect=query):
            with self.assertRaisesRegex(ValueError,'classification is unavailable'):
                audit.Audit().pacman()

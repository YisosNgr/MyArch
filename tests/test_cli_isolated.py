"""Real subprocess/PTY integration in a read-only, networkless Bubblewrap sandbox.

The CLI, confirmations, locks and Bash worker are real. Only package commands
and hardware identities are fixtures. No host package manager can be executed.
"""
import errno
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
BWRAP=shutil.which('bwrap')


def package_tool_mounts(fixtures, system_bin=Path('/usr/bin')):
    mounts = []
    for name in ('pacman', 'sudo'):
        # Resolve alternatives on the host before the sandbox masks /etc.
        executable = (system_bin/name).resolve()
        if executable.is_file():
            mounts.extend(('--ro-bind', str(fixtures/name), str(executable)))
    return mounts


class BubblewrapMounts(unittest.TestCase):
    def test_replaces_sudo_binary_behind_distro_alternatives_chain(self):
        (ROOT/'tests/.tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'tests/.tmp') as directory:
            root = Path(directory)
            bin_dir = root/'usr/bin'
            bin_dir.mkdir(parents=True)
            alternatives = root/'etc/alternatives'
            alternatives.mkdir(parents=True)
            real_sudo = bin_dir/'sudo-rs'
            real_sudo.touch()
            (alternatives/'sudo').symlink_to(real_sudo)
            (bin_dir/'sudo').symlink_to(alternatives/'sudo')
            fixtures = root/'fixtures'
            fixtures.mkdir()

            self.assertEqual(
                package_tool_mounts(fixtures, bin_dir),
                ['--ro-bind', str(fixtures/'sudo'), str(real_sudo)],
            )


@unittest.skipUnless(BWRAP,'Bubblewrap unavailable; isolated CLI integration skipped')
class IsolatedCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe=subprocess.run([BWRAP,'--unshare-all','--ro-bind','/','/','--dev','/dev',
                              '--proc','/proc','/usr/bin/true'],capture_output=True)
        if probe.returncode:
            raise unittest.SkipTest('Unprivileged user namespaces unavailable')

    def setUp(self):
        (ROOT/'tests/.tmp').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='cli-',dir=ROOT/'tests/.tmp')
        self.addCleanup(self.temp.cleanup)
        self.case=Path(self.temp.name)
        self.project=self.case/'project'
        self.home=self.case/'target-home'
        self.bin=self.case/'bin'
        for p in [self.project,self.home,self.bin]:p.mkdir()
        for name in ['lib','config','modules']:
            shutil.copytree(ROOT/name,self.project/name,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT/'installer.sh',self.project/'installer.sh')
        for name in ['bash','python3','cat','dirname']:
            (self.bin/name).symlink_to(shutil.which(name))
        (self.case/'etc').mkdir()
        (self.case/'etc/machine-id').write_text('b'*32+'\n')
        (self.case/'etc/os-release').write_text('ID=arch\n')
        (self.case/'etc/sddm.conf').write_text('')
        (self.case/'package-db.json').write_text('{}')
        driver=self.bin/'fixture-command'
        driver.write_text('''#!/usr/bin/python3
import json,os,pathlib,sys
root=pathlib.Path(os.environ['FIXTURE_ROOT']);args=sys.argv[1:];name=pathlib.Path(sys.argv[0]).name
if name=='lspci':
 print('00:01.0 VGA compatible controller: Fixture GPU');sys.exit(0)
if name=='pacman-conf':
 print(os.environ.get('FIXTURE_REPOSITORIES','extra').replace(' ','\\n'));sys.exit(0)
if name=='sudo':
 if args[:4]!=['--','pacman','-Syu','--needed'] or len(os.environ.get('MYARCH_APPROVED_PLAN',''))!=64:sys.exit(91)
 os.execv(str(root/'bin/pacman'),['pacman',*args[2:]])
db=json.loads((root/'package-db.json').read_text())
if args==['-Q']:
 for k,v in db.items():print(k+' '+v)
elif args==['-Sl']:print('extra foot 2.0')
elif args[:2]==['-Syu','--needed']:
 with (root/'package-calls.jsonl').open('a') as f:f.write(json.dumps(args)+'\\n')
 if len(os.environ.get('MYARCH_APPROVED_PLAN',''))!=64:sys.exit(92)
 for target in args[2:]:db[target.partition('/')[2]]='2.0'
 (root/'package-db.json').write_text(json.dumps(db))
 sys.exit(int(os.environ.get('FIXTURE_PACKAGE_EXIT','0')))
else:sys.exit(93)
''')
        driver.chmod(0o755)
        for name in ['pacman','pacman-conf','sudo','lspci']:
            # Copies preserve argv[0] and avoid following any host command path.
            shutil.copy2(driver,self.bin/name)
        self.env={'PATH':str(self.bin),'HOME':str(self.home),
                  'XDG_CONFIG_HOME':str(self.home/'.config'),
                  'PYTHONPATH':str(self.project/'lib'),'PYTHONDONTWRITEBYTECODE':'1',
                  'TERM':'xterm','LANG':'C.UTF-8','FIXTURE_ROOT':str(self.case)}
        seed=self.project/'seed.py'
        seed.write_text('''from myarch.common import ROOT,HOME,atomic_json,record_file,digest
p=HOME/'.config/foot/foot.ini';p.parent.mkdir(parents=True);p.write_text('font=Fixture\\n');p.chmod(0o644)
atomic_json(ROOT/'state/source-host.json',{'schema':1,'machine_hash':digest(('myarch-source-guard-v1:'+'a'*32).encode())})
atomic_json(ROOT/'manifests/dotfiles.json',{'entries':[{**record_file(p),'restore':'portable_candidate','risks':[]}],'include_graph':[]})
atomic_json(ROOT/'manifests/packages.json',{'schema':1,'packages':[{'name':'foot','version':'1.0','manager':'pacman','category':'desktop','installation_reason':'explicit','compatibility':'portable','origin':'repository_available_not_install_origin','evidence':'fixture','dependencies':[]}]})
atomic_json(ROOT/'manifests/applications.json',{'sddm':{}})
''')
        self.execute(['/usr/bin/python3',str(seed)],check=True)
        self.run_cli('capture',check=True)
        self.dest=self.home/'.config/foot/foot.ini'
        self.dest.write_text('original destination\n');self.dest.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def command(self,argv):
        return [BWRAP,'--unshare-all','--die-with-parent','--ro-bind','/','/',
                '--dev','/dev','--proc','/proc','--tmpfs','/run','--tmpfs','/tmp',
                '--bind',str(self.case),str(self.case),
                '--ro-bind',str(self.case/'etc'),'/etc',
                # Even an accidental absolute invocation reaches a fixture.
                *package_tool_mounts(self.bin),
                '--chdir',str(self.project),*argv]

    def execute(self,argv,check=False,extra=None):
        p=subprocess.run(self.command(argv),env={**self.env,**(extra or {})},capture_output=True,
                         text=True,timeout=15)
        if check:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        return p

    def run_cli(self,*args,check=False,extra=None):
        return self.execute(['/usr/bin/bash',str(self.project/'installer.sh'),*args],check,extra)

    def tty(self,args,text,extra=None):
        master,slave=pty.openpty()
        p=subprocess.Popen(self.command(['/usr/bin/bash',str(self.project/'installer.sh'),*args]),
                           env={**self.env,**(extra or {})},stdin=slave,stdout=slave,stderr=slave,
                           start_new_session=True)
        os.close(slave);output=bytearray();deadline=time.monotonic()+15
        try:
            os.write(master,text.encode())
            while time.monotonic()<deadline:
                ready,_,_=select.select([master],[],[],0.1)
                if ready:
                    try:
                        block = os.read(master, 65536)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        break  # Linux reports EIO when the slave terminal closes.
                    if not block:
                        break
                    output.extend(block)

            # The terminal may close while the process is still exiting.
            try:
                code = p.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                self.fail('PTY command timed out: '+output.decode(errors='replace'))
            return code, output.decode(errors='replace')
        finally:
            if p.poll() is None:p.kill();p.wait()
            os.close(master)

    def planned(self):
        p=self.run_cli('plan','--profile','desktop','--json',check=True)
        return json.loads(p.stdout)

    def mutation_calls(self):
        p=self.case/'package-calls.jsonl'
        return p.read_text().splitlines() if p.exists() else []

    def test_pty_waits_for_process_exit_after_terminal_closes(self):
        close_terminal = [
            '/usr/bin/python3', '-c',
            'import os, time; os.write(1, b"done"); '
            'os.close(0); os.close(1); os.close(2); time.sleep(0.3)',
        ]
        with patch.object(self, 'command', return_value=close_terminal):
            code, output = self.tty([], '')
        self.assertEqual(code, 0)
        self.assertEqual(output, 'done')

    def test_complete_install_validate_idempotence_and_rollback(self):
        plan=self.planned()
        code,out=self.tty(['apply'],'APLICAR '+plan['id'][:12]+'\n')
        self.assertEqual(code,0,out)
        self.assertEqual(self.dest.read_text(),'font=Fixture\n')
        self.assertEqual(self.dest.stat().st_mode & 0o777,0o644)
        tx=json.loads(next((self.project/'state/transactions').glob('*.json')).read_text())
        self.assertEqual(tx['status'],'Installed')
        self.assertTrue(json.loads(self.run_cli('validate','--plan','latest',check=True).stdout)['deployment_ok'])
        self.assertEqual(len(self.mutation_calls()),1)
        code,out=self.tty(['apply'],'APLICAR '+plan['id'][:12]+'\n')
        self.assertEqual(code,0,out);self.assertEqual(len(self.mutation_calls()),1)
        code,out=self.tty(['rollback',tx['id']],'RESTAURAR '+tx['id']+'\n')
        self.assertEqual(code,0,out)
        self.assertEqual(self.dest.read_text(),'original destination\n')
        self.assertEqual(self.dest.stat().st_mode & 0o777,0o600)
        self.assertEqual(json.loads((self.case/'package-db.json').read_text())['foot'],'2.0')

    def test_source_identity_blocked_without_package_call(self):
        self.planned();(self.case/'etc/machine-id').write_text('a'*32+'\n')
        p=self.run_cli('apply')
        self.assertEqual(p.returncode,2);self.assertIn('source computer',p.stderr)
        self.assertEqual(self.mutation_calls(),[])
        self.assertEqual(self.dest.read_text(),'original destination\n')

    def test_noninteractive_and_wrong_confirmation_do_not_mutate(self):
        plan=self.planned();p=self.run_cli('apply')
        self.assertEqual(p.returncode,2);self.assertIn('interactive terminal',p.stderr)
        code,out=self.tty(['apply'],'NO\n')
        self.assertEqual(code,2,out);self.assertIn('cancelled',out)
        self.assertEqual(self.mutation_calls(),[])

    def test_failed_package_worker_can_resume_actual_cli(self):
        plan=self.planned()
        code,out=self.tty(['apply'],'APLICAR '+plan['id'][:12]+'\n',{'FIXTURE_PACKAGE_EXIT':'1'})
        self.assertEqual(code,2,out)
        self.assertEqual(self.dest.read_text(),'original destination\n')
        tx=json.loads(next((self.project/'state/transactions').glob('*.json')).read_text())
        self.assertEqual(tx['packages']['status'],'Failed')
        code,out=self.tty(['apply','--resume',tx['id']],'APLICAR '+plan['id'][:12]+'\n')
        self.assertEqual(code,0,out);self.assertEqual(len(self.mutation_calls()),2)

    def test_stale_destination_is_rejected_before_worker(self):
        plan=self.planned();self.dest.write_text('new user edit')
        code,out=self.tty(['apply'],'APLICAR '+plan['id'][:12]+'\n')
        self.assertEqual(code,2,out);self.assertIn('changed since planning',out)
        self.assertEqual(self.mutation_calls(),[])
        self.assertEqual(self.dest.read_text(),'new user edit')

    def test_untrusted_repository_is_rejected_before_worker(self):
        plan=self.planned()
        code,out=self.tty(['apply'],'APLICAR '+plan['id'][:12]+'\n',{'FIXTURE_REPOSITORIES':'extra blackarch'})
        self.assertEqual(code,2,out);self.assertIn('configured target repository',out)
        self.assertEqual(self.mutation_calls(),[])

    def test_fallback_menu_opens_and_exits_on_a_real_tty(self):
        code,out=self.tty([],'13\n')
        self.assertEqual(code,0,out)
        self.assertIn('Personal Arch Linux Environment',out)
        self.assertIn('13. Exit',out)

    def test_host_filesystem_is_read_only(self):
        p=self.execute(['/usr/bin/python3','-c',
                        "from pathlib import Path; Path('/etc/myarch-test-should-never-exist').write_text('x')"])
        self.assertNotEqual(p.returncode,0)
        self.assertIn('Read-only file system',p.stderr)

    def test_help_without_python_and_no_runtime_state(self):
        minimal=self.case/'minimal-bin';minimal.mkdir()
        for name in ['dirname','cat']:(minimal/name).symlink_to(shutil.which(name))
        p=self.run_cli('--help',extra={'PATH':str(minimal)})
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('MYARCH',p.stdout)

    def test_malformed_snapshot_has_a_controlled_error(self):
        latest=json.loads((self.project/'state/latest-capture.json').read_text())['id']
        (self.project/'dotfiles/snapshots'/f'{latest}.json').write_text('[]')
        p=self.run_cli('validate')
        self.assertEqual(p.returncode,2)
        self.assertNotIn('Traceback',p.stderr)
        self.assertIn('JSON document must be an object',p.stderr)

    def test_partial_installation_returns_nonzero_and_manual_status(self):
        path=self.project/'manifests/packages.json'
        data=json.loads(path.read_text())
        data['packages'].append({**data['packages'][0],'name':'foreign-demo','origin':'foreign_unverified'})
        path.write_text(json.dumps(data))
        plan=self.planned()
        code,out=self.tty(['apply'],'APLICAR '+plan['id'][:12]+'\n')
        self.assertEqual(code,1,out)
        self.assertIn('Requires manual action',out)
        tx=json.loads(next((self.project/'state/transactions').glob('*.json')).read_text())
        self.assertEqual(tx['status'],'Requires manual action')
        self.assertEqual(self.dest.read_text(),'font=Fixture\n')

    def test_backup_import_and_stage_into_a_fresh_checkout(self):
        import hashlib
        bundle=json.loads(self.run_cli('backup',check=True).stdout)['bundle']
        self.run_cli('bundle-check',bundle,check=True)
        fresh=self.case/'fresh-project';fresh.mkdir()
        for name in ['lib','config','modules']:
            shutil.copytree(self.project/name,fresh/name)
        shutil.copy2(self.project/'installer.sh',fresh/'installer.sh')
        copied=fresh/'backups/bundles/recovery'
        shutil.copytree(bundle,copied)
        original=self.project
        self.project=fresh
        self.env['PYTHONPATH']=str(fresh/'lib')
        try:
            result=self.run_cli('bundle-import',str(copied),check=True)
            capture=json.loads(result.stdout)['capture']
            self.assertIn('exported',json.loads(result.stdout)['state'])
            self.run_cli('stage',check=True)
            staged=fresh/'staging'/capture/'home/.config/foot/foot.ini'
            self.assertEqual(staged.read_text(),'font=Fixture\n')
            self.assertEqual(self.dest.read_text(),'original destination\n')
        finally:
            self.project=original
            self.env['PYTHONPATH']=str(original/'lib')

    def test_package_worker_itself_refuses_the_source_computer(self):
        plan=self.planned();(self.case/'etc/machine-id').write_text('a'*32+'\n')
        p=self.execute(['/usr/bin/bash',str(self.project/'modules/packages.sh'),'extra/foot'],
                       extra={'MYARCH_APPROVED_PLAN':plan['id']})
        self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        self.assertIn('source computer',p.stderr)
        self.assertEqual(self.mutation_calls(),[])

    def test_package_worker_rejects_unplanned_targets(self):
        plan=self.planned()
        p=self.execute(['/usr/bin/bash',str(self.project/'modules/packages.sh'),'extra/unplanned'],
                       extra={'MYARCH_APPROVED_PLAN':plan['id']})
        self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        self.assertIn('targets differ',p.stderr)
        self.assertEqual(self.mutation_calls(),[])

    def test_package_worker_rejects_another_target_home(self):
        plan=self.planned();other=self.case/'other-home';other.mkdir()
        p=self.execute(['/usr/bin/bash',str(self.project/'modules/packages.sh'),'extra/foot'],
                       extra={'MYARCH_APPROVED_PLAN':plan['id'],'HOME':str(other)})
        self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        self.assertIn('different destination',p.stderr)
        self.assertEqual(self.mutation_calls(),[])

    def test_eof_confirmation_is_a_clean_cancellation(self):
        self.planned();code,out=self.tty(['apply'],'\x04')
        self.assertEqual(code,2,out)
        self.assertIn('confirmation input closed',out)
        self.assertNotIn('Traceback',out)
        self.assertEqual(self.mutation_calls(),[])

"""Transactional file deployment, destination-only package application and rollback."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from contextlib import contextmanager
from .common import ROOT, HOME, CONFIG, now, atomic_json, atomic_bytes, read_json, digest, inside, sensitive
from .resources import resource_path
from .snapshot import load_snapshot, verify, blob_path, safe_relative, check_snapshot_metadata
from .plan import (load_plan, target_file, host_fingerprint, require_destination_host,
                   inventory)
from .common import run


@contextmanager
def project_lock():
    p = ROOT/'state/operation.lock'
    inside(p,ROOT)
    p.parent.mkdir(exist_ok=True,mode=0o700)
    fd = os.open(p,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another MyArch operation is running') from exc
        yield
    finally:
        os.close(fd)


def no_symlinks(path, boundary):
    path, boundary = Path(path), Path(boundary)
    if not path.is_absolute() or not boundary.is_absolute() or not path.is_relative_to(boundary):
        raise ValueError('Destination escapes deployment boundary')
    # Check ancestors too: even a symlinked HOME or XDG root needs manual review.
    for part in [path,*path.parents]:
        if part.is_symlink():
            raise ValueError(f'Symlink destination is forbidden: {part}')
    if path.exists() and not path.is_file():
        raise ValueError('Destination exists and is not a regular file')


def write_target(path, data, mode, boundary):
    path=Path(path)
    no_symlinks(path,boundary)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    no_symlinks(path,boundary)
    fd,tmp=tempfile.mkstemp(prefix='.myarch-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp,mode & 0o777)
        no_symlinks(path,boundary)
        os.replace(tmp,path)
        dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def transaction_path(identifier):
    if not re.fullmatch(r'[a-z0-9TZ-]+',identifier):
        raise ValueError('Invalid transaction ID')
    return inside(ROOT/'state/transactions'/f'{identifier}.json',ROOT/'state/transactions')


def new_transaction(kind, plan_id, home, config):
    ident=now()[:19].replace(':','-')+'Z-'+os.urandom(6).hex()
    return {'schema':1,'id':ident,'kind':kind,'plan':plan_id,'target_host':host_fingerprint(),
            'home':str(home),'config':str(config),'created_at':now(),
            'status':'Pending','files':{},'packages':{'status':'Pending'}}


def save(tx):
    atomic_json(transaction_path(tx['id']),tx)


def deploy(entries,tx,progress=True):
    home,config=Path(tx['home']),Path(tx['config'])
    save(tx)
    tx['status']='Installing'
    save(tx)
    for e in entries:
        logical=e['path']
        safe_relative(logical)
        data=blob_path(e['sha256']).read_bytes()
        if digest(data)!=e['sha256'] or sensitive(logical,data):
            raise ValueError('Invalid or sensitive deployment object')
        dest=target_file(logical,home,config)
        boundary=config if logical.startswith('config/') else home
        no_symlinks(dest,boundary)
        item=tx['files'].get(logical)
        if item and item['status'] in {'Installed','Skipped'}:
            if not dest.is_file() or digest(dest.read_bytes())!=e['sha256'] or (dest.stat().st_mode & 0o777)!=e['mode']:
                raise ValueError('Previously completed destination changed; refusing resume overwrite')
            continue
        if not item and dest.is_file() and digest(dest.read_bytes())==e['sha256'] and (dest.stat().st_mode & 0o777)==e['mode']:
            tx['files'][logical]={'status':'Skipped','sha256':e['sha256'],'mode':e['mode'],'existed':True,'reason':'identical'}
            save(tx)
            continue
        if not item:
            item={'status':'Pending','sha256':e['sha256'],'mode':e['mode'],'existed':dest.exists()}
            if dest.exists():
                original=dest.read_bytes()
                # Backups remain private and inside MyArch; they can include target-local secrets.
                backup=ROOT/'backups'/tx['id']/logical
                atomic_bytes(backup,original)
                item.update(backup=str(backup.relative_to(ROOT)),before_sha256=digest(original),
                            before_mode=dest.stat().st_mode & 0o777)
            tx['files'][logical]=item
            save(tx)  # Recovery metadata reaches disk before touching the destination.
        elif item['status']=='Installing' and dest.is_file() and digest(dest.read_bytes())==e['sha256'] and (dest.stat().st_mode & 0o777)==e['mode']:
            item['status']='Installed'
            save(tx)
            continue
        elif item['existed']:
            if not dest.is_file() or digest(dest.read_bytes())!=item['before_sha256'] or (dest.stat().st_mode & 0o777)!=item['before_mode']:
                raise ValueError('Destination changed after backup; refusing overwrite')
        elif dest.exists():
            raise ValueError('A new destination appeared after the transaction began')
        item['status']='Installing'
        save(tx)
        if progress:
            print('Installing file: '+logical,flush=True)
        write_target(dest,data,e['mode'],boundary)
        item['status']='Installed'
        save(tx)
    tx['status']='Installed'
    save(tx)
    return tx


def stage(snapshot_id='latest',dest=None,portable_only=False):
    snap=load_snapshot(snapshot_id)
    errors=verify(snap)
    if errors:
        raise ValueError('Snapshot integrity failure: '+str(errors))
    base=Path(dest) if dest else ROOT/'staging'/snap['id']
    inside(base,ROOT/'staging')
    if base.exists():
        raise ValueError('Stage already exists; use a new directory inside MyArch/staging')
    tx=new_transaction('stage',snap['id'],base/'home',base/'home/.config')
    entries=[e for e in snap['entries'] if not portable_only or e['restore']=='portable_candidate']
    try:
        result=deploy(entries,tx)
        for resource in snap.get('resources',[]):
            dest=base/'resources'/resource['sha256']/resource['name']
            write_target(dest,resource_path(resource['sha256']).read_bytes(),0o600,base/'resources')
        atomic_json(base/'resources/index.json',snap.get('resources',[]))
        result['reference_assets']=str(base/'resources')
        return result
    except BaseException:
        tx['status']='Failed'
        save(tx)
        raise


def apply(plan_id='latest',resume=None):
    require_destination_host()
    plan=load_plan(plan_id)
    if plan['target_host']!=host_fingerprint() or plan['target_home']!=str(HOME) or plan['target_config']!=str(CONFIG):
        raise ValueError('Plan belongs to a different target; generate a plan on this destination')
    snap=load_snapshot(plan['capture'])
    if verify(snap):
        raise ValueError('Snapshot failed integrity validation')
    index={e['path']:e for e in snap['entries']}
    entries=[]
    for a in plan['actions']:
        if a['kind']=='file' and a['status'] in {'Pending','Skipped'}:
            e=index.get(a['path'])
            if not e or e['restore']!='portable_candidate' or e['sha256']!=a['sha256'] or e['mode']!=a['mode']:
                raise ValueError('Plan file differs from reviewed capture')
            entries.append(e)
    if resume:
        tx=read_json(transaction_path(resume))
        if tx['kind']!='apply' or tx['plan']!=plan['id'] or tx['target_host']!=host_fingerprint() or tx['home']!=str(HOME) or tx['config']!=str(CONFIG):
            raise ValueError('Resume transaction does not match this target and plan')
        if tx['status'] in {'Rolled back','Rolling back'} or any(i['status'] in {'Rolling back','Rolled back'} for i in tx['files'].values()):
            raise ValueError('Cannot resume a rolled-back or partially rolled-back transaction')
    else:
        tx=new_transaction('apply',plan['id'],HOME,CONFIG)
    save(tx)
    try:
        targets=[]
        current=inventory()
        # Preflight completed and interrupted writes before any package mutation.
        for logical,item in tx['files'].items():
            dest=target_file(logical)
            no_symlinks(dest,CONFIG if logical.startswith('config/') else HOME)
            actual=(digest(dest.read_bytes()),dest.stat().st_mode & 0o777) if dest.is_file() else (None,None)
            desired=(item['sha256'],item['mode'])
            before=(item.get('before_sha256'),item.get('before_mode')) if item['existed'] else (None,None)
            acceptable={desired} if item['status'] in {'Installed','Skipped'} else {desired,before}
            if actual not in acceptable:
                raise ValueError('Previously recorded destination changed; refusing resume before package mutation')
        # Preflight all remaining file destinations before invoking a privileged transaction.
        for a in plan['actions']:
            if a['kind']=='file' and a['status'] in {'Pending','Skipped'} and a['path'] not in tx['files']:
                dest=target_file(a['path'])
                no_symlinks(dest,CONFIG if a['path'].startswith('config/') else HOME)
                actual=digest(dest.read_bytes()) if dest.is_file() else None
                mode=(dest.stat().st_mode & 0o777) if dest.is_file() else None
                if (actual,mode) not in {(a['sha256'],a['mode']),(a.get('target_before'),a.get('target_before_mode'))}:
                    raise ValueError('Destination changed since planning; generate a new plan')
            if a['kind']=='package' and a['status']=='Skipped' and a['name'] not in current:
                raise ValueError('Package inventory changed since planning; generate a new plan')
        for a in plan['actions']:
            if a['kind']=='package' and a['status']=='Pending' and a['name'] not in current:
                target=a['target']
                if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9@._+:-]*',target):
                    raise ValueError('Invalid qualified package target')
                targets.append(target)
        # A failed upgrade may have installed its roots before failing elsewhere.
        # Re-run that reviewed transaction instead of mistaking it for completion.
        if tx['packages']['status'] in {'Installing','Failed'}:
            pending_targets=tx['packages'].get('targets',[])
            allowed={a.get('target') for a in plan['actions'] if a['kind']=='package' and a['status']=='Pending'}
            if any(t not in allowed for t in pending_targets):
                raise ValueError('Interrupted package targets differ from the plan')
            targets=list(dict.fromkeys([*pending_targets,*targets]))
        if targets:
            trusted=read_json(ROOT/'config/policy.json')['trusted_repositories']
            configured=run(['pacman-conf','--repo-list'])
            if configured['status']!='ok' or any(r not in trusted for r in configured['stdout'].splitlines()):
                raise ValueError('Review every configured target repository in config/policy.json before upgrading; dependencies use repository priority')
            if any(t.partition('/')[0] not in trusted for t in targets):
                raise ValueError('Plan contains an untrusted repository')
            tx['packages']={'status':'Installing','targets':targets}
            save(tx)
            env={**os.environ,'MYARCH_APPROVED_PLAN':plan['id']}
            # Bash owns the privileged transaction. No root Python process.
            proc=subprocess.run(['bash',str(ROOT/'modules/packages.sh'),*targets],env=env,check=False)
            if proc.returncode:
                raise ValueError('Package transaction failed or was cancelled; inspect pacman before resuming')
            current=inventory()
            if any(t.partition('/')[2] not in current for t in targets):
                raise ValueError('Package verification failed')
            tx['packages']['status']='Installed'
        elif tx['packages']['status']!='Installed':
            tx['packages']={'status':'Skipped','reason':'no_missing_automatic_package_targets'}
        save(tx)
        deploy(entries,tx)
        tx['manual_actions']=sum(a['status']=='Requires manual action' for a in plan['actions'])+len(plan['manual'])
        tx['status']='Requires manual action' if tx['manual_actions'] else 'Installed'
        save(tx)
        return tx
    except BaseException:
        tx['status']='Failed'
        if tx['packages']['status']=='Installing':
            tx['packages']['status']='Failed'
        save(tx)
        raise


def rollback(identifier):
    tx=read_json(transaction_path(identifier))
    if tx['target_host']!=host_fingerprint():
        raise ValueError('Transaction belongs to another computer')
    if tx['kind']=='apply':
        require_destination_host()
    elif tx['kind']=='stage':
        inside(Path(tx['home']),ROOT/'staging')
        inside(Path(tx['config']),ROOT/'staging')
    else:
        raise ValueError('Unknown transaction type')
    home,config=Path(tx['home']),Path(tx['config'])
    # Validate all destinations before any rollback writes, including crash recovery.
    done = set()
    for logical,item in tx['files'].items():
        if item['status'] not in {'Pending','Installed','Installing','Rolling back'}:
            continue
        dest=target_file(logical,home,config)
        no_symlinks(dest,config if logical.startswith('config/') else home)
        current=(digest(dest.read_bytes()),dest.stat().st_mode & 0o777) if dest.is_file() else (None,None)
        before=(item['before_sha256'],item['before_mode']) if item['existed'] else (None,None)
        if item['status'] in {'Pending','Installing','Rolling back'} and current==before:
            done.add(logical)
        elif current!=(item['sha256'],item.get('mode',current[1])):
            raise ValueError('Destination changed after deployment; manual recovery required')
        if item['existed']:
            backup=inside(ROOT/safe_relative(item['backup']),ROOT/'backups'/identifier)
            if backup.is_symlink() or digest(backup.read_bytes())!=item['before_sha256']:
                raise ValueError('Backup integrity failure')
    tx['status']='Rolling back'
    save(tx)
    for logical,item in reversed(list(tx['files'].items())):
        if item['status'] not in {'Pending','Installed','Installing','Rolling back'}:
            continue
        dest=target_file(logical,home,config)
        boundary=config if logical.startswith('config/') else home
        if logical not in done:
            item['status']='Rolling back'
            save(tx)
            if item['existed']:
                backup=inside(ROOT/safe_relative(item['backup']),ROOT/'backups'/identifier)
                write_target(dest,backup.read_bytes(),item['before_mode'],boundary)
            else:
                dest.unlink()
        item['status']='Rolled back'
        save(tx)
    tx['status']='Rolled back'
    tx['rollback_note']='Configuration files only; packages and system upgrade are not reverted.'
    save(tx)
    return tx


def backup_bundle(snapshot_id='latest'):
    """Private local bundle, no archive extraction and no unfiltered host copies."""
    snap=load_snapshot(snapshot_id)
    if verify(snap):
        raise ValueError('Snapshot integrity failure')
    ident=now()[:19].replace(':','-')+'Z-'+os.urandom(4).hex()
    base=ROOT/'backups/bundles'/ident
    sources=[ROOT/'dotfiles/snapshots'/f"{snap['id']}.json"]
    sources.extend(sorted((ROOT/'manifests').glob('*.json')))
    sources.append(ROOT/'state/source-host.json')
    sources.extend(blob_path(e['sha256']) for e in snap['entries'])
    sources.extend(resource_path(e['sha256']) for e in snap.get('resources',[]))
    checksum={}
    for source in sorted(set(sources)):
        inside(source,ROOT)
        if source.is_symlink():
            raise ValueError('Bundle source symlinks are forbidden')
        rel=str(source.relative_to(ROOT))
        data=source.read_bytes()
        atomic_bytes(base/rel,data)
        checksum[rel]=digest(data)
    atomic_json(base/'bundle.json',{'schema':1,'capture':snap['id'],'created_at':now(),'files':checksum})
    return {'bundle':str(base),'files':len(checksum),'state':'private_local_backup'}


def check_bundle(directory):
    base=inside(Path(directory),ROOT/'backups/bundles')
    data=read_json(base/'bundle.json')
    failures=[]
    for rel,sha in data['files'].items():
        p=inside(base/safe_relative(rel),base)
        try:
            valid=not p.is_symlink() and digest(p.read_bytes())==sha
        except OSError:
            valid=False
        if not valid:
            failures.append(rel)
    return {'valid':not failures,'failures':failures,'capture':data['capture']}


def import_bundle(directory):
    """Import into a fresh checkout only; never replace a different existing inventory."""
    checked=check_bundle(directory)
    if not checked['valid']:
        raise ValueError('Bundle integrity failure')
    base=inside(Path(directory),ROOT/'backups/bundles')
    meta=read_json(base/'bundle.json')
    capture_id=meta['capture']
    # Strict path allowlist prevents even a deliberately edited bundle from writing code.
    allowed_manifests={f'manifests/{n}.json' for n in ['system','hardware','packages','services','dotfiles','applications','audit-report']}
    sources=[]
    for rel,sha in meta['files'].items():
        safe_relative(rel)
        allowed=(rel in allowed_manifests or rel=='state/source-host.json' or
                 bool(re.fullmatch(r'(dotfiles|assets)/objects/[a-f0-9]{64}',rel)) or
                 bool(re.fullmatch(r'dotfiles/snapshots/[0-9TZ-]+-[a-f0-9]{12}\.json',rel)))
        if not allowed:
            raise ValueError('Unexpected path in bundle')
        source=inside(base/rel,base)
        dest=inside(ROOT/rel,ROOT)
        data=source.read_bytes()
        if digest(data)!=sha:
            raise ValueError('Bundle changed during import')
        if dest.is_symlink() or (dest.exists() and dest.read_bytes()!=data):
            raise ValueError('Existing inventory differs; use a fresh checkout to recover the bundle')
        sources.append((dest,data))
    required={'state/source-host.json',f'dotfiles/snapshots/{capture_id}.json','manifests/packages.json'}
    if not required.issubset(meta['files']):
        raise ValueError('Incomplete bundle')
    # Validate the complete imported document and its objects before the first write.
    source_data={str(dest.relative_to(ROOT)):data for dest,data in sources}
    try:
        imported=json.loads(source_data[f'dotfiles/snapshots/{capture_id}.json'])
        check_snapshot_metadata(imported,capture_id)
        errors=verify(imported,
                      lambda sha:source_data['dotfiles/objects/'+sha],
                      lambda sha:source_data['assets/objects/'+sha])
        guard=json.loads(source_data['state/source-host.json'])
        if not isinstance(guard,dict) or not isinstance(guard.get('machine_hash'),str) or not re.fullmatch(r'[a-f0-9]{64}',guard['machine_hash']):
            raise ValueError('Invalid source identity in bundle')
        packages=json.loads(source_data['manifests/packages.json'])
        if not isinstance(packages,dict) or not isinstance(packages.get('packages'),list):
            raise ValueError('Invalid package inventory in bundle')
    except (KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('Incomplete or invalid bundle documents') from exc
    if errors:
        raise ValueError('Imported snapshot did not validate: '+str(errors))
    for dest,data in sources:
        atomic_bytes(dest,data)
    snap=load_snapshot(capture_id)
    if verify(snap):
        raise ValueError('Imported snapshot did not validate')
    atomic_json(ROOT/'state/latest-capture.json',{'id':capture_id})
    return {'capture':capture_id,'imported_files':len(sources),'state':'exported; generate a fresh plan on destination'}

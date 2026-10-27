"""Read-only drift, integrity and diagnosis checks."""
import json
from pathlib import Path
from .common import ROOT, now, run, atomic_json, digest, expand_path, read_json
from .snapshot import load_snapshot, verify
from .plan import load_plan, target_file, inventory, host_fingerprint


def compare(snapshot_id='latest'):
    snapshot=load_snapshot(snapshot_id)
    files=[]
    for e in snapshot['entries']:
        p=target_file(e['path'])
        status='missing'
        if p.is_symlink():
            status='symlink_manual'
        elif p.is_file():
            status='changed' if digest(p.read_bytes())!=e['sha256'] else ('identical' if (p.stat().st_mode & 0o777)==e['mode'] else 'permission_changed')
        files.append({'path':e['path'],'status':status,'restore':e['restore']})
    observed=read_json(ROOT/'manifests/packages.json')
    current=inventory()
    pkgs=[]
    for p in observed['packages']:
        version=current.get(p['name'])
        pkgs.append({'name':p['name'],'status':'missing' if version is None else ('identical' if version==p['version'] else 'version_changed'),
                     'observed_version':p['version'],'current_version':version})
    result={'schema':1,'generated_at':now(),'capture':snapshot['id'],'files':files,'packages':pkgs,
            'note':'Version changes are drift observations, not a request to downgrade.'}
    atomic_json(ROOT/'reports/compare.json',result)
    return result


def validate(snapshot_id='latest',plan_id=None):
    snapshot=load_snapshot(snapshot_id)
    errors=verify(snapshot)
    result={'schema':1,'generated_at':now(),'capture':snapshot['id'],'integrity_errors':errors,
            'integrity_ok':not errors,'scope':'stored_snapshot', 'deployment_ok':None}
    if plan_id:
        plan=load_plan(plan_id)
        if plan['capture']!=snapshot['id'] or plan['target_host']!=host_fingerprint():
            raise ValueError('Validation plan does not match capture or current destination')
        checks=[]
        installed=inventory()
        for a in plan['actions']:
            if a['status']=='Requires manual action':
                checks.append({'kind':a['kind'],'name':a.get('name',a.get('path')),'status':'Requires manual action'})
            elif a['kind']=='package':
                checks.append({'kind':'package','name':a['name'],'status':'Installed' if a['name'] in installed else 'Failed'})
            else:
                dest=target_file(a['path'])
                ok=dest.is_file() and not dest.is_symlink() and digest(dest.read_bytes())==a['sha256'] and (dest.stat().st_mode & 0o777)==a['mode']
                checks.append({'kind':'file','name':a['path'],'status':'Installed' if ok else 'Failed'})
        result.update(scope='snapshot_and_destination',checks=checks,
                      deployment_ok=not errors and all(c['status']=='Installed' for c in checks) and not plan['manual'],
                      manual=plan['manual'])
    atomic_json(ROOT/'reports/validation.json',result)
    return result


def doctor():
    checks=[]
    for cmd in [['bash','--version'],['python3','--version'],['pacman','-V'],['git','--version'],['gum','--version'],['shellcheck','--version']]:
        q=run(cmd)
        checks.append({'tool':cmd[0],'status':q['status'],'required':cmd[0] in {'bash','python3','pacman'}})
    for argv in [['systemctl','--failed','--no-legend','--plain','--no-pager'],
                 ['systemctl','--user','--failed','--no-legend','--plain','--no-pager']]:
        q=run(argv,15)
        checks.append({'query':argv,'status':q['status'],
                       'failed_units':[l.split()[0] for l in q['stdout'].splitlines() if l.strip()]})
    result={'schema':1,'generated_at':now(),'checks':checks,
            'scope':'read_only; no repairs, service restarts or desktop client execution'}
    atomic_json(ROOT/'reports/doctor.json',result)
    return result

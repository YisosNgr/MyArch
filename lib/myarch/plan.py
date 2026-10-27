"""Pure plan construction. Observed, exported and desired states stay distinct."""
import os
from pathlib import Path
import re
from .common import ROOT, HOME, CONFIG, now, digest, read_json, atomic_json, run, inside
from .snapshot import load_snapshot, verify, safe_relative


def host_fingerprint():
    try:
        machine = Path('/etc/machine-id').read_text().strip()
    except OSError as exc:
        raise ValueError('Machine identity unavailable; refusing live deployment') from exc
    if not re.fullmatch(r'[a-f0-9]{32}', machine):
        raise ValueError('Machine identity unavailable; refusing live deployment')
    return digest(('myarch-source-guard-v1:'+machine).encode())


def source_guard():
    p = ROOT/'state/source-host.json'
    current = host_fingerprint()
    if not p.exists():
        atomic_json(p, {'schema': 1, 'machine_hash': current, 'recorded_at': now()})
    return read_json(p)


def require_destination_host():
    guard = read_json(ROOT/'state/source-host.json')
    if guard['machine_hash'] == host_fingerprint():
        raise ValueError('Live apply is forbidden on the audited source computer. Use staging inside MyArch.')
    if os.geteuid() == 0:
        raise ValueError('Run as the destination user; sudo is limited to the package transaction')
    if not Path('/etc/os-release').is_file() or not re.search(r'^ID=arch$', Path('/etc/os-release').read_text(), re.M):
        raise ValueError('Live apply requires an existing Arch Linux installation')


def profiles(names):
    categories, configs, only = set(), set(), set()
    visited, active, info = set(), set(), []
    def visit(name):
        if not re.fullmatch(r'[a-z][a-z0-9-]*', name):
            raise ValueError('Invalid profile name')
        if name in active:
            raise ValueError('Circular profile inheritance')
        if name in visited:
            return
        active.add(name)
        d = read_json(inside(ROOT/'config/profiles'/f'{name}.json', ROOT/'config/profiles'))
        for parent in d.get('extends', []):
            visit(parent)
        categories.update(d.get('categories', []))
        configs.update(d.get('dotfiles', []))
        only.update(d.get('only_packages', []))
        info.append({'name': name, 'hardware_review': d.get('hardware_review',False),
                     'services_review': d.get('services_review',False)})
        active.remove(name)
        visited.add(name)
    for name in names:
        visit(name)
    # A narrow profile must not constrain a broader profile selected alongside it.
    narrow = set(only) if set(names) == {'minimal'} else set()
    return categories, configs, narrow, info


def file_category(path):
    if path.startswith(('config/nvim/','config/Code/','config/VSCodium/')) or path == 'home/.gitconfig':
        return 'development'
    if path.startswith(('config/MangoHud/','config/gamemode')):
        return 'gaming'
    if path.startswith('config/sunshine/'):
        return 'multimedia'
    return 'desktop'


def target_file(logical, home=None, config=None):
    home = HOME if home is None else home
    config = CONFIG if config is None else config
    rel = safe_relative(logical)
    parts = rel.parts
    roots = {'config': Path(config), 'home': Path(home), 'state': Path(home)/'.local/state'}
    if parts[0] not in roots or len(parts) < 2:
        raise ValueError('Unrecognized logical configuration path')
    return roots[parts[0]].joinpath(*parts[1:])


def inventory():
    q = run(['pacman','-Q'])
    if q['status'] != 'ok':
        raise ValueError('Cannot inspect target package inventory')
    return dict(line.split(maxsplit=1) for line in q['stdout'].splitlines())


def make_plan(names, snapshot_id='latest'):
    packages = read_json(ROOT/'manifests/packages.json')
    policy = read_json(ROOT/'config/policy.json')
    categories, configs, only, info = profiles(names)
    snapshot = load_snapshot(snapshot_id)
    errors = verify(snapshot)
    if errors:
        raise ValueError('Snapshot validation failed: '+str(errors))
    installed = inventory()
    sync = run(['pacman','-Sl'],60)
    if sync['status'] != 'ok':
        raise ValueError('Cannot inspect target synchronization databases; no plan generated')
    available = {}
    for line in sync['stdout'].splitlines():
        parts = line.split()
        if len(parts) >= 3:
            available.setdefault(parts[1],set()).add(parts[0])
    actions, manual = [], []
    for p in packages['packages']:
        if p['installation_reason'] != 'explicit' or p['category'] not in categories or (only and p['name'] not in only):
            continue
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9@._+:-]*', p['name']):
            raise ValueError('Unsafe package name in inventory')
        a = {'kind': 'package', 'name': p['name'], 'observed_version': p['version'],
             'category': p['category'], 'origin': p['origin'], 'status': 'Pending',
             'evidence': p['evidence'], 'version_policy': 'current_repositories'}
        if p['compatibility'] != 'portable':
            a.update(status='Requires manual action', reason=p['compatibility'])
        elif p['origin'].startswith('foreign'):
            a.update(status='Requires manual action', reason='foreign_recipe_and_binary_origin_review')
        elif not available.get(p['name'],set()).intersection(policy['trusted_repositories']):
            a.update(status='Requires manual action', reason='missing_or_untrusted_target_repository')
        elif p['name'] in installed:
            a.update(status='Skipped', reason='already_installed', installed_version=installed[p['name']])
        else:
            # Qualify repository to avoid a higher-priority untrusted repository shadowing it.
            repo = next(r for r in policy['trusted_repositories'] if r in available[p['name']])
            a['target'] = repo+'/'+p['name']
        actions.append(a)
    for e in snapshot['entries']:
        cat = file_category(e['path'])
        if 'all' not in configs and cat not in configs:
            continue
        a = {'kind':'file', 'path':e['path'], 'sha256':e['sha256'], 'mode':e['mode'],
             'category':cat, 'status':'Pending', 'risks':e['risks']}
        if e['restore'] != 'portable_candidate':
            a.update(status='Requires manual action', reason=e['restore'])
        else:
            target = target_file(e['path'])
            if target.is_symlink() or (target.exists() and not target.is_file()):
                a.update(status='Requires manual action', reason='unsafe_destination_type')
            else:
                a['target_before'] = digest(target.read_bytes()) if target.is_file() else None
                a['target_before_mode'] = (target.stat().st_mode & 0o777) if target.is_file() else None
                if a['target_before'] == e['sha256'] and a['target_before_mode'] == e['mode']:
                    a.update(status='Skipped', reason='identical_content')
        actions.append(a)
    if any(p['services_review'] for p in info):
        svc_path=ROOT/'manifests/services.json'
        if svc_path.exists():
            services=read_json(svc_path)
            for scope, states in services['scopes'].items():
                for unit in sorted(set(states['enabled'])):
                    actions.append({'kind':'service','name':unit,'scope':scope,
                                    'status':'Requires manual action',
                                    'reason':'review_target_unit_and_dependencies_before_enabling; never_replay_active_state'})
    for profile in info:
        if profile['hardware_review']:
            manual.append('Review target GPU, hybrid graphics, kernel, firmware, suspend and monitor topology before configuring hardware.')
        if profile['services_review']:
            manual.append('Review manifests/services.json. Enable individually on destination; never replay active units or start/restart automatically.')
    # Every desktop plan explicitly exposes dependencies that cannot be resolved automatically.
    selected = {a['name'] for a in actions if a['kind']=='package'}
    by_name = {p['name']:p for p in packages['packages']}
    todo, seen = list(selected), set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        p = by_name.get(name,{})
        for dep in p.get('dependencies',[]):
            dep = re.split(r'[<>=]',dep)[0]
            if dep in by_name:
                todo.append(dep)
                d = by_name[dep]
                if dep not in selected and dep not in installed and (d['origin'].startswith('foreign') or d['compatibility']!='portable'):
                    manual.append(f"Dependency {dep} of {name}: {d['origin']}, {d['compatibility']}; verify on destination")
    body = {'schema':1, 'created_at':now(), 'profiles':sorted(set(names)), 'capture':snapshot['id'],
            'target_host':host_fingerprint(), 'target_home':str(HOME), 'target_config':str(CONFIG),
            'source_host':source_guard()['machine_hash'], 'target_is_source':source_guard()['machine_hash']==host_fingerprint(),
            'actions':actions, 'manual':sorted(set(manual)),
            'hardware': {'source':'manifests/hardware.json', 'target':target_hardware()},
            'warnings':['Package application includes a full Arch upgrade and can run package hooks; review Arch news and the pacman transaction.',
                        'Existing files are backed up before overwrite; services, shell, boot, partitioning and drivers are never configured automatically.',
                        'Foreign packages, hardware config, assets and external managers require manual review. A plan may be partially reproducible.']}
    body['id'] = plan_digest(body)
    atomic_json(ROOT/'state/plans'/f"{body['id']}.json",body)
    atomic_json(ROOT/'state/latest-plan.json',{'id':body['id']})
    return body


def target_hardware():
    q = run(['lspci','-nnk'])
    return {'gpu': [l.partition(' ')[2] for l in q['stdout'].splitlines() if re.search('VGA compatible|3D controller|Display controller',l)],
            'laptop': any(Path('/sys/class/power_supply').glob('BAT*')),
            'policy':'review only; drivers never inferred solely from vendor'}


def plan_digest(plan):
    import json
    return digest(json.dumps({k:v for k,v in plan.items() if k not in {'id','created_at'}}, sort_keys=True).encode())


def load_plan(identifier='latest'):
    if identifier=='latest':
        identifier = read_json(ROOT/'state/latest-plan.json')['id']
    if not re.fullmatch(r'[a-f0-9]{64}',identifier):
        raise ValueError('Invalid plan ID')
    plan = read_json(inside(ROOT/'state/plans'/f'{identifier}.json',ROOT/'state/plans'))
    if plan.get('id')!=identifier or plan_digest(plan)!=identifier:
        raise ValueError('Plan checksum mismatch; generate a new plan')
    return plan

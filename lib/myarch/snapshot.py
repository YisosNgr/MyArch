"""Content-addressed captures: exact bytes, explicit exclusions, no active writes."""
from pathlib import Path
import json
import os
import re
from .resources import capture_references, verify_resources
from .desktop_engine import capture_project, project_resource
from .common import (ROOT, HOME, CONFIG, now, digest, atomic_json, atomic_bytes,
                     read_json, inside, expand_path, sensitive, record_file)


def logical_path(path):
    path = Path(path)
    if path.is_relative_to(CONFIG):
        return 'config/' + str(path.relative_to(CONFIG))
    for prefix, root in [('state', HOME/'.local/state/caelestia')]:
        if path.is_relative_to(root):
            return prefix+'/caelestia/'+str(path.relative_to(root))
    if path.parent == HOME and path.name in {'.gitconfig', '.tmux.conf', '.bashrc', '.bash_profile'}:
        return 'home/'+path.name
    raise ValueError('Source is not in a recognized configuration root')


def safe_relative(value):
    if not isinstance(value,str) or not value or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Invalid relative path')
    p = Path(value)
    if p.is_absolute() or '..' in p.parts or not p.parts or str(p) != value or '\\' in value:
        raise ValueError('Invalid relative path')
    return p


def blob_path(sha):
    if not re.fullmatch(r'[a-f0-9]{64}', sha):
        raise ValueError('Invalid object digest')
    p = ROOT/'dotfiles/objects'/sha
    inside(p, ROOT/'dotfiles/objects')
    return p


def load_snapshot(identifier='latest'):
    if identifier == 'latest':
        identifier = read_json(ROOT/'state/latest-capture.json')['id']
    if not re.fullmatch(r'[0-9TZ-]+-[a-f0-9]{12}', identifier):
        raise ValueError('Invalid snapshot ID')
    data = read_json(inside(ROOT/'dotfiles/snapshots'/f'{identifier}.json', ROOT/'dotfiles/snapshots'))
    check_snapshot_metadata(data, identifier)
    return data


def check_snapshot_metadata(data, identifier):
    if not isinstance(data,dict) or type(data.get('schema')) is not int or data['schema'] not in {1,2}:
        raise ValueError('Unsupported snapshot schema')
    if data.get('id')!=identifier or not isinstance(data.get('entries'),list):
        raise ValueError('Snapshot identity or entries mismatch')
    expected=snapshot_digest(data)[:12] if data['schema']==2 else digest(str(data['entries']).encode())[:12]
    if identifier.rsplit('-',1)[1]!=expected:
        raise ValueError('Snapshot metadata checksum mismatch')


def snapshot_digest(data):
    body={k:v for k,v in data.items() if k not in {'id','created_at'}}
    return digest(json.dumps(body,sort_keys=True,ensure_ascii=False).encode())


def capture(desktop_engine_source=None):
    manifest = read_json(ROOT/'manifests/dotfiles.json')
    entries = list(manifest['entries'])
    for name in ['scheme.json', 'sequences.txt']:
        p = HOME/'.local/state/caelestia'/name
        if p.is_file() and not p.is_symlink():
            entries.append({**record_file(p), 'restore': 'portable_candidate', 'risks': []})
    accepted, excluded = [], []
    for entry in entries:
        if entry['status'] != 'candidate':
            excluded.append({'source': entry['source'], 'reason': entry['status']})
            continue
        p = expand_path(entry['source'])
        check = record_file(p)
        if check.get('sha256') != entry.get('sha256') or check['status'] != 'candidate':
            excluded.append({'source': entry['source'], 'reason': 'changed_since_audit_or_unsafe'})
            continue
        data = p.read_bytes()
        if b'\x00' in data or p.suffix.lower() in {'.png','.jpg','.jpeg','.gif','.webp','.woff','.ttf','.otf','.ico','.sqlite'}:
            excluded.append({'source': entry['source'], 'reason': 'binary_asset_requires_license_review'})
            continue
        if digest(data) != entry['sha256'] or sensitive(p, data):
            raise ValueError('File changed during capture or contains possible secret')
        logical = logical_path(p)
        sha = digest(data)
        atomic_bytes(blob_path(sha), data)
        accepted.append({'path': logical, 'source': entry['source'], 'sha256': sha,
                         'mode': entry['mode'] & 0o755, 'restore': entry.get('restore', 'manual_review'),
                         'risks': entry.get('risks', []), 'size': len(data)})
    apps_path = ROOT/'manifests/applications.json'
    resources = capture_references(read_json(apps_path)) if apps_path.exists() else []
    if desktop_engine_source is not None:
        state_home = Path(os.environ.get('XDG_STATE_HOME') or HOME/'.local/state')
        profiles = state_home/'desktop-engine/profiles.json'
        resources.append(capture_project(desktop_engine_source, profiles))
    elif (ROOT/'state/latest-capture.json').is_file():
        previous_project = project_resource(load_snapshot())
        if previous_project is not None:
            if verify_resources([previous_project]):
                raise ValueError('Previous Desktop Engine archive is unavailable; supply its source to refresh it')
            resources.append(previous_project)
    body = {'schema': 2, 'resources': resources, 'created_at': now(), 'entries': accepted, 'excluded': excluded,
            'include_graph': manifest['include_graph'],
            'state': 'exported_exact_bytes; desired_state_requires_plan_review'}
    ident = body['created_at'][:19].replace(':','-').replace('+','')+'Z-'+snapshot_digest(body)[:12]
    body['id'] = ident
    dest = ROOT/'dotfiles/snapshots'/f'{ident}.json'
    if dest.exists():
        raise ValueError('Capture ID already exists; wait a second before capturing again')
    atomic_json(dest, body)
    atomic_json(ROOT/'state/latest-capture.json', {'id': ident})
    return {'id': ident, 'captured': len(accepted), 'private_reference_resources': len(resources), 'excluded': excluded}


def verify(snapshot, object_reader=None, resource_reader=None):
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('entries'),list):
        return [{'error':'Invalid snapshot entries'}]
    errors = verify_resources(snapshot.get('resources', []), resource_reader)
    paths = set()
    for e in snapshot['entries']:
        try:
            if not isinstance(e,dict):
                raise ValueError('Invalid snapshot entry')
            safe_relative(e['path'])
            if e['path'] in paths:
                raise ValueError('Duplicate snapshot destination')
            if any(e['path'].startswith(p+'/') or p.startswith(e['path']+'/') for p in paths):
                raise ValueError('Conflicting parent and child destinations')
            paths.add(e['path'])
            mode=e.get('mode')
            if type(mode) is not int or mode<0 or mode & ~0o755:
                raise ValueError('Invalid snapshot permission mode')
            p = blob_path(e['sha256'])
            if object_reader is None:
                if p.is_symlink():
                    raise ValueError('Object symlink is forbidden')
                data=p.read_bytes()
            else:
                data=object_reader(e['sha256'])
            if digest(data)!=e['sha256']:
                raise ValueError('Object checksum mismatch')
            if type(e.get('size')) is not int or e['size']!=len(data):
                raise ValueError('Object size mismatch')
            if sensitive(e['path'],data):
                raise ValueError('Possible secret in snapshot')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({'path':e.get('path') if isinstance(e,dict) else None,'error':str(exc)})
    return errors

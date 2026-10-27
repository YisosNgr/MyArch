"""Content-addressed captures: exact bytes, explicit exclusions, no active writes."""
from pathlib import Path
import json
import re
from .resources import capture_references, verify_resources
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
    if data['id'] != identifier:
        raise ValueError('Snapshot identity mismatch')
    expected = snapshot_digest(data)[:12] if data['schema'] == 2 else digest(str(data['entries']).encode())[:12]
    if identifier.rsplit('-',1)[1] != expected:
        raise ValueError('Snapshot metadata checksum mismatch')
    return data


def snapshot_digest(data):
    body={k:v for k,v in data.items() if k not in {'id','created_at'}}
    return digest(json.dumps(body,sort_keys=True,ensure_ascii=False).encode())


def capture():
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


def verify(snapshot):
    errors = verify_resources(snapshot.get('resources', []))
    paths = set()
    for e in snapshot['entries']:
        try:
            safe_relative(e['path'])
            if e['path'] in paths:
                raise ValueError('Duplicate snapshot destination')
            paths.add(e['path'])
            p = blob_path(e['sha256'])
            if p.is_symlink() or digest(p.read_bytes()) != e['sha256']:
                raise ValueError('Object checksum mismatch')
            if sensitive(e['path'], p.read_bytes()):
                raise ValueError('Possible secret in snapshot')
        except (OSError, ValueError) as exc:
            errors.append({'path': e.get('path'), 'error': str(exc)})
    return errors

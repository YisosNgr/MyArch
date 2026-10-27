"""Private reference assets; never install or redistribute them automatically."""
from pathlib import Path
import re
from .common import ROOT, HOME, now, digest, atomic_bytes, local_path, sensitive, inside


def resource_path(sha):
    if not re.fullmatch(r'[a-f0-9]{64}',sha):
        raise ValueError('Invalid resource digest')
    return inside(ROOT/'assets/objects'/sha,ROOT/'assets/objects')


def capture_references(applications):
    paths=[]
    current=HOME/'.local/state/caelestia/wallpaper/current'
    if current.is_symlink():
        resolved=current.resolve()
        # Follow just this documented current-wallpaper link, never directory trees.
        if resolved.is_relative_to(HOME) and resolved.is_file():
            paths.append((resolved,'current_wallpaper','unknown_manual_review'))
    for p in [HOME/'.local/state/caelestia/wallpaper/path.txt',HOME/'.local/state/caelestia/dots-state.json',Path('/etc/sddm.conf')]:
        if p.is_file() and not p.is_symlink():
            paths.append((p,'reference_configuration','configuration_review'))
    themes=[]
    for lines in applications.get('sddm',{}).values():
        for line in lines:
            if line.startswith('Current=') and re.fullmatch(r'[A-Za-z0-9._-]+',line.partition('=')[2]):
                themes.append(line.partition('=')[2])
    for theme in themes:
        base=Path('/usr/share/sddm/themes')/theme
        metadata=base/'metadata.desktop'
        if metadata.is_file() and not metadata.is_symlink():
            paths.append((metadata,'sddm_metadata','configuration_review'))
            try:
                for value in re.findall(r'^ConfigFile\s*=\s*(.+)$',metadata.read_text(),re.M):
                    p=base/value.strip()
                    if p.resolve().is_relative_to(base.resolve()) and p.is_file() and not p.is_symlink():
                        paths.append((p,'sddm_theme_config','configuration_review'))
            except OSError:
                pass
        for name in ['theme.conf','theme.conf.user','LICENSE']:
            p=base/name
            if p.is_file() and not p.is_symlink():
                paths.append((p,'sddm_reference','configuration_review'))
    resources=[]
    for p,kind,license_state in paths:
        try:
            if p.stat().st_size>64*1024*1024 or sensitive(p):
                continue
            data=p.read_bytes()
            if sensitive(p,data):
                continue
            sha=digest(data)
            atomic_bytes(resource_path(sha),data)
            resources.append({'source':local_path(p),'name':p.name,'kind':kind,'sha256':sha,'size':len(data),
                              'restore':'manual_reference_only','redistribution':license_state,'private_only':True})
        except OSError:
            continue
    return resources


def verify_resources(resources, reader=None):
    if not isinstance(resources,list):
        return [{'error':'Invalid resources list'}]
    failures=[]
    for r in resources:
        try:
            if not isinstance(r,dict):
                raise ValueError('Invalid resource entry')
            name=r.get('name')
            if not isinstance(name,str) or not name or Path(name).name!=name or name in {'.','..'} or any(ord(c)<32 or ord(c)==127 for c in name):
                raise ValueError('Invalid resource display name')
            p=resource_path(r['sha256'])
            if reader is None:
                if p.is_symlink():
                    raise ValueError('Resource symlink is forbidden')
                data=p.read_bytes()
            else:
                data=reader(r['sha256'])
            if digest(data)!=r['sha256']:
                raise ValueError('Resource checksum mismatch')
            if type(r.get('size')) is not int or r['size']!=len(data):
                raise ValueError('Resource size mismatch')
        except (ValueError,OSError,KeyError,TypeError) as exc:
            failures.append({'resource':r.get('name') if isinstance(r,dict) else None,'error':str(exc)})
    return failures

"""Additional static dependency, provenance and visual-resource discovery."""
import json
import os
from pathlib import Path
import re
from .common import HOME, CONFIG, local_path, record_file, sensitive


def fields(path):
    result, key = {}, None
    for line in path.read_text().splitlines():
        if line.startswith('%') and line.endswith('%'):
            key = line.strip('%')
            result[key] = []
        elif key and line:
            result[key].append(line)
    return result


def package_metadata(packages):
    metadata = {}
    for path in Path('/var/lib/pacman/local').glob('*/desc'):
        try:
            d = fields(path)
            name = d.get('NAME', [''])[0]
            metadata[name] = d
        except (OSError, ValueError):
            continue
    for p in packages:
        d = metadata.get(p['name'], {})
        p['dependencies'] = d.get('DEPENDS', [])
        p['optional_dependencies'] = d.get('OPTDEPENDS', [])
        p['license_metadata'] = d.get('LICENSE', [])
        url = d.get('URL', [])
        p['upstream_url'] = [u for u in url if not sensitive('url', u.encode())]
        p['provides'] = d.get('PROVIDES', [])
        p['conflicts'] = d.get('CONFLICTS', [])
        if p['origin'] == 'foreign_unverified':
            evidence = []
            for root in [HOME/'.cache/paru/clone', HOME/'.cache/yay']:
                for base in d.get('BASE', [p['name']]):
                    candidate = root / base
                    if not candidate.is_dir():
                        continue
                    origin = None
                    conf = candidate / '.git/config'
                    if conf.is_file():
                        # Read the local Git configuration as text; no hooks, includes or network.
                        for line in conf.read_text(errors='replace').splitlines():
                            if re.match(r'\s*url\s*=', line):
                                value = line.partition('=')[2].strip()
                                if re.fullmatch(r'(https://aur\.archlinux\.org/|ssh://aur@aur\.archlinux\.org/)[A-Za-z0-9@._/-]+', value):
                                    origin = value
                                    break
                    evidence.append({'build_tree': local_path(candidate), 'remote': origin,
                                     'pkgbuild': record_file(candidate/'PKGBUILD'),
                                     'srcinfo': record_file(candidate/'.SRCINFO'),
                                     'meaning': 'local build tree; does not prove installed binary matches recipe'})
            p['source_evidence'] = evidence
            if any(e['remote'] for e in evidence):
                p['origin'] = 'foreign_with_local_aur_tree'
                p['restore'] = 'review_recipe_and_build_as_user'
    return packages


def lua_graph(entries):
    """Resolve literal require() against known config search roots. Never evaluate Lua."""
    graph = []
    for e in entries:
        if e['status'] != 'candidate' or not e['source'].endswith('.lua'):
            continue
        p = HOME/e['source'][2:] if e['source'].startswith('~/') else Path(e['source'])
        try:
            text = p.read_text()
        except (OSError, UnicodeError):
            continue
        roots = [CONFIG/'hypr', CONFIG/'caelestia'] if p.is_relative_to(CONFIG/'hypr') else [p.parent, CONFIG/'nvim/lua', CONFIG/'caelestia']
        for module in re.findall(r'\brequire\s*\(?\s*["\x27]([^"\x27]+)["\x27]', text):
            targets = []
            for root in roots:
                for tail in [module.replace('.', '/')+'.lua', module.replace('.', '/')+'/init.lua']:
                    candidate = root / tail
                    if candidate.is_file():
                        targets.append(local_path(candidate))
            graph.append({'from': e['source'], 'expression': 'require('+module+')',
                          'targets': sorted(set(targets)),
                          'status': 'resolved_static_lua' if targets else 'external_or_dynamic_manual'})
    return graph


def visual_resources():
    roots = [HOME/'.local/share/fonts', HOME/'.local/share/icons', HOME/'.local/share/themes',
             HOME/'.icons', HOME/'.themes', HOME/'Pictures/Wallpapers', HOME/'Imágenes/Wallpapers',
             Path('/usr/share/sddm/themes/sddm-astronaut-theme')]
    result = []
    for root in roots:
        if not root.is_dir():
            continue
        count, total, licenses = 0, 0, []
        for parent, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in {'.git', 'node_modules', 'Previews'})
            for n in names:
                p = Path(parent)/n
                if p.is_symlink():
                    continue
                try:
                    count += 1
                    total += p.stat().st_size
                except OSError:
                    continue
                if n.lower().startswith(('license', 'copying', 'ofl', 'copyright')):
                    licenses.append(record_file(p))
        result.append({'source': local_path(root), 'files': count, 'bytes': total,
                       'licenses': licenses, 'redistribution': 'manual_legal_review',
                       'restore': 'reinstall_from_verified_origin_or_local_private_resource'})
    state = HOME/'.local/state/caelestia'
    for name in ['scheme.json', 'sequences.txt', 'dots-state.json', 'wallpaper']:
        p = state/name
        if p.exists() or p.is_symlink():
            r = record_file(p)
            r['redistribution'] = 'manual_legal_review' if name == 'wallpaper' else 'configuration_review'
            result.append(r)
    return result


def desktop_runtime(query):
    active=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc/'comm').read_text().strip().lower()!='hyprland':
                continue
            args=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
            config=None
            for i,arg in enumerate(args):
                if arg in {'-c','--config'} and i+1<len(args):
                    config=local_path(Path(args[i+1]))
                elif arg.startswith('--config='):
                    config=local_path(Path(arg.partition('=')[2]))
            active.append({'explicit_config':config,'default_candidate':local_path(CONFIG/'hypr/hyprland.lua'),
                           'evidence':'Hyprland process command-line config option only'})
        except OSError:
            pass
    versions={}
    raw=query(['hyprctl','version'])
    versions['hyprland']=raw.splitlines()[:3]
    # CLI execution is unnecessary for other tools: package versions are authoritative inventory.
    nvim={}
    lock=CONFIG/'nvim/lazy-lock.json'
    if lock.is_file():
        try:
            nvim={'manager':'lazy.nvim','plugin_lock':json.loads(lock.read_text()),
                  'bootstrap':'manual: restore configuration, obtain lazy.nvim, then review plugin builds and external LSP tools before opening Neovim'}
        except (ValueError,OSError):
            nvim={'plugin_lock':'unreadable'}
    return {'hyprland_processes':active,'versions':versions,'neovim':nvim}

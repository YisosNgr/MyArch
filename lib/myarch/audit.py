"""Read-only inventory; output stays in MyArch. Never execute configuration files."""
from collections import Counter
import glob
import json
import os
from pathlib import Path
import platform
import re
import shutil
from .discovery import package_metadata, lua_graph, visual_resources, desktop_runtime
from .common import (ROOT, HOME, CONFIG, now, run, atomic_json, atomic_bytes,
                     local_path, record_file, sensitive)

OFFICIAL = {'core', 'extra', 'multilib', 'core-testing', 'extra-testing', 'multilib-testing',
            'core-staging', 'extra-staging', 'multilib-staging'}
CONFIG_NAMES = ['hypr', 'caelestia', 'quickshell', 'fish', 'fastfetch', 'nvim', 'foot',
                'kitty', 'alacritty', 'ghostty', 'starship.toml', 'fuzzel', 'rofi', 'wofi',
                'waybar', 'mako', 'swaync', 'gtk-3.0/settings.ini', 'gtk-4.0/settings.ini',
                'qt5ct', 'qt6ct', 'Kvantum', 'qtengine', 'tmux', 'zellij', 'MangoHud',
                'gamemode.ini', 'wireplumber', 'pipewire', 'xdg-desktop-portal',
                'systemd/user', 'autostart', 'sunshine/sunshine.conf', 'Code/User/settings.json',
                'Code/User/keybindings.json', 'VSCodium/User/settings.json', 'fontconfig']
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'cache', '.cache', 'lazy', 'plugged',
             'undo', 'swap', 'backups', 'logs', 'venv', '.venv', 'site-packages'}


def category(name, groups=()):
    n = name.lower()
    if any(g.startswith('blackarch') for g in groups) or re.search(r'^(nmap|wireshark|tcpdump|burpsuite|metasploit|sqlmap|john|hashcat|hydra|radare2|ghidra|gobuster|ffuf|aircrack|nikto|zaproxy|binwalk|sleuthkit)', n):
        return 'cybersecurity'
    if re.search(r'(steam|proton|wine|winetricks|lutris|heroic|gamemode|mangohud|gamescope|dxvk|vkd3d|retroarch|dolphin-emu|xone|xpadneo)', n):
        return 'gaming'
    if re.search(r'^(git|github-cli|code|codium|neovim|vim|nodejs|npm|pnpm|yarn|python|uv$|jdk|jre|gcc|clang|cmake|make$|rust|cargo|go$|php|docker|podman|postgresql|mariadb|sqlite|httpie|curl|jq|android|qemu|libvirt|test|meson|ninja|base-devel)', n):
        return 'development'
    if re.search(r'(sunshine|moonlight|obs-studio|ffmpeg|mpv|vlc|blender|gimp|krita|audacity|imagemagick)', n):
        return 'multimedia'
    if re.search(r'(hypr|caelestia|quickshell|sddm|wayland|xdg-desktop|pipewire|wireplumber|polkit|bluez|fish|foot|kitty|alacritty|ghostty|fastfetch|starship|font|ttf-|otf-|noto|gtk|qt[56]|kvantum|theme|icon|cursor|swww|waybar|rofi|wofi|fuzzel|mako|swaync)', n):
        return 'desktop'
    return 'core'


def compatibility(name):
    if re.search(r'^(lib32-)?(nvidia|opencl-nvidia)', name):
        return 'nvidia_manual'
    if re.search(r'^(lib32-)?(vulkan-radeon|amdvlk|xf86-video-amdgpu|rocm|opencl-rusticl)', name):
        return 'amd_manual'
    if re.search(r'^(lib32-)?(vulkan-intel|intel-media|xf86-video-intel)', name):
        return 'intel_manual'
    if re.search(r'(ucode$|^linux($|-)|^mkinitcpio|^dracut|^grub$|^refind|^systemd|firmware|^mesa$|^lib32-mesa$|^vulkan-|^lib32-vulkan-)', name):
        return 'system_manual'
    return 'portable'


class Audit:
    def __init__(self):
        self.evidence = []
        self.warnings = []

    def query(self, argv, timeout=30):
        q = run(argv, timeout)
        self.evidence.append({k: v for k, v in q.items() if k != 'stdout'})
        return q['stdout'] if q['status'] == 'ok' else ''

    def pacman(self):
        all_pkgs = self.query(['pacman', '-Q'])
        if self.evidence[-1]['status'] != 'ok' or not all_pkgs.strip():
            raise ValueError('Required pacman inventory is unavailable; previous manifests have been preserved')
        def selection(option):
            text=self.query(['pacman',option])
            evidence=self.evidence[-1]
            empty_set=evidence['returncode']==1 and not text
            if evidence['status']!='ok' and not empty_set:
                raise ValueError('Required pacman classification is unavailable; previous manifests have been preserved')
            return set(text.splitlines())
        explicit = selection('-Qeq')
        foreign = selection('-Qmq')
        orphans = set(self.query(['pacman', '-Qdtq']).splitlines())
        groups = {}
        for line in self.query(['pacman', '-Qg']).splitlines():
            parts = line.split()
            if len(parts) == 2:
                groups.setdefault(parts[1], []).append(parts[0])
        repos = {}
        for line in self.query(['pacman', '-Sl'], 60).splitlines():
            parts = line.split()
            if len(parts) >= 3:
                repos.setdefault(parts[1], []).append(parts[0])
        result = []
        for line in all_pkgs.splitlines():
            name, version = line.split(maxsplit=1)
            available = repos.get(name, [])
            is_foreign = name in foreign
            item = dict(name=name, version=version, manager='pacman',
                        installation_reason='explicit' if name in explicit else 'dependency',
                        origin='foreign_unverified' if is_foreign else 'repository_available_not_install_origin',
                        available_in=available, official_available=bool(OFFICIAL.intersection(available)),
                        groups=groups.get(name, []), orphan=name in orphans,
                        category=category(name, groups.get(name, [])), compatibility=compatibility(name),
                        necessary='observed_explicit' if name in explicit else 'dependency_resolver_or_review',
                        special_dependencies='resolved_by_pacman; optional_dependencies_need_review',
                        restore='manual_source_review' if is_foreign else 'current_repository_version',
                        confidence='high_inventory_origin_unverified', evidence='pacman -Q/-Qeq/-Qmq/-Qg/-Sl')
            result.append(item)
        repositories = self.query(['pacman-conf', '--repo-list']).splitlines()
        ignored = {key: self.query(['pacman-conf', key]).split() for key in ['IgnorePkg', 'IgnoreGroup']}
        return {'schema': 1, 'generated_at': now(), 'version_policy': 'historical_only; install_current_compatible_versions',
                'packages': package_metadata(result), 'repositories': repositories, 'ignored': ignored,
                'helpers': [h for h in ['yay', 'paru', 'pikaur', 'trizen', 'aura'] if shutil.which(h)],
                'foreign_is_not_aur': True}

    def system(self):
        def text(path):
            try:
                return Path(path).read_text().strip()
            except OSError:
                return None
        services = {}
        for scope in ['system', 'user']:
            prefix = ['systemctl'] + (['--user'] if scope == 'user' else [])
            services[scope] = {}
            for state, opts in [('enabled', ['list-unit-files', '--state=enabled']),
                                ('active', ['list-units', '--state=active', '--type=service']),
                                ('failed', ['--failed'])]:
                raw = self.query(prefix + opts + ['--no-legend', '--no-pager', '--plain'], 15)
                services[scope][state] = [line.split()[0] for line in raw.splitlines() if line.strip()]
        mounts = self.query(['findmnt', '-J', '-o', 'TARGET,FSTYPE,OPTIONS'])
        # No mount source, UUID, IP, MAC, serial, DMI identifiers or full environment.
        try:
            mount_data = json.loads(mounts)
            def clean(nodes):
                return [{'target': n['target'] if n['target'].startswith(('/boot', '/home', '/var')) or n['target'] == '/' else '[other]',
                         'fstype': n.get('fstype'), 'children': clean(n.get('children', []))} for n in nodes]
            mount_data = clean(mount_data.get('filesystems', []))
        except ValueError:
            mount_data = []
        lspci = self.query(['lspci', '-nnk'])
        gpu = []
        lines = lspci.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'VGA compatible|3D controller|Display controller', line):
                gpu.append({'device': line.partition(' ')[2],
                            'driver': next((v.strip().partition(': ')[2] for v in lines[i+1:i+4] if 'Kernel driver in use:' in v), None)})
        monitors = []
        try:
            for m in json.loads(self.query(['hyprctl', '-j', 'monitors', 'all']) or '[]'):
                monitors.append({k: m[k] for k in ['name', 'make', 'model', 'width', 'height', 'refreshRate', 'scale', 'x', 'y', 'disabled', 'availableModes'] if k in m})
        except (ValueError, TypeError):
            self.warnings.append('hyprctl monitor data unavailable')
        cpu = self.query(['lscpu', '-J'])
        try:
            wanted = {'Architecture:', 'CPU(s):', 'Model name:', 'Vendor ID:'}
            cpu = {r['field']: r['data'] for r in json.loads(cpu)['lscpu'] if r['field'] in wanted}
        except (ValueError, KeyError):
            cpu = {'architecture': platform.machine()}
        fonts = self.query(['fc-list', '--format=%{family}\t%{style}\n'])
        system = {'schema': 1, 'generated_at': now(), 'os_release': text('/etc/os-release'),
                  'architecture': platform.machine(), 'kernel': platform.release(),
                  'session': {k: os.environ.get(k) for k in ['XDG_CURRENT_DESKTOP', 'XDG_SESSION_TYPE', 'LANG']},
                  'xdg_paths': {k: local_path(os.environ[k]) for k in ['XDG_CONFIG_HOME', 'XDG_DATA_HOME'] if k in os.environ},
                  'locale': text('/etc/locale.conf'), 'keyboard': text('/etc/vconsole.conf'),
                  'timezone': self.query(['timedatectl', 'show', '-p', 'Timezone', '--value']).strip(),
                  'mounts_inventory_only': mount_data,
                  'boot_inventory_only': {'uefi': Path('/sys/firmware/efi').exists(),
                      'boot_entries': self.directory_names(Path('/boot')),
                      'policy': 'names only; no EFI variable or bootloader mutation'},
                  'network': {'services_only': [s for s in services['system']['enabled'] if re.search(r'NetworkManager|networkd|iwd|dhcpcd|resolved', s)],
                              'connections': 'excluded: profiles may contain credentials'},
                  'fonts': sorted(set(fonts.splitlines())),
                  'etc_candidates': [record_file(p) for p in self.etc_files()]}
        hardware = {'schema': 1, 'generated_at': now(), 'cpu': cpu, 'gpu': gpu,
                    'hybrid': len(gpu) > 1, 'memory_kib': next((l.split()[1] for l in (text('/proc/meminfo') or '').splitlines() if l.startswith('MemTotal:')), None),
                    'laptop': (Path('/sys/class/power_supply/BAT0').exists() or Path('/sys/class/power_supply/BAT1').exists()),
                    'monitors': monitors, 'storage_inventory': self.storage(),
                    'board': {n: text('/sys/class/dmi/id/'+n) for n in ['board_vendor','board_name']}, 'policy': 'inventory_only; no disk IDs; no driver or monitor auto-application'}
        return system, hardware, {'schema': 1, 'generated_at': now(), 'scopes': services,
                                  'restore': 'manual_enable_only; never_start_or_restart_automatically'}

    def directory_names(self, path):
        try:
            return {'status':'ok','entries':sorted(p.name for p in path.iterdir())}
        except OSError:
            self.warnings.append('Directory inventory unavailable without privileges: '+str(path))
            return {'status':'unavailable_without_privileges','entries':[]}

    def storage(self):
        raw=self.query(['lsblk','-J','-b','-o','NAME,TYPE,SIZE,ROTA,TRAN,FSTYPE'])
        try:
            return json.loads(raw)
        except ValueError:
            return {'status':'unavailable'}

    def etc_files(self):
        paths = [Path(p) for p in ['/etc/pacman.conf', '/etc/mkinitcpio.conf', '/etc/default/grub',
                  '/etc/sddm.conf', '/etc/environment', '/etc/locale.conf', '/etc/vconsole.conf']]
        for pattern in ['/etc/sddm.conf.d/*.conf', '/etc/mkinitcpio.d/*.preset',
                        '/etc/xdg/caelestia/*', '/usr/share/sddm/themes/*/theme.conf',
                        '/usr/share/wayland-sessions/*.desktop']:
            paths.extend(Path(p) for p in glob.glob(pattern))
        return [p for p in paths if p.is_file()]

    def configurations(self):
        files = []
        for name in CONFIG_NAMES:
            root = CONFIG / name
            if root.is_file() or root.is_symlink():
                files.append(root)
            elif root.is_dir():
                for parent, dirs, names in os.walk(root, followlinks=False):
                    dirs[:] = sorted(
                        directory for directory in dirs
                        if directory not in SKIP_DIRS and not sensitive(directory)
                        and not (name == 'quickshell' and directory.startswith('.desktop-engine-backup-'))
                    )
                    files.extend(Path(parent) / n for n in sorted(names))
                    # Directory symlinks are recorded explicitly, never silently traversed.
                    files.extend(Path(parent) / n for n in dirs if (Path(parent) / n).is_symlink())
        for name in ['.gitconfig', '.tmux.conf', '.bashrc', '.bash_profile']:
            if (HOME / name).exists():
                files.append(HOME / name)
        entries = [record_file(p) for p in sorted(set(files))]
        graph, refs, variables = lua_graph(entries), [], {}
        by_source = {e['source']: e for e in entries}
        hyprroot = CONFIG / 'hypr'
        # Resolve static Hyprland variables only. Commands and Lua remain data, never executed.
        for p in sorted(files):
            if not p.is_file() or p.is_symlink() or p.stat().st_size > 4*1024*1024:
                continue
            e = by_source[local_path(p)]
            if e['status'] != 'candidate':
                continue
            try:
                text = p.read_text()
            except (OSError, UnicodeError):
                e['restore'] = 'binary_asset_license_review'
                continue
            if p.is_relative_to(hyprroot):
                for key, val in re.findall(r'^\s*\$(\w+)\s*=\s*(.*?)\s*$', text, re.M):
                    if not re.search(r'[;`]|\$\(', val):
                        variables[key] = val
        for p in sorted(files):
            e = by_source[local_path(p)]
            if e['status'] != 'candidate' or not p.is_file():
                continue
            try:
                text = p.read_text()
            except (OSError, UnicodeError):
                continue
            risk = []
            if re.search(r'(?im)^\s*(monitor\s*=|.*HEADLESS|output_name\s*=)|hl\.monitor\s*\(', text):
                risk.append('monitor_or_headless')
            if re.search(r'(?im)^\s*(env\s*=\s*(?:AQ_DRM_DEVICES|WLR_DRM_DEVICES|GBM_BACKEND|__GLX_VENDOR)|.*nvidia)|/dev/dri/|/sys/', text):
                risk.append('hardware_specific')
            if p.is_relative_to(CONFIG / 'sunshine') or p.is_relative_to(CONFIG / 'systemd') or p.is_relative_to(CONFIG / 'autostart'):
                risk.append('service_or_streaming_manual')
            # Local Caelestia QML can execute commands and depend on excluded assets.
            if p.is_relative_to(CONFIG / 'quickshell/caelestia'):
                risk.append('quickshell_local_shell_review')
            if p.suffix == '.lua':
                risk.append('lua_dynamic_dependency_review')
            e['risks'] = risk
            e['restore'] = 'manual_review' if risk else 'portable_candidate'
            e['features'] = sorted(set(re.findall(r'^\s*(bind\w*|windowrule\w*|workspace|exec-once|animation|source|env|monitor)\s*=', text, re.M)))
            for raw in re.findall(r'^\s*source\s*=\s*([^\n#]+)', text, re.M):
                resolved = raw.strip().strip('"\'')
                for _ in range(10):
                    old = resolved
                    resolved = re.sub(r'\$(\w+)', lambda m: variables.get(m[1], m[0]), resolved)
                    if resolved == old:
                        break
                resolved = resolved.replace('~/', str(HOME) + '/')
                if not resolved.startswith('/'):
                    resolved = str(p.parent / resolved)
                matches = sorted(glob.glob(resolved)) if '$' not in resolved else []
                graph.append({'from': e['source'], 'expression': raw.strip(),
                              'targets': [local_path(Path(m)) for m in matches],
                              'status': 'resolved' if matches else 'unresolved_manual'})
            # Inventory referenced assets and scripts, without copying their contents.
            for ref in re.findall(r'(?:~/|/home/|/usr/share/|/etc/)[^\s"\x27,;)]+', text):
                if sensitive(ref):
                    continue
                rp = Path(os.path.expanduser(ref))
                refs.append({'from': e['source'], 'reference': local_path(rp),
                             'exists': rp.exists(), 'restore': 'path_and_license_review'})
        # Includes containing nonportable or unresolved configuration cannot be auto-restored.
        changed = True
        while changed:
            changed = False
            for edge in graph:
                parent = by_source.get(edge['from'])
                blocked = edge['status'] != 'resolved' or any(t not in by_source or by_source[t].get('restore') != 'portable_candidate' for t in edge['targets'])
                if parent and blocked and parent.get('restore') == 'portable_candidate':
                    parent['restore'] = 'manual_review'
                    parent.setdefault('risks', []).append('include_dependency_manual')
                    changed = True
        return {'schema': 1, 'generated_at': now(), 'entries': entries, 'include_graph': graph,
                'references': [dict(t) for t in sorted({tuple(r.items()) for r in refs}, key=str)],
                'visual_resources': visual_resources(),
                'limitations': ['Static analysis only: runtime exec, Lua, generated config and conditional includes require review.',
                                'Secret detection is heuristic; generated content remains ignored by Git pending human review.',
                                'Symlink targets, binary assets, hardware config and license terms require explicit review.']}

    def applications(self):
        inventory = []
        for scope in ['user', 'system']:
            for kind in ['app', 'runtime']:
                raw = self.query(['flatpak', 'list', '--' + scope, '--' + kind,
                                  '--columns=application,version,branch,origin,arch'], 20)
                for line in raw.splitlines():
                    cols = line.split('\t')
                    if cols:
                        inventory.append({'name': cols[0], 'version': cols[1] if len(cols)>1 else '',
                                          'manager': 'flatpak', 'scope': scope, 'kind': kind,
                                          'details': cols[2:], 'restore': 'remote_and_permissions_review', 'confidence': 'high'})
            # Names/options only: remote URLs can contain credentials.
            remotes = self.query(['flatpak', 'remotes', '--' + scope, '--columns=name,options'])
            inventory.append({'manager': 'flatpak', 'scope': scope, 'remotes': remotes.splitlines()})
            overrides = (HOME / '.local/share/flatpak/overrides') if scope == 'user' else Path('/var/lib/flatpak/overrides')
            inventory.append({'manager': 'flatpak', 'scope': scope,
                              'overrides': [record_file(p) for p in sorted(overrides.glob('*')) if p.is_file()],
                              'restore': 'permission_review'})
        commands = [(['python3', '-m', 'pip', 'list', '--format=json'], 'pip'),
                    (['pipx', 'list', '--json'], 'pipx'),
                    (['npm', 'ls', '-g', '--json', '--depth=0'], 'npm'),
                    (['pnpm', 'ls', '-g', '--json', '--depth=0'], 'pnpm'),
                    (['yarn', 'global', 'list', '--json'], 'yarn'),
                    (['cargo', 'install', '--list'], 'cargo'),
                    (['rustup', 'toolchain', 'list'], 'rustup')]
        for cmd, manager in commands:
            raw = self.query(cmd, 20)
            # JSON package metadata is stored only if it passes the same secret filter.
            if raw and not sensitive(manager, raw.encode()):
                raw = raw.replace(str(HOME), '~')
                inventory.append({'manager': manager, 'inventory': raw,
                                  'restore': 'manual_version_and_origin_review', 'confidence': 'observed'})
        # Do not run IDEs or launch plugins in the host; parse extension metadata on disk.
        for root in [HOME / '.vscode/extensions', HOME / '.vscode-oss/extensions']:
            for p in sorted(root.glob('*/package.json')):
                try:
                    d = json.loads(p.read_text())
                    inventory.append({'manager': 'vscode-extension', 'name': str(d.get('publisher'))+'.'+str(d.get('name')),
                                      'version': d.get('version'), 'restore': 'marketplace_review', 'confidence': 'metadata'})
                except (OSError, ValueError):
                    pass
        for root in [HOME / 'Applications', HOME / '.local/bin', Path('/usr/local/bin'),
                     HOME / '.local/share/Steam/compatibilitytools.d', HOME / '.steam/root/compatibilitytools.d',
                     HOME / '.sdkman/candidates', HOME / 'Android/Sdk', Path('/opt')]:
            if root.is_dir():
                inventory.append({'manager': 'manual_or_source_or_sdk', 'directory': local_path(root),
                                  'entries': [p.name for p in sorted(root.iterdir()) if not sensitive(p.name)],
                                  'restore': 'manual_origin_license_review', 'confidence': 'presence_only'})
        # SDDM theme selection only; not arbitrary config contents.
        sddm = {}
        for p in self.etc_files():
            if 'sddm' in str(p):
                try:
                    sddm[local_path(p)] = [l.strip() for l in p.read_text().splitlines() if re.match(r'^\s*(Current|ThemeDir|Font|CursorTheme|Session|DisplayServer|Background)\s*=', l)]
                except OSError:
                    pass
        return {'schema': 1, 'generated_at': now(), 'inventory': inventory, 'sddm': sddm, 'desktop_runtime': desktop_runtime(self.query),
                'containers': 'Only installed tools inventoried; no daemon calls, environment dumps or image exports.',
                'appimage': 'Top-level ~/Applications and ~/.local/bin names only; no whole-home scan.',
                'sdkman': 'Directory inventory; never source sdkman-init.sh.',
                'sunshine': 'Config metadata only. Credentials, pairing, HEADLESS and services never auto-restored.'}

    def execute(self):
        packages = self.pacman()
        system, hardware, services = self.system()
        configs = self.configurations()
        apps = self.applications()
        for name, data in [('packages', packages), ('system', system), ('hardware', hardware),
                           ('services', services), ('dotfiles', configs), ('applications', apps)]:
            atomic_json(ROOT / 'manifests' / (name + '.json'), data)
        for name, selection in [('pacman', [p['name'] for p in packages['packages'] if p['installation_reason']=='explicit' and not p['origin'].startswith('foreign')]),
                                ('foreign-unclassified', [p['name'] for p in packages['packages'] if p['origin'].startswith('foreign')]),
                                ('flatpak', [p['name'] for p in apps['inventory'] if p.get('kind')=='app'])]:
            atomic_bytes(ROOT / 'packages' / (name+'.txt'), ('\n'.join(sorted(set(selection)))+'\n').encode())
        report = {'schema': 1, 'generated_at': now(), 'evidence': self.evidence, 'warnings': self.warnings,
                  'summary': {'packages': len(packages['packages']),
                              'explicit': sum(p['installation_reason']=='explicit' for p in packages['packages']),
                              'foreign_unclassified': sum(p['origin'].startswith('foreign') for p in packages['packages']),
                              'config_files': len(configs['entries']),
                              'config_status': dict(Counter(e['status'] for e in configs['entries'])),
                              'manual_config': sum(e.get('restore')!='portable_candidate' for e in configs['entries'])},
                  'state': 'detected; not desired until plan review',
                  'guarantees': ['No privileged calls, package mutations, service changes or configuration execution.',
                                 'Inventory versions are historical observations, not pins.',
                                 'No hostname, disk UUID, serial, network profile or whole-environment export.']}
        atomic_json(ROOT / 'manifests/audit-report.json', report)
        return report['summary']

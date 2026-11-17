"""Copy an explicitly selected Desktop Engine project into a private bundle."""
import gzip
import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

from .common import atomic_bytes, digest, read_json, sensitive
from .resources import resource_path

KIND = 'desktop_engine_project'
PROJECT_DIRS = {'desktop_engine', 'ui', 'collection', 'integration', 'tools', 'tests', 'docs'}
PROFILES = 'myarch-profiles.json'
ROOT_FILES = {'desktopctl', 'desktop-manager', 'README.md', 'LICENSE', '.gitignore'}
REQUIRED = {'desktopctl', 'desktop-manager', 'desktop_engine/cli.py', 'ui/shell.qml'}
SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', '.venv', 'node_modules'}
ARCHIVE_LIMIT = 256 * 1024 * 1024
MAX_FILES = 5000
PRIVATE_FILE = re.compile(r'^(?:\.env(?:$|\.)|\.netrc$|credentials\.json$|auth\.json$|secrets\.json$|id_(?:rsa|ed25519)$)|\.(?:pem|key|p12|pfx)$', re.I)
PRIVATE_VALUE = re.compile(
    rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|'
    rb'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|'
    rb'AKIA[A-Z0-9]{16}|https?://[^\s/:]+:[^\s/@]+@'
)


def relative_member(name):
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or '..' in path.parts or name != str(path)
            or '\\' in name or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ValueError('Invalid Desktop Engine archive path')
    parts = path.parts
    selected = parts[0] in (ROOT_FILES | {PROFILES} if len(parts) == 1 else PROJECT_DIRS)
    if not selected or PRIVATE_FILE.search(path.name) or any(part in SKIP_DIRS for part in parts):
        raise ValueError('Unexpected Desktop Engine archive path')
    return path


def project_files(source):
    for name in sorted(ROOT_FILES | PROJECT_DIRS):
        path = source / name
        if path.is_symlink():
            raise ValueError(f'Desktop Engine source contains a link: {name}')
        if name in ROOT_FILES:
            if path.is_file():
                yield path
            continue
        for parent, directories, files in os.walk(path, followlinks=False):
            directories[:] = sorted(set(directories) - SKIP_DIRS)
            for child in directories + files:
                if (Path(parent) / child).is_symlink():
                    raise ValueError(f'Desktop Engine source contains a link: {child}')
            for child in sorted(files):
                if not PRIVATE_FILE.search(child) and not child.endswith(('.pyc', '.pyo', '.bak')):
                    yield Path(parent) / child


def capture_project(source, profiles=None):
    source = Path(source).expanduser()
    if not source.is_dir() or source.is_symlink():
        raise ValueError('Desktop Engine source must be a directory')
    selected = {path.relative_to(source).as_posix(): path for path in project_files(source)}
    if profiles is not None and (profiles.exists() or profiles.is_symlink()):
        profile_data(profiles)
        selected[PROFILES] = profiles
    if not REQUIRED <= selected.keys():
        raise ValueError('Desktop Engine source is missing a required entry point')
    if len(selected) > MAX_FILES or sum(path.stat().st_size for path in selected.values()) > ARCHIVE_LIMIT:
        raise ValueError('Desktop Engine source exceeds the archive limit')
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for name, path in sorted(selected.items()):
                relative_member(name)
                if not path.is_file():
                    raise ValueError(f'Desktop Engine source is not a regular file: {name}')
                data = path.read_bytes()
                if PRIVATE_VALUE.search(data):
                    raise ValueError(f'Possible credential in Desktop Engine file: {name}')
                entry = tarfile.TarInfo(name)
                entry.mode = path.stat().st_mode & 0o755
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
    data = buffer.getvalue()
    sha = digest(data)
    atomic_bytes(resource_path(sha), data)
    return {'kind': KIND, 'name': 'desktop-engine.tar.gz', 'sha256': sha, 'size': len(data),
            'files': len(selected), 'source': 'explicit_local_project', 'private_only': True,
            'redistribution': 'manual_license_review', 'restore': 'manual_project_install'}


def profile_data(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('Unsafe Desktop Engine profile file')
    data = path.read_bytes()
    if sensitive('desktop-engine profiles', data):
        raise ValueError('Possible secret in Desktop Engine profiles')
    profiles = read_json(path)
    if any(not isinstance(item, dict) or item.get('id') != key for key, item in profiles.items()):
        raise ValueError('Invalid Desktop Engine profiles')
    return data


def project_resource(snapshot):
    projects = [item for item in snapshot.get('resources', []) if item.get('kind') == KIND]
    if len(projects) > 1:
        raise ValueError('Snapshot contains multiple Desktop Engine projects')
    return projects[0] if projects else None


def extract_project(archive_path, destination):
    """Validate metadata before writing and publish a complete tree by rename."""
    destination = Path(destination)
    try:
        with tarfile.open(archive_path, 'r:gz') as archive:
            entries = {}
            size = 0
            for entry in archive:
                path = relative_member(entry.name)
                size += entry.size
                if entry.type != tarfile.REGTYPE or entry.size < 0 or size > ARCHIVE_LIMIT or len(entries) >= MAX_FILES:
                    raise ValueError('Invalid Desktop Engine archive entry')
                if path in entries or entry.mode & ~0o755:
                    raise ValueError('Invalid Desktop Engine archive permissions or duplicate path')
                entries[path] = entry
            if not REQUIRED <= {path.as_posix() for path in entries}:
                raise ValueError('Desktop Engine archive is missing a required entry point')
            for path in entries:
                if any(parent in entries for parent in path.parents):
                    raise ValueError('Desktop Engine archive contains overlapping paths')
            for script in ('desktop-manager', 'desktopctl'):
                if not entries[PurePosixPath(script)].mode & 0o100:
                    raise ValueError('Desktop Engine entry point is not executable')
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(prefix='.desktop-engine-', dir=destination.parent) as temp:
                staged = Path(temp) / 'project'
                for path, entry in entries.items():
                    target = staged.joinpath(*path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with archive.extractfile(entry) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(entry.mode)
                if destination.exists() or destination.is_symlink():
                    raise ValueError('Desktop Engine destination already exists')
                staged.rename(destination)
    except (tarfile.TarError, EOFError) as exc:
        raise ValueError('Cannot read Desktop Engine archive') from exc
    return destination


def launcher_content(sha):
    return (
        '[Desktop Entry]\n'
        'Type=Application\n'
        'Name=Desktop Manager\n'
        'Comment=Previsualizar y gestionar temas para Caelestia\n'
        f'Exec=/bin/sh -c "exec ~/.local/share/myarch/desktop-engine/{sha}/desktop-manager"\n'
        'Icon=preferences-desktop-theme\n'
        'Terminal=false\n'
        'Categories=Settings;DesktopSettings;\n'
        f'X-MyArch-Desktop-Engine={sha}\n'
    ).encode()

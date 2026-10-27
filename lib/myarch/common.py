"""Standard-library-only primitives. No shell evaluation of discovered data."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home()
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config'))
ENV = {**os.environ, 'LC_ALL': 'C', 'LANG': 'C', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
       'PYTHONDONTWRITEBYTECODE': '1', 'GIT_OPTIONAL_LOCKS': '0',
       'npm_config_cache': str(ROOT/'state/tool-cache/npm'),
       'npm_config_logs_dir': str(ROOT/'state/tool-cache/npm-logs'),
       'npm_config_update_notifier': 'false', 'PIP_CACHE_DIR': str(ROOT/'state/tool-cache/pip'),
       'COREPACK_ENABLE_NETWORK': '0', 'COREPACK_HOME': str(ROOT/'state/tool-cache/corepack'),
       'YARN_ENABLE_NETWORK': '0', 'RUSTUP_AUTO_INSTALL': '0'}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local_path(path):
    p = Path(path)
    try:
        return '~/' + str(p.relative_to(HOME))
    except ValueError:
        return str(p)


def expand_path(path):
    return HOME / path[2:] if path.startswith('~/') else Path(path)


def run(argv, timeout=30):
    """Only callers choose commands; never run command strings or config contents."""
    if not shutil.which(argv[0]):
        return {'argv': argv, 'status': 'unavailable', 'returncode': None, 'stdout': ''}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors='replace',
                           env=ENV, timeout=timeout, check=False)
        # stderr can contain personal content: retain exit status, never persist it.
        return {'argv': argv, 'status': 'ok' if p.returncode == 0 else 'failed',
                'returncode': p.returncode, 'stdout': p.stdout}
    except (OSError, subprocess.TimeoutExpired):
        return {'argv': argv, 'status': 'timeout_or_error', 'returncode': None, 'stdout': ''}


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def atomic_bytes(path, data, mode=0o600):
    path = Path(path)
    inside(path, ROOT)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix='.myarch-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path):
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key in project data')
            result[key]=value
        return result
    data=json.loads(Path(path).read_text(),object_pairs_hook=unique_object)
    if not isinstance(data,dict):
        raise ValueError('Project JSON document must be an object: '+Path(path).name)
    return data


def inside(path, parent):
    """Reject symlink escapes and paths outside the explicit output boundary."""
    path, parent = Path(path), Path(parent).resolve()
    if not path.resolve().is_relative_to(parent):
        raise ValueError(f'Path escapes output boundary: {path}')
    return path


SECRET_NAME = re.compile(r'(^|[._/-])(secrets?|credentials?|tokens?|passwords?|auth|history|cookies?|sessions?|keyring|wallet|pairings?)([._/-]|$)|id_(rsa|ed25519)|fish_variables|\.env($|\.)|\.pem$|\.key$|\.p12$|\.pfx$', re.I)
SECRET_CONTENT = re.compile(
    r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|'
    r'(?i:gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|sk-[a-z0-9_-]{20,}|AKIA[A-Z0-9]{16})|'
    r'(?i:(?:password|passwd|token|secret|api[_-]?key|authorization|credential)\s*["\x27]?\s*[:=]\s*["\x27]?[^\s"\x27,;}#]{3,})|'
    r'https?://[^\s/:]+:[^\s/@]+@|(?i:Bearer\s+[a-z0-9_.-]{12,})')


def sensitive(path, data=None):
    if SECRET_NAME.search(str(path)):
        return 'sensitive_filename'
    if data is not None and SECRET_CONTENT.search(data.decode('utf-8', errors='replace')):
        return 'possible_secret'
    return None


def record_file(path):
    p = Path(path)
    item = {'source': local_path(p), 'restore': 'manual_review', 'confidence': 'high'}
    try:
        if sensitive(p):
            return {**item, 'status': 'excluded_sensitive'}
        if p.is_symlink():
            return {**item, 'status': 'symlink_manual', 'target': local_path(p.resolve())}
        if not p.is_file():
            return {**item, 'status': 'not_regular_file'}
        size = p.stat().st_size
        item['size'] = size
        if size > 4 * 1024 * 1024:
            return {**item, 'status': 'oversize_manual'}
        data = p.read_bytes()
        if sensitive(p, data):
            return {**item, 'status': 'excluded_sensitive'}
        return {**item, 'status': 'candidate', 'sha256': digest(data), 'mode': p.stat().st_mode & 0o777}
    except (OSError, RuntimeError):
        return {**item, 'status': 'unreadable'}

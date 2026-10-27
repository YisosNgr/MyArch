#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd -- "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/lib"
for script in ./*.sh ./modules/*.sh ./scripts/*.sh; do bash -n "$script"; done
python3 -m unittest discover -s tests -v
if command -v shellcheck >/dev/null; then
  shellcheck installer.sh bootstrap.sh modules/*.sh scripts/*.sh
else
  printf 'ShellCheck no disponible: comprobación omitida; no se instalan dependencias.\n'
fi

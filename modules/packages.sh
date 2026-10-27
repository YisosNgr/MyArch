#!/usr/bin/env bash
# Invoked only by the destination engine after plan validation and confirmation.
set -Eeuo pipefail
export LC_ALL=C
[[ ${MYARCH_APPROVED_PLAN:-} =~ ^[a-f0-9]{64}$ ]] || { echo 'Missing approved plan' >&2; exit 2; }
(( $# > 0 )) || exit 0
for target in "$@"; do
  [[ $target =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9@._+:-]*$ ]] || exit 2
done
# A full upgrade avoids unsupported partial upgrades; pacman retains its own prompt.
# No --noconfirm, --overwrite, AUR helper, boot editing or service commands.
exec sudo -- pacman -Syu --needed "$@"

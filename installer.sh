#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/lib"
help() {
  cat <<'EOF'
MYARCH — Personal Arch Linux Environment

Usage: ./installer.sh [command] [options]
  audit                       Read-only system discovery; save private manifests
  capture [--desktop-engine DIR]  Capture audited configuration and an optional private desktop project
  plan --profile desktop      Build a reviewable destination plan (repeatable)
  stage [--portable-only]      Restore exact files only inside MyArch/staging
  install-desktop-engine       Install Desktop Manager from the bundle on a destination
  apply [--plan ID]            Destination only; requires typed confirmation
        [--resume TX]         Resume the same plan after inspecting failure
  validate [--plan ID]        Check stored hashes; optionally check destination
  compare                     Report drift without changing the system
  backup                      Bundle the current capture inside MyArch/backups
  bundle-check DIRECTORY      Verify a private bundle's checksums
  bundle-import DIRECTORY     Recover a bundle into a fresh checkout
  rollback TX                 Restore transaction file backups; not packages
  doctor                      Read-only diagnosis
  profiles                    List declarative profiles
  report                      Regenerate the local audit report
  --help                      This help works without Python, Gum or pacman

With no arguments: interactive menu (Gum if available, Bash fallback).
First use: ./bootstrap.sh; ./installer.sh audit; ./installer.sh capture
No dependencies are installed automatically. See README.md.
EOF
}
case ${1:-} in -h|--help|help) help; exit 0;; esac
command -v python3 >/dev/null || { echo 'Python 3 is required. Run ./bootstrap.sh for instructions.' >&2; exit 2; }
command_line() { python3 -m myarch.cli "$@"; }
if (( $# )); then command_line "$@"; exit $?; fi
[[ -t 0 && -t 1 ]] || { help; exit 0; }
header() {
  if command -v gum >/dev/null; then
    gum style --foreground '#b4befe' --bold 'M Y A R C H' 'Personal Arch Linux Environment'
  else
    printf '\nM Y A R C H\nPersonal Arch Linux Environment\n\n'
  fi
}
choose_profiles() {
  local defaults=$1 selected
  local -a args=() names=() chosen=()
  local profile_file
  for profile_file in "$ROOT"/config/profiles/*.json; do
    profile_file=${profile_file##*/}
    names+=("${profile_file%.json}")
  done
  if command -v gum >/dev/null; then
    selected=$(gum choose --no-limit --selected="$defaults" --header='Selecciona perfiles (espacio y Enter)' "${names[@]}") || return 1
    mapfile -t chosen <<< "$selected"
  else
    printf 'Perfiles disponibles: %s\n' "${names[*]}"
    read -r -p "Perfiles separados por espacios [$defaults]: " selected || return 1
    read -r -a chosen <<< "${selected:-$defaults}"
  fi
  for selected in "${chosen[@]}"; do
    [[ -n $selected ]] && args+=(--profile "$selected")
  done
  (( ${#args[@]} )) || return 1
  command_line plan "${args[@]}" || return
  printf '\nEl plan está guardado. Para aplicarlo en el destino: ./installer.sh apply\n'
}
options=('Full Installation' 'Desktop Environment' 'Development Tools' 'Cybersecurity Tools' 'Gaming Environment' 'Multimedia Applications' 'Restore Dotfiles' 'Configure Services' 'Hardware Configuration' 'Validate System' 'Backup Current System' 'System Doctor' 'Exit')
while true; do
  header
  if command -v gum >/dev/null; then
    choice=$(gum choose --header='MyArch — selecciona una operación' "${options[@]}") || exit 0
  else
    for i in "${!options[@]}"; do printf '%2d. %s\n' "$((i+1))" "${options[$i]}"; done
    read -r -p '> ' number || exit 0
    [[ $number =~ ^([1-9]|1[0-3])$ ]] || continue
    choice=${options[$((number-1))]}
  fi
  case $choice in
    'Full Installation') choose_profiles full || true;;
    'Desktop Environment') choose_profiles desktop || true;;
    'Development Tools') choose_profiles development || true;;
    'Cybersecurity Tools') choose_profiles cybersecurity || true;;
    'Gaming Environment') choose_profiles gaming || true;;
    'Multimedia Applications') choose_profiles multimedia || true;;
    'Restore Dotfiles') choose_profiles dotfiles || true;;
    'Configure Services') choose_profiles services || true;;
    'Hardware Configuration') choose_profiles hardware || true;;
    'Validate System') command_line validate || true;;
    'Backup Current System') command_line backup || true;;
    'System Doctor') command_line doctor || true;;
    'Exit') exit 0;;
  esac
  read -r -p 'Enter para volver al menú...' _ || exit 0
 done

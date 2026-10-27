#!/usr/bin/env bash
set -Eeuo pipefail
printf 'MyArch bootstrap — comprobación sin instalar dependencias\n'
missing=0
for tool in bash python3 pacman; do
  if command -v "$tool" >/dev/null; then printf 'OK       %s\n' "$tool";
  else printf 'REQUIRED %s\n' "$tool"; missing=1; fi
done
for tool in git gum shellcheck; do
  if command -v "$tool" >/dev/null; then printf 'OK       %s\n' "$tool";
  else printf 'OPTIONAL %s\n' "$tool"; fi
done
printf '\nRequiere Arch ya instalado, Bash 4+ y Python 3.11+. Gum es opcional.\n'
printf 'Si faltan herramientas, revisa docs/INSTALLATION.md antes de instalarlas.\n'
exit "$missing"

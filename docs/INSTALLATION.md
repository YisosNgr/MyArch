# Instalación

Requisitos: Arch instalado y arrancado, sesión de usuario, red para instalar paquetes, Bash 4+ y Python 3.11+. Git conserva el código. Gum es opcional; su ausencia no bloquea ayuda, auditoría o menú. El proyecto no instala dependencias durante el bootstrap. Revisa cualquier instalación de requisitos por separado.

## Flujo seguro en el origen

```bash
./bootstrap.sh
./installer.sh audit
./installer.sh capture
./installer.sh plan --profile full
./installer.sh stage
./installer.sh validate
./installer.sh backup
```

Consulta `reports/AUDIT.md`, `manifests/*.json` y `state/plans/*.json`. `stage` restaura incluso archivos que requieren revisión, exclusivamente en un árbol aislado. `stage --portable-only` reduce los dotfiles a candidatos portables; las referencias privadas siguen disponibles para examinarlas.

## Flujo en el destino

Transfiere el repositorio y el bundle privado por un canal que controles. El bundle es una carpeta, no un archivo ejecutable. En un clon nuevo:

```bash
./installer.sh bundle-check "$PWD/backups/bundles/ID"
./installer.sh bundle-import "$PWD/backups/bundles/ID"
./installer.sh plan --profile desktop --profile development --profile gaming
./installer.sh stage
./installer.sh apply
./installer.sh validate --plan latest
```

No ejecutes `audit` en el destino antes de importar el inventario del origen: crearías otro inventario y otra protección de origen. Para estudiar el destino utiliza `doctor` y el hardware incluido por `plan`. Guarda aparte un checkout distinto si deseas auditar también ese ordenador.

`apply` comprueba el origen, destino, índice y objetos. Muestra de nuevo el plan y pide `APLICAR <12 caracteres de ID>`. No acepta confirmación no interactiva ni un `--yes`. Si hay paquetes pendientes, la única elevación es `sudo -- pacman -Syu --needed repo/paquete …`. Pacman muestra la transacción y pregunta también. Revisa Arch News y conflictos antes de aprobarla. Los hooks de paquetes pueden tener efectos propios: por eso nunca se ejecutan sobre el equipo auditado durante desarrollo.

Todas las fuentes habilitadas de pacman deben estar revisadas en `config/policy.json`; calificar un paquete no controla la procedencia de todas sus dependencias. El proyecto no configura mirrors, claves ni repositorios externos. Los paquetes extranjeros no se construyen automáticamente.

## GPU y monitores

El plan detecta todas las controladoras gráficas y si es un portátil. AMD/Intel/NVIDIA y kernels/firmware se registran como revisión manual. En el HP OMEN comprueba el modelo exacto de GPU, kernel y compatibilidad del driver vigente; no deduzcas el controlador solamente del nombre NVIDIA. Revisa las dependencias multilib de Steam y Vulkan. Solo pueden seleccionarse paquetes observados; una adaptación que requiera paquetes nuevos debe ser una decisión explícita del usuario.

Las entradas DP-2, DP-3 y HEADLESS de origen no se activan en otro ordenador. Revisa modos anunciados, posiciones, escalado y captura/codificación antes de incorporar un fragmento de monitores. Sunshine queda desactivado hasta revisar emparejamiento y pantallas virtuales. No se cambia shell predeterminada, login gráfico ni servicios automáticamente.

Fuentes consultadas el 27-10-2026: [manual de pacman](https://man.archlinux.org/man/pacman.8.en), [mantenimiento de Arch](https://wiki.archlinux.org/title/System_maintenance), [monitores en Hyprland](https://wiki.hypr.land/configuring/core/monitors/), [Gum](https://github.com/charmbracelet/gum). El inventario local prevalece ante ejemplos de versiones distintas.

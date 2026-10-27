# MyArch

**Personal Arch Linux Environment**

Inventario, captura privada y reconstrucción revisable de un Arch Linux existente. La instalación auditada es la fuente de verdad. El punto de entrada es `./installer.sh`.

```bash
./bootstrap.sh
./installer.sh audit
./installer.sh capture
./installer.sh plan --profile full
./installer.sh stage
./installer.sh validate
./installer.sh compare
./scripts/test.sh
```

Estos comandos inspeccionan el equipo y escriben dentro de MyArch. `stage` reconstruye las configuraciones en `staging/<captura>/home`, sin activarlas. `./installer.sh` abre el menú con Gum si está disponible o con Bash; `--help` funciona sin Python ni Gum. El bootstrap comprueba dependencias y nunca las instala.

En este equipo se han detectado Hyprland con configuración **Lua**, Caelestia, el esquema personalizado `lifeos/lavender/dark.txt`, Fish, Starship, Foot, Fastfetch, Neovim, Steam y Sunshine. El informe actualizado está en `reports/AUDIT.md`; los números y versiones pertenecen a la fecha de auditoría, no son valores predeterminados del proyecto.

La captura conserva bytes originales, hashes SHA-256, modos de archivo, dependencias estáticas, exclusiones y estados de revisión. El esquema Lavender y los formatos de Fastfetch se conservan exactamente. Las configuraciones Lua, monitores físicos/HEADLESS, servicios y Sunshine requieren revisión antes de activarse en otro equipo. El wallpaper activo y referencias de SDDM se guardan de forma privada; las licencias pendientes impiden su distribución automática.

## Instalar en otro Arch

MyArch parte de **Arch Linux ya instalado** con usuario, red, Bash, Python 3.11+ y pacman. No particiona discos ni prepara EFI, GRUB, kernels o el sistema base.

1. En el origen, crea una captura y un bundle: `./installer.sh backup`.
2. Traslada el código y el bundle privado al destino. Un clon Git por sí solo no contiene tus datos personales.
3. Coloca el bundle en `MyArch/backups/bundles/<id>/` y ejecuta `./installer.sh bundle-import "$PWD/backups/bundles/<id>"` en un checkout nuevo.
4. Genera el plan **en el destino**: `./installer.sh plan --profile desktop --profile development`.
5. Revisa los paquetes, acciones manuales, hardware y repositorios. Prepara una restauración de prueba con `./installer.sh stage`.
6. `./installer.sh apply` muestra el plan, exige escribir su identificador y solicita privilegios únicamente para pacman. La aplicación real está bloqueada en el equipo de origen.
7. Verifica: `./installer.sh validate --plan latest`.

El motor instala únicamente raíces explícitas observadas, compatibles y disponibles en repositorios revisados; pacman resuelve dependencias. Usa versiones actuales y una transacción completa `pacman -Syu --needed` en el **destino confirmado**, con el prompt propio de pacman. Esa operación no se ha ejecutado durante el desarrollo. No ejecuta gestores AUR ni recetas descargadas. Las acciones manuales permanecen visibles; una reconstrucción parcial nunca se declara completa y apply devuelve código 1 si la validación queda incompleta.

## Perfiles y operaciones

Perfiles combinables: `full`, `desktop`, `development`, `cybersecurity`, `gaming`, `multimedia`, `minimal`, `laptop`, `dotfiles`, `services`, `hardware`. Los perfiles seleccionan categorías del inventario; no inventan paquetes ni habilitan repositorios. `minimal` reduce las raíces del escritorio al subconjunto observado. `laptop` añade revisión de hardware y no impone monitores del sobremesa.

| Operación | Resultado |
| --- | --- |
| `audit` / `report` | Manifiestos / informe local con evidencias y límites |
| `capture` | Snapshot inmutable con objetos por contenido |
| `plan --profile …` | Plan de destino con estados reales y huella verificable |
| `stage [--portable-only]` | Copia aislada dentro de MyArch/staging |
| `apply [--resume TX]` | Aplicación confirmada en otro equipo; journal y backups |
| `validate [--plan ID]` | Integridad; opcionalmente convergencia del destino |
| `compare` | Diferencias de archivos y versiones sin corregirlas |
| `backup` / `bundle-check DIR` | Bundle privado / comprobación de hashes |
| `bundle-import DIR` | Recuperación en un checkout nuevo sin reemplazar inventarios distintos |
| `rollback TX` | Deshace archivos de una transacción, preserva cambios posteriores |
| `doctor` | Diagnóstico sin reparaciones automáticas |

## Privacidad y Git

Los manifiestos, configuraciones, recursos, informes, cachés, journals y backups están excluidos de Git. El escáner descarta nombres sensibles, historiales, claves privadas y posibles credenciales. Es una defensa heurística: revisa los datos antes de compartirlos. Los backups de archivos preexistentes en destino pueden contener secretos y siempre son privados. No hagas `git add -f` de estas carpetas sin revisión.

El código y las políticas se conservan en Git; los bundles privados conservan tu entorno. Las actualizaciones del inventario son explícitas: `audit`, `capture`, `compare`, revisión y nuevo bundle. No hay sincronización automática ni pushes.

## Verificación y límites

`./scripts/test.sh` ejecuta comprobación sintáctica Bash y pruebas offline de secretos, procedencia, perfiles, hashes, rutas, symlinks, planificación, staging, backups, interrupciones, reanudación, rollback e importación. La integración de pacman se prueba mediante un sustituto simulado; las pruebas no instalan nada. Si Bubblewrap ya está disponible, también ejecuta la CLI y el menú en procesos y terminales reales, con el anfitrión en solo lectura y sin red; solo pacman y el hardware de destino se simulan. ShellCheck se ejecuta si ya existe. No se ha realizado una instalación real en VM o portátil ni una comparación visual de sesiones restauradas.

El análisis estático no puede demostrar todas las dependencias de Lua, comandos autostart o configuraciones generadas. AUR, otros gestores, servicios, drivers, SDDM, fuentes/recursos sin licencia confirmada, plugins de Neovim y rutas dependientes del usuario pueden requerir intervención. Estas limitaciones figuran en los manifiestos y planes, no se ocultan bajo un estado de éxito.

Documentación: [arquitectura](docs/ARCHITECTURE.md), [instalación](docs/INSTALLATION.md), [paquetes](docs/PACKAGES.md), [dotfiles](docs/DOTFILES.md), [perfiles](docs/PROFILES.md), [seguridad](docs/SECURITY.md), [recuperación](docs/RECOVERY.md), [problemas](docs/TROUBLESHOOTING.md), [cobertura](docs/COVERAGE.md), [pruebas](docs/TESTING.md), [plan de VM](docs/VM_TEST_PLAN.md).

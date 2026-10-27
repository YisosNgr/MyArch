# Cobertura y criterios de aceptación

El texto recibido termina a mitad del requisito inicial del apartado 14. No se han supuesto requisitos de secciones posteriores no recibidas.

| Área solicitada | Implementación y evidencia | Límite explícito |
| --- | --- | --- |
| Sistema/hardware | OS, kernel, CPU, placa, RAM, GPU/driver, monitores, almacenamiento sin IDs, montajes, locale, teclado, timezone, XDG, unidades | /boot protegido sin sudo; no imagen de disco ni prueba de arranque |
| Pacman/repositorios | Explícitos, dependencias, extranjeros, grupos, huérfanos, versiones, ignores, procedencia disponible, depends/optdepends/licenses | Disponibilidad no prueba origen binario; base sync local puede estar obsoleta |
| AUR | Helpers detectados; árboles locales, remoto restringido y metadatos estáticos | No red, no ejecución de recetas, no verificación de reproducibilidad binaria |
| Otros gestores | Flatpak por scope, pip/pipx/npm/pnpm/yarn/Cargo/Rustup, extensiones y directorios de SDK/binarios | Restauración revisada manual; no escaneo de todo HOME |
| Hyprland | Todos los archivos del árbol permitido; grafo source/require; monitores y hardware bloqueados | Análisis estático; Lua dinámica y archivos generados requieren inspección |
| Caelestia | Esquema Lavender, shell.json, overrides y estado de color; dependencias de paquetes | No se prueba visualmente una sesión restaurada; no se verifica cada modificación del código instalado |
| SDDM/recursos | Selección activa, metadatos, config de tema y licencia; wallpaper privado por hash | No activa SDDM ni redistribuye recursos sin licencia revisada |
| Terminal | Fish, Foot, Starship, Fastfetch y Neovim; configs exactas y lock de plugins | Sin variables universales, histories ni ejecución de prompts/plugins/LSP |
| Desarrollo/seguridad/gaming | Categorías sobre paquetes realmente detectados, grupos BlackArch, Steam/Proton y herramientas multimedia | Clasificación heurística; no juegos, proyectos, cachés o herramientas ofensivas en ejecución |
| Hardware portátil | Detección destino y perfil laptop; drivers/monitores pendientes explícitos | No se ha probado un HP OMEN real; no se elige un driver por marca solamente |
| Instalador | Menú 13 opciones, Gum opcional, combinación de perfiles, plan, estados, journal y reanudación | Aplicación real requiere Arch instalado y confirmación interactiva |
| Recuperación | Objetos SHA-256, bundle privado, importación, backups antes de sobrescribir, rollback con conflicto | Rollback solo de archivos; paquetes y hooks no se revierten |
| Git/CI | Código y política versionados; artefactos privados ignorados; pruebas offline | Sin remote/push/publicación ni dependencias instaladas localmente |

## Pruebas

`scripts/test.sh` usa unittest estándar y bash -n. Las pruebas cubren capturas, tampering de contenido/índice, secretos, fuentes cambiadas, perfiles duplicados/cíclicos, procedencia extranjera, calificación de repositorios, fuente protegida, destinos symlink, staging, backup/rollback con permisos, interrupciones en instalación y rollback, conflictos de edición, lock concurrente, importación de bundles y rechazo de rutas de código. Las pruebas de procesos/PTY ejecutan el trabajador Bash con sustitutos de pacman y sudo dentro de Bubblewrap, sin elevar privilegios del anfitrión. Se comprueban además la segunda protección del trabajador, salida no exitosa para instalaciones parciales, datos malformados y recuperación de un bundle en un checkout nuevo.

Los smoke tests del anfitrión se limitan a consultas, captura, hashes, staging, comparación, diagnóstico, backup e intento bloqueado de apply en origen. La CLI completa también se prueba en un entorno aislado con gestor de paquetes simulado. La validación en VM y la equivalencia visual de una instalación nueva permanecen pendientes. No hay una declaración de sistema reconstruido al 100 % basada únicamente en pasar pruebas unitarias.

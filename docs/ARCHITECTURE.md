# Arquitectura

Bash ofrece el punto de entrada, la interfaz opcional Gum, el bootstrap y la única transacción privilegiada. Python estándar analiza JSON, rutas, inventarios y recuperación sin instalar jq, librerías o gestores. Esta división evita evaluar configuraciones o reconstruir estructuras JSON mediante texto de shell. No se crean módulos vacíos para imitar un árbol orientativo.

| Componente | Responsabilidad |
| --- | --- |
| installer.sh | Ayuda independiente, menú, perfiles y despacho |
| bootstrap.sh | Comprobación sin instalación |
| modules/packages.sh / worker.py | Segunda comprobación de autorización junto a la frontera de privilegios; transacción de pacman en destino |
| lib/myarch/common.py | Consultas sin shell, límites de escritura, hashes y detección de secretos |
| audit.py / discovery.py | Inventarios, metadatos de pacman, grafo estático Lua/Hyprland y recursos |
| snapshot.py / resources.py | Capturas exactas y referencias privadas con hashes |
| plan.py | Perfiles, selección de raíces, confianza de repositorios y planes |
| engine.py | Locks, despliegue, journals, backups, recuperación y bundles |
| validation.py | Integridad, diferencias y diagnóstico |
| cli.py | CLI común, informes y confirmaciones |
| config/profiles/*.json | Selección declarativa y herencia comprobada |
| config/policy.json | Confianza explícita y límites de automatización |

## Estados

**Detectado**: manifests, respaldado por comandos y metadatos locales. **Exportado**: snapshot y objetos cuyo hash coincide con la fuente. **Deseado**: selección de perfiles en un plan revisable para un destino concreto. **Reproducible**: acciones automáticas compatibles; los paquetes se resuelven contra bases locales actuales. **Manual**: procedencia, compatibilidad, dependencia dinámica o licencia pendiente.

Las acciones usan `Pending`, `Installing`, `Installed`, `Skipped`, `Failed`, `Requires manual action` y, en recuperación, `Rolling back` / `Rolled back`. Los journals se escriben antes de cambiar archivos, con fsync y reemplazo atómico. Cada operación toma un lock exclusivo del proyecto. No hay porcentajes simulados.

## Datos

Los manifiestos y políticas usan `schema: 1`. Los snapshots nuevos usan `schema: 2`: entradas lógicas, objetos por SHA-256, grafo, recursos privados, exclusiones y digest del índice. Se admite lectura del primer formato local de snapshots. Los planes incluyen ID de contenido completo, captura, destino, perfiles, precondiciones de archivos y acciones. El timestamp no cambia la identidad de un plan idéntico.

Rutas lógicas: `config/…` se aplica al XDG_CONFIG_HOME del destino; `home/…` al HOME del destino; `state/caelestia/…` a ~/.local/state/caelestia. No se reutiliza como destino la ruta absoluta del usuario origen. Los contenidos originales se mantienen: las rutas internas escritas en ellos se revisan por separado.

Un hash de machine-id, excluido de Git, bloquea el equipo de origen. No es autenticación frente a un usuario que edite deliberadamente el código o los metadatos. Un plan solo se aplica en la máquina, HOME y XDG_CONFIG_HOME donde se generó. El directorio de proyecto y sus políticas son una frontera de confianza local.

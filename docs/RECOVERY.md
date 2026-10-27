# Backups, recuperación y reanudación

`backup` crea un bundle de la **última captura**, manifiestos, identidad protegida del origen y objetos necesarios. No vuelve a auditar ni asegura por sí solo que el estado actual coincida con la captura. Para respaldar cambios recientes, ejecuta audit, capture, compare y después backup. Los bundles permanecen dentro de MyArch/backups/bundles; copia uno a otro soporte por separado para protegerte de pérdida del disco.

`bundle-check RUTA` comprueba cada SHA-256. `bundle-import RUTA` solo importa rutas permitidas de inventario/objetos/identidad en un checkout nuevo o idéntico. Valida el índice, objetos, recursos, identidad e inventario antes de copiar el primer documento. Rechaza código, traversal, enlaces que escapen y archivos existentes diferentes. No extrae tar arbitrarios ni ejecuta contenido. Tras importar, genera un plan en el destino; nunca reutilices un plan de otra máquina.

`state/transactions/ID.json` registra acciones y backups. Si se interrumpe una aplicación de destino, inspecciona el error y el estado de pacman antes de ejecutar:

```bash
./installer.sh apply --plan ID_DEL_PLAN --resume ID_TRANSACCION
```

La reanudación verifica destino, plan, captura y todos los archivos registrados antes de iniciar una transacción de paquetes. Si cambiaste contenido o permisos desde entonces, se detiene. Conserva el éxito de una transacción de paquetes completada. Si la actualización falló o quedó interrumpida, vuelve a ejecutar sus raíces revisadas con la actualización completa, incluso si algunas ya quedaron instaladas: su presencia no demuestra que la actualización terminara. No elimina un lock de pacman ni intenta reparar automáticamente una actualización incompleta.

Para deshacer archivos:

```bash
./installer.sh rollback ID_TRANSACCION
```

En destino exige confirmación; para un staging aislado no. Antes de escribir valida todos los destinos y backups. Restaura contenido y permisos preexistentes; elimina únicamente archivos nuevos creados por esa transacción. Preserva cambios posteriores del usuario deteniéndose para revisión. Una interrupción durante el rollback se puede reanudar repitiendo el mismo comando. También reconoce interrupciones ocurridas antes de escribir el archivo. Una transacción parcialmente revertida no se puede reanudar como instalación.

El rollback no revierte paquetes, actualizaciones, dependencias, hooks ni directorios vacíos. Las referencias visuales del staging se conservan como recursos de revisión. La recuperación completa del sistema base requiere tu estrategia de snapshots/backups de disco; este proyecto no fabrica una imagen del disco ni garantiza recuperar un sistema que no arranca.

Backups de sobrescritura: backups/ID/<ruta lógica>. Son privados y pueden contener credenciales del destino. No borres los journals ni backups mientras necesites rollback. Un rollback repetido de una transacción ya revertida no vuelve a escribir los archivos.

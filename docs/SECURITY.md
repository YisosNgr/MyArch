# Seguridad y privacidad

## Límites operativos

Durante desarrollo se permiten consultas locales y escrituras dentro de MyArch. No se instalan dependencias, ejecutan herramientas ofensivas, configuran drivers, cambian servicios o sesión, ni editan dotfiles activos, GRUB/EFI o particiones. El único comando privilegiado del producto está en modules/packages.sh y solo se alcanza tras el bloqueo de origen y la confirmación de un destino. Los hooks de pacman pueden modificar el sistema de destino; se conserva su confirmación propia.

No hay `eval`, configuración `source` del usuario, comandos construidos mediante concatenación de shell, `curl | sh`, descargas de recetas ni acceso root persistente. Las rutas, nombres de paquetes y destinos se validan. El trabajador Bash vuelve a comprobar origen, plan, destino, paquetes y repositorios antes de sudo; invocarlo directamente no evita el bloqueo del origen. Los archivos destino y sus ancestros no pueden ser symlinks. El proceso asume que el usuario local de confianza no cambia rutas concurrentemente; no ofrece aislamiento frente a procesos hostiles con el mismo UID.

Los nombres sensibles y patrones de secretos provocan exclusión del archivo completo. Nunca se publican contenidos en informes. Se excluyen Fish universal variables, histories, claves, emparejamientos y bases de sesión. El filtrado es heurístico: configuraciones con formatos desconocidos pueden contener secretos no reconocidos. Por eso el contenido exportado permanece ignorado por Git y debe revisarse antes de compartirlo.

Las pruebas unitarias usan un entorno reducido para no volcar variables de sesión en errores de mocks. Las pruebas de CLI con Bubblewrap montan el anfitrión en solo lectura, ocultan /run, aíslan la red y sustituyen tanto pacman como sudo; no elevan privilegios del anfitrión.

Los archivos generados usan umask 077; objetos, manifiestos y backups son privados. Los backups no están cifrados. Los datos preexistentes en un destino se respaldan exactamente, incluso si contienen secretos; no se deben compartir. El bundle incluye un hash de identidad del origen para conservar la protección de equipo, sin almacenar machine-id en claro.

No se exportan UUID, seriales, MAC, IP, hostname ni el entorno completo como estado deseado. Montajes y nombres de dispositivos son inventario, nunca instrucciones. Las rutas internas de archivos y nombres de extensiones aún pueden revelar información personal. Los recursos visuales tienen revisión de redistribución separada de su copia privada de referencia.

## Consultas con efectos secundarios

npm puede generar logs incluso con `npm ls`. La implementación redirige su caché y logs a state/tool-cache; desactiva avisos de actualización y descarga automática de Corepack. Durante las dos primeras consultas del desarrollo se generaron dos logs externos antes de introducir esta protección: `~/.npm/_logs/2026-10-27T13_20_21_319Z-debug-0.log` y `2026-10-27T13_22_30_100Z-debug-0.log`. Se han conservado; no se borraron ni modificaron archivos fuera del proyecto para ocultar el efecto. No se cambiaron paquetes ni configuraciones activas.

La auditoría no solicita sudo para leer /boot u otros archivos protegidos. Registra `unavailable_without_privileges` y mantiene la necesidad de intervención manual.

## Revisar antes de compartir

El código es publicable bajo LICENSE. La licencia del código no relicencia dotfiles, fondos, fuentes o temas de terceros. Revisa `git diff --cached` y `git status --ignored` antes de cualquier publicación. Los artefactos privados se transfieren por un canal elegido por el usuario; el proyecto no envía datos ni hace push automáticamente.

# Próxima validación en una VM desechable

Estado: preparada, no ejecutada. Requiere autorización para preparar nuevas dependencias de prueba y descargar una imagen. El prompt original dice «NO instales dependencias sin mi aprobación». Ningún comando de instalación o actualización del anfitrión forma parte de este plan.

## Recursos y aislamiento

- QEMU y qemu-img portátiles dentro de `tests/vm/`, obtenidos de paquetes oficiales con firmas verificadas. La consulta de las bases sync locales del 27-10-2026 muestra `qemu-system-x86` y `qemu-img` 11.1.2-1; se resolverán de nuevo antes de descargar. No se fijan versiones incompatibles.
- Firmware y bibliotecas que falten también se extraerán dentro de esa carpeta; no se instalarán mediante pacman en el anfitrión.
- Imagen oficial Arch Linux verificada. La descarga de imagen y paquetes puede ocupar varios GB; se registrará su procedencia y hashes.
- VM con 4 vCPU, 6 GiB de RAM y disco virtual de 40 GiB disperso. Solo archivos regulares de prueba, nunca dispositivos de bloque del anfitrión.
- KVM es accesible al usuario actual. QEMU no está instalado; no se cambiarán grupos, módulos, permisos o servicios para usarlo.
- Proceso de QEMU aislado con el anfitrión en solo lectura y escritura limitada al directorio de VM. HOME/configuración de prueba propios. Red de usuario para el invitado, sin cambiar firewall o red del anfitrión.
- Sin USB, GPU passthrough, acceso a particiones reales ni carpetas personales compartidas. El código y el bundle de prueba se transfieren explícitamente al invitado.

## Comprobaciones

1. Arranque de Arch, identidad nueva y conectividad del invitado; pruebas negativas de protección del anfitrión.
2. Importación de un bundle revisado y generación del plan dentro del invitado.
3. Instalación de paquetes nativos solo dentro de la VM; confirmaciones y reanudación tras fallos controlados.
4. Dotfiles portables, backups, validación e idempotencia con pacman real del invitado.
5. Revisión separada de recetas extranjeras y configuración Lua/monitores antes de activar el escritorio de prueba. No se ejecutan herramientas ofensivas.
6. Arranque del escritorio, verificación de configuraciones y capturas del invitado almacenadas dentro de MyArch. Comparación visual solo de elementos con referencia suficiente y recursos disponibles.
7. Rollback de archivos, reinicio del invitado y registro de resultados con versiones y limitaciones.

La VM puede validar el flujo de instalación y el escritorio virtual. No demuestra compatibilidad física del RX 9070 XT ni de los gráficos híbridos del HP OMEN. Esas comprobaciones requieren esos equipos o hardware equivalente. No se etiquetará una instalación parcial como completa.

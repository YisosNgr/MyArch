# Pruebas y resultados

Ejecutar `./scripts/test.sh`. Todas las escrituras de fixtures e informes permanecen en MyArch. No se instala ninguna herramienta para completar la suite.

## Tres niveles

1. **Contratos offline** (`tests/test_myarch.py`): captura exacta, secretos, identidad, perfiles, hashes, paths, backups, permisos, staging e idempotencia.
2. **Fallos inyectados** (`tests/test_recovery_edges.py`): interrupciones antes y después de escribir, ediciones posteriores de contenido/permisos, prevalidación antes de paquetes, fallo parcial de actualización, recuperación de bundles incompletos/corruptos, validación del destino y configuración malformada.
3. **Procesos reales aislados** (`tests/test_cli_isolated.py`): si existen Bubblewrap y namespaces de usuario, ejecuta Bash/Python, CLI, menú y confirmaciones sobre PTY reales. Monta el anfitrión en solo lectura, oculta /run, deshabilita red y concede escritura únicamente a la carpeta de fixtures. Las identidades, pacman y sudo son sustitutos de prueba. Se comprueban instalación, validación, idempotencia, rollback, fallo/reanudación de paquetes, protección de origen incluso al invocar directamente el trabajador, cancelación/EOF, rutas de destino cambiadas, repositorios, instalación parcial y recuperación en otro checkout.

El tercer nivel no se etiqueta como una instalación real de Arch. Si el entorno no ofrece Bubblewrap/namespaces, unittest lo muestra como omitido; no instala ni solicita privilegios para habilitarlo. ShellCheck también se omite explícitamente si falta. Bash se comprueba siempre con bash -n.

## Fallos corregidos al ampliar las pruebas

- Rollback cuando la interrupción ocurrió antes de escribir: ahora reconoce el estado original o la ausencia del archivo nuevo.
- Ediciones de permisos entre backup y reanudación: se preservan igual que las ediciones de contenido.
- Conflictos en archivos completados: se detectan antes de cualquier nueva transacción de paquetes.
- Actualizaciones fallidas: estado Failed real; la presencia de las raíces no se confunde con actualización completada. La reanudación vuelve a intentar la transacción revisada.
- Rollback parcial: impide volver accidentalmente al modo instalación.
- Bundles: los archivos ausentes se notifican como inválidos; índice y objetos se validan antes de importar documentos.
- Datos: se rechazan índices/esquemas, permisos, tamaños, destinos superpuestos, claves JSON duplicadas y tipos de perfil/política inválidos.
- Validación: un plan de otro HOME/XDG no valida este destino; apply devuelve código no exitoso cuando quedan tareas manuales.
- Cobertura de full: las aplicaciones de otros gestores permanecen visibles como tareas manuales de revisión.
- Frontera de privilegios: el trabajador revalida por sí mismo origen, destino, plan, paquetes y repositorios.

Los resultados de cada ejecución están en reports/; contienen datos privados y permanecen excluidos de Git. El informe de aceptación ampliado registra número de pruebas, comparación del origen y límites reales.

## Lo que falta probar

Una VM con pacman real, arranque del escritorio y comparación visual. Véase VM_TEST_PLAN.md: preparar dependencias o descargar la imagen requiere la autorización pendiente del usuario. La compatibilidad de GPUs físicas y del portátil debe comprobarse sobre ese hardware; una VM no la demuestra.

# Resolución de problemas

| Síntoma | Acción |
| --- | --- |
| Falta Python/pacman | Ejecutar bootstrap y revisar requisitos; no instalar sobre el origen sin autorización |
| No aparece Gum | Utilizar el menú Bash; Gum es opcional y no se descarga automáticamente |
| No hay captura | Ejecutar audit y capture en el origen, o importar un bundle en el destino |
| Apply bloqueado en origen | Protección esperada. Usar stage para probar sin tocar la instalación |
| /boot no accesible | Revisar la advertencia del inventario; no elevar toda la auditoría |
| Possible secret / archivo excluido | Revisar localmente; no retirar el filtro de forma global |
| Cambió desde audit | Volver a auditar y capturar; no modificar el índice del snapshot protegido por hash |
| Snapshot/plan checksum mismatch | Recuperar un bundle válido o regenerar desde las fuentes revisadas |
| Stage already exists | Elegir --dest "$PWD/staging/otro-nombre"; no se sobrescribe un staging anterior |
| Another MyArch operation is running | Esperar; flock se libera al terminar o morir el proceso |
| Repositorio no confiable | Revisar origen, firmas y prioridades; editar política solo tras esa revisión |
| Pacman cancelado o fallido | Revisar salida y estado del sistema; no usar --overwrite ni borrar db.lck automáticamente |
| Lua/HEADLESS/servicio manual | Examinar copia aislada; adaptar al hardware antes de activarla |
| Import inventario diferente | Recuperar en otro checkout nuevo; no se reemplaza el inventario existente |
| Drift de versión | Dato esperado en rolling release; no implica downgrade |
| validate sin --plan devuelve integrity_ok | Solo comprueba el backup; no certifica la sesión o instalación destino |
| apply / validate --plan terminan con código 1 | Hay diferencias, fallos o acciones manuales; revisar reports/validation.json |

Los fallos de consultas figuran con argv y código de salida en audit-report.json; stderr no se persiste porque puede contener información personal. Los módulos no disponibles se distinguen de una consulta confirmada sin resultados. Algunas herramientas devuelven código distinto de cero para conjuntos vacíos (por ejemplo huérfanos): consulta la evidencia, no interpretes cada resultado como una avería.

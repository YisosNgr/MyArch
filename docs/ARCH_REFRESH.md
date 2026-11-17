# Estado de la captura de Arch Linux

La captura del 17 de noviembre de 2026 registra **1.192 paquetes**, **342 archivos de configuración** y **6 recursos privados de referencia**.

Los paquetes instalados y sus versiones coinciden con el inventario del 16 de noviembre. La captura incorpora 290 archivos de la configuración local de Caelestia para Quickshell y cinco configuraciones modificadas. La auditoría omite las copias de trabajo del escritorio.

La configuración local de Caelestia requiere revisión antes de activarla en otro equipo. Algunos componentes QML y recursos gráficos quedaron fuera por los filtros de captura. La personalización del escritorio debe comprobarse en el equipo de destino.

MyArch verificó el bundle, lo importó en una copia limpia y comparó el contenido y los permisos de los archivos restaurados en un directorio de pruebas. La instalación en una VM sigue pendiente de validación.

Para probar esta captura en otro Arch Linux, usa el bundle privado del 17 de noviembre y sigue la [guía de instalación](INSTALLATION.md).

El bundle posterior del mismo día incorpora Desktop Engine, con el gestor, los 18 temas del catálogo y 5 perfiles personales. La extracción y el lanzador se verificaron en un usuario simulado. Consulta la [guía de Desktop Engine](DESKTOP_ENGINE.md).

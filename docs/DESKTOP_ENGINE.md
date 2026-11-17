# Desktop Engine

MyArch puede guardar Desktop Engine en el bundle privado. El proyecto conserva el gestor gráfico, `desktopctl`, el catálogo, los recursos, los parches de Caelestia y los perfiles personales. GitHub contiene el código de MyArch que permite capturarlo, extraerlo e instalarlo.

## Actualizar la copia del proyecto

Desde el MyArch del equipo de origen, indica la carpeta del proyecto y genera un nuevo bundle.

```bash
./installer.sh audit
./installer.sh capture --desktop-engine "/ruta/a/desktop engine"
./installer.sh backup
```

Una captura normal conserva la última copia de Desktop Engine que se incluyó explícitamente. Repite el comando con `--desktop-engine` para incorporar los cambios del proyecto o de sus perfiles. El historial de temas aplicados y los checkpoints de Desktop Engine pertenecen al equipo de origen.

## Usarlo en un equipo nuevo

Importa el bundle privado con la versión actual de MyArch. El plan del perfil `laptop` muestra Desktop Engine si está incluido. Puedes extraer una copia para probar la CLI en un directorio aislado con `./installer.sh stage`. La salida indica dónde quedó el proyecto.

En el equipo de destino, ejecuta:

```bash
./installer.sh install-desktop-engine
```

El comando solicita confirmación y añade **Desktop Manager** al menú de aplicaciones del usuario. Si ya existe un lanzador ajeno a MyArch, pide resolver ese conflicto antes de reemplazarlo. Los perfiles personales se restauran cuando el destino aún carece de un archivo de perfiles. El resultado indica el estado de la restauración.

La interfaz usa Quickshell (`qs`). En la copia capturada, Desktop Engine comprueba versiones concretas de Hyprland, Quickshell y Caelestia antes de aplicar un tema. Haz esa comprobación en destino con `desktopctl doctor`, desde la carpeta del proyecto restaurado. La configuración local de Caelestia y la aplicación de temas deben verificarse aparte en el portátil.

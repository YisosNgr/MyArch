# Paquetes y procedencia

El inventario usa `pacman -Q`, `-Qeq`, `-Qmq`, `-Qdtq`, `-Qg`, `-Sl`, `pacman-conf` y la base local de pacman. Conserva nombre, versión, razón explícita/dependencia, grupos, disponibilidad en repositorios locales, categoría, compatibilidad, dependencias, dependencias opcionales, licencias declaradas, URL y método de restauración.

`repository_available_not_install_origin` significa que hay un paquete de ese nombre en una base sync local; no demuestra de dónde vino el binario instalado. `official_available` solo indica disponibilidad en repositorios oficiales. `foreign_unverified` nunca equivale a AUR. `foreign_with_local_aur_tree` añade una receta y un remoto aur.archlinux.org presentes en caché; no verifica que el binario instalado coincida con ellos. No se ejecutan PKGBUILD ni .SRCINFO.

Las versiones son datos históricos. El plan usa paquetes actuales, nunca URLs de archivos antiguos ni downgrades. La aplicación realiza una actualización completa en destino para evitar actualizaciones parciales. `--needed` y el inventario evitan reinstalar paquetes presentes. No restaura razones de dependencia mediante `pacman -D` ni elimina huérfanos.

Los perfiles seleccionan raíces explícitas; las dependencias automáticas las resuelve pacman. `full` no reinstala cada dependencia huérfana como si fuese una aplicación. Las dependencias opcionales se conservan para revisión. La clasificación por nombre/grupo es heurística y está separada de la certeza de que el paquete existe. Los grupos BlackArch se conservan; no se instala BlackArch entero. Una raíz fuera de repositorios confiables requiere revisión.

Flatpak se separa por usuario/sistema, aplicaciones/runtimes, origen y arquitectura. Se inventarían nombres/opciones de remotos, sin sus posibles URLs con credenciales; los overrides quedan registrados para revisar permisos. No se aplica un override a ciegas.

pip, pipx, npm global, pnpm, yarn, Cargo, Rustup, SDKMAN, extensiones VS Code, ~/.local/bin, /usr/local/bin, /opt, SDK Android y herramientas Proton locales se inspeccionan si existen. La salida fallida o ausente se conserva como evidencia de consulta, no como ausencia demostrada. Estos gestores requieren revisión de origen y versión; no se mezclan con pacman ni se ejecutan instaladores externos. No se leen proyectos personales, bibliotecas Steam, prefijos Wine, imágenes de contenedor ni variables del daemon.

Los listados `packages/pacman.txt`, `foreign-unclassified.txt` y `flatpak.txt` son índices de consulta. El motor usa los manifiestos estructurados, no los interpreta como comandos.

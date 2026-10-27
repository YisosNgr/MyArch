# Perfiles

Cada perfil es JSON, nunca código que se carga con `source`. `extends` compone perfiles y se detectan ciclos. La selección elimina duplicados de categorías, archivos y paquetes. Los nombres solo admiten letras minúsculas, números y guiones, sin traversal.

`categories` selecciona paquetes explícitos observados por categoría; `dotfiles` selecciona categorías de configuración (`all` incluye todas). `only_packages` limita `minimal` cuando se selecciona solo. Al combinar minimal con full/desktop prevalece el perfil más amplio. `hardware_review` y `services_review` agregan tareas manuales. Un perfil personalizado puede usar estos mismos campos en config/profiles/nombre.json.

| Perfil | Alcance |
| --- | --- |
| full | Todas las categorías observadas y dotfiles; conserva bloqueos de revisión |
| desktop | Componentes del escritorio y apariencia |
| development | Herramientas de desarrollo y configuración Neovim/IDE/Git |
| cybersecurity | Paquetes de seguridad detectados por nombre/grupos |
| gaming | Aplicaciones gaming observadas y configuración local pertinente |
| multimedia | Multimedia/streaming observado |
| minimal | Raíces reducidas del escritorio; dependencias no se eliminan |
| laptop | Desktop y revisión de energía, GPU híbrida, suspensión, escalado |
| hardware | Solo informe/revisión de hardware |
| services | Solo revisión de servicios observados |
| dotfiles | Configuración; no instala aplicaciones |

La selección de módulos se expresa combinando perfiles mediante `--profile` repetido o una lista separada por comas. El menú ofrece multiselección Gum o una línea de perfiles separados por espacios. El menú guarda el plan; aplicar es una operación explícita posterior.

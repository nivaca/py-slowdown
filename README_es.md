py-slowdown
===========

py-slowdown reproduce audio más lento o más rápido sin cambiarle la altura.
Sirve para transcribir grabaciones (clases, entrevistas, dictados) y para
sacar música de oído: el archivo se ve como una forma de onda, los mandos de
siempre lo recorren y los marcadores guardan los lugares a los que se quiere
volver.

*Read in English: [README.md](README.md).*

![py-slowdown, una grabación a 0,75× con dos marcadores](docs/img/main_es.png)

Lo que hace
-----------

- Abre archivos de audio y el sonido de los de video: MP3, M4A/AAC, MP4,
  FLAC, WAV, AIFF, Ogg, Opus, WMA y lo demás que lea FFmpeg. Los que tienen
  más de dos canales se mezclan en estéreo.
- Muestra el audio como forma de onda, con una regla de tiempos. Un clic
  lleva allí la posición; Ctrl+rueda acerca o aleja alrededor del puntero,
  y la rueda corre la vista. Un archivo largo se puede tocar mientras
  todavía se lee.
- Tocar, pausar, detener, ir al principio o al final, atrás y adelante (un
  salto que se elige en Configuración, de 1 a 60 segundos; con el botón
  apretado sigue saltando) y un segundo atrás o adelante.
- Velocidad de 0,25× a 3×, que se cambia mientras suena, sin que cambie la
  altura. El estiramiento lo hace la [biblioteca Rubber Band](https://breakfastquay.com/rubberband/),
  con su motor R3 («finer»), el de más calidad, por medio de un enlace
  pequeño, propio de py-slowdown. A 1× el archivo suena tal
  cual, muestra por muestra, sin pasar por Rubber Band.
- Marcadores en la posición que suena (B), o en cualquier punto con el clic
  derecho sobre la forma de onda; cada uno puede llevar un nombre. Se
  listan en un panel lateral, se dibujan sobre la forma de onda y se pueden
  exportar a un archivo de texto. Ctrl+← y Ctrl+→ van al marcador anterior
  y al siguiente.
- Recuerda, por archivo, sus marcadores y el punto donde se dejó, y la vez
  siguiente sigue desde allí.
- Interfaz en inglés y en español (Configuración > Idioma).

Teclado
-------

| Acción                            | Teclas                           |
|-----------------------------------|----------------------------------|
| Tocar / pausar                    | Espacio                          |
| Detener y volver al principio     | S                                |
| Ir al principio / al final        | Inicio / Fin                     |
| Atrás / adelante (el salto)       | ← / →                            |
| Un segundo atrás / adelante       | Mayús+← / Mayús+→                |
| Más lento / más rápido (0,05×)    | ↓ / ↑, o − / +                   |
| Velocidad normal                  | N                                |
| Añadir un marcador                | B                                |
| Marcador anterior / siguiente     | Ctrl+← / Ctrl+→, RePág / AvPág   |
| Acercar / alejar / todo           | Ctrl++ / Ctrl+− / Ctrl+0         |
| Abrir un archivo                  | Ctrl+O                           |

Instalación
-----------

Cada versión, en [GitHub](https://github.com/nivaca/py-slowdown/releases) y
en [Codeberg](https://codeberg.org/nivaca/py-slowdown/releases), trae:

- un RPM para Fedora (también en Copr: `sudo dnf copr enable
  nivaca/py-slowdown` y `sudo dnf install py-slowdown`), que usa el Rubber
  Band, el PortAudio y el ffmpeg de Fedora;
- una AppImage para cualquier Linux con glibc 2.34 o posterior (Ubuntu
  22.04, Debian 12, Fedora 35 y posteriores), que no necesita nada
  instalado: trae su propio Python, Qt, FFmpeg, Rubber Band y PortAudio;
- un paquete de Debian para Debian 12, Ubuntu 22.04 y posteriores, hecho de
  la AppImage, que la instala en `/opt/py-slowdown`;
- el wheel y el código, para instalarlo con pip.

Todos los archivos van firmados con la clave de
`packaging/RPM-GPG-KEY-py-slowdown` (`ARCHIVO.asc`, y `SHA256SUMS` con su
firma): `gpg --import RPM-GPG-KEY-py-slowdown` y luego `gpg --verify
ARCHIVO.asc ARCHIVO`.

Desde el código, con Python 3.14 o posterior, `install/install.sh` lo
instala para un usuario en Linux o en macOS, en un entorno propio, con su
entrada en el menú (`--uninstall` lo quita). Necesita del sistema la
biblioteca Rubber Band (versión 3 o posterior) y, en Linux, PortAudio:
`sudo dnf install rubberband-libs portaudio` en Fedora, `sudo apt install
librubberband2 libportaudio2` en Debian y Ubuntu, `brew install rubberband`
en macOS. Todavía no hay versión para Windows.

Para correrlo desde el código, con [uv](https://docs.astral.sh/uv/):

    uv run py-slowdown [ARCHIVO]

Las pruebas: `uv run python tools/test.py` (cada archivo en un proceso
propio, todos a la vez), o `uv run pytest`. Cómo se publica una versión
está en [packaging/RELEASING.md](packaging/RELEASING.md).

Dónde se guarda todo
--------------------

- Marcadores y posiciones: `~/.local/share/py-slowdown/bookmarks.json`
  (`$XDG_DATA_HOME`), por la ruta completa de cada archivo de audio. Si el
  archivo se mueve o se renombra, los pierde.
- Configuración (ventana, volumen, salto, idioma, archivos recientes):
  `~/.config/py-slowdown/py-slowdown.conf`.
- Mientras un archivo está abierto, sus muestras decodificadas van a un
  archivo temporal sin nombre en `~/.cache/py-slowdown/`, que desaparece al
  cerrarlo (dos horas en estéreo ocupan allí unos 2,5 GB, pero en la memoria
  queda solo lo que se lee).

Licencia
--------

py-slowdown es software libre, bajo la Licencia Pública General de GNU,
versión 3 o posterior (véase [LICENSE](LICENSE)). Usa la biblioteca Rubber
Band (GPL 2 o posterior), PortAudio (MIT), PyAV (BSD) con FFmpeg (LGPL 2.1
o posterior), PySide6 (LGPL 3), sounddevice (MIT) y NumPy (BSD), todas
compatibles con esa licencia. La AppImage y el paquete de Debian llevan un
Rubber Band compilado de su código, que se publica con cada versión.

Nicolas Vaughan &lt;nicolasvaughan@proton.me&gt;

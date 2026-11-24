py-slowdown
===========

py-slowdown reproduce audio más lento o más rápido sin cambiarle la altura.
Sirve para transcribir grabaciones (clases, entrevistas, dictados) y para
sacar música de oído: el archivo se ve como una forma de onda, los mandos de
siempre lo recorren y los marcadores guardan los lugares a los que se quiere
volver.

*Read in English: [README.md](README.md).*

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
  con su motor R3 («finer»), el de más calidad. A 1× el archivo suena tal
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

Instalación y uso
-----------------

py-slowdown necesita Python 3.14 o posterior. En Linux necesita además
PortAudio (`portaudio` en Fedora, `libportaudio2` en Debian y Ubuntu), con
el que sounddevice llega a la tarjeta de sonido; los paquetes de
sounddevice para Windows y macOS ya lo traen. PyAV trae su propio FFmpeg, y
pylibrb su propio Rubber Band.

Desde el código, con [uv](https://docs.astral.sh/uv/):

    uv run py-slowdown [ARCHIVO]

Las pruebas: `uv run python tools/test.py` (cada archivo en un proceso
propio, todos a la vez), o `uv run pytest`.

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
Band (GPL 2 o posterior) mediante pylibrb (GPL 2), PyAV (BSD) con FFmpeg
(LGPL 2.1 o posterior), PySide6 (LGPL 3), sounddevice (MIT) con PortAudio
(MIT) y NumPy (BSD).

Nicolas Vaughan &lt;nicolasvaughan@proton.me&gt;

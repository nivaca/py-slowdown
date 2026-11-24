# Registro de cambios

Los cambios notables de py-slowdown. Las versiones publicadas, con la
AppImage, el paquete de Debian, el RPM, el wheel y el código fuente, están en
[Codeberg](https://codeberg.org/nivaca/py-slowdown/releases) y
[GitHub](https://github.com/nivaca/py-slowdown/releases).

## 0.2.0 — 2026-11-24

- **Instaladores para Windows y macOS**, que llevan su propio Python, Qt,
  FFmpeg y Rubber Band: para Windows 10 y posteriores, un instalador hecho
  con Inno Setup, solo para el usuario (sin permisos de administrador) o
  para todos, con su entrada en el menú Inicio y py-slowdown en «Abrir con»
  para los archivos de audio; para macOS 13 y posteriores, una imagen de
  disco con py-slowdown.app, para Apple Silicon y para Intel. GitHub los
  hace, los prueba y los quita, en sus propias máquinas, y se firman como
  los demás archivos.
- **Un instalador para cualquier Linux** (`.run`), hecho de la AppImage:
  para el usuario o, con sudo, para todos, con la orden, la entrada del
  menú, los íconos, las páginas de manual y un desinstalador.
- **Los archivos que se abren desde el Finder** (Abrir con, o soltados sobre
  el ícono del Dock) los abre la ventana.
- **Los marcadores y el sonido decodificado, en las carpetas de cada
  sistema**: `%APPDATA%` y `%LOCALAPPDATA%` en Windows, `~/Library` en macOS
  (en Linux, como antes).
- Los manuales y los README explican cómo instalarlo en cada sistema, y qué
  hacer cuando Windows o macOS avisan que el programa no está firmado por
  ellos.

## 0.1.0 — 2026-11-24

La primera versión.

- **Abre archivos de audio y el sonido de los videos**: MP3, M4A/AAC, MP4,
  FLAC, WAV, AIFF, Ogg, Opus, WMA y lo demás que lea FFmpeg, mediante
  PyAV, o con el programa ffmpeg donde PyAV no está (como en Fedora). Se
  leen en segundo plano a un archivo temporal mapeado en memoria, de modo
  que una grabación larga se puede tocar mientras todavía se lee.
- **Una forma de onda** con una regla de tiempos, lo ya tocado en otro
  color, los marcadores, acercar y alejar alrededor del puntero
  (Ctrl+rueda) y una barra de desplazamiento; un clic o un arrastre mueven
  la posición.
- **Los mandos de siempre**: tocar, pausar, detener, al principio, al
  final, atrás y adelante una longitud de salto (de 1 a 60 s; con el botón
  apretado siguen), un segundo atrás o adelante, y el volumen.
- **La velocidad de 0,25× a 3×**, que se cambia mientras suena, sin cambiar
  la altura, con el motor R3 de la biblioteca Rubber Band; a 1× el archivo
  suena tal cual, muestra por muestra.
- **Marcadores** con nombre, sobre la forma de onda y en un panel lateral;
  anterior y siguiente; se exportan como texto. Se guardan por archivo,
  con el punto donde se dejó, y sigue desde allí.
- **Una interfaz en inglés y en español**, también las palabras propias de
  Qt.
- **Paquetes**: un RPM firmado (también en Copr), una AppImage y un paquete
  de Debian que llevan su propio Rubber Band y su propio PortAudio, el
  wheel, el código y un ZIP, todos los archivos firmados, con SHA256SUMS;
  un instalador para Linux y macOS; páginas de manual y manuales de
  usuario (PDF) en inglés y en español.

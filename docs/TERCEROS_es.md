Software de código abierto que usa py-slowdown
==============================================

*(English: [THIRD-PARTY.md](THIRD-PARTY.md))*

py-slowdown es software libre, bajo la Licencia Pública General de GNU,
versión 3 o posterior (GPL-3.0-or-later). Está hecho sobre el software de
código abierto que se lista aquí: las bibliotecas que usa, los programas que
corre y las herramientas con que se hace, se prueba y se empaqueta. Las
versiones son las de py-slowdown 1.6.0 (como las resuelve `uv.lock`); `uv
tree` muestra las de cualquier versión posterior. Las licencias van como
identificadores SPDX, tal como cada proyecto las declara.

Todas estas licencias permiten su uso en un programa bajo la GPL 3. La
biblioteca Rubber Band está bajo la GPL 2 «o (a su elección) cualquier
versión posterior», así que puede usarse bajo la GPL 3. PySide6 y Qt se usan
bajo la LGPL 3 de GNU, como bibliotecas que se cargan al correr. La primera
versión de py-slowdown llegaba a Rubber Band por medio de pylibrb, que
declara solo la GPL 2 y por eso no puede combinarse con un programa bajo la
GPL 3; se reemplazó por un enlace propio de py-slowdown
(`src/py_slowdown/rubberband.py`).


Las bibliotecas que py-slowdown necesita
----------------------------------------

| Software | Versión | Licencia | Qué hace py-slowdown con él |
|---|---|---|---|
| [Rubber Band Library](https://breakfastquay.com/rubberband/) | 3 o posterior (4.0.0 en la AppImage) | GPL-2.0-or-later (o una licencia comercial de Particular Programs) | Cambia la velocidad sin cambiar la altura (su motor R3) |
| [PyAV](https://github.com/PyAV-Org/PyAV) (con FFmpeg 9.0) | 19.0 | BSD-3-Clause (FFmpeg: LGPL-2.1-or-later) | Lee los archivos de audio |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | 0.5 | MIT | Lleva el sonido a la tarjeta de sonido |
| [PortAudio](https://www.portaudio.com/) | 19.7 | MIT | La tarjeta de sonido, debajo de sounddevice |
| [PySide6](https://pyside.org) y Shiboken6 (con Qt 6) | 6.12 | LGPL-3.0-only (o GPL-2.0-only o GPL-3.0-only) | La ventana |
| [NumPy](https://numpy.org) | 2.5 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Las muestras, la forma de onda |

Lo que estas traen consigo:

| Software | Versión | Licencia |
|---|---|---|
| [cffi](https://github.com/python-cffi/cffi) | 2.1 | MIT-0 |
| [pycparser](https://github.com/eliben/pycparser) | 3.12 | BSD-3-Clause |

El RPM usa los paquetes de Fedora de Rubber Band, PortAudio, NumPy,
sounddevice y PySide6. Fedora no tiene PyAV, así que allí los archivos los
leen los programas `ffmpeg` y `ffprobe` ([FFmpeg](https://ffmpeg.org),
LGPL-2.1-or-later en el ffmpeg-free de Fedora).

La AppImage y el paquete de Debian traen su propio Python
([python-appimage](https://github.com/niess/python-appimage), Python bajo
la PSF-2.0), y un Rubber Band y un PortAudio compilados por
`tools/build-libs.py` de su código (que se publica con cada versión, el de
Rubber Band), con la biblioteca de C++ de [zig](https://ziglang.org) (la
libc++ de LLVM, Apache-2.0 WITH LLVM-exception) dentro.


Lo que aprendió de otros programas
----------------------------------

| Software | Licencia | Lo que py-slowdown le debe |
|---|---|---|
| [Transcribe-xsc-file-converter](https://github.com/roryokane/Transcribe-xsc-file-converter), de Rory O’Kane | BlueOak-1.0.0 | Cómo se escriben los marcadores en los archivos de Transcribe! (`.xsc`), que py-slowdown abre (`src/py_slowdown/transcribe.py`) |

py-slowdown no tiene nada de su código: se leyó su analizador para conocer
el formato, que Seventh String Software, los autores de Transcribe!, no
publican.


Las herramientas con que se hace, se prueba y se empaqueta
---------------------------------------------------------

| Software | Licencia | Para qué |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) y uv_build | Apache-2.0 OR MIT | El entorno, el wheel y el paquete de código |
| [pytest](https://pytest.org) | MIT | Las pruebas |
| [zig](https://ziglang.org) (el paquete ziglang de PyPI) | MIT | Compila Rubber Band y PortAudio para la AppImage |
| [appimagetool](https://github.com/AppImage/appimagetool) | MIT | Hace la AppImage |
| [rpm-build](https://rpm.org), rpm-sign, rpmdevtools | GPL-2.0-or-later | El RPM |
| [GnuPG](https://gnupg.org) | GPL-3.0-or-later | Firma los archivos, el RPM y la etiqueta |
| [Inkscape](https://inkscape.org) | GPL-2.0-or-later | Dibuja los íconos a partir de su SVG |
| [Pillow](https://python-pillow.org) | MIT-CMU | El ícono para Windows (.ico) |
| [LuaLaTeX](https://www.luatex.org), [latexmk](https://ctan.org/pkg/latexmk), makeindex | GPL-2.0-or-later, GPL-2.0-only, MIT | Los manuales de usuario |
| [Junicode](https://github.com/psb1558/Junicode-font), [DejaVu](https://dejavu-fonts.github.io) | OFL-1.1, Bitstream-Vera | Las fuentes de los manuales |
| [python-build-standalone](https://github.com/astral-sh/python-build-standalone) | MPL-2.0 (Python: PSF-2.0) | El Python de los instaladores para Windows y macOS |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Inno Setup License (BSD-style) | Hace el instalador para Windows |
| [AppStream](https://www.freedesktop.org/wiki/Distributions/AppStream/), desktop-file-utils | LGPL-2.1-or-later, GPL-2.0-or-later | Comprueban los metadatos y la entrada del menú |

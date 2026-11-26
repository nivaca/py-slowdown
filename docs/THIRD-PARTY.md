Open-source software used by py-slowdown
========================================

*(Español: [TERCEROS_es.md](TERCEROS_es.md))*

py-slowdown is free software, under the GNU General Public License, version 3
or later (GPL-3.0-or-later). It is built on the open-source software listed
here: the libraries it uses, the programs it runs, and the tools that build,
test and package it. The versions are those of py-slowdown 1.6.0 (as
`uv.lock` resolves them); `uv tree` shows those of any later version.
Licences are given as SPDX identifiers, as each project declares them.

All of these licences allow their use in a program under the GPL 3. The
Rubber Band Library is under the GPL 2 "or (at your option) any later
version", and so may be used under the GPL 3. PySide6 and Qt are used under
the GNU LGPL 3, as libraries loaded at run time. The first version of
py-slowdown reached Rubber Band through pylibrb, which declares the GPL 2
only and so cannot be combined with a program under the GPL 3; it was
replaced by a binding of py-slowdown's own (`src/py_slowdown/rubberband.py`).


The libraries py-slowdown needs
-------------------------------

| Software | Version | Licence | What py-slowdown does with it |
|---|---|---|---|
| [Rubber Band Library](https://breakfastquay.com/rubberband/) | 3 or later (4.0.0 in the AppImage) | GPL-2.0-or-later (or a commercial licence from Particular Programs) | Changes the speed without changing the pitch (its R3 engine) |
| [PyAV](https://github.com/PyAV-Org/PyAV) (with FFmpeg 9.0) | 19.0 | BSD-3-Clause (FFmpeg: LGPL-2.1-or-later) | Reads the audio files |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | 0.5 | MIT | Takes the sound to the sound card |
| [PortAudio](https://www.portaudio.com/) | 19.7 | MIT | The sound card, under sounddevice |
| [PySide6](https://pyside.org) and Shiboken6 (with Qt 6) | 6.12 | LGPL-3.0-only (or GPL-2.0-only or GPL-3.0-only) | The window |
| [NumPy](https://numpy.org) | 2.5 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | The samples, the waveform |

What these bring with them:

| Software | Version | Licence |
|---|---|---|
| [cffi](https://github.com/python-cffi/cffi) | 2.1 | MIT-0 |
| [pycparser](https://github.com/eliben/pycparser) | 3.12 | BSD-3-Clause |

The RPM uses Fedora's packages of Rubber Band, PortAudio, NumPy,
sounddevice and PySide6. Fedora has no PyAV, so there the files are read by
the `ffmpeg` and `ffprobe` programs ([FFmpeg](https://ffmpeg.org),
LGPL-2.1-or-later in Fedora's ffmpeg-free).

The AppImage and the Debian package carry their own Python
([python-appimage](https://github.com/niess/python-appimage), Python under
PSF-2.0), and a Rubber Band and a PortAudio compiled by
`tools/build-libs.py` from their sources (published with each release, for
Rubber Band), with the C++ library of [zig](https://ziglang.org) (LLVM's
libc++, Apache-2.0 WITH LLVM-exception) inside.


What it learnt from other programs
----------------------------------

| Software | Licence | What py-slowdown owes it |
|---|---|---|
| [Transcribe-xsc-file-converter](https://github.com/roryokane/Transcribe-xsc-file-converter), by Rory O’Kane | BlueOak-1.0.0 | How the markers are written in the files of Transcribe! (`.xsc`), which py-slowdown opens (`src/py_slowdown/transcribe.py`) |

No code of it is in py-slowdown: its parser was read to learn the format,
which Seventh String Software, the makers of Transcribe!, do not publish.


Tools that build, test and package it
-------------------------------------

| Software | Licence | What for |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) and uv_build | Apache-2.0 OR MIT | The environment, the wheel and the source package |
| [pytest](https://pytest.org) | MIT | The tests |
| [zig](https://ziglang.org) (the ziglang package of PyPI) | MIT | Compiles Rubber Band and PortAudio for the AppImage |
| [appimagetool](https://github.com/AppImage/appimagetool) | MIT | Makes the AppImage |
| [rpm-build](https://rpm.org), rpm-sign, rpmdevtools | GPL-2.0-or-later | The RPM |
| [GnuPG](https://gnupg.org) | GPL-3.0-or-later | Signs the files, the RPM and the tag |
| [Inkscape](https://inkscape.org) | GPL-2.0-or-later | Draws the icons from their SVG |
| [Pillow](https://python-pillow.org) | MIT-CMU | The icon for Windows (.ico) |
| [LuaLaTeX](https://www.luatex.org), [latexmk](https://ctan.org/pkg/latexmk), makeindex | GPL-2.0-or-later, GPL-2.0-only, MIT | The user manuals |
| [Junicode](https://github.com/psb1558/Junicode-font), [DejaVu](https://dejavu-fonts.github.io) | OFL-1.1, Bitstream-Vera | The fonts of the manuals |
| [python-build-standalone](https://github.com/astral-sh/python-build-standalone) | MPL-2.0 (Python: PSF-2.0) | The Python of the installers for Windows and macOS |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Inno Setup License (BSD-style) | Makes the installer for Windows |
| [AppStream](https://www.freedesktop.org/wiki/Distributions/AppStream/), desktop-file-utils | LGPL-2.1-or-later, GPL-2.0-or-later | Check the metadata and the menu entry |

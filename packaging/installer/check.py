"""Comprueba, con el Python de un instalador, que el programa corre por sí solo: lee un archivo, lo estira con
Rubber Band (el de dentro del paquete), encuentra PortAudio y hace la ventana, sin tarjeta de sonido. La corren
tools/bundle-installer.py, antes de hacer el instalador, y .github/workflows/installers.yml, una vez instalado.

    PYTHON check.py
"""

import os
import sys
import tempfile
import wave

import av
import numpy
import PySide6

from py_slowdown import __version__, engine, rubberband
from py_slowdown.audio import Audio
from py_slowdown.engine import Renderer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

with tempfile.TemporaryDirectory() as folder:
    path = os.path.join(folder, "tone.wav")
    with wave.open(path, "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(44100)
        out.writeframes((numpy.sin(numpy.arange(88200) / 7) * 9000).astype("<i2").repeat(2).tobytes())
    audio = Audio(path)
    audio.wait(30)
    renderer = Renderer(audio)
    renderer.set_speed(0.5)
    frames = 0
    while True:
        block, _seam = renderer.render()
        if block is None:
            break
        frames += len(block.frames)
    assert frames > 150000, frames  # (dos segundos a 0.5×: unos cuatro)
    audio.close()

library = rubberband.library()._name
assert "py_slowdown" in library, f"Rubber Band from outside the package: {library}"
sounddevice = engine.sounddevice()

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from py_slowdown.bookmarks import Store
from py_slowdown.window import Window

app = QApplication([])
with tempfile.TemporaryDirectory() as folder:  # (ni la configuración ni los marcadores del usuario)
    window = Window(settings=QSettings(os.path.join(folder, "s.ini"), QSettings.Format.IniFormat),
                    store=Store(Path(folder) / "b.json"))
    window.close()
print(f"py-slowdown {__version__}: PyAV {av.__version__}, NumPy {numpy.__version__}, PySide6 {PySide6.__version__}, "
      f"{sounddevice.get_portaudio_version()[1]}, Rubber Band {os.path.basename(library)}; "
      f"Python {sys.version.split()[0]}: a file read and stretched to 0.5x, the window made")

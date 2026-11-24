#!/usr/bin/env python3
"""Hace las capturas de la ventana para el README y los centros de software:

    uv run python tools/screenshots.py

Escribe docs/img/main_en.png y docs/img/main_es.png: la ventana, en cada idioma, con una grabación de
muestra (ruido rosa que sube y baja, hecho aquí con ffmpeg) a 0,75×, dos marcadores y la posición a un
tercio. La ventana se dibuja fuera de la pantalla, sin tarjeta de sonido y sin tocar la configuración del
usuario.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "img"
SIZE = (1200, 560)


class Silent:
    """A sound card that plays nothing."""

    latency = 0.0

    def open(self, rate, channels, callback):
        pass

    def close(self):
        pass

    @staticmethod
    def supports(rate):
        return True

    @staticmethod
    def default_rate():
        return 48000


def sample(folder: Path) -> Path:
    path = folder / "song.m4a"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=95:c=pink:a=0.3",
                    "-af", "volume='0.15+0.85*abs(sin(t*0.45))*abs(sin(t*0.07+0.4))':eval=frame", "-ac", "2",
                    "-c:a", "aac", str(path)], check=True)
    return path


def shoot(lang: str, audio: Path, folder: Path) -> Path:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from py_slowdown import interface, window
    from py_slowdown.app import translate_qt
    from py_slowdown.bookmarks import Store
    from py_slowdown.engine import Player

    interface.use(lang)
    app = QApplication.instance() or QApplication([])
    for old in app.findChildren(__import__("PySide6.QtCore", fromlist=["QTranslator"]).QTranslator):
        app.removeTranslator(old)
    translate_qt(app)
    window.Output = Silent
    settings = QSettings(str(folder / f"{lang}.ini"), QSettings.Format.IniFormat)
    w = window.Window(player=Player(Silent()), store=Store(folder / f"{lang}.json"), settings=settings)
    w.resize(*SIZE)
    w.show()
    w.open_file(audio)
    w.audio.wait(30)
    labels = {"en": ("Second verse", "Guitar solo"), "es": ("Segunda estrofa", "Solo de guitarra")}
    for seconds, label in zip((21.5, 58.0), labels[lang]):
        w._renamed(w.add_bookmark_at(seconds), label)
    w._show_bookmarks()
    w.set_speed(0.75)
    w.seek(33.2)
    for _ in range(5):
        app.processEvents()
    w.statusBar().clearMessage()
    path = OUT / f"main_{lang}.png"
    w.grab().save(str(path))
    w.close()
    interface.use("en")
    return path


def main() -> int:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="py-slowdown-shots-") as tmp:
        folder = Path(tmp)
        os.environ["XDG_DATA_HOME"] = str(folder)  # (nada en los datos del usuario)
        audio = sample(folder)
        for lang in ("en", "es"):
            print(f"Wrote {shoot(lang, audio, folder).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

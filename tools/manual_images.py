#!/usr/bin/env python3
"""Hace las imágenes del manual de usuario (docs/MANUAL_en.tex, docs/MANUAL_es.tex), en inglés y en español:

    uv run python tools/manual_images.py

Escribe docs/img/manual/NOMBRE_IDIOMA.png: la ventana con un archivo abierto, la forma de onda de cerca, el
menú del clic derecho sobre la forma de onda, una selección que se repite con la cuenta previa, el diálogo de la
cuenta previa, el del nombre de un marcador, los menús Reproducción y Configuración, y los atajos de teclado. Todo sobre una grabación de muestra hecha aquí (con ffmpeg), dibujado
fuera de la pantalla, sin tarjeta de sonido y con una configuración propia: la del usuario no se lee ni se
escribe (HOME y las carpetas XDG apuntan a una carpeta temporal).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
OUT = ROOT / "docs" / "img" / "manual"
SIZE = (1200, 560)
LABELS = {"en": ("Question from the audience", "Second part"), "es": ("Pregunta del público", "Segunda parte")}


def settle(app, seconds: float = 0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def save(widget, name: str, lang: str) -> Path:
    path = OUT / f"{name}_{lang}.png"
    widget.grab().save(str(path))
    print(f"Wrote {path.relative_to(ROOT)}")
    return path


def menu_shot(app, menu, name: str, lang: str):
    """A menu as it opens (grabbed alone: offscreen, a popup is a window of its own)."""
    menu.popup(menu.parentWidget().mapToGlobal(menu.parentWidget().rect().topLeft()))
    settle(app)
    save(menu, name, lang)
    menu.hide()


def window(lang: str, audio: Path, folder: Path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from screenshots import Silent

    from py_slowdown import interface
    from py_slowdown import window as module
    from py_slowdown.app import translate_qt
    from py_slowdown.bookmarks import Store
    from py_slowdown.engine import Player

    interface.use(lang)
    app = QApplication.instance() or QApplication([])
    for old in app.findChildren(__import__("PySide6.QtCore", fromlist=["QTranslator"]).QTranslator):
        app.removeTranslator(old)
    translate_qt(app)
    module.Output = Silent
    settings = QSettings(str(folder / f"{lang}.ini"), QSettings.Format.IniFormat)
    w = module.Window(player=Player(Silent()), store=Store(folder / f"{lang}.json"), settings=settings)
    w.resize(*SIZE)
    w.show()
    w.open_file(audio)
    w.audio.wait(30)
    for seconds, label in zip((21.5, 58.0), LABELS[lang]):
        w._renamed(w.add_bookmark_at(seconds), label)
    w._show_bookmarks()
    w.set_speed(0.75)
    w.seek(33.2)
    settle(app)
    w.statusBar().clearMessage()
    return app, w


def shoot(lang: str, audio: Path, folder: Path):
    from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox

    from py_slowdown import interface
    from py_slowdown.interface import tr
    from py_slowdown.timefmt import clock
    from py_slowdown.window import shortcut_rows

    app, w = window(lang, audio, folder)
    save(w, "window", lang)
    save(w.transport, "controls", lang)
    save(w.panel, "panel", lang)

    # De cerca: unos diez segundos alrededor del primer marcador.
    w.wave.zoom(9.0, w.wave.x_of(21.5))
    w.seek(23.0)
    settle(app)
    save(w.view, "zoom", lang)
    w.wave.fit()

    # Una selección que se repite, con la cuenta previa en su tercer golpe.
    w.set_selection((40.0, 52.0))
    w.a_repeat.setChecked(True)
    w.a_count.setChecked(True)
    w.seek(44.0)
    settle(app)
    w.timer.stop()  # (si no, el reloj de la ventana borra el número: no está sonando)
    w.wave.set_count(3)
    app.processEvents()
    save(w.view, "repeat", lang)
    w.wave.set_count(None)
    w.timer.start()
    w.a_count.setChecked(False)
    w.a_repeat.setChecked(False)
    w.set_selection(None)

    from py_slowdown.countin import CountIn, CountInDialog

    dialog = CountInDialog(CountIn(True, 4, 120, True), 0.75, w)
    dialog.show()
    settle(app)
    save(dialog, "countin", lang)
    dialog.close()

    # El menú del clic derecho, sobre el primer marcador (el que contextMenuEvent arma).
    menu = QMenu(w.wave)
    menu.addAction(tr("Add a bookmark here"))
    menu.addAction(tr("Rename the bookmark…"))
    menu.addAction(tr("Remove the bookmark"))
    menu.addAction(tr("Select from here to the next bookmark"))
    menu_shot(app, menu, "context", lang)

    for title, name in ((tr("&Playback"), "menu_playback"), (tr("&Bookmarks"), "menu_bookmarks"),
                        (tr("&Settings"), "menu_settings")):
        action = next(a for a in w.menuBar().actions() if a.text() == title)
        menu_shot(app, action.menu(), name, lang)

    mark = w.bookmarks[0]
    dialog = QInputDialog(w)
    dialog.setWindowTitle(tr("Bookmark at {time}", time=clock(mark.time, tenths=True)))
    dialog.setLabelText(tr("Label:"))
    dialog.setTextValue(mark.label)
    dialog.show()
    settle(app)
    save(dialog, "rename", lang)
    dialog.close()

    rows = shortcut_rows()
    box = QMessageBox(QMessageBox.Icon.Information, tr("Keyboard shortcuts"),
                      "<table cellspacing='4'>" + "".join(
                          f"<tr><td>{what}</td><td>&nbsp;&nbsp;<b>{keys}</b></td></tr>" for what, keys in rows)
                      + "</table>", parent=w)
    box.show()
    settle(app)
    save(box, "shortcuts", lang)
    box.close()
    w.close()
    interface.use("en")


def main() -> int:
    from screenshots import sample

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="py-slowdown-manual-") as tmp:
        folder = Path(tmp)
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            os.environ[name] = str(folder)
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        audio = sample(folder)
        for lang in ("en", "es"):
            shoot(lang, audio, folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())

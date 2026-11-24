"""El arranque de py-slowdown: py-slowdown [ARCHIVO]."""

from __future__ import annotations

import argparse
import sys

from . import __version__, interface
from .interface import tr

# La descripción del programa, en inglés (la clave de su traducción).
USAGE = "Play audio slower or faster without changing its pitch, with a waveform and bookmarks."


def build_parser() -> argparse.ArgumentParser:
    """The options of the command line, in the language of the interface."""
    parser = argparse.ArgumentParser(prog="py-slowdown", description=tr(USAGE), add_help=False)
    parser.add_argument("file", nargs="?", metavar=tr("FILE"), help=tr("an audio or video file to open"))
    parser.add_argument("-h", "--help", action="help", help=tr("show this help and quit"))
    parser.add_argument("--version", action="version", version=f"py-slowdown {__version__}",
                        help=tr("show the version and quit"))
    return parser


def settings():
    from PySide6.QtCore import QSettings

    return QSettings("py-slowdown", "py-slowdown")


def translate_qt(app) -> None:
    """Qt's own words (OK, Cancel, the names of the keys in the menus) in the language of the interface."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    code = interface.current()
    if code == interface.REFERENCE:
        return
    QLocale.setDefault(QLocale(code))  # (también los números: 0,75×)
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f"qtbase_{code}", folder):
        app.installTranslator(translator)
        app._qt_translator = translator  # (que no se lo lleve el recolector)


def application_class():
    """The QApplication of the program, which also takes the files that macOS sends as events (Open With in
    the Finder, a file dropped on the icon in the Dock): to the window, or kept until there is one."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    class Application(QApplication):
        window = None

        def event(self, event):
            if event.type() == QEvent.Type.FileOpen and event.file():
                if self.window is not None:
                    self.window.open_file(event.file())
                else:
                    self.waiting.append(event.file())
                return True
            return super().event(event)

    return Application


def main(argv: list[str] | None = None) -> int:
    config = settings()
    interface.use(config.value("interface", "") or interface.system_code())
    interface.translate_argparse()
    # (macOS antiguo añadía -psn_... al abrir una aplicación desde el Finder)
    argv = [a for a in (sys.argv[1:] if argv is None else argv) if not a.startswith("-psn_")]
    args = build_parser().parse_args(argv)

    app = application_class()(sys.argv[:1])
    app.waiting = []
    app.setApplicationName("py-slowdown")
    app.setOrganizationName("py-slowdown")
    app.setDesktopFileName("py-slowdown")
    translate_qt(app)

    from .window import Window

    window = Window(settings=config)
    window.show()
    app.window = window
    for path in ([args.file] if args.file else []) + app.waiting:
        window.open_file(path)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

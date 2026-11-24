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


def main(argv: list[str] | None = None) -> int:
    config = settings()
    interface.use(config.value("interface", "") or interface.system_code())
    interface.translate_argparse()
    args = build_parser().parse_args(argv)

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    app.setApplicationName("py-slowdown")
    app.setOrganizationName("py-slowdown")
    app.setDesktopFileName("py-slowdown")

    from .window import Window

    window = Window(settings=config)
    window.show()
    if args.file:
        window.open_file(args.file)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

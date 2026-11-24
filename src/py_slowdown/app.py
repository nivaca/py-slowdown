"""El arranque de py-slowdown: py-slowdown [ARCHIVO]."""

from __future__ import annotations

import argparse
import sys

from . import __version__, interface

USAGE = "Play audio slower or faster without changing its pitch."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="py-slowdown", description=USAGE)
    parser.add_argument("file", nargs="?", help="an audio or video file to open")
    parser.add_argument("--version", action="version", version=f"py-slowdown {__version__}")
    args = parser.parse_args(argv)

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    app.setApplicationName("py-slowdown")
    app.setOrganizationName("py-slowdown")
    app.setDesktopFileName("py-slowdown")
    settings = QSettings("py-slowdown", "py-slowdown")
    interface.use(settings.value("interface", "") or interface.system_code())

    from .window import Window

    window = Window(settings=settings)
    window.show()
    if args.file:
        window.open_file(args.file)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

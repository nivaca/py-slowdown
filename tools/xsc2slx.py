#!/usr/bin/env python3
"""Convierte a .slx todos los archivos de Transcribe! (.xsc) de una carpeta y de sus subcarpetas.

No es parte de py-slowdown: usa el py-slowdown instalado (el del RPM, el de
install/install.sh o cualquiera que Python encuentre), con su propia lectura
de los .xsc (transcribe.read) y su propia escritura de los .slx
(sidecar.save), así que el resultado es el mismo que da abrir el .xsc (File > Open)
seguido de un guardado. Se pone en la carpeta de las grabaciones y se corre
allí; sin argumentos, recorre la carpeta donde está el script.

Los .xsc no se tocan. Si una grabación ya tiene su .slx, se deja como está,
salvo con --force.

py-slowdown: Copyright (C) 2026 Nicolas Vaughan <nicolasvaughan@proton.me>
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if sys.version_info < (3, 14):
    sys.exit("xsc2slx.py: it needs Python 3.14 or later")

HELP = """Convert every file of Transcribe! (.xsc) in a folder, and in its subfolders, to the settings
file of py-slowdown (.slx), written beside its recording (or in --folder). The .xsc files are left as
they are; a recording that already has its .slx is skipped, unless --force is given."""

# Los entornos de install/install.sh, por si el Python de este script no ve py-slowdown.
_VENVS = [
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "py-slowdown/venv/bin/python",
    Path.home() / "Library/Application Support/py-slowdown/venv/bin/python",
]


def _import():
    # El py-slowdown instalado; si este Python no lo tiene, el script vuelve a empezar con el de su entorno.
    try:
        from py_slowdown import sidecar, transcribe
    except ImportError:
        for python in _VENVS:
            if python.is_file() and Path(sys.executable).resolve() != python.resolve():
                os.execv(python, [str(python), *sys.argv])
        sys.exit("xsc2slx.py: py-slowdown is not installed for this Python (" + sys.executable + ")")
    return sidecar, transcribe


def main() -> int:
    parser = argparse.ArgumentParser(prog="xsc2slx.py", description=HELP)
    parser.add_argument("directory", nargs="?", type=Path, default=Path(__file__).resolve().parent,
                        help="the folder to search (default: the folder of this script)")
    parser.add_argument("--folder", type=Path, default=None,
                        help="write the .slx files in this folder, not beside each recording")
    parser.add_argument("-f", "--force", action="store_true", help="replace a .slx that already exists")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only say what would be done")
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error(f"{args.directory} is not a folder")
    sidecar, transcribe = _import()

    # Todos los .xsc, sin importar mayúsculas (.XSC), en orden para que la salida se pueda leer.
    files = sorted(p for p in args.directory.rglob("*") if p.suffix.lower() == transcribe.EXTENSION and p.is_file())
    converted = skipped = failed = 0
    for xsc in files:
        try:
            audio, state = transcribe.read(xsc)
        except transcribe.TranscribeError as error:
            print(f"failed   {xsc}: {error}", file=sys.stderr)
            failed += 1
            continue
        existing = sidecar.find(audio.resolve(), args.folder)
        if existing is not None and not args.force:
            print(f"skipped  {xsc}: {existing.name} already exists")
            skipped += 1
            continue
        if args.dry_run:
            print(f"would    {xsc} -> {sidecar.target(audio, args.folder)}")
            converted += 1
            continue
        try:
            written = sidecar.save(audio, state, args.folder)
        except OSError as error:
            print(f"failed   {xsc}: {error.strerror or error}", file=sys.stderr)
            failed += 1
            continue
        print(f"written  {xsc} -> {written}")
        converted += 1

    # Un resumen al final, y un código de salida distinto de cero si algo falló.
    verb = "to convert" if args.dry_run else "converted"
    print(f"{len(files)} .xsc found: {converted} {verb}, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

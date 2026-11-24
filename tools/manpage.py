#!/usr/bin/env python3
"""Hace las páginas de manual de py-slowdown con la ayuda del programa mismo:

    uv run python tools/manpage.py [--check]

Escribe packaging/man/py-slowdown.1 (inglés) y packaging/man/es/py-slowdown.1 (español), que instalan el
RPM y el paquete de Debian. Cada una tiene la descripción y las opciones de la línea de órdenes, como las
imprime --help, y los atajos de teclado de la ventana, como los muestra Ayuda > Atajos de teclado: el manual
no puede decir nada que el programa no diga. --check solo dice si están al día (las pruebas lo usan).
(De la de py-pdftools.)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
MAN = ROOT / "packaging" / "man"

# The headings of the page, in each language
HEADINGS = {
    "en": {"name": "NAME", "synopsis": "SYNOPSIS", "description": "DESCRIPTION", "options": "OPTIONS",
           "keys": "KEYBOARD", "files": "FILES", "author": "AUTHOR",
           "summary": "play audio slower or faster without changing its pitch",
           "files_text": [
               ("~/.config/py-slowdown/py-slowdown.conf",
                "The settings: the window, the volume, the skip length, the language and the recent files."),
               ("~/.local/share/py-slowdown/bookmarks.json",
                "The bookmarks of each audio file, and the point where it was left ($XDG_DATA_HOME)."),
               ("~/.cache/py-slowdown/",
                "The decoded samples of the file open, in an unnamed temporary file that goes with it."),
           ]},
    "es": {"name": "NOMBRE", "synopsis": "SINOPSIS", "description": "DESCRIPCIÓN", "options": "OPCIONES",
           "keys": "TECLADO", "files": "ARCHIVOS", "author": "AUTOR",
           "summary": "reproducir audio más lento o más rápido sin cambiar su altura",
           "files_text": [
               ("~/.config/py-slowdown/py-slowdown.conf",
                "La configuración: la ventana, el volumen, el salto, el idioma y los archivos recientes."),
               ("~/.local/share/py-slowdown/bookmarks.json",
                "Los marcadores de cada archivo de audio y el punto donde se dejó ($XDG_DATA_HOME)."),
               ("~/.cache/py-slowdown/",
                "Las muestras decodificadas del archivo abierto, en un archivo temporal sin nombre que se va con él."),
           ]},
}


def roff(text: str) -> str:
    """TEXT safe in roff: backslashes doubled, and no line starting with . or '."""
    out = []
    for line in text.replace("\\", "\\e").replace("-", "\\-").splitlines():
        out.append("\\&" + line if line.startswith((".", "'")) else line)
    return "\n".join(out)


def page(lang: str) -> str:
    from py_slowdown import __version__, interface
    from py_slowdown.app import build_parser
    from py_slowdown.window import shortcut_rows

    interface.use(lang)
    interface.translate_argparse()
    os.environ.update(COLUMNS="78", NO_COLOR="1", PYTHON_COLORS="0")  # (the same text in and out of a terminal)
    h = HEADINGS[lang]
    parser = build_parser()
    lines = [f'.TH PY-SLOWDOWN 1 "" "py-slowdown {__version__}" "py-slowdown"',
             f".SH {h['name']}", f"py\\-slowdown \\- {h['summary']}",
             f".SH {h['synopsis']}", ".B py\\-slowdown", f"[\\-\\-version] [{roff(interface.tr('FILE'))}]",
             f".SH {h['description']}", roff(parser.description), f".SH {h['options']}"]
    for action in parser._actions:
        name = ", ".join(action.option_strings) or action.metavar
        lines += [".TP", f".B {roff(name)}", roff(action.help)]
    lines.append(f".SH {h['keys']}")
    for what, keys in shortcut_rows():
        lines += [".TP", f".B {roff(' '.join(keys.split()))}", roff(what)]
    lines.append(f".SH {h['files']}")
    for path, text in h["files_text"]:
        lines += [".TP", f".I {roff(path)}", roff(text)]
    lines += [f".SH {h['author']}", "Nicolas Vaughan <nicolasvaughan@proton.me>"]
    interface.use("en")
    return "\n".join(lines) + "\n"


def targets() -> dict[str, Path]:
    return {"en": MAN / "py-slowdown.1", "es": MAN / "es" / "py-slowdown.1"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make the manual pages from the help of the program.")
    parser.add_argument("--check", action="store_true", help="only say whether they are up to date")
    args = parser.parse_args(argv)
    stale = []
    for lang, path in targets().items():
        text = page(lang)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"Wrote {path.relative_to(ROOT)}")
    if stale:
        sys.exit("Out of date (run uv run python tools/manpage.py): " + ", ".join(str(p.relative_to(ROOT))
                                                                          for p in stale))


if __name__ == "__main__":
    main()

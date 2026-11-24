"""El idioma de la interfaz: menús, botones, mensajes.

La interfaz está escrita en inglés. Cada otro idioma tiene un archivo en la
carpeta ``locale`` del paquete, ``locale/CÓDIGO.xml``, como en py-pdftools:

    <interface code="es" name="Spanish" native="Español">
      <text>
        <en>Opened {name}</en>
        <tr>Abierto {name}</tr>
      </text>
    </interface>

Un texto se busca por su inglés, con los espacios reducidos a uno; puede tener
partes con nombre ({name}), que tr() llena, y la traducción tiene las mismas.
Lo que el archivo no traduce se muestra en inglés.
"""

from __future__ import annotations

import locale
import xml.etree.ElementTree as ET
from pathlib import Path

REFERENCE = "en"
FOLDER = Path(__file__).resolve().parent / "locale"

_code = REFERENCE
_texts: dict[str, str] = {}


def key_of(english: str) -> str:
    return " ".join(english.split())


def names() -> dict[str, str]:
    """{code: name of the language in itself}, English first."""
    out = {REFERENCE: "English"}
    for path in sorted(FOLDER.glob("*.xml")):
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        out[path.stem] = root.get("native") or path.stem
    return out


def read(code: str) -> dict[str, str]:
    """{English key: translation} of the language CODE."""
    root = ET.parse(FOLDER / f"{code}.xml").getroot()
    texts = {}
    for text in root.iter("text"):
        en, tr_ = text.findtext("en"), text.findtext("tr")
        if en is not None and tr_ is not None:
            texts[key_of(en)] = tr_
    return texts


def system_code() -> str:
    """The language of the system, if there is a file for it; English otherwise."""
    try:
        name = locale.getlocale(locale.LC_MESSAGES)[0] or ""
    except (AttributeError, ValueError):
        name = ""
    code = (name or "").split("_")[0].lower()
    return code if code in names() else REFERENCE


def use(code: str) -> None:
    """Show the interface in CODE from now on (English if there is no such file)."""
    global _code, _texts
    if code != REFERENCE and (FOLDER / f"{code}.xml").is_file():
        try:
            _texts = read(code)
            _code = code
            return
        except (OSError, ET.ParseError):
            pass
    _code, _texts = REFERENCE, {}


def current() -> str:
    return _code


def tr(english: str, **parts) -> str:
    """ENGLISH in the language of the interface, with its {parts} filled in."""
    text = _texts.get(key_of(english), english) if _texts else english
    return text.format(**parts) if parts else text

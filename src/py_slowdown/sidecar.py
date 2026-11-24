"""Cómo se tocó cada archivo, en un archivo XML con su mismo nombre (canción.mp3: canción.xml).

El XML va junto al archivo de audio, o en una carpeta elegida en la configuración,
y viaja con él: si se mueven los dos, la posición, la velocidad, la altura, la
manera de oír, la selección, la cuenta previa, los marcadores y los bucles siguen
con el archivo. Dice además dónde estaba el archivo de audio (su ruta completa),
su tamaño y su fecha:

    <?xml version="1.0" encoding="UTF-8"?>
    <py-slowdown version="1.2.0" format="1">
      <file path="/home/.../canción.mp3" name="canción.mp3" size="4861932" modified="2026-11-20T18:04:11"/>
      <saved>2026-11-24T19:30:02</saved>
      <position seconds="83.25"/>
      <playback speed="0.75" pitch="-2.0" formants="true"/>
      <hearing channels="both" filter="bass"/>
      <selection start="95.0" end="103.5" repeat="true"/>
      <countin on="true" bpm="96" offset="0.0"/>
      <bookmarks><bookmark time="21.5">La segunda estrofa</bookmark></bookmarks>
      <loops><loop start="95.0" end="103.5">El puente</loop></loops>
    </py-slowdown>

Si canción.xml ya es de otro archivo (canción.flac, en la misma carpeta), el XML
de este se llama canción.mp3.xml; y si también ese es de otro (en una carpeta
elegida, dos canción.mp3 de carpetas distintas), lleva además unas letras de su
ruta. Al leer, vale el XML que nombra este archivo: por su ruta, o por su nombre
si se movió con él.
"""

from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__
from .bookmarks import Bookmark, Loop

FORMAT = "1"


@dataclass
class FileState:
    """How a file was played: what the XML keeps."""

    position: float = 0.0
    settings: dict = field(default_factory=dict)  # como Window._file_settings: speed, pitch, hearing...
    bookmarks: list[Bookmark] = field(default_factory=list)
    loops: list[Loop] = field(default_factory=list)


def candidates(audio: Path, folder: Path | None = None) -> list[Path]:
    """The names its XML can have, in order: canción.xml, canción.mp3.xml, canción.mp3.LETTERS.xml."""
    where = folder if folder is not None else audio.parent
    letters = hashlib.sha256(str(audio).encode()).hexdigest()[:8]
    return [where / f"{audio.stem}.xml", where / f"{audio.name}.xml", where / f"{audio.name}.{letters}.xml"]


def _owner(path: Path) -> tuple[str, str] | None:
    # (ruta, nombre) del archivo de audio que un XML nombra; None si no es un XML de py-slowdown.
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    element = root.find("file")
    if root.tag != "py-slowdown" or element is None:
        return None
    return element.get("path", ""), element.get("name", "")


def find(audio: Path, folder: Path | None = None) -> Path | None:
    """The XML of AUDIO, if there is one: the one with its path, or else one with its name (moved with it)."""
    audio = audio.resolve()
    by_name = None
    for path in candidates(audio, folder):
        owner = _owner(path) if path.is_file() else None
        if owner is None:
            continue
        if owner[0] == str(audio):
            return path
        if owner[1] == audio.name and by_name is None and not Path(owner[0]).is_file():
            by_name = path  # (su archivo ya no está donde estaba: es este, que se movió con su XML)
    return by_name


def target(audio: Path, folder: Path | None = None) -> Path:
    """Where to write the XML of AUDIO: its own, or the first name that is free or not another file's."""
    audio = audio.resolve()
    found = find(audio, folder)
    if found is not None:
        return found
    for path in candidates(audio, folder):
        if not path.exists():
            return path
        owner = _owner(path)
        if owner is not None and (owner[0] == str(audio) or not Path(owner[0]).is_file()):
            return path  # (de este archivo, o de uno que ya no existe)
    return candidates(audio, folder)[-1]


def _number(element: ET.Element | None, name: str, default: float) -> float:
    try:
        return float(element.get(name)) if element is not None and element.get(name) is not None else default
    except ValueError:
        return default


def _flag(element: ET.Element | None, name: str) -> bool:
    return element is not None and element.get(name, "").lower() in ("true", "1", "yes")


def load(audio: Path, folder: Path | None = None) -> FileState | None:
    """What the XML of AUDIO keeps, or None if it has none (or it cannot be read)."""
    path = find(audio, folder)
    if path is None:
        return None
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    state = FileState(position=max(0.0, _number(root.find("position"), "seconds", 0.0)))
    playback = root.find("playback")
    settings: dict = {"speed": _number(playback, "speed", 1.0), "pitch": _number(playback, "pitch", 0.0)}
    if _flag(playback, "formants"):
        settings["formants"] = True
    hearing = root.find("hearing")
    if hearing is not None:
        settings["hearing"] = [hearing.get("channels", "both"), hearing.get("filter", "none")]
    selection = root.find("selection")
    if selection is not None:
        start, end = _number(selection, "start", -1.0), _number(selection, "end", -1.0)
        if 0.0 <= start < end:
            settings["selection"] = [start, end]
            if _flag(selection, "repeat"):
                settings["repeat"] = True
    countin = root.find("countin")
    if _flag(countin, "on"):
        settings["countin"] = {"bpm": int(_number(countin, "bpm", 100)), "offset": _number(countin, "offset", 0.0)}
    state.settings = settings
    for mark in root.iterfind("bookmarks/bookmark"):
        time = _number(mark, "time", -1.0)
        if time >= 0:
            state.bookmarks.append(Bookmark(time, (mark.text or "").strip()))
    for loop in root.iterfind("loops/loop"):
        start, end = _number(loop, "start", -1.0), _number(loop, "end", -1.0)
        if 0.0 <= start < end:
            state.loops.append(Loop(start, end, (loop.text or "").strip()))
    return state


def _text(value: float) -> str:
    return repr(round(float(value), 3))


def save(audio: Path, state: FileState, folder: Path | None = None) -> Path:
    """Write the XML of AUDIO (raises OSError if it cannot); its path."""
    audio = audio.resolve()
    path = target(audio, folder)
    root = ET.Element("py-slowdown", version=__version__, format=FORMAT)
    try:
        stat = audio.stat()
        ET.SubElement(root, "file", path=str(audio), name=audio.name, size=str(stat.st_size),
                      modified=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"))
    except OSError:
        ET.SubElement(root, "file", path=str(audio), name=audio.name)
    ET.SubElement(root, "saved").text = datetime.now().isoformat(timespec="seconds")
    ET.SubElement(root, "position", seconds=_text(state.position))
    settings = state.settings
    ET.SubElement(root, "playback", speed=_text(settings.get("speed", 1.0)), pitch=_text(settings.get("pitch", 0.0)),
                  formants="true" if settings.get("formants") else "false")
    channels, filter_ = settings.get("hearing", ("both", "none"))
    ET.SubElement(root, "hearing", channels=str(channels), filter=str(filter_))
    if settings.get("selection"):
        start, end = settings["selection"]
        ET.SubElement(root, "selection", start=_text(start), end=_text(end),
                      repeat="true" if settings.get("repeat") else "false")
    countin = settings.get("countin")
    if countin:
        ET.SubElement(root, "countin", on="true", bpm=str(int(countin.get("bpm", 100))),
                      offset=_text(countin.get("offset", 0.0)))
    marks = ET.SubElement(root, "bookmarks")
    for mark in sorted(state.bookmarks, key=lambda b: b.time):
        ET.SubElement(marks, "bookmark", time=_text(mark.time)).text = mark.label
    loops = ET.SubElement(root, "loops")
    for loop in sorted(state.loops, key=lambda x: (x.start, x.end)):
        ET.SubElement(loops, "loop", start=_text(loop.start), end=_text(loop.end)).text = loop.label
    ET.indent(root, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    ET.ElementTree(root).write(temporary, encoding="UTF-8", xml_declaration=True)
    os.replace(temporary, path)  # (entero o nada, aunque el programa muera mientras escribe)
    return path

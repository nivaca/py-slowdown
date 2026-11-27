"""Cómo se tocó cada archivo, en un archivo .slx con su mismo nombre (canción.mp3: canción.slx).

El .slx (un XML de py-slowdown) va junto al archivo de audio, o en una carpeta
elegida en la configuración, y viaja con él: si se mueven los dos, la posición,
la velocidad, la altura, la manera de oír, la selección, la cuenta previa, los
marcadores (entre ellos el primer pulso) y los bucles siguen con el archivo.
Dice además dónde estaba el archivo de audio (su ruta completa), su tamaño y su
fecha:

    <?xml version="1.0" encoding="UTF-8"?>
    <py-slowdown version="1.2.0" format="1">
      <file path="/home/.../canción.mp3" name="canción.mp3" size="4861932" modified="2026-11-20T18:04:11"/>
      <saved>2026-11-24T19:30:02</saved>
      <position seconds="83.25"/>
      <playback speed="0.75" pitch="-2.0" formants="true"/>
      <hearing channels="both" filter="bass"/>
      <equalizer gains="3 0 -2 0 4" on="true"/>
      <volume percent="120"/>
      <selection start="95.0" end="103.5" repeat="true"/>
      <countin on="true" bpm="96" offset="0.0"/>
      <bookmarks>
        <bookmark time="0.82" first-beat="true">Primer pulso</bookmark>
        <bookmark time="21.5">La segunda estrofa</bookmark>
      </bookmarks>
      <loops><loop start="95.0" end="103.5">El puente</loop></loops>
      <pitch start="95.0" end="103.5">
        <curve>95.012 196.021 95.032 196.018 ...</curve>
        <note start="95.06" end="95.46" hz="196.0193"/>
      </pitch>
    </py-slowdown>

La altura seguida (Notas > Seguir la altura) va en <pitch>: el trozo, los pares
tiempo y hertz de la curva (solo donde se halló altura) y las notas.

Si canción.slx ya es de otro archivo (canción.flac, en la misma carpeta), el de
este se llama canción.mp3.slx; y si también ese es de otro (en una carpeta
elegida, dos canción.mp3 de carpetas distintas), lleva además unas letras de su
ruta. Al leer, vale el que nombra este archivo: por su ruta, o por su nombre si
se movió con él. Los de la versión 1.2.0 terminaban en .xml (canción.xml): se
leen todavía, y se borran cuando ya está escrito su .slx.
"""

from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from . import __version__
from .bookmarks import Bookmark, Loop
from .pitch import Note, Track

FORMAT = "1"
EXTENSION = ".slx"
OLD_EXTENSION = ".xml"  # (la de py-slowdown 1.2.0)


@dataclass
class FileState:
    """How a file was played: what the .slx keeps."""

    position: float = 0.0
    settings: dict = field(default_factory=dict)  # como Window._file_settings: speed, pitch, hearing...
    bookmarks: list[Bookmark] = field(default_factory=list)
    loops: list[Loop] = field(default_factory=list)
    pitch: Track | None = None  # la altura seguida en un trozo (Notes > Track the pitch)


def candidates(audio: Path, folder: Path | None = None, extension: str = EXTENSION) -> list[Path]:
    """The names its file can have, in order: canción.slx, canción.mp3.slx, canción.mp3.LETTERS.slx (with
    EXTENSION .xml, those of py-slowdown 1.2.0)."""
    where = folder if folder is not None else audio.parent
    letters = hashlib.sha256(str(audio).encode()).hexdigest()[:8]
    return [where / f"{audio.stem}{extension}", where / f"{audio.name}{extension}",
            where / f"{audio.name}.{letters}{extension}"]


def _owner(path: Path) -> tuple[str, str] | None:
    # (ruta, nombre) del archivo de audio que un .slx (o un .xml de 1.2.0) nombra; None si no es de py-slowdown.
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    element = root.find("file")
    if root.tag != "py-slowdown" or element is None:
        return None
    return element.get("path", ""), element.get("name", "")


def owners(path: Path) -> list[Path]:
    """The audio files that the .slx at PATH may be of: the one with its name beside the .slx (moved with it),
    and the one at the path it says, when they are two different files; empty if PATH is not a file of
    py-slowdown, or its audio file is in neither place."""
    found = _owner(path)
    if found is None:
        return []
    where, name = found
    seen: list[Path] = []
    for audio in (path.parent / name if name else None, Path(where) if where else None):
        if audio is None or str(audio) in ("", ".") or not audio.name or not audio.is_file():
            continue
        # (el mismo archivo por dos caminos, un enlace o la carpeta misma, cuenta una vez)
        if not any(audio.resolve() == other.resolve() for other in seen):
            seen.append(audio)
    return seen


def owner(path: Path) -> Path | None:
    """The audio file that the .slx at PATH is of (where it is, or, if it was moved with it, beside the .slx);
    None if PATH is not a file of py-slowdown, or its audio file is in neither place."""
    found = owners(path)
    return found[-1] if found else None


def find(audio: Path, folder: Path | None = None, extension: str = EXTENSION) -> Path | None:
    """The file of AUDIO, if there is one: the one with its path, or else one with its name (moved with it)."""
    audio = audio.resolve()
    by_name = None
    for path in candidates(audio, folder, extension):
        owner = _owner(path) if path.is_file() else None
        if owner is None:
            continue
        if owner[0] == str(audio):
            return path
        if owner[1] == audio.name and by_name is None and not Path(owner[0]).is_file():
            by_name = path  # (su archivo ya no está donde estaba: es este, que se movió con su .slx)
    return by_name


def target(audio: Path, folder: Path | None = None) -> Path:
    """Where to write the .slx of AUDIO: its own, or the first name that is free or not another file's."""
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
    """What the .slx of AUDIO keeps (or its .xml, from 1.2.0), or None if it has none (or it cannot be read)."""
    path = find(audio, folder) or find(audio, folder, OLD_EXTENSION)
    return read(path) if path is not None else None


def read(path: Path) -> FileState | None:
    """What the file at PATH keeps, or None if it cannot be read (or is not one of py-slowdown)."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    if root.tag != "py-slowdown":
        return None
    state = FileState(position=max(0.0, _number(root.find("position"), "seconds", 0.0)))
    playback = root.find("playback")
    settings: dict = {"speed": _number(playback, "speed", 1.0), "pitch": _number(playback, "pitch", 0.0)}
    if _flag(playback, "formants"):
        settings["formants"] = True
    volume = root.find("volume")
    if volume is not None and volume.get("percent") is not None:
        settings["volume"] = int(_number(volume, "percent", 100))
    hearing = root.find("hearing")
    if hearing is not None:
        settings["hearing"] = [hearing.get("channels", "both"), hearing.get("filter", "none")]
    eq = root.find("equalizer")
    if eq is not None:
        try:
            gains = [int(g) for g in eq.get("gains", "").split()]
        except ValueError:
            gains = []
        if len(gains) == 5 and any(gains):
            settings["eq"] = gains
            if eq.get("on", "true").lower() in ("false", "0", "no"):
                settings["eq_on"] = False
    selection = root.find("selection")
    if selection is not None:
        start, end = _number(selection, "start", -1.0), _number(selection, "end", -1.0)
        if 0.0 <= start < end:
            settings["selection"] = [start, end]
            if _flag(selection, "repeat"):
                settings["repeat"] = True
    if "selection" not in settings and _flag(root.find("repeat"), "whole"):
        settings["repeat"] = True  # (sin selección: el archivo entero)
    countin = root.find("countin")
    if countin is not None:
        # (apagada, se guarda igual si hay un primer pulso: su tempo es el de la pieza)
        settings["countin"] = {"bpm": int(_number(countin, "bpm", 100)), "offset": _number(countin, "offset", 0.0),
                               "on": _flag(countin, "on")}
    state.settings = settings
    for mark in root.iterfind("bookmarks/bookmark"):
        time = _number(mark, "time", -1.0)
        if time >= 0:
            state.bookmarks.append(Bookmark(time, (mark.text or "").strip(), _flag(mark, "first-beat")))
    for loop in root.iterfind("loops/loop"):
        start, end = _number(loop, "start", -1.0), _number(loop, "end", -1.0)
        if 0.0 <= start < end:
            state.loops.append(Loop(start, end, (loop.text or "").strip()))
    state.pitch = _read_pitch(root.find("pitch"))
    return state


def _read_pitch(element: ET.Element | None) -> Track | None:
    # La altura guardada, o None si no la hay (o no se entiende).
    if element is None:
        return None
    start, end = _number(element, "start", -1.0), _number(element, "end", -1.0)
    if not 0.0 <= start < end:
        return None
    try:
        values = [float(v) for v in (element.findtext("curve") or "").split()]
    except ValueError:
        return None
    pairs = np.array(values[: len(values) // 2 * 2]).reshape(-1, 2)
    notes = []
    for note in element.iterfind("note"):
        a, b, hz = _number(note, "start", -1.0), _number(note, "end", -1.0), _number(note, "hz", 0.0)
        if 0.0 <= a <= b and hz > 0:
            notes.append(Note(a, b, hz))
    return Track(start, end, pairs[:, 0].copy(), pairs[:, 1].copy(), notes)


def _text(value: float) -> str:
    return repr(round(float(value), 3))


def save(audio: Path, state: FileState, folder: Path | None = None) -> Path:
    """Write the .slx of AUDIO (raises OSError if it cannot), and remove its .xml of 1.2.0; its path."""
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
    if settings.get("eq"):
        # (las cinco bandas, de 60 Hz a 12 kHz, en dB)
        ET.SubElement(root, "equalizer", gains=" ".join(str(int(g)) for g in settings["eq"]),
                      on="false" if settings.get("eq_on") is False else "true")
    if settings.get("volume") is not None:
        ET.SubElement(root, "volume", percent=str(int(settings["volume"])))
    if settings.get("selection"):
        start, end = settings["selection"]
        ET.SubElement(root, "selection", start=_text(start), end=_text(end),
                      repeat="true" if settings.get("repeat") else "false")
    elif settings.get("repeat"):
        ET.SubElement(root, "repeat", whole="true")
    countin = settings.get("countin")
    if countin:
        ET.SubElement(root, "countin", on="true" if countin.get("on", True) else "false",
                      bpm=str(int(countin.get("bpm", 100))), offset=_text(countin.get("offset", 0.0)))
    marks = ET.SubElement(root, "bookmarks")
    for mark in sorted(state.bookmarks, key=lambda b: b.time):
        element = ET.SubElement(marks, "bookmark", time=_text(mark.time))
        if mark.first_beat:
            element.set("first-beat", "true")
        element.text = mark.label
    loops = ET.SubElement(root, "loops")
    for loop in sorted(state.loops, key=lambda x: (x.start, x.end)):
        ET.SubElement(loops, "loop", start=_text(loop.start), end=_text(loop.end)).text = loop.label
    if state.pitch is not None:
        track = state.pitch
        element = ET.SubElement(root, "pitch", start=_text(track.start), end=_text(track.end))
        found = track.hz > 0
        ET.SubElement(element, "curve").text = " ".join(
            f"{t:.3f} {f:.3f}" for t, f in zip(track.times[found], track.hz[found]))
        for note in track.notes:
            ET.SubElement(element, "note", start=_text(note.start), end=_text(note.end), hz=f"{note.hz:.4f}")
    ET.indent(root, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    ET.ElementTree(root).write(temporary, encoding="UTF-8", xml_declaration=True)
    os.replace(temporary, path)  # (entero o nada, aunque el programa muera mientras escribe)
    old = find(audio, folder, OLD_EXTENSION)
    if old is not None and _owner(old) is not None and _owner(old)[0] == str(audio):
        try:
            old.unlink()  # (su .xml de 1.2.0, que el .slx reemplaza; solo si nombra este mismo archivo)
        except OSError:
            pass
    return path

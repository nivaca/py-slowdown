"""Los archivos de Transcribe! (.xsc), leídos como lo que guardaría un .slx de py-slowdown.

Un .xsc es texto, en líneas de campos separados por comas (una coma dentro de
un campo va como \\C, una barra como \\\\), agrupadas en secciones
(SectionStart,Nombre ... SectionEnd,Nombre). De él se toma:

- la grabación: SoundFileName,nombre,…,ruta completa (Main); si ya no está en
  esa ruta, la del mismo nombre junto al .xsc;
- la velocidad: FX_Speed,activo,?,100000,? (en milésimas de por ciento:
  100000 es 1×), y la afinación: FX_Tuning,activo,?,?,?,centésimas,…
  (View0), que pasa a ser la altura;
- la selección: SelectionLeft y SelectionRight (View0), cada una con su
  muestra y su tiempo (H:MM:SS.ffffff); vacía, es la posición;
- los marcadores (Markers), una línea cada uno:

      S,7350,1,A1,0,0:00:00.167
      tipo (S sección, M compás, B pulso), muestra, nombre automático (1/0),
      nombre, subdivisiones, tiempo

  Las secciones pasan a marcadores; de los compases, solo los que tienen un
  nombre propio (numerados, serían cientos); los pulsos no. Si hay pulsos, el
  primer compás o pulso es el primer pulso de la grabación, y la mediana de
  sus intervalos el tempo de la cuenta previa (apagada);
- los bucles guardados (Loops), con su nombre, su principio y su final:

      L,1,0,0,0,,White,,0:00:00.000000,0:00:00.000000

  Los vacíos (principio igual al final) no cuentan.

El .xsc no se toca: lo que se lee se guarda luego en el .slx de la grabación,
como cualquier cambio.
"""

from __future__ import annotations

import re
from pathlib import Path

from .bookmarks import Bookmark, Loop
from .countin import MAX_BPM, MIN_BPM
from .engine import clamp_pitch, clamp_speed
from .interface import tr
from .sidecar import FileState

EXTENSION = ".xsc"
_TIME = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2}(?:\.\d*)?)$")


class TranscribeError(Exception):
    """A file that is not one of Transcribe!, or whose recording cannot be found."""


def _fields(line: str) -> list[str]:
    # Los campos de una línea, con \C (coma) y \\ (barra) ya resueltos.
    fields, current, chars = [], [], iter(line)
    for char in chars:
        if char == "\\":
            following = next(chars, "")
            current.append({"C": ",", "\\": "\\"}.get(following, "\\" + following))
        elif char == ",":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def seconds(text: str) -> float | None:
    """The seconds of a time of Transcribe! (H:MM:SS.ffffff), or None if TEXT is not one."""
    found = _TIME.match(text.strip())
    if not found:
        return None
    hours, minutes, rest = found.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def _sections(text: str) -> dict[str, list[list[str]]]:
    # Las líneas (ya en campos) de cada sección, por su nombre.
    sections: dict[str, list[list[str]]] = {}
    current: str | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = _fields(line.rstrip("\r\n"))
        if fields[0] == "SectionStart" and len(fields) > 1:
            current = fields[1]
            sections.setdefault(current, [])
        elif fields[0] == "SectionEnd":
            current = None
        elif current is not None:
            sections[current].append(fields)
    return sections


def _value(lines: list[list[str]], key: str) -> list[str] | None:
    # Los valores de la primera línea KEY,… de una sección.
    return next((fields[1:] for fields in lines if fields[0] == key), None)


def _number(values: list[str] | None, index: int) -> float | None:
    try:
        return float(values[index]) if values is not None else None
    except (IndexError, ValueError):
        return None


def _letters(n: int) -> str:
    # A, B, … Z, AA, AB…: como Transcribe! nombra solo las secciones.
    name = ""
    n += 1
    while n:
        n, rest = divmod(n - 1, 26)
        name = chr(ord("A") + rest) + name
    return name


def recording(path: Path, main: list[list[str]]) -> Path | None:
    """The recording a .xsc at PATH is of: where it says, or else the file of that name beside the .xsc."""
    values = _value(main, "SoundFileName") or []
    places = []
    if len(values) > 2 and values[2]:
        places.append(Path(values[2]))
    if values and values[0]:
        places.append(path.parent / Path(values[0]).name)
    return next((place for place in places if place.is_file()), None)


def read(path: str | Path) -> tuple[Path, FileState]:
    """The recording of the Transcribe! file at PATH and what py-slowdown keeps of it; raises TranscribeError
    if it is not one, or its recording is not there."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise TranscribeError(error.strerror or str(error)) from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    lines = text.splitlines()
    if not any(line.startswith("Transcribe!,") for line in lines[:3]):
        raise TranscribeError(tr("it is not a file of Transcribe!"))
    sections = _sections(text)
    audio = recording(path, sections.get("Main", []))
    if audio is None:
        name = (_value(sections.get("Main", []), "SoundFileName") or ["?"])[0]
        raise TranscribeError(tr("its recording, {name}, is not there", name=Path(name).name or "?"))
    state = FileState()
    view = sections.get("View0", [])
    settings: dict = {}

    # La velocidad (100000 es 1×) y la afinación (centésimas de semitono).
    speed = _number(_value(view, "FX_Speed"), 2)
    if speed and speed > 0 and clamp_speed(speed / 100000) != 1.0:
        settings["speed"] = clamp_speed(speed / 100000)
    cents = _number(_value(view, "FX_Tuning"), 4)
    if cents:
        settings["pitch"] = clamp_pitch(cents / 100)

    # La selección (o, vacía, el punto donde se estaba).
    left = _value(view, "SelectionLeft")
    right = _value(view, "SelectionRight")
    start = seconds(left[-1]) if left else None
    end = seconds(right[-1]) if right else None
    if start is not None and end is not None and end - start >= 0.01:
        settings["selection"] = [round(start, 3), round(end, 3)]
        state.position = round(start, 3)
    elif start is not None:
        state.position = round(start, 3)

    # Los marcadores: las secciones, los compases con nombre; los pulsos dan el primero y el tempo.
    beats: list[float] = []
    has_beats = False
    sections_seen = 0
    for fields in sections.get("Markers", []):
        if fields[0] not in ("S", "M", "B") or len(fields) < 4:
            continue
        time = next((seconds(f) for f in reversed(fields) if seconds(f) is not None), None)
        if time is None:
            continue
        automatic = fields[2] == "1"
        name = fields[3].strip()
        if fields[0] == "S":
            state.bookmarks.append(Bookmark(round(time, 3), name or (_letters(sections_seen) if automatic else "")))
            sections_seen += 1
        elif fields[0] == "M" and name:
            state.bookmarks.append(Bookmark(round(time, 3), name))
        if fields[0] in ("M", "B"):
            beats.append(time)
            has_beats = has_beats or fields[0] == "B"
    beats.sort()
    if has_beats and len(beats) > 1:
        intervals = sorted(b - a for a, b in zip(beats, beats[1:]) if b - a > 0.05)
        if intervals:
            middle = len(intervals) // 2
            median = intervals[middle] if len(intervals) % 2 else (intervals[middle - 1] + intervals[middle]) / 2
            bpm = int(round(min(MAX_BPM, max(MIN_BPM, 60.0 / median))))
            first = round(beats[0], 3)
            same = next((mark for mark in state.bookmarks if abs(mark.time - first) < 0.001), None)
            if same is not None:
                same.first_beat = True
            else:
                state.bookmarks.append(Bookmark(first, tr("First beat"), True))
            settings["countin"] = {"bpm": bpm, "offset": 0.0, "on": False}
    state.bookmarks.sort(key=lambda mark: mark.time)

    # Los bucles guardados: L,número,…,nombre,color,…,principio,final.
    for fields in sections.get("Loops", []):
        if fields[0] != "L" or len(fields) < 4:
            continue
        times = [seconds(f) for f in fields[-2:]]
        if None in times or times[1] - times[0] < 0.01:
            continue
        name = fields[5].strip() if len(fields) > 5 else ""
        state.loops.append(Loop(round(times[0], 3), round(times[1], 3), name))

    state.settings = settings
    return audio, state

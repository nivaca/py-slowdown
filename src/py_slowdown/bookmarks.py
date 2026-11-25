"""Los marcadores de cada archivo, sus selecciones guardadas (bucles), y el punto donde se dejó.

Se guardan juntos en un archivo JSON de la carpeta de datos del usuario
($XDG_DATA_HOME/py-slowdown/bookmarks.json, o ~/.local/share/... en Linux;
%APPDATA%\\py-slowdown en Windows; ~/Library/Application Support/py-slowdown en
macOS), por la ruta completa del archivo de audio:

    {"version": 1,
     "files": {"/home/.../clase.mp3": {
         "bookmarks": [{"time": 0.82, "label": "Primer pulso", "first_beat": true},
                       {"time": 83.25, "label": "La segunda estrofa"}],
         "loops": [{"start": 95.0, "end": 103.5, "label": "El puente"}],
         "position": 412.8,
         "settings": {"speed": 0.75, "pitch": -2.0, "selection": [95.0, 103.5], "repeat": true}}}}

En "settings" va lo que la ventana quiere recordar de ese archivo (la velocidad,
la altura, cómo se oye, la selección, la cuenta previa), solo lo que no es lo de
siempre.

El archivo de audio no se toca. Si se mueve o se renombra, sus marcadores se
quedan con la ruta vieja.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Bookmark:
    time: float  # segundos desde el principio
    label: str = ""
    first_beat: bool = False  # el primer pulso de la grabación, para la cuenta previa (uno solo por archivo)


@dataclass
class Loop:
    """A selection kept with a name, to repeat it again."""

    start: float  # segundos
    end: float
    label: str = ""


def data_dir() -> Path:
    """Where the bookmarks are kept: the folder of each system for the data of programs."""
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "py-slowdown"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "py-slowdown"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "py-slowdown"


class Store:
    """The bookmarks of every file, read once and written on each change."""

    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "bookmarks.json"
        self._files: dict[str, dict] = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("files"), dict):
                self._files = data["files"]
        except (OSError, ValueError):
            pass  # sin archivo, o dañado: se empieza de cero (y se reescribe en el primer cambio)

    @staticmethod
    def key(audio_path: str | os.PathLike) -> str:
        return str(Path(audio_path).expanduser().resolve())

    def bookmarks(self, audio_path) -> list[Bookmark]:
        entry = self._files.get(self.key(audio_path), {})
        out = []
        for item in entry.get("bookmarks", []):
            try:
                beat = item.get("first_beat") is True
                out.append(Bookmark(float(item["time"]), str(item.get("label", "")), beat))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(out, key=lambda b: b.time)

    def set_bookmarks(self, audio_path, bookmarks: list[Bookmark]) -> None:
        entry = self._files.setdefault(self.key(audio_path), {})
        entry["bookmarks"] = [
            {"time": round(b.time, 3), "label": b.label} | ({"first_beat": True} if b.first_beat else {})
            for b in sorted(bookmarks, key=lambda b: b.time)
        ]
        self._tidy(audio_path)
        self.save()

    def loops(self, audio_path) -> list[Loop]:
        entry = self._files.get(self.key(audio_path), {})
        out = []
        for item in entry.get("loops", []):
            try:
                start, end = sorted((float(item["start"]), float(item["end"])))
                out.append(Loop(start, end, str(item.get("label", ""))))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(out, key=lambda loop: (loop.start, loop.end))

    def set_loops(self, audio_path, loops: list[Loop]) -> None:
        entry = self._files.setdefault(self.key(audio_path), {})
        entry["loops"] = [{"start": round(loop.start, 3), "end": round(loop.end, 3), "label": loop.label}
                          for loop in sorted(loops, key=lambda loop: (loop.start, loop.end))]
        self._tidy(audio_path)
        self.save()

    def saving(self, audio_path) -> str:
        """How the changes of this file are saved, if the user chose it for it: "always", "never", or "" (as
        Settings > Ask to save says for all)."""
        value = self._files.get(self.key(audio_path), {}).get("saving", "")
        return value if value in ("always", "never") else ""

    def set_saving(self, audio_path, saving: str) -> None:
        entry = self._files.setdefault(self.key(audio_path), {})
        entry["saving"] = saving if saving in ("always", "never") else ""
        self._tidy(audio_path)
        self.save()

    def settings(self, audio_path) -> dict:
        """What was kept of how the file was played (see Window): {} if nothing."""
        value = self._files.get(self.key(audio_path), {}).get("settings", {})
        return dict(value) if isinstance(value, dict) else {}

    def set_settings(self, audio_path, settings: dict) -> None:
        entry = self._files.setdefault(self.key(audio_path), {})
        entry["settings"] = dict(settings)
        self._tidy(audio_path)
        self.save()

    def position(self, audio_path) -> float:
        try:
            return float(self._files.get(self.key(audio_path), {}).get("position", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def set_position(self, audio_path, seconds: float) -> None:
        entry = self._files.setdefault(self.key(audio_path), {})
        entry["position"] = round(max(0.0, seconds), 3)
        self._tidy(audio_path)
        self.save()

    def _tidy(self, audio_path) -> None:
        # Un archivo sin marcadores y leído desde el principio no ocupa lugar.
        key = self.key(audio_path)
        entry = self._files.get(key, {})
        for name in ("bookmarks", "loops", "settings", "saving"):
            if not entry.get(name):
                entry.pop(name, None)
        if not entry.get("position"):
            entry.pop("position", None)
        if not entry:
            self._files.pop(key, None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        text = json.dumps({"version": 1, "files": self._files}, ensure_ascii=False, indent=1)
        temporary.write_text(text + "\n", encoding="utf-8")
        temporary.replace(self.path)  # whole or not at all, even if the program dies while writing


def export_text(bookmarks: list[Bookmark], audio_name: str) -> str:
    """The bookmarks as plain text, one per line: time, a tab, the label."""
    from .timefmt import clock

    lines = [f"# {audio_name}"]
    lines += [f"{clock(b.time, tenths=True)}\t{b.label}" for b in bookmarks]
    return "\n".join(lines) + "\n"

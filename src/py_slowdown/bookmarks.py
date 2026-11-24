"""Los marcadores de cada archivo, y el punto donde se dejó.

Se guardan juntos en un archivo JSON de la carpeta de datos del usuario
($XDG_DATA_HOME/py-slowdown/bookmarks.json, o ~/.local/share/... en Linux;
%APPDATA%\\py-slowdown en Windows; ~/Library/Application Support/py-slowdown en
macOS), por la ruta completa del archivo de audio:

    {"version": 1,
     "files": {"/home/.../clase.mp3": {
         "bookmarks": [{"time": 83.25, "label": "La segunda pregunta"}],
         "position": 412.8}}}

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
                out.append(Bookmark(float(item["time"]), str(item.get("label", ""))))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(out, key=lambda b: b.time)

    def set_bookmarks(self, audio_path, bookmarks: list[Bookmark]) -> None:
        entry = self._files.setdefault(self.key(audio_path), {})
        entry["bookmarks"] = [
            {"time": round(b.time, 3), "label": b.label} for b in sorted(bookmarks, key=lambda b: b.time)
        ]
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
        if not entry.get("bookmarks"):
            entry.pop("bookmarks", None)
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

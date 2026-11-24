"""Tiempos como texto: 1:23.4, 1:02:03."""

from __future__ import annotations

import re


def clock(seconds: float, tenths: bool = False) -> str:
    """SECONDS as m:ss or h:mm:ss, with tenths if asked (0:07.3)."""
    seconds = max(0.0, seconds)
    if tenths:
        whole = int(seconds * 10 + 1e-6)
        hours, rest = divmod(whole, 36000)
        minutes, rest = divmod(rest, 600)
        sec, tenth = divmod(rest, 10)
        tail = f"{sec:02d}.{tenth}"
    else:
        whole = int(seconds + 1e-6)
        hours, rest = divmod(whole, 3600)
        minutes, sec = divmod(rest, 60)
        tail = f"{sec:02d}"
    if hours:
        return f"{hours}:{minutes:02d}:{tail}"
    return f"{minutes}:{tail}"


_CLOCK = re.compile(r"^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:[.,]\d*)?)\s*$")


def parse(text: str) -> float | None:
    """Seconds from "83", "1:23", "1:23.5" or "1:01:23"; None if TEXT is none of them."""
    match = _CLOCK.match(text)
    if not match:
        return None
    a, b, c = match.groups()
    sec = float(c.replace(",", "."))
    if b is not None:
        return int(a) * 3600 + int(b) * 60 + sec
    if a is not None:
        return int(a) * 60 + sec
    return sec

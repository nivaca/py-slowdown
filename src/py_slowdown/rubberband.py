"""La biblioteca Rubber Band, llamada por su interfaz en C (rubberband-c.h).

Un enlace propio y mínimo, con ctypes: solo las funciones que usa el estirador
en tiempo real de engine.py. Rubber Band está bajo la GPL, versión 2 o posterior,
compatible con la de py-slowdown (GPL 3 o posterior).

La biblioteca se busca, en este orden: la que nombre $PY_SLOWDOWN_RUBBERBAND; una
copia dentro del paquete (``lib/``, la que ponen la AppImage y el paquete de
Debian, hecha por tools/build-rubberband.py); la del sistema (rubberband-libs en
Fedora, librubberband en Debian y Ubuntu, rubberband en Homebrew). Hace falta la
versión 3 o posterior, que trae el motor R3.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from pathlib import Path

import numpy as np

PROCESS_REALTIME = 0x00000001
WINDOW_STANDARD = 0x00000000
CHANNELS_TOGETHER = 0x10000000
ENGINE_FINER = 0x20000000

HERE = Path(__file__).resolve().parent


class RubberBandError(OSError):
    """The Rubber Band Library is missing, or too old."""


def _candidates() -> list[str]:
    names = []
    if os.environ.get("PY_SLOWDOWN_RUBBERBAND"):
        names.append(os.environ["PY_SLOWDOWN_RUBBERBAND"])
    for bundled in ("librubberband.so", "librubberband.dylib", "rubberband.dll"):
        if (HERE / "lib" / bundled).is_file():
            names.append(str(HERE / "lib" / bundled))
    found = ctypes.util.find_library("rubberband")
    if found:
        names.append(found)
    if sys.platform == "darwin":
        names += ["/opt/homebrew/lib/librubberband.dylib", "/usr/local/lib/librubberband.dylib"]
    elif sys.platform != "win32":
        # (find_library needs ldconfig or gcc; these are the names the distributions install)
        names += ["librubberband.so.3", "librubberband.so.2"]
    return names


_lib = None


def library() -> ctypes.CDLL:
    """The Rubber Band Library, loaded once (RubberBandError if there is none)."""
    global _lib
    if _lib is not None:
        return _lib
    tried = []
    for name in _candidates():
        try:
            lib = ctypes.CDLL(name)
        except OSError as error:
            tried.append(f"{name}: {error}")
            continue
        if not hasattr(lib, "rubberband_get_engine_version"):
            tried.append(f"{name}: older than version 3")
            continue
        _declare(lib)
        _lib = lib
        return lib
    raise RubberBandError("the Rubber Band Library (version 3 or later) was not found"
                          + ("".join(f"\n  {t}" for t in tried)))


def _declare(lib: ctypes.CDLL) -> None:
    state, uint, f = ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_float)
    table = {
        "rubberband_new": (state, [uint, uint, ctypes.c_int, ctypes.c_double, ctypes.c_double]),
        "rubberband_delete": (None, [state]),
        "rubberband_reset": (None, [state]),
        "rubberband_get_engine_version": (ctypes.c_int, [state]),
        "rubberband_set_time_ratio": (None, [state, ctypes.c_double]),
        "rubberband_get_preferred_start_pad": (uint, [state]),
        "rubberband_get_start_delay": (uint, [state]),
        "rubberband_get_samples_required": (uint, [state]),
        "rubberband_set_max_process_size": (None, [state, uint]),
        "rubberband_process": (None, [state, ctypes.POINTER(f), uint, ctypes.c_int]),
        "rubberband_available": (ctypes.c_int, [state]),
        "rubberband_retrieve": (uint, [state, ctypes.POINTER(f), uint]),
        "rubberband_set_default_debug_level": (None, [ctypes.c_int]),
    }
    for name, (restype, argtypes) in table.items():
        function = getattr(lib, name)
        function.restype = restype
        function.argtypes = argtypes
    lib.rubberband_set_default_debug_level(0)  # sin mensajes en la terminal


def _pointers(planes: np.ndarray):
    # Un puntero por canal (float **), sobre un arreglo canales × muestras contiguo.
    row = planes.strides[0]
    base = planes.ctypes.data
    array = (ctypes.POINTER(ctypes.c_float) * planes.shape[0])()
    for i in range(planes.shape[0]):
        array[i] = ctypes.cast(base + i * row, ctypes.POINTER(ctypes.c_float))
    return array


class Stretcher:
    """A real-time stretcher of Rubber Band: audio in (channels × samples), audio out."""

    def __init__(self, rate: int, channels: int, options: int, time_ratio: float = 1.0):
        self._lib = library()
        self.channels = channels
        self._state = self._lib.rubberband_new(rate, channels, options, time_ratio, 1.0)
        if not self._state:
            raise RubberBandError("the Rubber Band Library could not make a stretcher")
        self._ratio = time_ratio

    def __del__(self):
        state = getattr(self, "_state", None)
        if state:
            self._lib.rubberband_delete(state)
            self._state = None

    @property
    def engine_version(self) -> int:
        return self._lib.rubberband_get_engine_version(self._state)

    @property
    def time_ratio(self) -> float:
        return self._ratio

    @time_ratio.setter
    def time_ratio(self, ratio: float) -> None:
        self._ratio = float(ratio)
        self._lib.rubberband_set_time_ratio(self._state, self._ratio)

    def reset(self) -> None:
        self._lib.rubberband_reset(self._state)

    def set_max_process_size(self, samples: int) -> None:
        self._lib.rubberband_set_max_process_size(self._state, samples)

    def get_preferred_start_pad(self) -> int:
        return self._lib.rubberband_get_preferred_start_pad(self._state)

    def get_start_delay(self) -> int:
        return self._lib.rubberband_get_start_delay(self._state)

    def get_samples_required(self) -> int:
        return self._lib.rubberband_get_samples_required(self._state)

    def available(self) -> int:
        """Output samples ready; -1 once everything was given and taken."""
        return self._lib.rubberband_available(self._state)

    def process(self, audio: np.ndarray, final: bool = False) -> None:
        """Give AUDIO (channels × samples, float32) to the stretcher."""
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        self._lib.rubberband_process(self._state, _pointers(audio), audio.shape[1], int(final))

    def retrieve(self, samples: int) -> np.ndarray:
        """Up to SAMPLES output samples (channels × n)."""
        out = np.empty((self.channels, max(0, samples)), np.float32)
        got = self._lib.rubberband_retrieve(self._state, _pointers(out), out.shape[1]) if samples > 0 else 0
        return out[:, :got]

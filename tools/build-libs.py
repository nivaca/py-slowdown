#!/usr/bin/env python3
"""Compila las bibliotecas que llevan la AppImage, el paquete de Debian y los instaladores:

    uv run python tools/build-libs.py [--target linux|windows-x64|macos-arm64|macos-x86_64] [-o CARPETA]

Para linux (lo de siempre), en CARPETA (build/libs por omisión) deja:

    librubberband.so    Rubber Band 4.0.0, el estirador (GPL 2 o posterior)
    libportaudio.so.2   PortAudio 19.7.0, la salida de sonido (MIT), solo con ALSA
    rubberband-4.0.0.tar.bz2   el código de Rubber Band, que se publica con cada versión (la GPL lo pide)

Para Windows y macOS (build/libs-OBJETIVO), solo Rubber Band: rubberband.dll, compilado con zig desde
cualquier sistema, o librubberband.dylib, compilado en macOS con su clang (Rubber Band usa allí la FFT de
Accelerate, el marco de Apple, que zig no trae). PortAudio viene ya en los paquetes de sounddevice para esos
dos sistemas.

El RPM no las usa: Fedora tiene las suyas. Pero las de Fedora piden una glibc muy nueva (la 2.43, y la 2.38
PortAudio, que además trae JACK y PipeWire), y la AppImage debe correr desde la 2.34. Así que se compilan
aquí, del código de cada proyecto (cuyo SHA-256 se comprueba), con el compilador de C y C++ de zig (el
paquete ziglang de PyPI, que uvx trae), para glibc 2.28, y con la biblioteca de C++ de zig dentro: no
dependen más que de la glibc. Rubber Band se compila en un solo archivo (single/RubberBandSingle.cpp, con
su FFT y su remuestreador propios); PortAudio, solo con ALSA, que carga al correr (PA_ALSA_DYNAMIC): toda
distribución la tiene, y PipeWire y PulseAudio la atienden. Para compilarlo hacen falta los encabezados de
ALSA (alsa-lib-devel en Fedora, libasound2-dev en Debian).

Lo descargado queda en ~/.cache/py-slowdown-build.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIG = ["uvx", "--from", "ziglang==0.17.1", "python", "-m", "ziglang"]
TARGET = "x86_64-linux-gnu.2.28"
TARGETS = ("linux", "windows-x64", "macos-arm64", "macos-x86_64")
MACOS_MINIMUM = "13.0"  # (PySide6 and PyAV need macOS 13)

RUBBERBAND = {
    "url": "https://breakfastquay.com/files/releases/rubberband-4.0.0.tar.bz2",
    "sha256": "af050313ee63bc18b35b2e064e5dce05b276aaf6d1aa2b8a82ced1fe2f8028e9",
    "folder": "rubberband-4.0.0",
}
PORTAUDIO = {
    "url": "https://files.portaudio.com/archives/pa_stable_v190700_20210406.tgz",
    "sha256": "47efbf42c77c19a05d22e627d42873e991ec0c1357219c0d74ce6a2948cb2def",
    "folder": "portaudio",
}
ALSA_HEADERS = Path("/usr/include/alsa/asoundlib.h")


def say(text: str):
    print(text, file=sys.stderr, flush=True)


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    path = base / "py-slowdown-build"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch(source: dict) -> Path:
    """The archive of SOURCE, downloaded once and checked by its SHA-256."""
    path = cache_dir() / source["url"].rsplit("/", 1)[1]
    if not path.is_file():
        say(f"Downloading {source['url']}")
        tmp = path.with_name(path.name + ".tmp")
        with urllib.request.urlopen(source["url"], timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != source["sha256"]:
        path.unlink()
        raise OSError(f"{path.name} is not the archive expected (SHA-256 {digest}); it was removed")
    return path


def unpack(archive: Path, into: Path, folder: str) -> Path:
    with tarfile.open(archive) as tar:
        tar.extractall(into, filter="data")
    return into / folder


def zig(*args: str, cwd: Path):
    subprocess.run([*ZIG, *args], cwd=cwd, check=True)


def build_rubberband(work: Path, out: Path) -> Path:
    say("Compiling Rubber Band (one file; a minute or so)")
    source = unpack(fetch(RUBBERBAND), work, RUBBERBAND["folder"])
    target = out / "librubberband.so"
    zig("c++", "-target", TARGET, "-shared", "-fPIC", "-O2", "-s", "-std=c++17", "-DNDEBUG",
        "single/RubberBandSingle.cpp", "-o", str(target), cwd=source)
    shutil.copy2(fetch(RUBBERBAND), out / Path(RUBBERBAND["url"]).name)
    return target


def build_portaudio(work: Path, out: Path) -> Path:
    if not ALSA_HEADERS.is_file():
        raise OSError("ALSA's headers are needed to build PortAudio (sudo dnf install alsa-lib-devel, or "
                      "sudo apt install libasound2-dev)")
    say("Compiling PortAudio (ALSA only)")
    source = unpack(fetch(PORTAUDIO), work, PORTAUDIO["folder"])
    # Solo los encabezados de ALSA del sistema, no toda /usr/include: los de C son los de zig, para glibc 2.28.
    headers = work / "alsa-headers"
    headers.mkdir()
    (headers / "alsa").symlink_to(ALSA_HEADERS.parent)
    files = sorted(str(p.relative_to(source)) for p in (source / "src/common").glob("*.c"))
    files += ["src/os/unix/pa_unix_hostapis.c", "src/os/unix/pa_unix_util.c", "src/hostapi/alsa/pa_linux_alsa.c"]
    target = out / "libportaudio.so.2"
    zig("cc", "-target", TARGET, "-shared", "-fPIC", "-O2", "-s", "-DNDEBUG", "-DPA_USE_ALSA=1",
        "-DPA_ALSA_DYNAMIC=1", "-DPA_LITTLE_ENDIAN", "-Iinclude", "-Isrc/common", "-Isrc/os/unix",
        f"-I{headers}", *files, "-Wl,-soname,libportaudio.so.2", "-o", str(target), "-lpthread", "-ldl", "-lm",
        cwd=source)
    return target


def check(lib: Path, symbol: str):
    """Stop unless LIB exports SYMBOL and (on Linux) needs no glibc newer than 2.28."""
    import ctypes
    import re

    if not hasattr(ctypes.CDLL(str(lib)), symbol):
        raise OSError(f"{lib.name} does not export {symbol}")
    if shutil.which("objdump") and lib.suffix != ".dylib":
        dump = subprocess.run(["objdump", "-T", str(lib)], capture_output=True, text=True, check=True).stdout
        versions = {tuple(map(int, v.split("."))) for v in re.findall(r"GLIBC_([0-9.]+)", dump)}
        if versions and max(versions) > (2, 28):
            raise OSError(f"{lib.name} needs glibc {'.'.join(map(str, max(versions)))}")


def build_windows(work: Path, out: Path) -> Path:
    say("Compiling Rubber Band for Windows (one file; a minute or so)")
    source = unpack(fetch(RUBBERBAND), work, RUBBERBAND["folder"])
    target = out / "rubberband.dll"
    # (zig deja también una biblioteca de importación, RubberBandSingle.lib, que no hace falta)
    zig("c++", "-target", "x86_64-windows-gnu", "-shared", "-O2", "-s", "-std=c++17", "-DNDEBUG",
        "-D_USE_MATH_DEFINES", "single/RubberBandSingle.cpp", "-o", str(target), cwd=source)
    for extra in out.glob("*.lib"):
        extra.unlink()
    return target


def build_macos(work: Path, out: Path, arch: str) -> Path:
    if sys.platform != "darwin" or not shutil.which("clang++"):
        raise OSError("the library for macOS is compiled on macOS, with its clang++ (xcode-select --install)")
    say(f"Compiling Rubber Band for macOS ({arch})")
    source = unpack(fetch(RUBBERBAND), work, RUBBERBAND["folder"])
    target = out / "librubberband.dylib"
    subprocess.run(["clang++", "-arch", arch, f"-mmacosx-version-min={MACOS_MINIMUM}", "-dynamiclib", "-O2",
                    "-std=c++17", "-DNDEBUG", "-install_name", "@loader_path/librubberband.dylib",
                    "single/RubberBandSingle.cpp", "-framework", "Accelerate", "-o", str(target)],
                   cwd=source, check=True)
    return target


def build(out: Path, target: str = "linux") -> list[Path]:
    if not shutil.which("uvx") and target in ("linux", "windows-x64"):
        raise OSError("uvx (of uv) is needed, to run zig's compiler (https://docs.astral.sh/uv/)")
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="py-slowdown-libs-") as tmp:
        if target == "windows-x64":
            return [build_windows(Path(tmp), out)]
        if target.startswith("macos-"):
            lib = build_macos(Path(tmp), out, target.split("-", 1)[1])
            check(lib, "rubberband_get_engine_version")
            return [lib]
        rubberband = build_rubberband(Path(tmp), out)
        portaudio = build_portaudio(Path(tmp), out)
    check(rubberband, "rubberband_get_engine_version")
    check(portaudio, "Pa_Initialize")
    return [rubberband, portaudio]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools/build-libs.py",
                                     description="Compile Rubber Band and PortAudio for the AppImage.")
    parser.add_argument("--target", choices=TARGETS, default="linux",
                        help="the system they are for (default: linux, for the AppImage)")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="the folder to write them in (build/libs, or build/libs-TARGET)")
    args = parser.parse_args(argv)
    if args.target == "linux" and not sys.platform.startswith("linux"):
        sys.exit("build-libs.py: the libraries of the AppImage are made on Linux")
    output = args.output or ROOT / "build" / ("libs" if args.target == "linux" else f"libs-{args.target}")
    try:
        built = build(output, args.target)
    except (OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        sys.exit(f"build-libs.py: {error}")
    for path in built:
        print(f"Wrote {path} ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

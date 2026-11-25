#!/usr/bin/env python3
"""Hace los instaladores de py-slowdown para Windows y macOS, con un Python propio:

    uv run python tools/bundle-installer.py --system windows|macos [--arch ARQ] [-o CARPETA]
                                            [--stage-only] [--iscc ISCC]

Cada uno lleva un Python 3.14 del proyecto python-build-standalone
(https://github.com/astral-sh/python-build-standalone), sin lo que el programa no usa, con py-slowdown y sus
paquetes instalados dentro (PyAV con su FFmpeg, NumPy, sounddevice con su PortAudio, PySide6 recortado como en
la AppImage) y el Rubber Band de tools/build-libs.py:

* Windows: dist/py-slowdown-VERSIÓN-windows-x64-setup.exe, hecho con Inno Setup
  (packaging/installer/py-slowdown.iss): para el usuario (sin permisos de administrador) o para todos, con
  la entrada del menú Inicio, un ícono en el escritorio si se pide, py-slowdown en «Abrir con» de los
  archivos de audio y el desinstalador en Configuración > Aplicaciones. Necesita ISCC, es decir, Windows.
* macOS: dist/py-slowdown-VERSIÓN-macos-ARQ.dmg (arm64 o x86_64), una imagen de disco con py-slowdown.app,
  que se arrastra a Aplicaciones; la aplicación abre los archivos de audio («Abrir con» del Finder).
  Necesita macOS (hdiutil, codesign, y clang para el Rubber Band).

Los paquetes de Python se instalan con el Python del instalador cuando este corre en el sistema para el que
es (así se hace en GitHub, en .github/workflows/installers.yml); en otro sistema, con --stage-only, uv los
instala para esa plataforma, y queda solo la carpeta del instalador, para revisarla (y para las pruebas). El
Python se descarga la primera vez, se comprueba con su SHA-256 y se guarda en ~/.cache/py-slowdown-build.
"""

from __future__ import annotations

import argparse
import compileall
import hashlib
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
INSTALLER = ROOT / "packaging" / "installer"
ICONS = ROOT / "src" / "py_slowdown" / "icons"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
APP = "py-slowdown"
BUNDLE_ID = "io.github.nivaca.py-slowdown"
SETTINGS_UTI = f"{BUNDLE_ID}.settings"  # el tipo de los .slx
MACOS_MINIMUM = "13.0"  # (PySide6 and PyAV need macOS 13)

# El Python de los instaladores: una versión fija de python-build-standalone, sin símbolos de depuración, con la
# suma SHA-256 de cada tarball (de su SHA256SUMS). Para cambiarla, cambiar las tres cosas juntas.
PYTHON_VERSION = "3.14.10"
PBS_RELEASE = "20261123"
PBS_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/{release}/"
           "cpython-{version}+{release}-{triple}-install_only_stripped.tar.gz")
TRIPLES = {
    ("windows", "x64"): "x86_64-pc-windows-msvc",
    ("macos", "arm64"): "aarch64-apple-darwin",
    ("macos", "x86_64"): "x86_64-apple-darwin",
}
PBS_SHA256 = {
    "x86_64-pc-windows-msvc": "a0fb3d44b5c890c45679b398a685bd4a9e885d6a6100d9565de17545d5ef985c",
    "aarch64-apple-darwin": "f4b4683e628b86490baccd466d9fb9d4f1e73d57c96690634b6a1c0e91f3c5f7",
    "x86_64-apple-darwin": "6441b7990a38e4050149da626ce263766bd11a6017779f45382820bbe91cb7b0",
}
PYTHON_MINOR = ".".join(PYTHON_VERSION.split(".")[:2])

# Lo que se quita del Python: las pruebas, IDLE, Tk (la ventana es de Qt), los archivos para compilar...
STDLIB_LEFT_OUT = ("test", "idlelib", "turtledemo", "tkinter", "turtle.py", "ensurepip", "lib2to3")
UNIX_LEFT_OUT = ("include", "share/man", "lib/pkgconfig", f"lib/python{PYTHON_MINOR}/config-*", "bin/idle*",
                 "bin/pydoc*", "bin/2to3*", "bin/*-config", "lib/tcl*", "lib/tk*", "lib/itcl*", "lib/thread*",
                 "lib/libtcl*", "lib/libtk*", f"lib/python{PYTHON_MINOR}/lib-dynload/_tkinter*")
WINDOWS_LEFT_OUT = ("include", "libs", "tcl", "DLLs/_tkinter.pyd", "DLLs/tcl*.dll", "DLLs/tk*.dll")

# El ejecutable de py-slowdown.app: el Python de la aplicación, con el programa
MACOS_LAUNCHER = r"""#!/bin/sh
# Starts py-slowdown with the Python inside the application (see tools/bundle-installer.py).
here=$(cd -- "$(dirname -- "$0")/../Resources" && pwd -P)
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP VIRTUAL_ENV
exec "$here/python/bin/python3" -m py_slowdown "$@"
"""

# Las extensiones que la aplicación dice abrir (Abrir con, en el Finder y en el Explorador de Windows)
AUDIO = ("mp3", "m4a", "m4b", "aac", "mp4", "flac", "wav", "aif", "aiff", "ogg", "oga", "opus", "wma", "mka",
         "webm", "mkv", "mov")


def say(text: str):
    print(text, file=sys.stderr, flush=True)


def host() -> tuple[str, str]:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x86_64" if system == "macos" else "x64", "arm64": "arm64",
            "aarch64": "arm64"}.get(machine, machine)
    return system, arch


def default_arch(system: str) -> str:
    here_system, here_arch = host()
    if system == "windows":
        return "x64"
    return here_arch if here_system == "macos" else "arm64"


def name(system: str, arch: str) -> str:
    return {"windows": f"{APP}-{VERSION}-windows-{arch}-setup.exe",
            "macos": f"{APP}-{VERSION}-macos-{arch}.dmg"}[system]


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    path = base / "py-slowdown-build"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def python_tarball(system: str, arch: str) -> Path:
    """The Python of the installer, downloaded once and checked by its SHA-256."""
    triple = TRIPLES[system, arch]
    url = PBS_URL.format(release=PBS_RELEASE, version=PYTHON_VERSION, triple=triple)
    path = cache_dir() / url.rsplit("/", 1)[1]
    if not path.is_file():
        say(f"Downloading {url}")
        tmp = path.with_name(path.name + ".tmp")
        with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, path)
    found = sha256(path)
    if found != PBS_SHA256[triple]:
        path.unlink()
        raise OSError(f"{path.name}: its SHA-256 is {found}, not the one expected; it was deleted (try again)")
    return path


def remove(path: Path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def interpreter(python: Path, system: str) -> Path:
    return python / "python.exe" if system == "windows" else python / "bin" / "python3"


def site_packages(python: Path, system: str) -> Path:
    if system == "windows":
        return python / "Lib" / "site-packages"
    return python / "lib" / f"python{PYTHON_MINOR}" / "site-packages"


def unpack_python(tarball: Path, into: Path, system: str) -> Path:
    """The Python of TARBALL in INTO/python, without what the program doesn't use."""
    with tarfile.open(tarball) as tar:
        tar.extractall(into, filter="data")
    python = into / "python"
    stdlib = python / "Lib" if system == "windows" else python / "lib" / f"python{PYTHON_MINOR}"
    for entry in STDLIB_LEFT_OUT:
        remove(stdlib / entry)
    for pattern in WINDOWS_LEFT_OUT if system == "windows" else UNIX_LEFT_OUT:
        for path in python.glob(pattern):
            remove(path)
    return python


def wheel(folder: Path) -> Path:
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(folder)], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    return next(folder.glob(f"py_slowdown-{VERSION}-*.whl"))


def install_packages(python: Path, system: str, arch: str, whl: Path, native: bool):
    """py-slowdown and the packages it needs, into the Python of the installer."""
    site = site_packages(python, system)
    if native:
        # En su propio sistema: el pip del Python del instalador elige los paquetes justos.
        env = clean_env()
        subprocess.run([str(interpreter(python, system)), "-s", "-m", "pip", "install", "--isolated",
                        "--no-cache-dir", "--no-warn-script-location", "--disable-pip-version-check", "--quiet",
                        str(whl)], check=True, env=env)
    else:
        # En otro sistema (--stage-only), uv los elige para el de destino.
        subprocess.run(["uv", "pip", "install", "--quiet", "--target", str(site), "--python-platform",
                        TRIPLES[system, arch], "--python-version", PYTHON_MINOR, "--only-binary", ":all:",
                        str(whl)], check=True)
    prune(site, system)
    remove(site / "bin")  # (las órdenes que uv --target deja, para otro sistema)
    # De los PortAudio que trae sounddevice, solo el de este sistema y esta arquitectura
    keep = {"windows": ("libportaudio64bit.dll", "libportaudio64bit-asio.dll"), "macos": ("libportaudio.dylib",)}
    for path in (site / "_sounddevice_data" / "portaudio-binaries").glob("*"):
        if path.name not in keep[system] and path.name != "README.md":
            remove(path)
    for path in (python / "Scripts" if system == "windows" else python / "bin").glob("pip*"):
        remove(path)
    remove(site / "pip")
    for path in site.glob("pip-*.dist-info"):
        remove(path)


# Las mismas partes de Qt que deja fuera la AppImage, con los nombres de sus archivos en Windows y en macOS
QT_LEFT_OUT = {
    "windows": ("PySide6/Qt6Qml*.dll", "PySide6/Qt6Quick*.dll", "PySide6/Qt6Designer*.dll",
                "PySide6/Qt6ShaderTools*.dll", "PySide6/Qt6Help*.dll", "PySide6/designer.exe",
                "PySide6/assistant.exe", "PySide6/linguist.exe", "PySide6/lrelease.exe", "PySide6/lupdate.exe",
                "PySide6/qml*.exe", "PySide6/qsb.exe", "PySide6/balsam*.exe", "PySide6/svgtoqml.exe"),
    "macos": ("PySide6/Qt/lib/QtQml*.framework", "PySide6/Qt/lib/QtQuick*.framework",
              "PySide6/Qt/lib/QtDesigner*.framework", "PySide6/Qt/lib/QtShaderTools.framework",
              "PySide6/Qt/lib/QtHelp.framework", "PySide6/Designer.app", "PySide6/Assistant.app",
              "PySide6/Linguist.app"),
}


def prune(site: Path, system: str):
    """Out with the parts of PySide6 the program doesn't use (the lists of the AppImage)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("bundle_appimage", ROOT / "tools" / "bundle-appimage.py")
    appimage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(appimage)
    for rel in appimage.PRUNE:
        remove(site / rel)
    for pattern in appimage.PRUNE_GLOBS + list(QT_LEFT_OUT[system]):
        for path in site.glob(pattern):
            remove(path)


def add_rubberband(python: Path, system: str, arch: str, native: bool):
    """The Rubber Band of tools/build-libs.py, in py_slowdown/lib (where rubberband.py looks first)."""
    target = f"windows-{arch}" if system == "windows" else f"macos-{arch}"
    libs = ROOT / "build" / f"libs-{target}"
    lib_name = "rubberband.dll" if system == "windows" else "librubberband.dylib"
    if not (libs / lib_name).is_file():
        if system == "macos" and not native:
            # (el de macOS se compila solo en macOS: en una carpeta de prueba hecha en otro sistema, falta)
            say("(without Rubber Band: the library for macOS is compiled on macOS)")
            return
        subprocess.run([sys.executable, str(ROOT / "tools" / "build-libs.py"), "--target", target], check=True)
    lib = site_packages(python, system) / "py_slowdown" / "lib"
    lib.mkdir(exist_ok=True)
    shutil.copy2(libs / lib_name, lib / lib_name)


def clean_env(**extra) -> dict:
    """The environment without anything that would make a Python look outside its own folders."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTHON", "PIP_", "VIRTUAL_ENV", "UV_", "CONDA"))}
    env.update(PYTHONNOUSERSITE="1", **extra)
    return env


def check(python: Path, system: str):
    """Stop unless the Python of the installer can, on its own, read a file, stretch it with Rubber Band, find
    PortAudio and make the window (no sound card is needed for that)."""
    result = subprocess.run([str(interpreter(python, system)), "-s", str(INSTALLER / "check.py")],
                            capture_output=True, text=True, check=False,
                            env=clean_env(QT_QPA_PLATFORM="offscreen"))
    if result.returncode != 0:
        raise OSError(f"the Python of the installer cannot run the program:\n{result.stdout}{result.stderr}")
    say(result.stdout.strip())


def make_image(work: Path, system: str, arch: str, native: bool) -> Path:
    """The folder of the installed program: python/ (with py-slowdown inside) and its icon."""
    image = work / "image"
    image.mkdir()
    python = unpack_python(python_tarball(system, arch), image, system)
    install_packages(python, system, arch, wheel(work / "wheel"), native)
    add_rubberband(python, system, arch, native)
    if native:
        check(python, system)
        # (compilado de antemano: en Archivos de programa o en /Applications no se puede escribir el caché)
        compileall.compile_dir(str(site_packages(python, system)), quiet=1, workers=0)
    shutil.copy2(ROOT / "LICENSE", image / "LICENSE.txt")
    if system == "windows":
        shutil.copy2(ICONS / "windows" / f"{APP}.ico", image / f"{APP}.ico")
    return image


# --------------------------------------------------------------------------- Windows: Inno Setup

def find_iscc() -> str | None:
    for command in ("iscc", "ISCC"):
        if shutil.which(command):
            return shutil.which(command)
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            found = sorted(Path(base).glob("Inno Setup */ISCC.exe"))
            if found:
                return str(found[-1])
    return None


def file_version() -> str:
    numbers = [n for n in VERSION.split(".") if n.isdigit()]
    return ".".join((numbers + ["0"] * 4)[:4])


def build_windows(image: Path, output: Path, arch: str, iscc: str | None) -> Path:
    iscc = iscc or find_iscc()
    if not iscc:
        raise OSError("Inno Setup (ISCC.exe) is not installed; it makes the installer for Windows "
                      "(choco install innosetup), or use --stage-only")
    out_name = name("windows", arch)[: -len(".exe")]
    extensions = ";".join(AUDIO)
    subprocess.run([iscc, "/Q", f"/DAppVersion={VERSION}", f"/DFileVersion={file_version()}",
                    f"/DSourceDir={image}", f"/DOutputDir={output}", f"/DOutputName={out_name}",
                    f"/DAudio={extensions}", str(INSTALLER / f"{APP}.iss")], check=True)
    return output / name("windows", arch)


# --------------------------------------------------------------------------- macOS: py-slowdown.app in a .dmg

def info_plist() -> dict:
    return {
        "CFBundleName": APP,
        "CFBundleDisplayName": APP,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": APP,
        "CFBundleIconFile": APP,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleDevelopmentRegion": "en",
        "CFBundleLocalizations": ["en", "es"],
        "LSMinimumSystemVersion": MACOS_MINIMUM,
        "LSApplicationCategoryType": "public.app-category.music",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "© 2026 Nicolas Vaughan. GPL-3.0-or-later.",
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Audio file",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": ["public.audio", "public.movie"],
            "CFBundleTypeExtensions": list(AUDIO),
        }, {
            # Los .slx, los ajustes de cada grabación: son de py-slowdown, que los abre (abre su grabación).
            "CFBundleTypeName": "py-slowdown settings of a recording",
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Owner",
            "LSItemContentTypes": [SETTINGS_UTI],
        }],
        "UTExportedTypeDeclarations": [{
            "UTTypeIdentifier": SETTINGS_UTI,
            "UTTypeDescription": "py-slowdown settings of a recording",
            "UTTypeConformsTo": ["public.xml"],
            "UTTypeTagSpecification": {"public.filename-extension": ["slx"],
                                       "public.mime-type": ["application/x-py-slowdown"]},
        }],
    }


def make_app(image: Path, work: Path) -> Path:
    app = work / "dmg" / f"{APP}.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    resources = contents / "Resources"
    resources.mkdir()
    shutil.move(str(image / "python"), resources / "python")
    shutil.copy2(image / "LICENSE.txt", resources / "LICENSE.txt")
    shutil.copy2(ICONS / "macos" / f"{APP}.icns", resources / f"{APP}.icns")
    launcher = contents / "MacOS" / APP
    launcher.write_text(MACOS_LAUNCHER, encoding="utf-8")
    launcher.chmod(0o755)
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info_plist(), f)
    return app


def build_macos(image: Path, work: Path, output: Path, arch: str) -> Path:
    for tool in ("hdiutil", "codesign"):
        if not shutil.which(tool):
            raise OSError(f"{tool} is needed: the installer for macOS is made on macOS (or use --stage-only)")
    app = make_app(image, work)
    # Una firma ad hoc (sin certificado de Apple): sella la aplicación, como macOS exige en Apple Silicon.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    (work / "dmg" / "Applications").symlink_to("/Applications")
    target = output / name("macos", arch)
    remove(target)
    subprocess.run(["hdiutil", "create", "-volname", f"{APP} {VERSION}", "-srcfolder", str(work / "dmg"),
                    "-fs", "HFS+", "-format", "UDZO", "-imagekey", "zlib-level=9", "-ov", str(target)],
                   check=True, stdout=subprocess.DEVNULL)
    return target


# ---------------------------------------------------------------------------

def build(system: str, arch: str, output: Path, stage_only: bool = False, iscc: str | None = None) -> Path:
    native = host() == (system, arch) or (system == "windows" and host()[0] == "windows")
    if not native and not stage_only:
        raise OSError(f"the installer for {system} ({arch}) is made on {system}; here, use --stage-only")
    output.mkdir(parents=True, exist_ok=True)
    if stage_only:
        stage = output / f"{APP}-{system}-{arch}-stage"
        remove(stage)
        stage.mkdir()
        image = make_image(stage, system, arch, native)
        remove(stage / "wheel")
        if system == "macos":
            make_app(image, stage)
            remove(image)
        return stage
    with tempfile.TemporaryDirectory(prefix="py-slowdown-installer-") as tmp:
        work = Path(tmp)
        image = make_image(work, system, arch, native)
        path = build_windows(image, output, arch, iscc) if system == "windows" else build_macos(
            image, work, output, arch)
    # Solo el de esta versión en dist/, por sistema y arquitectura
    for old in output.glob(name(system, arch).replace(VERSION, "*")):
        if old.name != path.name:
            old.unlink()
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools/bundle-installer.py",
                                     description="Make the installer of py-slowdown for Windows or macOS.")
    parser.add_argument("--system", choices=("windows", "macos"), required=True)
    parser.add_argument("--arch", help="x64 (Windows), arm64 or x86_64 (macOS); default: this machine's")
    parser.add_argument("-o", "--output", type=Path, default=DIST, help="the folder to write it in (dist)")
    parser.add_argument("--stage-only", action="store_true",
                        help="only lay out the folder of the installer (on any system)")
    parser.add_argument("--iscc", help="the ISCC.exe of Inno Setup (default: found)")
    args = parser.parse_args(argv)
    arch = args.arch or default_arch(args.system)
    if (args.system, arch) not in TRIPLES:
        sys.exit(f"bundle-installer.py: no installer for {args.system} {arch}")
    try:
        path = build(args.system, arch, args.output, args.stage_only, args.iscc)
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, StopIteration) as error:
        sys.exit(f"bundle-installer.py: {error}")
    size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else path.stat().st_size
    print(f"Wrote {path} ({size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

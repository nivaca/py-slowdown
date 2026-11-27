#!/usr/bin/env python3
"""Hace el instalador de py-slowdown para cualquier Linux, un .run:

    uv run python tools/bundle-run.py [--appimage APPIMAGE] [-o CARPETA]

El instalador es build/release/py-slowdown-VERSIÓN-linux-x86_64.run: el script packaging/installer/install-run.sh
seguido de un tar.gz con lo que trae la AppImage (tools/bundle-appimage.py), que se desempaca, más las páginas
de manual. Instala para el usuario, o para todos si se corre como root, con la orden, la entrada del menú, los
íconos y un desinstalador (véase install-run.sh). Sirve en las distribuciones que no usan .deb ni .rpm, y en
las que sí, para quien prefiera no instalar paquetes del sistema.
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
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "build" / "release"  # (no dist/, que solo guarda el RPM)
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
APP = "py-slowdown"
HEADER = ROOT / "packaging" / "installer" / "install-run.sh"


def say(text: str):
    print(text, file=sys.stderr, flush=True)


def run_name() -> str:
    return f"{APP}-{VERSION}-linux-x86_64.run"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def normalised(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Every file owned by root and readable by all; those that run, runnable."""
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    if info.isdir():
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o755 if info.mode & 0o100 else 0o644
    return info


def payload(appimage: Path, work: Path) -> Path:
    """The tar.gz of the installer: app/ (the files of the AppImage, and the manual pages)."""
    say(f"Unpacking {appimage.name}")
    subprocess.run([str(appimage.resolve()), "--appimage-extract"], cwd=work, check=True,
                   stdout=subprocess.DEVNULL)
    app = work / "app"
    (work / "squashfs-root").rename(app)
    for lang, folder in (("", "man"), ("es", "es")):
        target = app / "man" / (folder if lang else "")
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "packaging" / "man" / lang / f"{APP}.1", target / f"{APP}.1")
    data = work / "payload.tar.gz"
    say("Compressing it")
    with tarfile.open(data, "w:gz", compresslevel=9) as tar:
        tar.add(app, arcname="app", filter=normalised)
    return data


def build(appimage: Path, output: Path) -> Path:
    with tempfile.TemporaryDirectory(dir=ROOT / "build" if (ROOT / "build").is_dir() else None) as tmp:
        work = Path(tmp)
        data = payload(appimage, work)
        header = HEADER.read_text(encoding="utf-8")
        if not header.endswith("\n"):
            header += "\n"
        line = header.count("\n") + 1  # (el contenido empieza en la línea que sigue al script)
        header = (header.replace("@VERSION@", VERSION).replace("@PAYLOAD_LINE@", str(line))
                  .replace("@PAYLOAD_SHA256@", sha256(data)))
        if "@" in "".join(x for x in header.splitlines() if x.startswith(("VERSION=", "PAYLOAD_"))):
            raise ValueError("install-run.sh still has a @FIELD@")
        target = output / run_name()
        tmp_target = target.with_name(target.name + ".tmp")
        with open(tmp_target, "wb") as out, open(data, "rb") as f:
            out.write(header.encode("utf-8"))
            shutil.copyfileobj(f, out)
        tmp_target.chmod(0o755)
        os.replace(tmp_target, target)
    for old in output.glob(f"{APP}-*-linux-x86_64.run"):
        if old.name != target.name:
            old.unlink()
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools/bundle-run.py",
                                     description="Make the installer of py-slowdown for Linux (.run), from its AppImage.")
    parser.add_argument("--appimage", type=Path, default=DIST / f"{APP}-{VERSION}-x86_64.AppImage",
                        help="the AppImage to make it from (tools/bundle-appimage.py)")
    parser.add_argument("-o", "--output", type=Path, default=DIST, help="the folder to write it in (build/release)")
    args = parser.parse_args(argv)
    if not args.appimage.is_file():
        sys.exit(f"bundle-run.py: there is no {args.appimage} (make it first: tools/bundle-appimage.py)")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        path = build(args.appimage, args.output)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        sys.exit(f"bundle-run.py: {error}")
    print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

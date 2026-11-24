"""Los instaladores: el .run de Linux, hecho de una AppImage de mentira, se instala y se desinstala en una
carpeta personal de la prueba; el de Windows (Inno Setup) y el de macOS tienen lo que deben, aunque solo se
hacen en su sistema (.github/workflows/installers.yml)."""

from __future__ import annotations

import importlib.util
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "packaging" / "installer"


def tool(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAKE_APPIMAGE = """#!/bin/sh
# A stand-in AppImage: --appimage-extract lays out what bundle-run.py takes from a real one.
[ "$1" = --appimage-extract ] || exit 2
mkdir -p squashfs-root/usr/share/icons/hicolor/48x48/apps
printf '#!/bin/sh\\necho "py-slowdown ran: $*"\\n' > squashfs-root/AppRun
chmod 755 squashfs-root/AppRun
cp "{desktop}" squashfs-root/py-slowdown.desktop
printf 'png' > squashfs-root/usr/share/icons/hicolor/48x48/apps/py-slowdown.png
"""


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the .run is for Linux")
def test_the_run_installs_and_uninstalls(tmp_path):
    run_tool = tool("bundle-run")
    fake = tmp_path / "fake.AppImage"
    fake.write_text(FAKE_APPIMAGE.format(desktop=ROOT / "packaging" / "py-slowdown.desktop"))
    fake.chmod(0o755)
    out = tmp_path / "out"
    out.mkdir()
    run = run_tool.build(fake, out)
    assert run.name == run_tool.run_name() and os.access(run, os.X_OK)
    home = tmp_path / "home"
    home.mkdir()
    # (una carpeta personal propia, también la de datos: nunca la del usuario)
    env = {"HOME": str(home), "XDG_DATA_HOME": str(home / "data"), "PATH": "/usr/bin:/bin"}

    def sh(*args, check=True):
        return subprocess.run(["sh", *map(str, args)], capture_output=True, text=True, env=env, check=check)

    assert "whole" in sh(run, "--check").stdout
    sh(run, "--yes")
    app = home / "data" / "py-slowdown" / "app"
    command = home / ".local" / "bin" / "py-slowdown"
    assert subprocess.run([str(command), "talk.mp3"], check=False, capture_output=True, text=True,
                          env=env).stdout.strip() == "py-slowdown ran: talk.mp3"
    desktop = (home / "data" / "applications" / "py-slowdown.desktop").read_text()
    assert f'Exec="{command}" %f' in desktop
    assert (home / "data" / "icons" / "hicolor" / "48x48" / "apps" / "py-slowdown.png").is_file()
    assert (home / "data" / "man" / "es" / "man1" / "py-slowdown.1").is_file()
    # Los marcadores del usuario están junto a la carpeta del programa: se quedan.
    (home / "data" / "py-slowdown" / "bookmarks.json").write_text("{}")
    sh(run, "--yes")  # (otra vez: reemplaza la instalación)
    subprocess.run([str(app / "uninstall.sh"), "--yes"], capture_output=True, env=env, check=True)
    assert not app.exists() and not command.exists()
    assert not (home / "data" / "applications" / "py-slowdown.desktop").exists()
    assert (home / "data" / "py-slowdown" / "bookmarks.json").is_file()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the .run is for Linux")
def test_a_damaged_run_says_so(tmp_path):
    run_tool = tool("bundle-run")
    fake = tmp_path / "fake.AppImage"
    fake.write_text(FAKE_APPIMAGE.format(desktop=ROOT / "packaging" / "py-slowdown.desktop"))
    fake.chmod(0o755)
    run = run_tool.build(fake, tmp_path)
    run.write_bytes(run.read_bytes()[:-100])  # (una descarga incompleta)
    r = subprocess.run(["sh", str(run), "--check"], check=False, capture_output=True, text=True,
                       env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 1 and "damaged" in r.stderr


def test_windows_installer_script():
    iss = (INSTALLER / "py-slowdown.iss").read_text(encoding="utf-8")
    # (el AppId nunca cambia: así Windows reconoce cada versión como el mismo programa)
    assert "AppId={{6F3B2C1E-8D4A-4B7E-9C55-2A1D0E7F4B93}" in iss
    assert "PrivilegesRequired=lowest" in iss and "MinVersion=10.0" in iss
    assert '"compiler:Languages\\Spanish.isl"' in iss
    assert '"-s -m py_slowdown"' in iss and "uninsdeletekey" in iss
    for define in ("AppVersion", "FileVersion", "SourceDir", "OutputDir", "OutputName", "Audio"):
        assert f"/D{define}=" in (ROOT / "tools" / "bundle-installer.py").read_text(), define


def test_installer_tool():
    bundle = tool("bundle-installer")
    assert set(bundle.TRIPLES.values()) == set(bundle.PBS_SHA256)
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in bundle.PBS_SHA256.values())
    assert bundle.PYTHON_MINOR == "3.14"
    assert bundle.name("windows", "x64") == f"py-slowdown-{bundle.VERSION}-windows-x64-setup.exe"
    assert bundle.name("macos", "arm64") == f"py-slowdown-{bundle.VERSION}-macos-arm64.dmg"
    plist = bundle.info_plist()
    assert plist["LSMinimumSystemVersion"] == "13.0" and plist["CFBundleExecutable"] == "py-slowdown"
    assert "mp3" in plist["CFBundleDocumentTypes"][0]["CFBundleTypeExtensions"]
    plistlib.dumps(plist)  # (se escribe sin errores)
    assert "-m py_slowdown" in bundle.MACOS_LAUNCHER
    compile((INSTALLER / "check.py").read_text(), "check.py", "exec")


def test_workflow_and_release_agree():
    """The names the workflow makes are those release.py --installers looks for."""
    release = (ROOT / "tools" / "release.py").read_text()
    workflow = (ROOT / ".github" / "workflows" / "installers.yml").read_text()
    for suffix in ("windows-x64-setup.exe", "macos-arm64.dmg", "macos-x86_64.dmg"):
        assert suffix in release
    assert "--system windows" in workflow and "--arch ${{ matrix.arch }}" in workflow
    assert "macos-15-intel" in workflow and "x86_64" in workflow

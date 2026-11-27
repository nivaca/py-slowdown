#!/usr/bin/env python3
"""Publica una versión de py-slowdown en GitHub (con gh) y en Codeberg (con
tea): la etiqueta vVERSIÓN (la versión de pyproject.toml), firmada, con el wheel, el
paquete del código, un ZIP del código, la AppImage, el paquete de Debian y el RPM firmado adjuntos (el RPM
también en Copr), y el código de la biblioteca Rubber Band que llevan dentro la AppImage y el paquete de Debian
(la GPL lo pide), cada uno con su firma (ARCHIVO.asc), con SHA256SUMS y su firma, y con la clave pública que
las comprueba todas; y (--pypi) el wheel y el paquete del código en PyPI.

Todo se firma con la clave del proyecto (SIGNING_KEY de packaging/build-rpm.sh), y cada firma se comprueba
con la clave pública que se publica, antes de publicar nada.

    uv run python tools/release.py [--notes TEXT | --notes-file FILE] [--no-rpm | --no-copr] [--pypi]
                                   [--no-build] [--no-appimage] [--no-tests] [--redo]
                                   [--only github|codeberg] [--dry-run] [--yes]
    uv run python tools/release.py --installers [--dry-run] [--yes]

Los instaladores de Windows y macOS los hace GitHub, en sus propias máquinas, cuando llega la etiqueta
(.github/workflows/installers.yml), y los añade a la versión una vez que este script la ha publicado; entonces
--installers los descarga, los firma aquí (ARCHIVO.asc, SHA256SUMS-installers y su firma) y adjunta las firmas
a la versión de GitHub, y los instaladores con sus firmas a la de Codeberg.

En orden, cada paso solo si hace falta:

1. comprueba que el repositorio esté en main, sin nada por confirmar, que
   las versiones coincidan (pyproject.toml, __init__.py y, salvo con --no-rpm,
   el spec), que las herramientas estén instaladas (gh, tea, gpg; salvo con
   --no-rpm, rpmbuild y copr-cli) y que la clave de firma esté en gpg;
2. corre las pruebas (salvo con --no-tests);
3. hace el wheel y el paquete del código (uv build), el ZIP del código
   (git archive de HEAD), las bibliotecas de la AppImage
   (tools/build-libs.py), la AppImage (tools/bundle-appimage.py),
   y el paquete de Debian y el instalador para Linux (.run) que salen de ella
   (tools/bundle-deb.py, tools/bundle-run.py)
   en build/release/, salvo con --no-build (entonces se usan los que haya en
   build/release/); salvo con --no-rpm, también el RPM firmado en build/rpm/
   (packaging/build-rpm.sh --sign, que comprueba su firma; gpg pide la
   frase de contraseña); luego firma cada archivo (tools/sign_release.py:
   ARCHIVO.asc, build/release/SHA256SUMS y su .asc) y comprueba cada firma solo
   con la clave pública que se publica (packaging/RPM-GPG-KEY-py-slowdown);
4. pone en HEAD la etiqueta vVERSIÓN, firmada con la misma clave (git tag
   --sign), y la comprueba (git tag -v). Si la etiqueta ya está en otro
   commit, se detiene, salvo que --redo la mueva;
5. sube main y la etiqueta a cada remoto (origin es GitHub, codeberg es
   Codeberg; --redo sube la etiqueta con --force);
6. en cada forja, hace la versión de la etiqueta, o conserva la que haya,
   y le adjunta los archivos, en lugar de los que tengan el mismo nombre;
7. salvo con --no-rpm o --no-copr, manda el RPM de código firmado a Copr (copr-cli build, proyecto
   nivaca/py-slowdown). Copr lo compila para cada Fedora del proyecto y lo
   firma con su propia clave. Cada compilación necesita una versión-revisión
   mayor que la anterior, así que el spec debe haberse subido antes
   (rpmdev-bumpspec; véase packaging/RELEASING.md);
8. salvo con --no-apt (o --no-appimage, con el que no hay paquete de Debian),
   añade el paquete de Debian al repositorio APT de estos programas,
   github.com/nivaca/apt, con su herramienta (../apt/tools/apt_repo.py: el
   índice firmado y comprobado);
9. con --pypi, sube el wheel y el paquete del código a PyPI (uv publish,
   con el token de la API en $UV_PUBLISH_TOKEN). PyPI nunca acepta dos veces
   un archivo: con --redo, los que ya están se saltan, no se reemplazan.

Hecha la publicación, aquí solo quedan, en dist/, el RPM (que packaging/build-rpm.sh copia allí y deja
también en build/rpm/), el paquete fuente (.tar.gz) y el ZIP del código, cada uno en lugar de los de
versiones anteriores; lo demás (la rueda, la AppImage, SHA256SUMS y todas las firmas) ya lo tienen las forjas
y Zenodo. Al final se borran build/release/ y build/zenodo/, y la firma del código de Rubber Band (build/libs/
conserva el código mismo, para la compilación siguiente), porque las forjas y Zenodo ya tienen lo que
contenían; --installers borra también build/installers/ una vez firmados y adjuntos los instaladores.

Antes de hacer nada, muestra las órdenes que va a correr y pregunta; con --yes
no pregunta, y con --dry-run solo las muestra. Las notas de una versión nueva son
--notes, --notes-file o, si no, las que hace GitHub con los commits (en Codeberg,
ninguna); una versión que ya está conserva sus notas.

El depósito para Zenodo se reúne en build/zenodo/ después de la etiqueta (tools/zenodo.py collect: el árbol
de la etiqueta, firmado, con SHA256SUMS y la clave pública), y al final se sube a Zenodo y se publica (el token
está en $ZENODO_TOKEN o en el llavero, véase tools/zenodo.py), salvo con --no-zenodo. Allí se publica con un
DOI nuevo; con --zenodo-draft queda como borrador, para publicarlo a mano.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
TAG = f"v{VERSION}"
TITLE = f"py-slowdown {VERSION}"
BRANCH = "main"
# Lo que se publica se hace en build/release/, no en dist/: en local se guardan, en dist/, solo el RPM, el paquete
# fuente y el ZIP, la última versión de cada uno
OUT = "build/release"
WHEEL = f"{OUT}/py_slowdown-{VERSION}-py3-none-any.whl"
SDIST = f"{OUT}/py_slowdown-{VERSION}.tar.gz"
ZIP = f"{OUT}/py-slowdown-{VERSION}.zip"
# Los paquetes que se guardan en dist/ (además del RPM), la última versión de cada clase: (archivo, patrón de los viejos)
KEPT = ((SDIST, "py_slowdown-*.tar.gz"), (ZIP, "py-slowdown-*.zip"))
APPIMAGE = f"{OUT}/py-slowdown-{VERSION}-x86_64.AppImage"
DEB = f"{OUT}/py-slowdown_{VERSION}-1_amd64.deb"  # (hecho de la AppImage, va con ella)
# La herramienta del repositorio APT de estos programas: el proyecto apt, junto a este (github.com/nivaca/apt)
APT_TOOL = Path(__file__).resolve().parent.parent.parent / "apt" / "tools" / "apt_repo.py"
# The source of the Rubber Band compiled into the AppImage and the .deb (tools/build-libs.py): it is published
# with them, as the GPL asks of whoever distributes a program built from it.
RUBBERBAND_SOURCE = "build/libs/rubberband-4.0.0.tar.bz2"
RUN = f"{OUT}/py-slowdown-{VERSION}-linux-x86_64.run"  # (el instalador para Linux, hecho de la AppImage)
# Windows y macOS los hace GitHub (.github/workflows/installers.yml), y --installers los baja aquí
CI_INSTALLERS = [f"build/installers/{name}" for name in (
    f"py-slowdown-{VERSION}-windows-x64-setup.exe",
    f"py-slowdown-{VERSION}-macos-arm64.dmg",
    f"py-slowdown-{VERSION}-macos-x86_64.dmg",
)]
CI_SUMS = "build/installers/SHA256SUMS-installers"
SPEC = "packaging/py-slowdown.spec"
PUBLIC_KEY = "packaging/RPM-GPG-KEY-py-slowdown"  # (the public key published with every release)
SUMS = f"{OUT}/SHA256SUMS"
COPR_PROJECT = "py-slowdown"  # (of the copr-cli user, nivaca)
REMOTES = {"github": "origin", "codeberg": "codeberg"}


def signing_key() -> str:
    """The project's signing key, as packaging/build-rpm.sh pins it."""
    m = re.search(r'SIGNING_KEY="\$\{SIGNING_KEY:-([0-9A-F]{40})\}"', (ROOT / "packaging/build-rpm.sh").read_text())
    return m.group(1) if m else ""


def init_version() -> str:
    m = re.search(r'^__version__ = "([^"]+)"', (ROOT / "src/py_slowdown/__init__.py").read_text(), re.M)
    return m.group(1) if m else ""


def rpm_nvr() -> str:
    """NAME-VERSION-RELEASE of the RPM that build-rpm.sh makes (py-slowdown-0.1.0-1.fc45)."""
    try:
        nvr = subprocess.run(["rpmspec", "-q", "--srpm", "--qf", "%{name}-%{version}-%{release}", SPEC], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("release.py: rpmspec cannot read the spec (sudo dnf install rpm-build)")
    if not nvr.startswith(f"py-slowdown-{VERSION}-"):
        sys.exit(f"release.py: {SPEC} is not at version {VERSION} (rpmdev-bumpspec -n {VERSION} ...)")
    return nvr


def rpm() -> str:
    return f"build/rpm/RPMS/noarch/{rpm_nvr()}.noarch.rpm"


def srpm() -> str:
    return f"build/rpm/SRPMS/{rpm_nvr()}.src.rpm"


def outside_env() -> dict[str, str]:
    """The environment without this project's virtual environment (uv run's), for the
    RPM build: it builds and tests with Fedora's own Python and packages."""
    venv = os.environ.get("VIRTUAL_ENV")
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_RUN_RECURSION_DEPTH")}
    if venv:
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                      if not p.startswith(venv))
    return env


class Release:
    """The steps, run (or only shown) in order."""

    def __init__(self, args):
        self.args = args
        self.planned: list[tuple[str, list[str]]] = []

    def read(self, *command, check=True) -> str:
        """The output of COMMAND (which only reads, so it runs even with --dry-run)."""
        out = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if check and out.returncode != 0:
            sys.exit(f"release.py: {shlex.join(command)}: {(out.stderr or out.stdout).strip()}")
        return out.stdout.strip() if out.returncode == 0 else ""

    def plan(self, description: str, *command):
        self.planned.append((description, [str(c) for c in command]))

    def run_plan(self):
        print(f"Releasing {TAG}:")
        for description, command in self.planned:
            print(f"\n  # {description}\n  {shlex.join(command)}")
        print()
        if self.args.dry_run:
            return
        if not self.args.yes:
            answer = input("Run these commands? [y/N] ").strip().lower()
            if answer not in ("y", "yes", "s", "sí", "si"):
                sys.exit("Nothing done.")
        for description, command in self.planned:
            print(f"\n==> {description}", flush=True)
            if subprocess.run(command, cwd=ROOT, env=outside_env() if command[0].startswith("packaging/")
                              else None).returncode != 0:
                sys.exit(f"release.py: failed: {shlex.join(command)}\nThe steps before it were done; after fixing "
                         "the cause, run the script again (with --redo if the tag was already moved).")
        print(f"\nReleased {TAG}.")

    # -------------------------------------------------------------- checks

    def check(self):
        tools = ["git", "uv"] + [t for t, f in (("gh", "github"), ("tea", "codeberg")) if f in self.forges]
        tools += ["gpg"]
        if self.args.rpm:
            tools += ["rpmbuild", "rpmsign"] + ([] if self.args.no_copr else ["copr-cli"])
        for tool in tools:
            if not shutil.which(tool):
                sys.exit(f"release.py: {tool} is not installed")
        if self.args.pypi and not os.environ.get("UV_PUBLISH_TOKEN"):
            sys.exit("release.py: --pypi needs a PyPI API token in $UV_PUBLISH_TOKEN (make one at "
                     "https://pypi.org/manage/account/token/)")
        # Todo se firma, siempre: sin la clave no hay versión.
        key = signing_key()
        have = subprocess.run(["gpg", "--batch", "--list-secret-keys", key], capture_output=True).returncode
        if not key or have != 0:
            sys.exit(f"release.py: the signing key {key or '(none pinned)'} is not in this machine's gpg "
                     "keyring; import it first (see packaging/RELEASING.md)")
        if not (ROOT / PUBLIC_KEY).is_file():
            sys.exit(f"release.py: there is no {PUBLIC_KEY}, the public key published with the release")
        if init_version() != VERSION:
            sys.exit(f"release.py: pyproject.toml says {VERSION}, src/py_slowdown/__init__.py says "
                     f"{init_version()}")
        branch = self.read("git", "rev-parse", "--abbrev-ref", "HEAD")
        if branch != BRANCH:
            sys.exit(f"release.py: on branch {branch}, not {BRANCH}")
        if self.read("git", "status", "--porcelain"):
            message = "there are changes not committed (see git status)"
            if not self.args.dry_run:
                sys.exit(f"release.py: {message}")
            print(f"release.py: (dry run) {message}", file=sys.stderr)

    def repos(self) -> dict[str, str]:
        """{forge: owner/name}, from the push addresses of the remotes."""
        found = {}
        for forge in self.forges:
            url = self.read("git", "remote", "get-url", "--push", REMOTES[forge], check=False)
            m = re.search(r"(github\.com|codeberg\.org)[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
            if not m or ("github" in m[1]) != (forge == "github"):
                sys.exit(f"release.py: the remote {REMOTES[forge]} does not push to {forge} (git remote -v)")
            found[forge] = m[2]
        return found

    # -------------------------------------------------------------- steps

    def tests(self):
        if not self.args.no_tests:
            # (a la vez, cada archivo en su proceso: tools/test.py, como el %check del RPM)
            self.plan("Run the tests", "uv", "run", "python", "tools/test.py")

    def build(self):
        if self.args.no_build:
            for f in self.files:
                if not (ROOT / f).is_file():
                    sys.exit(f"release.py: there is no {f} (leave out --no-build to make it)")
            return
        self.plan(f"Make the folder of the release, {OUT}/", "mkdir", "-p", OUT)
        self.plan("Make the wheel and the source package", "uv", "build", "--out-dir", OUT)
        self.plan("Make the ZIP of the source", "git", "archive", "--format=zip", f"--prefix=py-slowdown-{VERSION}/",
                  "--output", ZIP, "HEAD")
        if APPIMAGE in self.files:
            self.plan("Compile Rubber Band and PortAudio for the AppImage", "uv", "run", "python",
                      "tools/build-libs.py")
            self.plan("Make the AppImage", "uv", "run", "python", "tools/bundle-appimage.py", "--output", OUT)
            self.plan("Make the Debian package", "uv", "run", "python", "tools/bundle-deb.py", "--appimage", APPIMAGE,
                      "--output", OUT)
            self.plan("Make the installer for Linux", "uv", "run", "python", "tools/bundle-run.py", "--appimage",
                      APPIMAGE, "--output", OUT)
        if self.args.rpm:
            self.plan("Make the signed RPM", "packaging/build-rpm.sh", "--sign")

    def sign(self):
        """Every file published signed (FILE.asc), with SHA256SUMS and its signature, and each signature checked
        with only the public key published."""
        signed = [f for f in self.files if f != PUBLIC_KEY]
        self.plan("Sign the files, and check each signature with the published key", sys.executable,
                  "tools/sign_release.py", "--key", signing_key(), "--public", PUBLIC_KEY, "--sums", SUMS, *signed)
        self.files = signed + [f"{f}.asc" for f in signed] + [SUMS, f"{SUMS}.asc", PUBLIC_KEY]

    def tag(self):
        head = self.read("git", "rev-parse", "HEAD")
        tagged = self.read("git", "rev-parse", "--verify", "--quiet", f"refs/tags/{TAG}^{{commit}}", check=False)
        if tagged and tagged != head and not self.args.redo:
            sys.exit(f"release.py: {TAG} is already the tag of {tagged[:7]}, not of HEAD ({head[:7]}); --redo "
                     "moves it (and replaces the files of the releases)")
        if tagged != head:
            self.plan("Move the tag to HEAD, signed" if tagged else "Tag HEAD, signed", "git", "tag", "--force",
                      "--sign", "--local-user", signing_key(), TAG, "--message", TITLE)
            self.plan("Check the signature of the tag", "git", "tag", "--verify", TAG)
        for forge in self.forges:
            remote = REMOTES[forge]
            self.plan(f"Push {BRANCH} to {remote}", "git", "push", remote, BRANCH)
            if self.args.redo:
                self.plan(f"Push the tag to {remote} (replacing it)", "git", "push", "--force", remote,
                          f"refs/tags/{TAG}")
                continue
            there = self.read("git", "ls-remote", "--tags", remote, f"refs/tags/{TAG}^{{}}", check=False)
            on_remote = there.split()[0] if there else ""
            if on_remote == head:
                continue
            if on_remote:
                sys.exit(f"release.py: on {remote}, {TAG} is the tag of {on_remote[:7]}; --redo moves it")
            self.plan(f"Push the tag to {remote}", "git", "push", remote, f"refs/tags/{TAG}")

    def notes(self, github: bool) -> list[str]:
        if self.args.notes_file:
            return ["--notes-file" if github else "--note-file", self.args.notes_file]
        if self.args.notes:
            return ["--notes" if github else "--note", self.args.notes]
        return ["--generate-notes"] if github else []

    def github(self, repo: str):
        exists = subprocess.run(["gh", "release", "view", TAG, "--repo", repo], cwd=ROOT,
                                capture_output=True).returncode == 0
        if exists:
            self.plan("GitHub: attach the files to the release (replacing those there)", "gh", "release", "upload",
                      TAG, *self.files, "--clobber", "--repo", repo)
        else:
            self.plan("GitHub: make the release", "gh", "release", "create", TAG, *self.files, "--title", TITLE,
                      "--verify-tag", *self.notes(True), "--repo", repo)

    def codeberg(self, repo: str):
        where = ["--repo", repo, "--login", self.args.tea_login]
        releases = self.tea_json("releases", "ls", "--limit", "50", *where)
        if any(TAG in (r.get("tagname"), r.get("tag")) for r in releases):
            names = {a.get("name") for a in self.tea_json("releases", "assets", "ls", TAG, *where)}
            old = [Path(f).name for f in self.files if Path(f).name in names]
            if old:
                self.plan("Codeberg: remove the files of the same name (tea cannot replace them)", "tea",
                          "releases", "assets", "delete", TAG, *old, "--confirm", *where)
            self.plan("Codeberg: attach the files to the release", "tea", "releases", "assets", "create", TAG,
                      *self.files, *where)
        else:
            assets = [a for f in self.files for a in ("--asset", f)]
            self.plan("Codeberg: make the release", "tea", "releases", "create", "--tag", TAG, "--title", TITLE,
                      *self.notes(False), *assets, *where)

    def tea_json(self, *command) -> list[dict]:
        """The rows tea gives in JSON, with its keys made plain ("tag-_name" is tagname)."""
        out = self.read("tea", *command, "--output", "json")
        try:
            rows = json.loads(out or "[]")
        except ValueError:
            sys.exit(f"release.py: tea {' '.join(command)}: not JSON: {out[:200]}")
        return [{re.sub("[^a-z]", "", k.lower()): v for k, v in r.items()} for r in rows]

    def copr(self):
        if self.args.no_build and not (ROOT / srpm()).is_file():
            sys.exit(f"release.py: there is no {srpm()} (leave out --no-build to make it)")
        self.plan(f"Copr: build the RPM (project {COPR_PROJECT})", "copr-cli", "build", COPR_PROJECT, srpm())

    def pypi(self):
        self.plan("PyPI: upload the wheel and the source package", "uv", "publish",
                  "--check-url", "https://pypi.org/simple/", WHEEL, SDIST)

    def installers(self):
        """--installers: those of Windows and macOS, from the release on GitHub (made by installers.yml) to
        the one on Codeberg, each signed here, with the signatures attached to both."""
        self.forges = ["github", "codeberg"]
        for tool in ("gh", "tea", "gpg"):
            if not shutil.which(tool):
                sys.exit(f"release.py: {tool} is not installed")
        key = signing_key()
        if not key or subprocess.run(["gpg", "--batch", "--list-secret-keys", key],
                                     capture_output=True).returncode != 0:
            sys.exit(f"release.py: the signing key {key or '(none pinned)'} is not in this machine's gpg keyring")
        repos = self.repos()
        names = [Path(f).name for f in CI_INSTALLERS]
        on_github = self.read("gh", "release", "view", TAG, "--repo", repos["github"], "--json", "assets",
                              "--jq", ".assets[].name", check=False).split("\n")
        missing = [n for n in names if n not in on_github]
        if missing:
            sys.exit(f"release.py: the release {TAG} on GitHub does not have {', '.join(missing)} "
                     "(has installers.yml finished?)")
        patterns = [a for n in names for a in ("--pattern", n)]
        self.plan("Download the installers from GitHub", "gh", "release", "download", TAG, *patterns, "--dir",
                  "build/installers", "--clobber", "--repo", repos["github"])
        # Se firman aquí, como los demás archivos de la versión, con sus propias sumas; las firmas van a las dos
        self.plan("Sign the installers, and check each signature with the published key", sys.executable,
                  "tools/sign_release.py", "--key", key, "--public", PUBLIC_KEY, "--sums", CI_SUMS, *CI_INSTALLERS)
        signatures = [f"{f}.asc" for f in CI_INSTALLERS] + [CI_SUMS, f"{CI_SUMS}.asc"]
        self.plan("GitHub: attach their signatures to the release", "gh", "release", "upload", TAG, *signatures,
                  "--clobber", "--repo", repos["github"])
        self.files = CI_INSTALLERS + signatures
        self.codeberg(repos["codeberg"])
        # (they are on both forges now, signed: no copy kept here)
        self.plan("Delete the installers from build/ (the forges have them)", "rm", "-rf", "build/installers")
        self.run_plan()

    def apt(self):
        """The Debian package added to the APT repository of these programs (github.com/nivaca/apt), by its own
        tool, which keeps only the newest version, signs the index and checks it before uploading."""
        if not APT_TOOL.is_file():
            sys.exit(f"release.py: {APT_TOOL} is not there (clone github.com/nivaca/apt beside this project, "
                     "or use --no-apt)")
        self.plan("APT: add the Debian package to github.com/nivaca/apt", sys.executable, str(APT_TOOL), "add", DEB)

    def zenodo_collect(self):
        """The deposit of the release for Zenodo, in build/zenodo/ (tools/zenodo.py): the tree of the tag, signed,
        with SHA256SUMS and the public key, each signature checked with only that key."""
        self.plan("Zenodo: collect the deposit in build/zenodo/", sys.executable, "tools/zenodo.py", "collect",
                  "--tag", TAG)

    def zenodo_upload(self):
        """Unless --no-zenodo, build/zenodo/ uploaded to Zenodo and published (with
        --zenodo-draft, only as a draft, published there by hand)."""
        if self.args.no_zenodo:
            return
        # (sin token se para aquí, antes de hacer nada, y no al final de la versión)
        if not self.args.dry_run:
            done = subprocess.run([sys.executable, "tools/zenodo.py", "check-token"], cwd=ROOT, check=False,
                                  capture_output=True, text=True)
            if done.returncode != 0:
                sys.exit(f"release.py: the upload to Zenodo needs a token: {done.stderr.strip()}\n"
                         "(--no-zenodo leaves it out)")
        publish = [] if self.args.zenodo_draft else ["--publish"]
        what = " as a draft (not published)" if self.args.zenodo_draft else " and publish it"
        self.plan("Zenodo: upload the deposit" + what, sys.executable, "tools/zenodo.py", "upload", *publish)

    def __call__(self):
        a = self.args
        if a.installers:
            return self.installers()
        self.forges = [a.only] if a.only else ["github", "codeberg"]
        a.rpm = not a.no_rpm  # (the signed RPM, always, unless --no-rpm)
        self.files = [WHEEL, SDIST, ZIP] + ([] if a.no_appimage else [APPIMAGE, DEB, RUN, RUBBERBAND_SOURCE])
        if a.rpm:
            self.files += [rpm()]
        self.files += [PUBLIC_KEY]
        self.check()
        repos = self.repos()
        self.tests()
        self.build()
        self.sign()
        self.tag()
        self.zenodo_collect()
        for forge in self.forges:
            getattr(self, forge)(repos[forge])
        if a.rpm and not a.no_copr:
            self.copr()
        if not a.no_appimage and not a.no_apt:
            self.apt()
        if a.pypi:
            self.pypi()
        self.zenodo_upload()
        self.clean_up()
        self.run_plan()

    def clean_up(self):
        """Once all is published: dist/ keeps the RPM (copied by build-rpm.sh), the source package and the ZIP, the
        newest of each; the rest of build/release/ is deleted, as it is on the forges and on Zenodo."""
        self.plan("Keep the source package and the ZIP in dist/, in place of older ones", sys.executable,
                  "tools/release.py", "--keep-in-dist")
        # (el código de Rubber Band se queda en build/libs/, donde tools/build-libs.py lo busca; su firma, no)
        self.plan("Delete what was published from build/ (only the RPM stays there)", "rm", "-rf", OUT, "build/zenodo",
                  f"{RUBBERBAND_SOURCE}.asc")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools/release.py",
                                     description=f"Publish {TAG} on GitHub and Codeberg, with the wheel, the source "
                                                 "package, the ZIP, the AppImage, the Debian package and the RPM "
                                                 "(also on Copr), all signed.")
    notes = parser.add_mutually_exclusive_group()
    notes.add_argument("--notes", metavar="TEXT", help="the notes of a new release")
    notes.add_argument("--notes-file", metavar="FILE", help="the notes of a new release, from FILE")
    parser.add_argument("--rpm", action="store_true",
                        help="(the signed RPM, and a Copr build of it, are made always now: kept for older scripts)")
    parser.add_argument("--no-rpm", action="store_true", help="without the RPM (nor its Copr build)")
    parser.add_argument("--no-copr", action="store_true", help="don't send the RPM to Copr")
    parser.add_argument("--no-apt", action="store_true",
                        help="don't add the Debian package to the APT repository (github.com/nivaca/apt)")
    parser.add_argument("--pypi", action="store_true",
                        help="also upload the wheel and the source package to PyPI ($UV_PUBLISH_TOKEN)")
    parser.add_argument("--no-build", action="store_true",
                        help="use the files in build/release/ (and build/rpm/) as they are")
    parser.add_argument("--no-appimage", action="store_true", help="without the AppImage (nor the Debian package)")
    parser.add_argument("--no-tests", action="store_true", help="don't run the tests first")
    parser.add_argument("--redo", action="store_true",
                        help=f"move {TAG} to HEAD if it is on another commit (here and on the remotes), and "
                             "replace the files of the releases")
    parser.add_argument("--only", choices=("github", "codeberg"), help="publish on one forge only")
    parser.add_argument("--installers", action="store_true",
                        help="only sign the installers for Windows and macOS (made on GitHub by installers.yml) "
                             "and copy them, with their signatures, to the release on Codeberg")
    parser.add_argument("--tea-login", default="codeberg", help="the login of tea for Codeberg (default: codeberg)")
    parser.add_argument("--no-zenodo", action="store_true",
                        help="don't upload build/zenodo/ to Zenodo (by default it is uploaded and "
                             "published, with the token in $ZENODO_TOKEN or the keyring)")
    parser.add_argument("--zenodo-draft", action="store_true",
                        help="upload it to Zenodo as a draft, not published")
    parser.add_argument("--zenodo", action="store_true",
                        help="(the upload to Zenodo is made always now, unless --no-zenodo: kept "
                             "for older scripts)")
    parser.add_argument("--keep-in-dist", action="store_true",
                        help="only copy the source package and the ZIP of build/release/ to dist/, in place of "
                             "older ones (the release does it at the end)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only show the commands")
    parser.add_argument("-y", "--yes", action="store_true", help="don't ask before running them")
    args = parser.parse_args(argv)
    if args.notes_file:
        args.notes_file = str(Path(args.notes_file).resolve())
    if args.keep_in_dist:
        sys.exit(keep_in_dist())
    Release(args)()


def keep_in_dist(root: Path = ROOT) -> int:
    """Copies the source package and the ZIP of build/release/ to dist/, deleting their older versions there. Copias,
    no movimientos: la publicación los borra de build/release/ después, con todo lo demás."""
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    for made, pattern in KEPT:
        source = root / made
        if not source.is_file():
            print(f"release.py: there is no {made}", file=sys.stderr)
            return 1
        for old in dist.glob(pattern):
            if old.name != source.name:
                old.unlink()
        shutil.copy2(source, dist / source.name)
        print(f"Kept {source.name} in dist/")
    return 0


if __name__ == "__main__":
    main()

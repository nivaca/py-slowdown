#!/usr/bin/env python3
"""Publish a release of py-slowdown on GitHub (with gh) and Codeberg (with
tea): the tag vVERSION (the version of pyproject.toml), signed, with the wheel, the
source package, a ZIP of the source, the AppImage, the Debian package and the signed RPM attached (the RPM
also published on Copr), and the source of the Rubber Band Library built into the AppImage and the Debian
package (the GPL asks for it), each with its signature (FILE.asc), with SHA256SUMS and its signature, and with
the public key that checks them all; and (--pypi) the wheel and the source package on PyPI.

Everything is signed with the project's key (SIGNING_KEY of packaging/build-rpm.sh), and every signature is
checked, against the public key published, before anything is published.

    uv run python tools/release.py [--notes TEXT | --notes-file FILE] [--no-rpm | --no-copr] [--pypi]
                                   [--no-build] [--no-appimage] [--no-tests] [--redo]
                                   [--only github|codeberg] [--dry-run] [--yes]
    uv run python tools/release.py --installers [--dry-run] [--yes]

The installers for Windows and macOS are made by GitHub, on its own machines, when the tag arrives
(.github/workflows/installers.yml), and added to the release once this has published it; then --installers
downloads them, signs them here (FILE.asc, SHA256SUMS-installers and its signature), and attaches the
signatures to the release on GitHub and the installers and their signatures to the one on Codeberg.

In order, each step only if it is needed:

1. checks that the repository is on main, with nothing left to commit, that
   the versions agree (pyproject.toml, __init__.py and, unless --no-rpm, the
   spec), that the tools are installed (gh, tea, gpg; unless --no-rpm,
   rpmbuild and copr-cli) and that the signing key is in gpg;
2. runs the tests (unless --no-tests);
3. makes the wheel and the source package (uv build), the ZIP of the
   source (git archive of HEAD), the libraries of the AppImage
   (tools/build-libs.py), the AppImage (tools/bundle-appimage.py),
   and the Debian package and the installer for Linux (.run) made from it
   (tools/bundle-deb.py, tools/bundle-run.py)
   in dist/, unless --no-build (then those in
   dist/ are used); unless --no-rpm, also the signed RPM in build/rpm/
   (packaging/build-rpm.sh --sign, which checks its signature; gpg asks for
   the passphrase); then signs every file (tools/sign_release.py: FILE.asc,
   dist/SHA256SUMS and its .asc), and checks each signature with only the
   public key that is published (packaging/RPM-GPG-KEY-py-slowdown);
4. tags HEAD as vVERSION, a tag signed with the same key (git tag --sign),
   and checks it (git tag -v). If the tag is already on another commit, it
   stops, unless --redo moves it;
5. pushes main and the tag to each remote (origin is GitHub, codeberg is
   Codeberg; --redo pushes the tag with --force);
6. on each forge, makes the release of the tag, or keeps the one there is,
   and attaches the files to it, replacing those of the same name;
7. unless --no-rpm or --no-copr, sends the signed source RPM to Copr (copr-cli build, project
   nivaca/py-slowdown), unless --no-copr. Copr builds it for each Fedora of
   the project and signs it with its own key. Each build needs a higher
   version-release than the last, so the spec must have been bumped
   (rpmdev-bumpspec; see packaging/RELEASING.md);
8. unless --no-apt (or --no-appimage, which makes no Debian package), adds the
   Debian package to the APT repository of these programs, github.com/nivaca/apt,
   with its tool (../apt/tools/apt_repo.py: the index signed and checked);
9. with --pypi, uploads the wheel and the source package to PyPI (uv publish,
   with the API token in $UV_PUBLISH_TOKEN). PyPI never takes a file twice:
   with --redo, those already there are skipped, not replaced.

Before doing anything, it shows the commands it will run and asks; --yes
doesn't ask, --dry-run only shows them. The notes of a new release are
--notes, --notes-file, or else made by GitHub from the commits (on Codeberg,
none); a release that is there keeps its notes.

The deposit for Zenodo is collected in dist/zenodo/ after the tag (tools/zenodo.py collect: the tree of the
tag, signed, with SHA256SUMS and the public key), and at the end uploaded to Zenodo as a draft (the token
in $ZENODO_TOKEN), unless --no-zenodo. The draft is never published here: review it and publish it on
Zenodo by hand.
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
WHEEL = f"dist/py_slowdown-{VERSION}-py3-none-any.whl"
SDIST = f"dist/py_slowdown-{VERSION}.tar.gz"
ZIP = f"dist/py-slowdown-{VERSION}.zip"
APPIMAGE = f"dist/py-slowdown-{VERSION}-x86_64.AppImage"
DEB = f"dist/py-slowdown_{VERSION}-1_amd64.deb"  # (hecho de la AppImage, va con ella)
# La herramienta del repositorio APT de estos programas: el proyecto apt, junto a este (github.com/nivaca/apt)
APT_TOOL = Path(__file__).resolve().parent.parent.parent / "apt" / "tools" / "apt_repo.py"
# The source of the Rubber Band compiled into the AppImage and the .deb (tools/build-libs.py): it is published
# with them, as the GPL asks of whoever distributes a program built from it.
RUBBERBAND_SOURCE = "build/libs/rubberband-4.0.0.tar.bz2"
RUN = f"dist/py-slowdown-{VERSION}-linux-x86_64.run"  # (el instalador para Linux, hecho de la AppImage)
# Windows y macOS los hace GitHub (.github/workflows/installers.yml), y --installers los baja aquí
CI_INSTALLERS = [f"build/installers/{name}" for name in (
    f"py-slowdown-{VERSION}-windows-x64-setup.exe",
    f"py-slowdown-{VERSION}-macos-arm64.dmg",
    f"py-slowdown-{VERSION}-macos-x86_64.dmg",
)]
CI_SUMS = "build/installers/SHA256SUMS-installers"
SPEC = "packaging/py-slowdown.spec"
PUBLIC_KEY = "packaging/RPM-GPG-KEY-py-slowdown"  # (the public key published with every release)
SUMS = "dist/SHA256SUMS"
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
            # (a la vez, cada archivo en su proceso: tools/test.py; el %check del RPM las corre una tras otra)
            self.plan("Run the tests", "uv", "run", "python", "tools/test.py")

    def build(self):
        if self.args.no_build:
            for f in self.files:
                if not (ROOT / f).is_file():
                    sys.exit(f"release.py: there is no {f} (leave out --no-build to make it)")
            return
        self.plan("Make the wheel and the source package", "uv", "build", "--out-dir", "dist")
        self.plan("Make the ZIP of the source", "git", "archive", "--format=zip", f"--prefix=py-slowdown-{VERSION}/",
                  "--output", ZIP, "HEAD")
        if APPIMAGE in self.files:
            self.plan("Compile Rubber Band and PortAudio for the AppImage", "uv", "run", "python",
                      "tools/build-libs.py")
            self.plan("Make the AppImage", "uv", "run", "python", "tools/bundle-appimage.py")
            self.plan("Make the Debian package", "uv", "run", "python", "tools/bundle-deb.py")
            self.plan("Make the installer for Linux", "uv", "run", "python", "tools/bundle-run.py")
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
        self.run_plan()

    def apt(self):
        """The Debian package added to the APT repository of these programs (github.com/nivaca/apt), by its own
        tool, which keeps only the newest version, signs the index and checks it before uploading."""
        if not APT_TOOL.is_file():
            sys.exit(f"release.py: {APT_TOOL} is not there (clone github.com/nivaca/apt beside this project, "
                     "or use --no-apt)")
        self.plan("APT: add the Debian package to github.com/nivaca/apt", sys.executable, str(APT_TOOL), "add", DEB)

    def zenodo_collect(self):
        """The deposit of the release for Zenodo, in dist/zenodo/ (tools/zenodo.py): the tree of the tag, signed,
        with SHA256SUMS and the public key, each signature checked with only that key."""
        self.plan("Zenodo: collect the deposit in dist/zenodo/", sys.executable, "tools/zenodo.py", "collect",
                  "--tag", TAG)

    def zenodo_upload(self):
        """Unless --no-zenodo, dist/zenodo/ uploaded to Zenodo as a draft, never published: it is reviewed and
        published there by hand."""
        if self.args.no_zenodo:
            return
        # (sin token se para aquí, antes de hacer nada, y no al final de la versión)
        if not os.environ.get("ZENODO_TOKEN") and not self.args.dry_run:
            sys.exit("release.py: the upload to Zenodo needs a token in $ZENODO_TOKEN (see tools/zenodo.py); "
                     "--no-zenodo leaves it out")
        self.plan("Zenodo: upload the deposit as a draft (not published)", sys.executable, "tools/zenodo.py",
                  "upload")

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
        self.run_plan()


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
    parser.add_argument("--no-build", action="store_true", help="use the files in dist/ (and build/rpm/) as they are")
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
                        help="don't upload dist/zenodo/ to Zenodo (by default it goes as a draft, "
                             "never published, with the token in $ZENODO_TOKEN)")
    parser.add_argument("--zenodo", action="store_true",
                        help="(the upload to Zenodo is made always now, unless --no-zenodo: kept "
                             "for older scripts)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only show the commands")
    parser.add_argument("-y", "--yes", action="store_true", help="don't ask before running them")
    args = parser.parse_args(argv)
    if args.notes_file:
        args.notes_file = str(Path(args.notes_file).resolve())
    Release(args)()


if __name__ == "__main__":
    main()

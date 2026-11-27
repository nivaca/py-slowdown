# Releasing py-slowdown

1. Set the new version in `pyproject.toml` and `src/py_slowdown/__init__.py`,
   add it to the releases of
   `packaging/io.github.nivaca.py-slowdown.metainfo.xml`, remake the manual
   pages (`uv run python tools/manpage.py`), then bump the spec, with a
   changelog entry:

   ```bash
   rpmdev-bumpspec -n 0.2.0 -c "What changed" \
       -u "Nicolas Vaughan <nicolasvaughan@proton.me>" packaging/py-slowdown.spec
   ```

   `tests/test_packaging.py` fails while the versions differ.

2. Commit, then publish:

   ```bash
   uv run python tools/release.py --notes-file NOTES.md
   ```

   This runs the tests; makes the wheel, the source package, the ZIP of the
   source, the AppImage, the Debian package and the signed RPM (always;
   `--no-rpm` leaves it out); signs every file (`FILE.asc`), with
   `SHA256SUMS` and its signature, and checks each signature with only the
   public key that is published (`tools/sign_release.py`); tags `vVERSION`,
   a signed tag, and checks it (`git tag -v`); pushes to GitHub (`origin`)
   and Codeberg (`codeberg`); and attaches the files to the release on both;
   then it sends the signed source RPM to Copr (project nivaca/py-slowdown).
   `--dry-run` only shows the commands. It also makes the installer for
   Linux (`.run`, from the AppImage).

3. The tag starts `.github/workflows/installers.yml` on GitHub, which makes
   the installers for Windows (Inno Setup) and macOS (a `.dmg` for Apple
   Silicon and one for Intel), each on its own system, installs each one,
   tries it, removes it, and adds them to the release. When it has
   finished (half an hour or so), sign them and copy them to Codeberg:

   ```bash
   uv run python tools/release.py --installers
   ```

   This downloads them, signs them here (`FILE.asc`, and
   `SHA256SUMS-installers` with its signature), checks each signature with
   the published key, and attaches the signatures to GitHub's release and
   the installers with their signatures to Codeberg's.

   With SignPath set up (below), the Windows job waits for its signing
   request to be approved: approve it on SignPath (signing requests of the
   project py-slowdown) once the tag is pushed; it waits up to four hours.

## Signing the Windows installer with SignPath

The installer for Windows is signed with Authenticode by SignPath, for free,
with SignPath Foundation's certificate; `CODE_SIGNING_POLICY.md` is the
policy that SignPath asks for, and the README links to it. To set it up,
once:

1. Apply at https://signpath.org/apply, with the repository and that policy.
2. When accepted, in SignPath: add the trusted build system "GitHub.com" to
   the organization and link it to the project, install the SignPath GitHub
   App (https://github.com/apps/signpath) on the repository, and paste
   `packaging/signpath/artifact-configuration.xml` as the project's
   artifact configuration. Turn on multi-factor authentication there (and on
   GitHub, where it is already on).
3. In the repository's settings on GitHub (Secrets and variables > Actions):
   the secret `SIGNPATH_API_TOKEN` (a SignPath user that may submit), and
   the variables `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG` and
   `SIGNPATH_SIGNING_POLICY_SLUG`.

From then on `installers.yml` sends each Windows installer to SignPath,
waits for the approval, checks the signature (`Get-AuthenticodeSignature`)
and installs the signed one to try it. Without those variables the steps
are skipped. The release notes say, with the files: "Code signing policy:
see CODE_SIGNING_POLICY.md", as SignPath asks for on the download pages.
`tools/release.py --installers` then adds the GPG signatures, as before.

## What the RPM build needs

```bash
sudo dnf install rpm-build rpm-sign rpmdevtools python3-devel pyproject-rpm-macros \
    python3-uv-build python3-pyside6 python3-numpy python3-sounddevice python3-pytest \
    rubberband-libs ffmpeg-free desktop-file-utils /usr/bin/appstreamcli
```

`rpmbuild` checks the build dependencies of the spec, and `%check` runs the
whole test suite on the installed package, so they must be installed here.
It runs it as `tools/test.py` does, each test file in a process of its own,
as many at once as the build may use (`RPM_BUILD_NCPUS` lowers it): the
whole RPM is built in under a minute.
(Where RPM Fusion's `ffmpeg` is installed, it provides `/usr/bin/ffmpeg`
instead of `ffmpeg-free`.)

## The installers for Windows and macOS

`tools/bundle-installer.py` makes them, on their own systems (that is,
on GitHub): a Python 3.14 of python-build-standalone, pinned with its
SHA-256, with py-slowdown and its wheels installed into it, Qt trimmed as
in the AppImage, and the Rubber Band of `tools/build-libs.py` (for
Windows compiled with zig, from any system; for macOS with Apple's clang,
on macOS). `--stage-only` lays out the folder of an installer on any
system, to look at it. They are not signed by Microsoft or Apple (that
needs paid certificates), so SmartScreen and Gatekeeper warn the first
time; the manuals say what to do.

## The libraries in the AppImage and the Debian package

The RPM uses Fedora's Rubber Band (`rubberband-libs`) and PortAudio. The
AppImage and the Debian package, which must run on older systems (glibc 2.34
and later), carry their own, compiled by `tools/build-libs.py` from the
sources it pins (Rubber Band 4.0.0 and PortAudio 19.7.0, checked by their
SHA-256), with zig's C and C++ compiler (from PyPI, run by `uvx`) for glibc
2.28. PortAudio is built with only ALSA, loaded when it runs, so it needs
ALSA's headers to build (`sudo dnf install alsa-lib-devel`). Rubber Band is
under the GPL, so its source (`rubberband-4.0.0.tar.bz2`) is published with
every release, next to the files built with it.

## The signing key

The RPMs are signed with the same key as the author's other projects,
`81870643CA221AF90C30554EBE6832CD35994948` (Nicolas Vaughan, RPM signing).
`packaging/build-rpm.sh` pins it, and `--sign` stops if it is not in this
machine's gpg keyring. A copy of the public key is
`packaging/RPM-GPG-KEY-py-slowdown`, published with every release.

The same key signs everything a release publishes: the RPM (inside it), each
file (a detached signature, `FILE.asc`), `SHA256SUMS`, and the tag. A
release stops before publishing anything if one signature doesn't verify
with the published key. gpg must have the key's passphrase cached when the
release runs in the background (sign anything once first, e.g. `echo test |
gpg --clearsign -u 81870643CA221AF90C30554EBE6832CD35994948 > /dev/null`).

For GitHub to show the tags as "Verified", the public key must be added to
the GitHub account (Settings > SSH and GPG keys), and its e-mail address be
one of the account's verified addresses.

## Copr

The project is https://copr.fedorainfracloud.org/coprs/nivaca/py-slowdown/
(to be made: `copr-cli create py-slowdown --chroot fedora-45-x86_64
--chroot fedora-rawhide-x86_64`). Each Copr build needs a higher
version-release than the last, so bump the spec first. `copr-cli` needs an
API token in `~/.config/copr` (it expires after 180 days).

## Zenodo

Each release leaves in `dist/zenodo/` what goes to Zenodo: the tree of the
tag as `py-slowdown-VERSION-source.tar.gz`, made with `git archive`, its signature,
a `SHA256SUMS` of only that file with its signature, and the public key.
`tools/release.py` makes it after the tag (`tools/zenodo.py collect`),
and checks every signature there with only the public key.
`tools/zenodo.py collect --packages` also puts the files published with the
release in it, with their signatures.

At the end of each release, `tools/release.py` sends it to Zenodo and
publishes it (unless `--no-zenodo`; with `--zenodo-draft` it stays a draft;
`tools/zenodo.py upload [--publish]` does the same on its own),
with the metadata of `.zenodo.json`, the version, the date of the tag,
links to the tag on Codeberg and GitHub, and the whole `README.md` of the tag
as the description, in HTML (headings become bold paragraphs and images are
left out, since Zenodo doesn't take them). What Zenodo's deposit API doesn't
take is then set on the draft through its records API: the languages
(`languages` in `.zenodo.json`), the copyright (the year of the tag and the
first creator), the repository on GitHub, the programming language and the
development status (`programming_language`, `development_status`). If Zenodo already has a published
deposit with the same title, the draft is a new version of it, under the
same concept DOI. It is published at the end, with a new DOI, once
all of that is set; a draft left on Zenodo (with `--zenodo-draft`, or
by a failure) is published with `tools/zenodo.py publish`. The token (made at
https://zenodo.org/account/settings/applications/, with deposit:write and
deposit:actions) is kept once in the desktop keyring:

    secret-tool store --label="Zenodo token" service zenodo

`$ZENODO_TOKEN`, if it is set, goes before the keyring.
`tools/zenodo.py check-token` says whether there is one, without showing it.
To try the whole thing first, use `tools/zenodo.py upload --sandbox`, with a
token of sandbox.zenodo.org in the keyring as `service zenodo-sandbox` (or in
`$ZENODO_SANDBOX_TOKEN`); `--dry-run` only shows what would be sent.

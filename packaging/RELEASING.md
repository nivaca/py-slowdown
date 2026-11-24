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
   `--dry-run` only shows the commands.

## What the RPM build needs

```bash
sudo dnf install rpm-build rpm-sign rpmdevtools python3-devel pyproject-rpm-macros \
    python3-uv-build python3-pyside6 python3-numpy python3-sounddevice python3-pytest \
    rubberband-libs ffmpeg-free desktop-file-utils /usr/bin/appstreamcli
```

`rpmbuild` checks the build dependencies of the spec, and `%check` runs the
whole test suite on the installed package, so they must be installed here.
(Where RPM Fusion's `ffmpeg` is installed, it provides `/usr/bin/ffmpeg`
instead of `ffmpeg-free`.)

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

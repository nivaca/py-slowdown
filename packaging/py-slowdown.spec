# py-slowdown, which plays audio slower or faster without changing its pitch.
# Copyright (C) 2026 Nicolas Vaughan <nicolasvaughan@proton.me>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed WITHOUT ANY
# WARRANTY; see the LICENSE file, or <https://www.gnu.org/licenses/>.
#
# Build with packaging/build-rpm.sh, which makes the source tarball.

Name:           py-slowdown
Version:        1.2.0
Release:        1%{?dist}
Summary:        Play audio slower or faster without changing its pitch

License:        GPL-3.0-or-later
URL:            https://github.com/nivaca/py-slowdown
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
BuildRequires:  /usr/bin/appstreamcli
# For %%check: the tests run the window (headless), stretch with Rubber Band,
# and make and read audio files with ffmpeg (Fedora has no PyAV).
BuildRequires:  python3-pytest
BuildRequires:  python3-pyside6
BuildRequires:  rubberband-libs >= 3
BuildRequires:  /usr/bin/ffmpeg
BuildRequires:  /usr/bin/ffprobe

# numpy and sounddevice come from the package's metadata (pyproject.toml).
# The window: Fedora's PySide6 (pyproject.toml names the PyPI wheel, pyside6-essentials).
Requires:       python3-pyside6
# The stretching (loaded with ctypes, so rpm cannot find this dependency itself)
Requires:       rubberband-libs >= 3
# The files are read by the ffmpeg program where PyAV is not installed, as here
# (ffmpeg-free, or the ffmpeg of RPM Fusion).
Requires:       /usr/bin/ffmpeg
Requires:       /usr/bin/ffprobe
Requires:       hicolor-icon-theme

%description
py-slowdown plays a recording slower or faster without changing its pitch,
for practising music and learning it by ear; it is made for music, not for
transcribing speech. The speed goes from 0.25x to 3x, changed while it plays, with the R3
engine of the Rubber Band Library; at 1x the file is played as it is. The
file is shown as a waveform, with the usual controls, and bookmarks with
labels keep the places to come back to, for each file, with the point where
it was left.

The window is in English or Spanish.

%prep
%autosetup -n %{name}-%{version}
# (Fedora's PySide6 is python3-pyside6, which doesn't provide pyside6-essentials;
# and Fedora has no PyAV: the ffmpeg program reads the files instead)
sed -i -e '/"pyside6-essentials/d' -e '/"av>=/d' pyproject.toml

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l py_slowdown
desktop-file-install --dir=%{buildroot}%{_datadir}/applications packaging/py-slowdown.desktop
install -d %{buildroot}%{_datadir}/icons
cp -pr src/py_slowdown/icons/linux/hicolor %{buildroot}%{_datadir}/icons/
install -Dpm 0644 packaging/py-slowdown-mime.xml %{buildroot}%{_datadir}/mime/packages/py-slowdown.xml
install -Dpm 0644 packaging/io.github.nivaca.py-slowdown.metainfo.xml \
    %{buildroot}%{_metainfodir}/io.github.nivaca.py-slowdown.metainfo.xml
install -Dpm 0644 packaging/man/py-slowdown.1 %{buildroot}%{_mandir}/man1/py-slowdown.1
install -Dpm 0644 packaging/man/es/py-slowdown.1 %{buildroot}%{_mandir}/es/man1/py-slowdown.1

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/py-slowdown.desktop
appstreamcli validate --no-net %{buildroot}%{_metainfodir}/io.github.nivaca.py-slowdown.metainfo.xml
export QT_QPA_PLATFORM=offscreen
%pyproject_check_import
# The whole test suite, on the installed package, with no settings of the
# builder's and the window drawn offscreen.
export HOME="$PWD/check-home"
%pytest -q tests
%{py3_test_envvars} %{buildroot}%{_bindir}/py-slowdown --version | grep -q '%{version}'

%files -f %{pyproject_files}
%doc README.md README_es.md docs/DESCRIPTION.md docs/DESCRIPCIÓN_es.md
%{_bindir}/py-slowdown
%{_datadir}/applications/py-slowdown.desktop
%{_datadir}/icons/hicolor/*/apps/py-slowdown.*
%{_datadir}/mime/packages/py-slowdown.xml
%{_metainfodir}/io.github.nivaca.py-slowdown.metainfo.xml
%{_mandir}/man1/py-slowdown.1*
%lang(es) %{_mandir}/es/man1/py-slowdown.1*

%changelog
* Tue Nov 24 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.2.0-1
- The settings of each recording in an XML file of its name, beside it or in a
  folder chosen; speeds chosen beforehand in a button Speeds; a choice of
  playback quality (R3, R3 lighter, R2); Hear and Count-in with menus of their
  own, without their buttons; Formants only with the pitch moved; buttons that
  are on clearly on; no two entries of a menu with the same letter

* Tue Nov 24 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.1.0-1
- Export the audio as it sounds (WAV, FLAC, MP3, Opus); hear one part of the mix
  (a channel, the mix without its centre, only the bass, or all but the bass);
  keep the formants; loops, selections kept with a name; each file as it was
  played; keyboard shortcuts of one's own; the whole waveform at once the second
  time; long files read in four parts at once, files read faster and kept in
  half the space; the waveform fills the window when a file is opened

* Tue Nov 24 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 1.0.0-1
- Version 1.0.0, the first stable version: the pitch in semitones; tap the
  tempo; the count-in's offset, also set on the waveform, and heard on
  Bluetooth earphones; the count-in's settings easy to reach; reopen the last
  file when starting; the controls in two rows

* Tue Nov 24 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.2.0-1
- Version 0.2.0: a selection repeated without a gap; a count-in before
  playing; installers for Windows (Inno Setup) and macOS (a .dmg, Apple
  Silicon and Intel), and a .run for any Linux; files opened from the Finder;
  the bookmarks and the cache in the folders of each system

* Tue Nov 24 2026 Nicolas Vaughan <nicolasvaughan@proton.me> - 0.1.0-1
- First package: the speed from 0.25x to 3x with Rubber Band's R3 engine,
  a waveform, the usual controls, bookmarks kept for each file, in English
  and Spanish

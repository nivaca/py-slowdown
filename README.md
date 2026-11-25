py-slowdown
===========

py-slowdown plays audio slower or faster without changing its pitch. It is
made for music: for practising a piece and learning it by ear, hearing a
passage again and again at a speed one can follow. The file is shown as a
waveform, the usual player controls move through it, and bookmarks keep the
places one wants to come back to.

It is an app for music, not for transcribing speech (lectures, interviews,
dictations): what it does besides playing, such as the count-in, the tempo
or the pitch in semitones, is meant for musicians.

*Leer en español: [README_es.md](README_es.md).*

![py-slowdown, a recording at 0.75× with two bookmarks](docs/img/main_en.png)

What it does
------------

- Opens audio files and the sound of video files: MP3, M4A/AAC, MP4,
  FLAC, WAV, AIFF, Ogg, Opus, WMA and whatever else FFmpeg reads. Files
  with more than two channels are mixed down to stereo.
- Shows the audio as a waveform, with a time ruler. A click moves the
  position there; Ctrl+wheel zooms around the pointer, the wheel scrolls.
  A long file can be played while it is still being read.
- Play, pause, stop, go to the start or to the end, back and forward (by a
  skip length chosen in Settings, 1 to 60 seconds; hold the button to keep
  going), and one second back or forward. A pause takes the position back
  to where playing started, so that Space plays the same passage again;
  Shift+Space continues from the pause instead.
- Speed from 0.25× to 3×, changed while it plays, with the pitch kept. The
  stretching is done by the [Rubber Band Library](https://breakfastquay.com/rubberband/),
  with its R3 ("finer") engine, its highest quality, called through a small
  binding of py-slowdown's own. At 1× the file is
  played as it is, sample for sample, without going through Rubber Band.
  The button Speeds has a list of speeds of one's own (50%, 75%, 100%,
  125%…). A lighter quality (half the processor) or the older R2 engine (crisp
  attacks) can be chosen (Settings > Playback quality).
- Bookmarks at the playing position (B), or anywhere with a right click on
  the waveform; each can have a label. They are listed in a side panel,
  drawn on the waveform, and can be exported as a text file. Ctrl+← and
  Ctrl+→ go to the previous and next bookmark.
- Moves the pitch up or down, in semitones (from −12 to +12) and cents
  (hundredths of a semitone, from −50 to +50, to tune a recording to an
  instrument), each with a knob, without changing the speed, also
  while it plays; with Playback > Keep the formants, a voice or an instrument keeps its timbre.
- Hears one part of the mix (Hear): one channel, the two in one, the mix
  without its centre (where the voice and the solo usually are), only the
  bass, or everything but the bass.
- Repeats a selection without end and without a gap (Shift+drag on the
  waveform, or I and O, then L): the end of the passage runs into its
  start through a short fade, at any speed. Selections can be kept as
  loops with a name (Shift+L), to repeat them again with a double click.
- Counts in before playing, as a metronome (C): the number of clicks and
  the tempo are chosen, and the tempo can follow the speed; the tempo can
  be measured by tapping with the beat (T). With the recording's first
  beat marked (Count-in > The first beat is here, Shift+C), a bookmark of
  its own that is kept with the others, the recording comes in on the
  nearest beat wherever playing starts.
- Exports the recording, or the selection, as it sounds (at the speed and
  pitch chosen, and as it is heard, if asked): WAV, FLAC, MP3 or Opus
  (File > Export the audio, Ctrl+E).
- Remembers, for each file, its bookmarks, its loops, the point where it
  was left and how it was played (speed, pitch, way of hearing, selection,
  count-in), and goes on from there the next time, with its whole waveform
  at once. All that is also written in a file with the recording's name and
  the extension `.slx` (`song.slx` for `song.mp3`), beside it or in a
  folder chosen, so that it travels with the recording; opening the `.slx`
  opens the recording. File > Save the .slx (Ctrl+S) writes it at once. It can also reopen the last file when it starts
  (Settings > Reopen the last file when starting).
- The keyboard shortcuts can be changed (Settings > Keyboard shortcuts),
  also for a foot pedal that sends keys.
- Interface in English and in Spanish (Settings > Language).

Keyboard
--------

| Action                         | Keys                             |
|--------------------------------|----------------------------------|
| Play / pause (and go back)     | Space                            |
| Continue from the pause        | Shift+Space                      |
| Stop and go back to the start  | S                                |
| Go to the start / end          | Home / End                       |
| Back / forward (skip length)   | ← / →                            |
| One second back / forward      | Shift+← / Shift+→                |
| Slower / faster (0.05×)        | ↓ / ↑, or − / +                  |
| Normal speed                   | N                                |
| Add a bookmark                 | B                                |
| Previous / next bookmark       | Ctrl+← / Ctrl+→, PgUp / PgDn     |
| Zoom in / out / whole file     | Ctrl++ / Ctrl+− / Ctrl+0         |
| A semitone higher / lower      | Ctrl+↑ / Ctrl+↓                  |
| Original pitch                 | Shift+N                          |
| Repeat the selection           | L                                |
| Select                         | Shift+drag, or I and O           |
| Clear the selection            | Esc                              |
| Save the selection as a loop   | Shift+L                          |
| Count in before playing        | C                                |
| Tap the tempo (with the beat)  | T                                |
| The first beat is here         | Shift+C                          |
| Open a file                    | Ctrl+O                           |
| Save the .slx                  | Ctrl+S                           |
| Export the audio               | Ctrl+E                           |

These are the keys of always; Settings > Keyboard shortcuts changes them.

Installing
----------

Each release, on [GitHub](https://github.com/nivaca/py-slowdown/releases)
and [Codeberg](https://codeberg.org/nivaca/py-slowdown/releases), has
installers that carry all the program needs (their own Python, Qt, FFmpeg
and Rubber Band), so nothing else has to be installed:

- **Windows** 10 or later: `py-slowdown-VERSION-windows-x64-setup.exe`. It
  installs for you alone, without administrator's rights (or for everyone,
  if you choose so), with a Start-menu entry and "Open with" for audio
  files; it opens the `.slx` files too. The installer is not signed by Microsoft: if SmartScreen stops it,
  choose *More info > Run anyway*.
- **macOS** 13 or later: `py-slowdown-VERSION-macos-arm64.dmg` (Apple
  Silicon) or `-macos-x86_64.dmg` (Intel). Drag py-slowdown to
  Applications. It is not notarized by Apple: the first time, choose *Open
  Anyway* in System Settings > Privacy & Security.
- **Linux**: an RPM for Fedora (also in Copr: `sudo dnf copr enable
  nivaca/py-slowdown` and `sudo dnf install py-slowdown`), which uses
  Fedora's Rubber Band, PortAudio and ffmpeg; a Debian package for Debian
  12, Ubuntu 22.04 and later (also in the APT repository of my programs,
  [github.com/nivaca/apt](https://github.com/nivaca/apt), so that `apt
  upgrade` brings each new version); and, for any Linux with glibc 2.34 or later,
  an installer (`sh py-slowdown-VERSION-linux-x86_64.run`, for you alone,
  or with sudo for everyone, with a menu entry and an uninstaller) and an
  AppImage, which needs no installing.
- The wheel and the source, for installing with pip.

Every file is signed with the key in `packaging/RPM-GPG-KEY-py-slowdown`
(`FILE.asc`, and `SHA256SUMS` with its signature; those of the installers
for Windows and macOS, which GitHub makes, in `SHA256SUMS-installers`):
`gpg --import RPM-GPG-KEY-py-slowdown`, then `gpg --verify FILE.asc FILE`.

From the source, with Python 3.14 or later, `install/install.sh` installs it
for one user on Linux or macOS, in an environment of its own, with a menu
entry (`--uninstall` removes it). It needs the Rubber Band Library (version
3 or later) and, on Linux, PortAudio from the system: `sudo dnf install
rubberband-libs portaudio` on Fedora, `sudo apt install librubberband3
libportaudio2` on Debian and Ubuntu (`librubberband2` on older releases), `brew install rubberband` on macOS.

To run it from the source, with [uv](https://docs.astral.sh/uv/):

    uv run py-slowdown [FILE]

The tests: `uv run python tools/test.py` (each file in a process of its
own, at once), or `uv run pytest`. How a release is made is told in
[packaging/RELEASING.md](packaging/RELEASING.md).

Documentation
-------------

- The user manual: [docs/MANUAL_en.pdf](docs/MANUAL_en.pdf) (in Spanish,
  [docs/MANUAL_es.pdf](docs/MANUAL_es.pdf)); `man py-slowdown` once the
  RPM or the Debian package is installed.
- How it was made: [docs/DESCRIPTION.md](docs/DESCRIPTION.md).
- The open-source software it uses, with its licences:
  [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md).
- The changes of each version: [CHANGELOG.md](CHANGELOG.md).

Where things are kept
---------------------

- How each recording was played, with its bookmarks and loops, in a file
  of its name (`song.slx`, in XML), beside it, or in the folder chosen in
  Settings > Settings files of each recording (or not at all). Those of
  version 1.2.0 (`song.xml`) are still read, and replaced.
- Bookmarks, loops, positions and how each file was played:
  `bookmarks.json`, by the full path of each audio
  file, in `~/.local/share/py-slowdown/` on Linux (`$XDG_DATA_HOME`),
  `%APPDATA%\py-slowdown` on Windows and `~/Library/Application
  Support/py-slowdown/` on macOS. A file that is moved or renamed loses
  them.
- Settings (window, volume, skip length, language, recent files, keyboard
  shortcuts, way of hearing, the last export):
  `~/.config/py-slowdown/py-slowdown.conf` on Linux, the registry
  (`HKEY_CURRENT_USER\Software\py-slowdown`) on Windows, and
  `~/Library/Preferences/com.py-slowdown.py-slowdown.plist` on macOS.
- While a file is open, its decoded samples are kept in an unnamed
  temporary file in the cache folder (`~/.cache/py-slowdown/`,
  `%LOCALAPPDATA%\py-slowdown\cache`, `~/Library/Caches/py-slowdown/`),
  which disappears when the file is closed (two hours of stereo take about
  1.3 GB there, but only what is read stays in memory). While a long file
  is read in parts, each part has one more there, until it is added
  (on Windows they are named `part-…`).
- The waveforms of the last 200 files read, in the folder `peaks` of that
  cache folder (about 4 MB for an hour and a half), so that the whole
  waveform is there as soon as a file is opened again. They can be deleted
  at any time.

Uninstalling the program never removes them.

License
-------

py-slowdown is free software, under the GNU General Public License,
version 3 or later (see [LICENSE](LICENSE)). It uses the Rubber Band
Library (GPL 2 or later), PortAudio (MIT), PyAV (BSD) with FFmpeg (LGPL 2.1
or later), PySide6 (LGPL 3), sounddevice (MIT) and NumPy (BSD), all of them
compatible with that licence. The AppImage and the Debian package carry a
Rubber Band compiled from its source, which is published with each release.

Nicolas Vaughan &lt;nicolasvaughan@proton.me&gt;

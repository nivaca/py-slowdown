py-slowdown
===========

py-slowdown plays audio slower or faster without changing its pitch. It is
meant for transcribing recordings (lectures, interviews, dictations) and for
learning music by ear: the file is shown as a waveform, the usual player
controls move through it, and bookmarks keep the places one wants to come
back to.

*Leer en español: [README_es.md](README_es.md).*

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
  going), and one second back or forward.
- Speed from 0.25× to 3×, changed while it plays, with the pitch kept. The
  stretching is done by the [Rubber Band Library](https://breakfastquay.com/rubberband/),
  with its R3 ("finer") engine, its highest quality. At 1× the file is
  played as it is, sample for sample, without going through Rubber Band.
- Bookmarks at the playing position (B), or anywhere with a right click on
  the waveform; each can have a label. They are listed in a side panel,
  drawn on the waveform, and can be exported as a text file. Ctrl+← and
  Ctrl+→ go to the previous and next bookmark.
- Remembers, for each file, its bookmarks and the point where it was left,
  and goes on from there the next time.
- Interface in English and in Spanish (Settings > Language).

Keyboard
--------

| Action                         | Keys                             |
|--------------------------------|----------------------------------|
| Play / pause                   | Space                            |
| Stop and go back to the start  | S                                |
| Go to the start / end          | Home / End                       |
| Back / forward (skip length)   | ← / →                            |
| One second back / forward      | Shift+← / Shift+→                |
| Slower / faster (0.05×)        | ↓ / ↑, or − / +                  |
| Normal speed                   | N                                |
| Add a bookmark                 | B                                |
| Previous / next bookmark       | Ctrl+← / Ctrl+→, PgUp / PgDn     |
| Zoom in / out / whole file     | Ctrl++ / Ctrl+− / Ctrl+0         |
| Open a file                    | Ctrl+O                           |

Installing and running
----------------------

py-slowdown needs Python 3.14 or later. On Linux it also needs PortAudio
(`portaudio` on Fedora, `libportaudio2` on Debian and Ubuntu), which
sounddevice uses to reach the sound card; the wheels of sounddevice for
Windows and macOS include it. PyAV brings its own FFmpeg, and pylibrb its
own Rubber Band.

From the source, with [uv](https://docs.astral.sh/uv/):

    uv run py-slowdown [FILE]

The tests: `uv run python tools/test.py` (each file in a process of its
own, at once), or `uv run pytest`.

Where things are kept
---------------------

- Bookmarks and positions: `~/.local/share/py-slowdown/bookmarks.json`
  (`$XDG_DATA_HOME`), by the full path of each audio file. A file that is
  moved or renamed loses them.
- Settings (window, volume, skip length, language, recent files):
  `~/.config/py-slowdown/py-slowdown.conf`.
- While a file is open, its decoded samples are kept in an unnamed
  temporary file in `~/.cache/py-slowdown/`, which disappears when the file
  is closed (two hours of stereo take about 2.5 GB there, but only what is
  read stays in memory).

License
-------

py-slowdown is free software, under the GNU General Public License,
version 3 or later (see [LICENSE](LICENSE)). It uses Rubber Band Library
(GPL 2 or later) through pylibrb (GPL 2), PyAV (BSD) with FFmpeg (LGPL 2.1
or later), PySide6 (LGPL 3), sounddevice (MIT) with PortAudio (MIT), and
NumPy (BSD).

Nicolas Vaughan &lt;nicolasvaughan@proton.me&gt;

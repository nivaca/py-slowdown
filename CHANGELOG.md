# Changelog

All notable changes to py-slowdown. The releases, with the AppImage, the
Debian package, the RPM, the wheel and the source, are on
[Codeberg](https://codeberg.org/nivaca/py-slowdown/releases) and
[GitHub](https://github.com/nivaca/py-slowdown/releases).

## Unreleased

- **The pitch, in semitones**: from 12 down to 12 up, by steps of one or in
  tenths (to tune a recording that is off pitch to an instrument), without
  changing the speed, and while it plays, without a click (Rubber Band's
  option for pitch that changes as it plays). The box Pitch, beside the
  speed; Ctrl+↑ and Ctrl+↓; Shift+N, or the button 0, for the original
  pitch. Measured, a tone lands within a cent of the pitch asked for.
- **The count-in is heard on Bluetooth earphones**: many of them mute
  themselves while they receive silence and wake too late for a short click,
  so they swallowed the count. It now begins with a very faint hiss, 0.4 s
  before the first click, and keeps it between the clicks; the clicks are
  fuller (60 ms, a tone and its octave). The beat appears on the waveform
  with the first click.
- **The recording's offset after the count-in**: when the first beat of the
  recording is not exactly at the position, Recording offset, in the dialog
  of the count-in, brings it in earlier (negative) or later (positive), by
  up to 2 seconds of the recording, so that it comes in on the beat at any
  speed; earlier only up to the last click, which is not cut.
- **Tap the tempo**: the button Tap, beside Count-in, or the key T, pressed
  with the beat while the music plays, measures its tempo (the middle value
  of the intervals between the last eight taps; a pause of over two seconds
  begins again), which becomes the tempo of the count-in; at another speed,
  with the count-in following it, the recording's own tempo is kept. The
  dialog of the count-in has a Tap button too.
- **The settings of the count-in are easy to find**: an arrow beside the
  button Count-in opens them, and so does Settings > Count-in (besides
  Playback > Count-in settings); the button's tooltip says what they are.
- The controls are in two rows, the speed, the pitch and the volume under
  the others: in one, the window did not fit a screen 1366 pixels wide.

## 0.2.0 — 2026-11-24

- **Installers for Windows and macOS**, which carry their own Python, Qt,
  FFmpeg and Rubber Band: for Windows 10 and later, a setup made with Inno
  Setup, for the user alone (without administrator's rights) or for
  everyone, with a Start-menu entry and py-slowdown in "Open with" for audio
  files; for macOS 13 and later, a disk image with py-slowdown.app, for
  Apple Silicon and for Intel. GitHub makes them, tries them and removes
  them, on its own machines, and they are signed like the other files.
- **An installer for any Linux** (`.run`), made from the AppImage: for the
  user, or with sudo for everyone, with the command, the menu entry, the
  icons, the manual pages and an uninstaller.
- **The sound no longer breaks off while playing** (in 0.1.0, about once a
  second in a long file): each time the position moved a pixel, the
  waveform was drawn again, which took more than 100 ms and kept the sound
  from reaching the sound card. It is now drawn once, and only copied as
  the position moves; the sound card also has a larger buffer (0.1 s).
- **Repeat a selection, without a gap**: Shift+drag on the waveform, I and
  O at the position, or "Select from here to the next bookmark"; then
  Playback > Repeat the selection (L), or its button. The end of the
  selection fades into what precedes its start in a hundredth of a second,
  before the stretching, so the passage sounds as one stream at any speed.
- **Count-in before playing** (Playback > Count in before playing, C, or its
  button): 1 to 16 clicks at 20 to 300 BPM, the first one higher, then the
  recording; the tempo can follow the speed (120 BPM at 0.5× counted at
  60); the waveform shows the beat in large figures.
- **Files opened from the Finder** (Open With, or dropped on the icon in the
  Dock) are opened by the window.
- **The bookmarks and the decoded sound in the folders of each system**:
  `%APPDATA%` and `%LOCALAPPDATA%` on Windows, `~/Library` on macOS (on
  Linux, as before).
- The manuals and the READMEs tell how to install on each system, and what
  to do when Windows or macOS warn that the program is not signed by them.

## 0.1.0 — 2026-11-24

The first version.

- **Opens audio files and the sound of video files**: MP3, M4A/AAC, MP4,
  FLAC, WAV, AIFF, Ogg, Opus, WMA and whatever else FFmpeg reads, through
  PyAV, or through the ffmpeg program where PyAV is missing (as in
  Fedora). They are read in the background into a temporary file mapped in
  memory, so long recordings can be played while they are still read.
- **A waveform** with a ruler of times, the played part in another colour,
  the bookmarks, zoom around the pointer (Ctrl+wheel) and a scroll bar; a
  click or a drag moves the position.
- **The usual controls**: play, pause, stop, to the start, to the end, back
  and forward by a skip length (1 to 60 s; held down, they keep going), one
  second back or forward, and a volume.
- **The speed from 0.25× to 3×**, changed while it plays, with the pitch
  kept, by the R3 engine of the Rubber Band Library; at 1× the file is
  played as it is, sample for sample.
- **Bookmarks** with labels, on the waveform and in a side panel; previous
  and next; exported as text. They are kept for each file, with the point
  where it was left, and it goes on from there.
- **An interface in English and Spanish**, Qt's own words included.
- **Packages**: a signed RPM (also on Copr), an AppImage and a Debian
  package that carry their own Rubber Band and PortAudio, the wheel, the
  source and a ZIP, every file signed, with SHA256SUMS; an installer for
  Linux and macOS; manual pages and user manuals (PDF) in English and
  Spanish.

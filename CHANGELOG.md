# Changelog

All notable changes to py-slowdown. The releases, with the AppImage, the
Debian package, the RPM, the wheel and the source, are on
[Codeberg](https://codeberg.org/nivaca/py-slowdown/releases) and
[GitHub](https://github.com/nivaca/py-slowdown/releases).

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

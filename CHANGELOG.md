Changes
=======

0.1.0 (unreleased)
------------------

The first version.

- Opens audio files and the sound of video files (whatever FFmpeg reads,
  through PyAV), decoded in the background into a temporary file mapped in
  memory, so long recordings can be played while they are still read.
- A waveform with a time ruler, the played part in another color, zoom
  around the pointer (Ctrl+wheel) and a scroll bar.
- Play, pause, stop, to the start, to the end, back and forward by a skip
  length (1 to 60 s; held down, they keep going), one second back or forward.
- Speed from 0.25× to 3× while playing, with the pitch kept, by the R3
  engine of the Rubber Band Library; at 1× the file is played as it is.
- Bookmarks with labels, on the waveform and in a side panel; previous and
  next; exported as text. They are kept for each file, with the point where
  it was left.
- Interface in English and in Spanish.
- Rubber Band through a binding of its own (rubberband.py), not pylibrb,
  whose licence (GPL 2 only) cannot be combined with GPL 3 or later.
- Files also read by the ffmpeg program where PyAV is missing (as in Fedora).
- Packages: a signed RPM (and Copr), an AppImage and a Debian package that
  carry their own Rubber Band and PortAudio (tools/build-libs.py), the wheel,
  the source and a ZIP, all signed, with SHA256SUMS; an installer for Linux
  and macOS; manual pages in English and Spanish.

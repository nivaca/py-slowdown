How py-slowdown was made
========================

py-slowdown is an audio player that plays a recording slower or faster
without changing its pitch, shows it as a waveform and keeps bookmarks in
it. Nicolas Vaughan made it in November 2026, for transcribing recorded
lectures and interviews, where one needs to hear a passage again and again
at a speed one can follow; it follows the shape of his other desktop
programs, such as py-pdftools (a Qt window, an interface in English and
Spanish, settings kept between sessions). Here I explain how it was made,
in six stages.

py-slowdown is free software, under the GNU General Public License,
version 3 or later. The stretching is done by the Rubber Band Library, by
Breakfast Quay (GPL 2 or later), through a binding of its own; the files
are read with PyAV (BSD), which brings FFmpeg (LGPL 2.1 or later), or with
the ffmpeg program; the sound reaches the sound card through sounddevice
(MIT) and PortAudio (MIT); the window uses PySide6 (LGPL 3), and the
numbers NumPy (BSD).

Nicolas Vaughan is Associate Professor of Literature at the School of Arts
and Humanities of the Universidad de los Andes, Bogotá, Colombia.

1. A first version
------------------

The requirements were few and clear: open the usual audio files (MP3,
MP4, FLAC and the rest), show the waveform, have the controls of any
player, put bookmarks at the playing position, and change the speed while
the audio plays, with very high quality. The last one decided almost
everything else.

There are several ways to change the tempo of audio without changing the
pitch. The simple ones (overlap-add methods such as WSOLA, or a plain phase
vocoder) are easy to write in NumPy, but they sound metallic or blurred as
soon as the speed is far from 1. The Rubber Band Library is the reference
in this field, and its newer engine, R3 (called "finer"), is clearly better
than the older one with speech and with music. pylibrb gives Python a
direct binding to it, with both the offline and the real-time modes, and
its wheels for Python 3.14 already include the library. I chose the
real-time mode, because the speed must change while the audio plays,
without preparing the whole file again. A first measure showed that R3,
called from Python by blocks of 1,024 frames, runs between 15 and 24 times
faster than real time on this computer, so there was room enough.

For reading the files I chose PyAV, which includes FFmpeg in its wheels and
so reads practically every format, also the sound of video files. Each
file is converted by FFmpeg's resampler to 32-bit floats, mono or stereo
(more channels are mixed down). For the sound card I chose sounddevice
rather than QtMultimedia: its callback runs in a thread of PortAudio,
outside Qt's event loop, so the drawing of the window cannot delay it.

2. Playing at another speed
---------------------------

The engine has two parts. `Renderer` makes the output audio, block by
block, from the decoded samples and a speed; `Player` takes these blocks to
the sound card. A thread of its own (the producer) keeps a short queue
filled, about 0.15 seconds, and PortAudio's callback only copies from this
queue, which costs it less than five milliseconds. A first version used a
quarter of a second; but a change of speed is heard only after the queue
already made at the old speed is played, and at 3× that delay was audible,
so I made it shorter.

The position shown must be the one that is heard, also at another speed.
Each block therefore carries the frame of the file where it starts and how
many frames of the file each output frame is worth. To make the output of
Rubber Band correspond exactly to a point of the file, the stretcher
receives before that point the audio that precedes it (the padding that
Rubber Band asks for at the start), and the first output frames, as many as
its announced delay, are discarded. A test with a file of clicks, one per
second, confirms it: at every speed from 0.25× to 3× each click is heard
within 20 milliseconds of the time the position says, and within about
3 milliseconds between 0.5× and 2×.

At speed 1, R3 is not transparent: with a noisy sound the difference
between its output and the original was about −40 dB. So at 1× the file is
copied as it is, sample by sample, and Rubber Band is used only at other
speeds. Each cut (a pause, a seek, the change between the copy and Rubber
Band) is smoothed with a ramp of a few milliseconds, going down before the
cut and up after it, so it does not click. One problem appeared here: on
a seek, the few frames kept to go down to zero were sometimes played before
the producer put the next block in the queue, and so they were not faded.
Now they are faded at the moment of the seek.

3. Long files
-------------

A recorded lecture of two hours, in stereo and in 32-bit floats, takes
about 2.5 GB. To keep it all in memory was not reasonable, and to decode it
on the fly, with seeking, would complicate every jump. The decoded samples
go instead to an unnamed temporary file in the user's cache folder (not
`/tmp`, which on Fedora lives in memory), mapped in memory with NumPy, so
the system keeps in memory only what is read. When the file is closed, or
the program ends in any way, the temporary file disappears with it.

The decoding runs in its own thread. While it goes on, the window draws and
plays what is already there, and the status bar shows the percentage.
Since the size of the temporary file is computed from the duration that the
file announces, a file longer than announced makes it grow, without losing
what was written. The waveform is drawn from peaks (the minimum and the
maximum of each group of 256 frames), computed during the decoding; when
the view is closer than one group per pixel, the samples themselves are
used.

4. The window
-------------

The window has the waveform on top, with a time ruler, the part already
played in another color, the position as a red line and the bookmarks with
their labels; under it, the controls (to the start, back, play or pause,
stop, forward, to the end), the time, the speed (a slider and a number box,
from 0.25× to 3×, and a button for 1×) and the volume; on the right, the
panel of bookmarks, where a label is edited in place and a double click on
the time goes there. The waveform is scaled to the loudest point of the
file, because a quiet recording, as lectures often are, looked almost flat.
All the actions have keyboard shortcuts, and the back and forward buttons
keep jumping while they are held down.

The bookmarks and the point where each file was left are kept in a JSON
file in the user's data folder, by the full path of the audio file, which
is not touched. The interface is written in English, and its Spanish
translation is an XML file of texts, as in py-pdftools; the language
follows the system's unless one is chosen in Settings.

5. The licence, and the packages
--------------------------------

When the first version was done, a question was left about its licence.
pylibrb declares "GPLv2" and ships the bare text of version 2, with no
"or later" anywhere, not even in its source files. If it is GPL 2 only, it
cannot be combined with a program under GPL 3 or later, and not with
PySide6 either (LGPL 3, or as Fedora packages it, LGPL 3 or GPL 3). The
Rubber Band Library itself has no such problem: its headers say "version 2
of the License, or (at your option) any later version". So I kept the
licence of all my programs, GPL 3 or later, and replaced pylibrb by a small
binding of my own (`rubberband.py`), with ctypes, to the C interface of
Rubber Band, which has all that the engine uses. It loads the library of
the system (rubberband-libs in Fedora, librubberband2 in Debian and Ubuntu,
rubberband in Homebrew), or a copy inside the package. The tests passed as
they were, with the new binding.

The release tooling is the same as py-pdftools': a signed RPM (also built
on Copr), an AppImage, a Debian package made from it, the wheel, the
source and a ZIP, every file signed with the project's key, with
`SHA256SUMS`, a signed tag, and every signature checked with only the
published key before anything is published. Two things were new. First,
Fedora has no package of PyAV, so the files can also be read by the
`ffmpeg` program (ffmpeg-free), through a pipe, with `ffprobe` for the
duration; the RPM uses it, and the tests run with both. Second, the
AppImage must run on systems older than the one where it is made, and
Fedora's Rubber Band and PortAudio need glibc 2.43 and 2.38 (PortAudio
also JACK and PipeWire). `tools/build-libs.py` compiles both from their
sources, which it checks by their SHA-256, with zig's compiler for glibc
2.28 and with the C++ library inside: Rubber Band from its single-file
build, with its own FFT (it runs 12 to 19 times faster than real time,
somewhat slower than with FFTW), and PortAudio with only ALSA, which it
loads when it runs, and which PipeWire and PulseAudio serve. Since that
Rubber Band is distributed in binary form, its source is published with
each release, as the GPL asks.

A test of the installer, run in a temporary home, went into my real data
folder, because the shell had `XDG_DATA_HOME` set; the installer only
removes what it made, so nothing was lost. The installer's own test, in
`tests/`, gives it a home of its own and no `XDG_DATA_HOME`.

6. The documentation
--------------------

The documentation follows that of py-pdftools, in English and Spanish: the
READMEs, the changelogs, these two descriptions, a list of the open-source
software the program uses, with its versions and licences
(`docs/THIRD-PARTY.md`, `docs/TERCEROS_es.md`), the manual pages, and a user
manual in each language (`docs/MANUAL_en.tex`, `docs/MANUAL_es.tex`, made
into PDFs with LuaLaTeX, with an index). The manual tells how to install
the program and check the signatures of a release, the window, opening a
file, the controls, the speed, the waveform, the bookmarks, the settings,
the files it keeps, the keys, and what to do when something goes wrong. Its
pictures, ten in each language, are made by `tools/manual_images.py`: the
window, drawn offscreen with a sample recording made by ffmpeg, with a
configuration of its own, so that the user's settings are never read nor
written.

The Spanish pictures showed two things that the window had wrong. Qt's own
words (OK, Cancel, and the names of the keys in the menus: Space, Left)
were in English, because Qt's translations were not loaded; now they are,
in the language of the interface, and the speed is written as 0,75× in
Spanish. And the list of keys of Help named them in English; now it names
them in the language of the interface too. The manuals also showed that
the monospaced font joined two hyphens into a dash (`--help` came out as
`–help`), so TeX's ligatures are turned off in it.

Testing
-------

The program has 75 tests (`tests/`), which `tools/test.py` runs at once,
each file in a process of its own, in a few seconds. They read the five
main kinds of files (WAV, FLAC, MP3, AAC and Opus), made by the tests
themselves, with PyAV and with the ffmpeg program, and check that the
decoded samples are the written ones, also when a file is longer than it
announces or is cut halfway. They check that at 1× the output is the file
itself, sample for sample; that at six speeds the output has the right
length, keeps the pitch (a tone of 220 Hz stays at 220 Hz) and keeps each
click at its place; that a seek while playing makes no click; and the
binding to Rubber Band, also when the library is missing. The player is
tested with a sound card that the tests drive themselves, and the window
offscreen: opening a file, the controls, the speed, the bookmarks, the
point where it was left, a file that is not audio, the window without
Rubber Band, and the Spanish interface, whose file must have every text of
the program and no other. Other tests check the packaging and the
documentation: the versions
agree, the licence, the desktop file, the metainfo, the spec, the manual
pages, the icons, the signing key and the signing of a release (with a key
made for the test), and that the manuals have the version of the program,
the same pictures in both languages, and their PDFs. Besides, the player was run on the real sound card at
seven speeds, with no buffer underrun, also through the PortAudio and the
Rubber Band compiled for the AppImage; the AppImage was built and started
with a file, the Debian package was built and its contents checked, the
RPM was built (its tests need two Fedora packages not installed here), and
the installer installed the program in a temporary home and removed it.
The program has 57 files and about 8,400 lines (5,200 of them in Python).

How py-slowdown was made
========================

py-slowdown is an audio player that plays a recording slower or faster
without changing its pitch, shows it as a waveform and keeps bookmarks in
it. Nicolas Vaughan made it in November 2026, for transcribing recorded
lectures and interviews, where one needs to hear a passage again and again
at a speed one can follow; it follows the shape of his other desktop
programs, such as py-pdftools (a Qt window, an interface in English and
Spanish, settings kept between sessions). Here I explain how it was made,
in thirteen stages.

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
the system (rubberband-libs in Fedora, librubberband3, or librubberband2, in Debian and Ubuntu,
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

7. Installers for Windows, macOS and Linux
-----------------------------------------

The packages so far served Linux, and macOS only from the source. For the
installers of the other two systems I followed py-words, which already has
them: each carries its own Python, a pinned build of python-build-standalone
checked by its SHA-256, with the program and its wheels installed into it
and Qt trimmed as in the AppImage, and each is made on its own system, by
GitHub, which installs it, tries it with `packaging/installer/check.py` (a
file read and stretched, PortAudio found, the window made), removes it,
and adds it to the release; `tools/release.py --installers` then signs them
here and copies them to Codeberg. For Windows it is a setup made with Inno
Setup, for one user without administrator's rights or for everyone, with
an entry in the Start menu and py-slowdown in "Open with" for audio files,
under a file type of its own, so no other program loses the files it
opens. For macOS it is a disk image with `py-slowdown.app`, one for Apple
Silicon and one for Intel, rather than py-words' package: py-slowdown is
only a window, and dragging it to Applications is what a Mac user
expects.

Rubber Band had to be compiled for each. For Windows, zig makes the DLL
from Linux as well, and it needs only what Windows 10 already has; for
macOS it is compiled on the Mac, with Apple's clang, because there Rubber
Band uses Apple's own FFT, in a framework that zig does not bring.
PortAudio comes with sounddevice's own wheels for both. Laying out the
installers here, with the packages for Windows and macOS (`--stage-only`),
showed two things: PySide6 and PyAV need macOS 13, not 11, and the
bookmarks and the decoded sound went to `~/.local/share` and `~/.cache` on
every system. They now go where each system keeps such things
(`%APPDATA%` and `%LOCALAPPDATA%` on Windows, `~/Library` on macOS). And
files opened from the Finder reach a program as an event, not as an
argument, so the window now takes them.

For Linux, the RPM, the Debian package and the AppImage were already
there; but the AppImage puts nothing in the menu, and many distributions
use neither of the two packages. So there is also an installer, a `.run`
made from the AppImage, as the Debian package is: a shell script followed
by its contents, checked by their SHA-256, which installs for the user or,
with sudo, for everyone, with the command, the menu entry, the icons, the
manual pages and an uninstaller that removes only what it put. Its test
builds it from a stand-in AppImage and installs it in a home of its own,
with its own data folder too (the lesson of stage 5).

None of the installers is signed by Microsoft or Apple, which needs
certificates that cost money every year; so SmartScreen and Gatekeeper
warn the first time, and the manuals say what to do. The signature of
each file, with the project's key, is what proves that it is the one
published.

8. Repeating a selection, and counting in
----------------------------------------

Two things that musicians, above all, ask of such a program came next: to
repeat a passage again and again, and to be counted in before the
recording starts.

The repeating had to be without a gap, which ruled out the simple way, a
seek back to the start each time the end is reached: that leaves a small
silence and a click, and with the stretcher it would restart Rubber Band at
every turn. Instead, the selection is repeated where the file is read, so
that the renderer, and through it Rubber Band, receives one continuous
stream: the selection, then the selection again. At the joint, the last
hundredth of a second of the selection fades out while what precedes its
start fades in (an equal-power crossfade), and the stream goes on from the
start, so the end runs into the start with neither a gap nor a click. Each
block of output stops at the end of the selection, so that the position
shown jumps back to its start exactly when the start is heard. The tests
check that at normal speed the output is the selection itself, sample for
sample, turn after turn, with no jump at the joints; that while stretching,
the click of the test file in the selection is heard once per turn, in its
place, and each turn lasts what it should; and that the position never
leaves the selection. A first version of the test counted the clicks by
their place in the file, so the same click, heard in every turn, was
counted once; they are now counted by when they are heard.

The count-in is a few clicks made by the program (short tones, the first
higher and louder), put at the front of the queue of sound, before the
recording: so it is exact to the sample, and the recording comes in on the
next beat. Its tempo can follow the speed, so that a song at 120 BPM played
at half speed is counted at 60, as it will sound. The waveform shows the
beat in large figures while it counts.

Three things went wrong on the way. Clicking the new buttons checked the
menu item but did nothing: the window connected its actions by `triggered`,
which a change made by a button does not emit; actions that are switched on
and off are now connected by `toggled`, which a test now checks. The
selection was drawn under the waveform, where only its gaps showed it; it
is now drawn over it, transparent. And the two new buttons squeezed the
volume slider to nothing, so the speed slider is now narrower. In the
dialog of the count-in, the numbers are written as the language of the
interface writes them (0,75× in Spanish).

9. A sound that broke off
-------------------------

After 0.1.0 was published, the sound broke off about once a second while
it played. My checks on the real sound card had driven the player without
the window, so they had not seen it. Run with the window, a long file and
the sound card, and with each part timed, the cause was plain: the
callback that feeds the sound card took less than two milliseconds, but it
ran late. It is Python code, and must wait for Python's lock; and each time
the red line of the position moved a pixel (every 1.3 seconds in a file of
twenty minutes), the window drew the waveform again, as a polygon of
thousands of peaks that Qt filled in 110 to 265 milliseconds, with the lock
held. The sound card's buffer held 35 milliseconds.

The waveform is now drawn once, with NumPy, into two images, the played
part and the rest, and when the position moves they are only copied; a
drawing takes two to five milliseconds, and a move of the position less.
The buffer of the sound card is also 0.1 seconds now, for room. With a
large window, while the file is still read, and zoomed in to the samples,
there were no breaks in the sound, even with the old buffer. A test keeps
the waveform from being drawn again when the position moves.

10. The pitch
------------

Rubber Band moves the pitch as well as the tempo, in the same pass, so the
pitch in semitones needed little in the engine: the plain copy of the file
is now used only at 1× and at the recording's own pitch, and the
stretcher, given the factor of the frequencies (2 to the power of the
semitones over twelve), does the rest. Changing it while the recording
plays is what Rubber Band's option for pitch that changes as it plays is
for, so the stretcher is made with it. The measurements were the test: a
tone of 220 Hz, moved by each pitch at several speeds, lands within a
cent of the frequency asked for, an octave down at 0.25× and an octave up
at 3× included, and the clicks of the test file stay in their place.

Two measurements misled me first. The FFT of the test, at its length,
cannot tell frequencies closer than 2.7 Hz apart, which an octave down is
more than a quarter of a semitone; the peak is now found between its bins.
And at 1.5× a click of the file fell inside the stretch measured, and
spread over the whole spectrum; the stretch is now taken between two
clicks. A test of a change of pitch in the middle of the sound found a jump
too, but it was my test's own seek, which, without the player, fades the
new sound in and not the old one out.

The pitch box made the row of controls too wide: the window could not be
narrower than 1350 pixels, more than a common laptop screen. The speed,
the pitch and the volume are now in a second row, and the window can be
800 pixels wide.

11. A count-in that was not heard
---------------------------------

The count-in did not work for me: I heard no clicks. Recorded in the
callback, with the real window and sound card, the four clicks were there,
at the tempo set, before the music. So the sound was followed further, into
a silent virtual output of PipeWire made for the test, with the program
playing into it: there too the clicks arrived whole. So they were lost
after PipeWire; and the output was a pair of Bluetooth earphones, which,
like many, may mute themselves while they receive silence and take a
moment to wake, so that a click of 35 milliseconds after silence would not
wake them, and the music, which goes on, would. The count now begins with a very faint hiss (about −58 dB), four
tenths of a second before the first click, and keeps it, fainter, between
the clicks, so that the output is never exact silence while it counts; the
clicks are fuller, a tone and its octave for 60 milliseconds. Through the
virtual output, the hiss and the clicks arrive as they should.

12. Tapping the tempo
--------------------

To set the tempo of the count-in, the simplest is to tap it: a button, Tap,
beside Count-in, and the key T, pressed with the beat while the music
plays. The tempo is the middle value (the median) of the intervals between
the last eight taps, not their mean, so that one tap early or late does not
move it; a pause of more than two seconds begins a new measure. What is
tapped is the tempo heard, so at another speed, when the count-in follows
the speed, the recording's own is kept (the tempo tapped divided by the
speed): a beat tapped at 60 at half speed is 120 in the recording, and the
count-in is right at every speed. The tests tap with times given, not with
the clock, uneven by a few hundredths and with one tap late. In the dialog,
the box of the tempo and its Tap button side by side left the label without
the box its key leads to, so it showed its ampersand ("&Tempo"); the label
now names its box.

13. The recording off the beat
------------------------------

After the count, the recording comes in on the next beat only if its own
first beat is exactly at the position, and often it is not: a bookmark a
little before the first beat makes the music come in late. So the
count-in has an offset, in seconds of the recording, from 2 earlier to 2
later. Later is simple: the count is longer, by a faint hiss. Earlier
means that the end of the count, the silence after its last click, is
shortened, so the recording comes in sooner; it can go no further than the
last click, which is never cut, and the dialog says so when more is asked
for. Being in seconds of the recording, the offset is divided by the speed
before it is heard: a first beat 0.2 seconds after the position, at half
speed, comes 0.4 seconds later, and an offset of −0.2 is right at both.

A number of seconds is not how one thinks of the place of a beat, so it
can also be set on the waveform, where the beat is seen: a right click on
the recording's first beat sets the offset from the position to that
point, and a green line marked 1 shows where the count-in expects it, to
check it by eye.

Since the program already remembered where each file was left, one more
setting made it pick up a session where it stopped: Settings > Reopen the
last file when starting, off at first, opens the last file again, at its
place, unless another is named on the command line, or the last one is
gone.

14. A waveform that stayed half drawn
-------------------------------------

After 1.0.0, a file just opened sometimes showed a waveform that did not
fill the window. It was drawn while the file was still being read, and
nothing asked it to be drawn again: neither the reading, as it went on,
nor its end, when the real length took the place of the announced one. It
stayed so until a click or a resize redrew it. Now the waveform follows the
reading.

That fix had a cost that I measured before going on. Each drawing during
the reading makes the two images of the waveform again, and on a screen
of 3800 pixels that took 18 ms, up to thirty times a second, with the GIL
held: the same kind of load that broke the sound after 0.1.0. Three
changes followed. While a file is read, the waveform is drawn at most five
times a second, and once more at the end. The images are kept while only
the position moves, even during the reading: they are made again only when
the column where the reading ends, within the view, or the loudest peak
read so far (the scale) changes. And instead of filling two 32-bit images
with NumPy, the program makes one map of bytes and lets Qt colour it twice,
from a table of two colours. At 3800 pixels the images take 2.7 ms instead
of 12, and reading a file of 30 minutes makes them 13 times, not about 75.

The decoded samples went from 32-bit floats to 16-bit integers in the
temporary file, which is half the size: 1.3 GB for two hours of stereo. A
16-bit file, by far the most common, is kept exactly, sample for sample;
other files lose what is below about -96 dB, less than the noise of any
recording. What goes past full scale, as some decoded MP3s do, is clipped,
as the sound card would clip it anyway.

Opening a file was still slow, and when I measured it, the decoding itself
was less than half of the time. An MP3 comes from FFmpeg in pieces of 1152
frames or fewer, about 69,000 for 30 minutes, and each piece was converted
to an array, turned into 16 bits by NumPy, written to the temporary file
and added to the peaks, one by one, in Python. Now FFmpeg's resampler gives
16-bit samples itself (it rounds and clips as the program did: not one
sample differed in 30 minutes of MP3), the readers gather the pieces in
blocks of 32,768 frames before handing them over, the peaks are found in
the integers, and PyAV decodes in several threads where the codec allows
it. A file of 30 minutes is read in 1.3 seconds instead of 2.2 as MP3, and
in 0.3 instead of 1.2 as FLAC; with the ffmpeg program, as in the RPM, the
MP3 takes 1.1 seconds instead of 2.0.

Testing
-------

The program has 115 tests (`tests/`), which `tools/test.py` runs at once,
each file in a process of its own, in a few seconds. They read the five
main kinds of files (WAV, FLAC, MP3, AAC and Opus), made by the tests
themselves, with PyAV and with the ffmpeg program, and check that the
decoded samples are the written ones, also when a file is longer than it
announces or is cut halfway. They check that at 1× the output is the file
itself, sample for sample; that at six speeds the output has the right
length, keeps the pitch (a tone of 220 Hz stays at 220 Hz) and keeps each
click at its place; that a seek while playing makes no click; and the
binding to Rubber Band, also when the library is missing; and the
repeating of a selection, at normal speed and stretching, the count-in,
and the pitch, by the frequency of a tone. The player is
tested with a sound card that the tests drive themselves, and the window
offscreen: opening a file, the controls, the speed, the bookmarks, the
point where it was left, a file that is not audio, the window without
Rubber Band, and the Spanish interface, whose file must have every text of
the program and no other. Other tests check the packaging and the
documentation: the versions
agree, the licence, the desktop file, the metainfo, the spec, the manual
pages, the icons, the signing key and the signing of a release (with a key
made for the test), and that the manuals have the version of the program,
the same pictures in both languages, and their PDFs; and the installers:
the `.run` installed and uninstalled, the Inno Setup script, and the names
that the workflow makes and the release looks for. Besides, the player was run on the real sound card at
seven speeds, with no buffer underrun, also through the PortAudio and the
Rubber Band compiled for the AppImage; the AppImage was built and started
with a file, the Debian package was built and its contents checked, the
RPM was built (its tests need two Fedora packages not installed here), and
the installer installed the program in a temporary home and removed it.
The program has 65 files and about 11,100 lines (6,800 of them in Python).

# Changelog

All notable changes to py-slowdown. The releases, with the AppImage, the
Debian package, the RPM, the wheel and the source, are on
[Codeberg](https://codeberg.org/nivaca/py-slowdown/releases) and
[GitHub](https://github.com/nivaca/py-slowdown/releases).

## Unreleased

- `tools/zenodo.py` prepares the deposit of a release for Zenodo. `collect`
  puts in `dist/zenodo/` the tree of the tag as
  `py-slowdown-VERSION-source.tar.gz`, with its signature, a signed
  `SHA256SUMS` of the deposit and the public key, and checks every signature
  with only that key (`--packages` adds the files of the release). `upload`
  sends it to Zenodo as a draft, a new version of the deposit if there is
  one already, and never publishes it. `tools/release.py` now collects the
  deposit after the tag and uploads it as a draft, unless `--no-zenodo`. The
  metadata are in `.zenodo.json`; the description is the whole README of the
  tag, in HTML. The languages, the copyright, the repository on GitHub, the
  programming language and the development status, which Zenodo's deposit
  API doesn't take, are added to the draft through its records API.

## 1.4.0 — 2026-11-25

Knobs for the speed and the volume, a five-band equalizer, the program's
own icons, and many smaller things to make practising easier: reset the
sound, the loops on the waveform, a clock of bars and beats, a compact
mode, a start screen.

- **Zoom to the selection** (View, Z): just the selection, with a little
  room on each side; and on a touchpad, a pinch zooms around the fingers.
- **A start screen**: without a file, the waveform lists the recordings
  opened last, each with a small picture of its waveform (from its peaks
  kept); a click opens one; one gone is greyed, not found. The clock goes
  back to zero when a file is closed.
- **Compact mode** (View, Ctrl+Shift+M): only the controls and a short
  waveform, without the side panels and the status bar, in a small window
  on top of the others, to practise beside a score; off, the window as it
  was.
- **A panel Sound**, at the side of the window, below Bookmarks and loops:
  the channels and the filter (as the menu Hear, the two always agreeing)
  and the equalizer, which is no longer a window of its own. EQ and Hear >
  Equalizer show it; View > Sound shows or hides it.
- **A clock that switches**: a click on the time shows the time left, and,
  with a first beat, the bar and the beat (at the count-in's tempo, as
  many beats in a bar as it has clicks); remembered.
- **The whole file above a closer view**: zoomed in, a strip above the
  waveform shows the whole file, the part in view shaded and the position
  in red; a click or a drag there shows that part.
- **The equalizer's curve and presets**: a curve above the knobs shows
  what it does from 20 Hz to 20 kHz; Presets has some for music (Bass up,
  Hear the bass line, Voice and solos forward, Bright, Warm, Cut the hiss)
  and the user's, saved by name and removed again.
- **Knobs that show they can be turned, also from the keyboard**: the
  pointer over a knob is a hand and lights up its rim; Tab reaches the
  knobs, whose rim then lights up too, and the arrows move it a step, Page
  Up and Down more, Home back to its usual value.
- **A menu on every knob**: a right click on a knob offers its usual
  values (the chosen speeds; the intervals of 1, 2, 3, 5, 7 and 12
  semitones; steps of cents, volume and decibels), the one now ticked, and
  Back to its usual one.
- **The speed knob stops at the chosen speeds**: dragged, it stays at a
  speed of the list (50%, 75%, 100%…) when it passes within a few degrees
  of one; the wheel and the keys move it as before.
- **The loops on the waveform**: each saved loop is a band of its own
  colour at the foot of the waveform, with its name; a click on it selects
  it, repeats it and goes to its start.
- **The value just changed, large on the waveform**: a speed changed from
  the keyboard or the menu of speeds, or a pitch changed from the keyboard,
  is shown in the middle of the waveform for a moment, then fades.
- **Reset the sound** (Playback, Ctrl+Shift+N): speed 100%, the recording's
  pitch, the formants off, both channels without a filter and the equalizer
  flat, at once; the volume stays.
- **Icons of the program's own for every button**: Bookmark, Speeds and
  EQ, which had text (a ribbon with a +, a speedometer and three faders),
  and the buttons of playing, repeat and the speaker of the volume, which
  had Qt's, of another style and not always fit for a dark theme. All drawn
  in the theme's colours (light or dark, on every system), white on a
  button that is on. The buttons of playing are a fifth larger.
- **A five-band equalizer**: the button EQ, at the right of the controls,
  or Hear > Equalizer, opens five knobs (60 Hz, 250 Hz, 1 kHz, 4 kHz and
  12 kHz, each from −12 to +12 dB), with On, to compare, and Flat. The
  sound changes as they turn, without a click; EQ is filled while it
  changes the sound. Kept with each file (in its `.slx` too); applied to
  an export as it is heard, without its 40 ms of delay.
- **Repeat without a selection repeats the whole file**: L, or the button
  with the two arrows, with nothing selected, goes on from the beginning at
  the end of the file (once it is read to its end). Kept with the file.
- **The speed is a knob**, as the pitch: its value inside, in percent, 100%
  straight up, 25–100% on its left half and 100–300% on its right; 5% for
  each notch of the wheel, a double click back to 100%. The slider and the
  box beside it go; 1× and Speeds stay.
- **The volume is a knob too**, beside the pitch, from 0 to 100% (the
  recording's sound), with **Boost**, which multiplies the sound by 1.8 and
  leaves the knob's number as it is (Settings > Volume boost: ×1.2, 1.5,
  1.8, 2, 2.5 or 3); where that is louder than the recording (from 75%
  with ×1.8), the knob's value and pointer are red. A recording
  kept by 1.3 above 100% opens boosted, at about the same loudness.
- **The arrow of Save**, in the question before closing a file: Always
  save, for this recording (from then on saved as it is done, without
  asking); Always save, for all recordings (Ask to save turned off); Never
  save this recording's changes (the title says so). Settings > Changes of
  this recording shows the recording's choice, and takes it back.
- The control panel is centred under the waveform, both its rows.
- The Spanish manual pointed to the section of the count-in with a "??".

## 1.3.1 — 2026-11-24

- **The ticks of the pitch knobs show on dark themes.** They were drawn in
  the theme's Mid colour, which in many dark themes (KDE's NordicDarker,
  for one) is that of the background; now they are drawn in the text
  colour, partly transparent, as is the outline of the knobs.

## 1.3.0 — 2026-11-24

Made for practising: a pause goes back to where playing started, the
count-in comes in on the beats of a first beat that stays, the pitch is
set in semitones and cents with two knobs, and the settings of each
recording travel in a `.slx` file of its own, saved when asked.

- **A pause goes back to where playing started**: Space, or the button,
  pauses and takes the position back there, so that the same passage is
  played again from the same place; the status bar says where it was
  paused. Moved while it plays, it goes back to the new place; with a
  selection repeated, inside it; at the end of the file, too. Playback >
  Continue from the pause (Shift+Space) goes on from where it was paused,
  as Space did until now. While it does not play, the place of that pause
  is marked on the waveform with a red dotted line and a pause sign at its
  foot.
- **The volume goes up to 150%**, for recordings made quietly; its value is
  shown in percent beside the slider, and above 100% the slider and the
  number are red. What goes beyond full scale is clipped.
- **The pitch in semitones and cents**, each with a knob (0 at the top),
  its value written in the middle, a short pointer at its edge: one step for each notch of the mouse wheel, a
  double click back to 0. The semitones from −12 to +12, the cents (hundredths of a semitone) from −50
  to +50, to tune a recording to an instrument; they add up. Ctrl+↑ and
  Ctrl+↓ move a semitone and keep the cents; moving the cents never makes
  the semitones jump. The volume moves to the right of the first row, to
  make room.
- **Go to the start goes to the first beat** (Home, the button, the menu)
  when the count-in is on and the file has a first beat, so that the count
  leads into it; otherwise to the beginning of the file. Its tooltip says
  which.
- **Each file starts from the usual settings**: a file with nothing kept
  opens at normal speed, the recording's pitch, both channels, the
  formants off and the count-in at 100 BPM, not with those of the file
  before (also when dropped on the window); a file with settings kept gets
  its own; the count-in is off for it and the volume at 100% (the volume
  is now kept with each file). The count-in's clicks stay.
- **No Formants button**: keeping the formants is only in the menu,
  Playback > Keep the formants (greyed out, as the button was, while the
  pitch is the recording's). The two pitch knobs and the button ø
  (the original pitch, until now 0) are evenly spaced.
- **Count-in > Clicks**: how many clicks the count-in gives (4 at first),
  from a list in the menu (1 to 8, 12, 16), the one chosen ticked; the
  dialog still takes any number from 1 to 16.
- **Ask to save before closing a file** (Settings, on at first): what is
  done to a file (bookmarks, loops, how it is played) is saved only with
  File > Save the .slx (Ctrl+S) or when closing it, opening another or
  quitting, when the program asks: Save, Discard (the position is kept) or
  Cancel. The title begins with • while there are changes. Off, all is
  saved as it is done: each bookmark or loop added, renamed or removed is
  written in `bookmarks.json` and the `.slx` right away.
- **Ctrl+W closes the file and leaves the program open; Alt+F4 (or Ctrl+Q)
  quits**, the same on every desktop (not Qt's standard keys, which
  changed with it).
- **File > Save the .slx** (Ctrl+S) writes the recording's `.slx` at once,
  without closing it; with Settings files set to Not saved, beside the
  recording all the same.
- **The settings files end in `.slx`**: `song.slx` for `song.mp3` (and
  `song.flac.slx`, if `song.slx` is another file's), still XML inside. The
  `song.xml` files of 1.2.0 are still read, and removed once their `.slx`
  is written. Opening a `.slx` (File > Open, the file manager, or dropped
  on the window) opens its recording, where it says or, moved with it,
  beside it. The installers make py-slowdown the program of the `.slx`
  files: on Linux a type of its own, `application/x-py-slowdown`, in the
  RPM, the Debian package, the installer of the AppImage and
  `install/install.sh`; on Windows in the registry, as the program of
  `.slx` only if no other was (Simulink's models end in `.slx` too); on
  macOS, a type declared by the application.
- **The first beat, a bookmark of its own**: Count-in > The first beat is
  here (Shift+C), or the right click on the waveform, marks the
  recording's first beat with a green bookmark marked 1, in bold in the
  panel, kept with the other bookmarks (in `bookmarks.json` and in the
  `.slx`), so that it is not lost when the position moves or the file is
  closed. There is one per file; Count-in > Remove the first beat removes
  it. With it, the recording comes in after the count on the nearest beat
  of the grid that the first beat and the tempo make, wherever playing
  starts; the count-in's offset is then not used, and its dialog greys it
  out. The tempo of the count-in is kept with the file even when the
  count-in is off, if there is a first beat. Count-in: the first beat at
  the position goes from the right click (the menu entry does it).

## 1.2.0 — 2026-11-24

The settings of each recording travel with it, in an XML file of its name;
speeds of one's own in a button; a choice of playback quality; and a
clearer window: Hear and Count-in in the menu bar, buttons that show when
they are on.

- **Formants only with the pitch moved**: the button Formants (and Playback >
  Keep the formants) is greyed out while the pitch is that of the
  recording, where it changes nothing; it keeps its state.
- **Buttons that are on are clearly on**: Formants and the repeat button,
  when on, are filled with the theme's selection colour (grey, if on but
  greyed out), not just slightly sunken.
- **Speeds chosen beforehand**: the button Speeds, beside 1×, and Playback >
  Speed presets list speeds in percent (at first 50, 60, 70, 75, 80, 90,
  100, 110, 125 and 150), the one playing ticked; Edit the speeds changes
  the list, Restore the usual speeds brings it back. The slider stays.
- In each menu, no two entries share the letter of Alt any more, in either
  language (Forward and Keep the formants did; a test checks them all).
- **The settings of each recording in an XML file of its name**: when a
  file is closed, its position, speed, pitch, formants, way of hearing,
  selection, count-in, bookmarks and loops are written in `song.xml` (for
  `song.mp3`), with the recording's full path, size and date. It travels
  with the recording: moved or copied together, everything comes back; when
  a file is opened, its XML comes first. If `song.xml` belongs to another
  file, it is `song.flac.xml`. Settings > Settings files of each recording:
  beside the audio file (at first), in a folder, or not saved.
- **No Count-in and Hear buttons**: their menus are enough; the Tap button
  stays. What the count-in does now is shown in the status bar, with the
  pointer over the items of its menu. Settings > Keyboard shortcuts has its
  own letter (H): S was also Skip length's.
- **Hear and Count-in have menus of their own**, in the menu bar, between
  Playback and Bookmarks: Hear has the channels and the filters (as its
  button), and Count-in has Count in before playing, Tap the tempo and the
  count-in's settings, which are no longer in Playback and Settings.
- **Playback quality** (Settings): Highest, Rubber Band's R3 engine as
  until now; Lighter, R3 with a short window, which needs half the
  processor and has less delay, with a little less detail in the low notes;
  or the Older engine, R2, with crisp attacks, which some prefer for drums
  and percussion. It changes while it plays, and is remembered. Exports
  always use the highest.

## 1.1.0 — 2026-11-24

For working on music: export what is heard, hear one part of the mix, keep
loops and each file as it was played, change the keys; and files are read
much faster.

- **The whole waveform at once, the second time**: once a file is read,
  its waveform is kept in the cache folder (about 4 MB for an hour and a
  half, for the 200 files opened last), and the next time the whole
  waveform and the exact length are there as soon as it opens, while the
  sound is read as before. A file that changed is read anew.
- **Keyboard shortcuts of one's own**: Settings > Keyboard shortcuts lists
  every action with its keys; a click on the keys and the new ones change
  them (a foot pedal that sends keys works the same way). Keys given to two
  actions are refused, Restore the defaults brings back those of always,
  and only the changed ones are kept. Help > Keyboard shortcuts shows the
  keys as they are. The manual pages list Shift+L and Ctrl+E.
- **Each file as it was played**: when a file is closed, its speed, pitch,
  formants, way of hearing, selection (and whether it was repeated) and,
  with the count-in on, the count-in's tempo and offset are kept with its
  bookmarks, and they come back when it is opened again. Only what is not
  the usual is kept; a file with nothing kept leaves them as they are.
- **Loops, selections kept with a name**: Playback > Save the selection as a
  loop (Shift+L), or Save the selection in the new tab Loops of the panel
  (now Bookmarks and loops), keeps the selection, and its name is written in
  the list. A double click on its times selects it again, repeats it, and
  goes to its start. They are kept for each file, with its bookmarks.
- **Export the audio**: File > Export the audio (Ctrl+E) saves the whole
  file, or the selection, as it sounds: at the speed and the pitch chosen,
  with the formants if they are kept, and, if asked, as it is heard (Hear).
  As WAV, FLAC, MP3 or Opus, named after the recording with its speed and
  pitch. It is done in the background, with a progress bar and Cancel, while
  the recording goes on playing (about 13 times faster than real time). The
  whole file at 1× is the file itself, sample for sample; a selection comes
  in and goes out on a short ramp; a filter does not delay it.
- **Hear one part of the mix**: Playback > Hear, and the button Hear in the
  second row, choose the channels (both, the left or the right only, the
  two in one, or the mix without its centre, where the voice and the solo
  usually are) and a filter (only the bass, below 250 Hz, to follow the bass
  line, or everything but the bass). The filters are linear-phase, applied
  block after block without seams; a change, while it plays, goes from one
  to the other in a fade. The choice is remembered.
- **Keep the formants**: the button Formants, beside the pitch, and
  Playback > Keep the formants, make Rubber Band keep the formants when the
  pitch moves, so that a voice or an instrument keeps its natural timbre
  instead of sounding smaller (higher) or bigger (lower). It can be changed
  while it plays, and is remembered.
- **The waveform fills the window when a file is opened**: it was drawn
  while the file was still being read, and sometimes stayed so, half drawn
  or at the scale of the length the file announced, until something else
  (a click, a resize) drew it again. It is now drawn again as the file is
  read, and at its real length once it is all read.
- **Lighter waveform**: while a file is read it is drawn again at most five
  times a second; moving the position no longer makes its images again
  during the reading; and the images are made by Qt from one map of bytes,
  more than twice as fast (2.7 ms instead of 12 on a screen 3800 pixels
  wide).
- **Half the space for the decoded samples**: they are kept in 16 bits, not
  in 32-bit floats (1.3 GB for two hours of stereo, not 2.5 GB). A 16-bit
  file is kept sample for sample; what goes past full scale is clipped.
- **Files open faster**: FFmpeg gives the samples in 16 bits itself, they
  are stored in blocks instead of in pieces of a thousand frames, and PyAV
  decodes in several threads where the codec allows it. A file of 30
  minutes is read in 1.3 s instead of 2.2 as MP3, and in 0.3 s instead of
  1.2 as FLAC.
- **Long files are read in four parts at once**: a file of four minutes or
  more in MP3, FLAC, Ogg Vorbis or Opus is read in parts, each by a process
  of its own, and each part is joined to the one before only where a
  second of both agrees sample for sample; if not, the file is read
  straight on. The result is always that of a straight reading. An MP3 of
  98 minutes is read in 3.1 s instead of 7.5. AAC, and a file
  played at another rate than its own, are read straight on.

## 1.0.0 — 2026-11-24

The first stable version.

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
- **Reopen the last file when starting** (Settings): the program opens again
  the file that was open last, where it was left, unless another is named
  on the command line. Off at first.
- **The first beat on the waveform**: a right click on the recording's first
  beat, Count-in: the first beat is here, sets the offset from the position
  to it (and turns the count-in on); a green line marked 1 shows where the
  count-in expects it.
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

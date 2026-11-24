"""La reproducción: el audio a otra velocidad, sin cambiar su altura.

Renderer produce el audio de salida por bloques, a partir de un Audio, de una
velocidad y de un cambio de altura en semitonos. A velocidad 1 y sin cambio de
altura copia las muestras tal cual (bit a bit); si no, las pasa por el motor R3 («finer») de Rubber Band (rubberband.py), en modo
de tiempo real, que estira o encoge el tiempo y conserva la altura y el timbre.
Rubber Band no es transparente a velocidad 1 (deja un error de unos -40 dB en un sonido ruidoso), y
por eso no se usa entonces.

Player lo lleva a la tarjeta de sonido: un hilo productor llena una cola corta
(0,15 segundos) con bloques de Renderer, y la función que PortAudio llama
(mediante sounddevice) toma de esa cola. Cada bloque lleva la posición del
archivo donde empieza y cuántos cuadros del archivo vale cada cuadro de salida,
de modo que la posición que se muestra es la que suena. Los cortes (pausa, salto,
cambio entre copia y Rubber Band) se suavizan con rampas de pocos milisegundos,
para que no chasqueen.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable

import numpy as np

from . import rubberband
from .audio import Audio

MIN_SPEED = 0.25
MAX_SPEED = 3.0
BLOCK = 1024  # output frames per block
FADE = 192  # cuadros de cada rampa contra chasquidos (unos 4 ms)
OUTPUT_LATENCY = 0.1  # segundos del búfer de la tarjeta: margen para cuando Python tarda en atenderla
QUEUE_SECONDS = 0.15  # audio preparado de antemano: también el retraso de un cambio de velocidad

OPTIONS = (
    rubberband.PROCESS_REALTIME
    | rubberband.ENGINE_FINER  # R3, the high-quality engine
    | rubberband.CHANNELS_TOGETHER  # keeps the stereo image and mono compatibility of a mix
    | rubberband.WINDOW_STANDARD
    | rubberband.PITCH_HIGH_CONSISTENCY  # the pitch changes while it plays, without a click
)
MAX_PITCH = 12.0  # semitonos, arriba o abajo


def clamp_speed(speed: float) -> float:
    return min(MAX_SPEED, max(MIN_SPEED, round(float(speed), 3)))


def clamp_pitch(semitones: float) -> float:
    return min(MAX_PITCH, max(-MAX_PITCH, round(float(semitones), 2)))


def pitch_scale(semitones: float) -> float:
    """The factor of the frequencies for SEMITONES: 2 ** (semitones / 12)."""
    return 2.0 ** (semitones / 12.0)


class Block:
    """Output frames, and where they come from in the file."""

    __slots__ = ("count", "frames", "start", "step", "used")

    def __init__(self, frames: np.ndarray, start: float, step: float, count: tuple[int, int, int] | None = None):
        self.frames = frames  # n × canales, float32
        self.start = start  # cuadro del archivo donde empieza
        self.step = step  # cuadros del archivo por cuadro de salida (la velocidad); 0 en la cuenta previa
        self.used = 0  # cuadros ya tocados
        self.count = count  # (silencio inicial, cuadros por pulso, pulsos) si es una cuenta previa

    def position(self) -> float:
        return self.start + self.used * self.step


LOOP_FADE = 0.01  # segundos del fundido con que el final de una selección repetida entra en su principio
MIN_LOOP = 0.1  # segundos: una selección más corta no se repite
COUNT_LEAD = 0.06  # segundos de silencio antes del primer pulso: la rampa de arranque no lo recorta
CLICK = 0.035  # duración de cada golpe de la cuenta
MIN_BPM, MAX_BPM = 20, 300
MAX_BEATS = 16


def count_in(rate: int, channels: int, beats: int, bpm: float) -> Block:
    """A count-in: BEATS clicks at BPM (the first one higher and louder), as a block that stays at the
    position of the file while it is heard. The recording comes in on the beat after the last click."""
    beats = min(max(1, int(beats)), MAX_BEATS)
    bpm = min(max(MIN_BPM, float(bpm)), MAX_BPM)
    lead = int(COUNT_LEAD * rate)
    beat = round(rate * 60.0 / bpm)
    frames = np.zeros((lead + beats * beat, channels), np.float32)
    t = np.arange(int(CLICK * rate)) / rate
    envelope = np.exp(-t / 0.008)
    for n in range(beats):
        pitch, level = (1760.0, 0.5) if n == 0 else (1320.0, 0.35)
        click = (level * envelope * np.sin(2 * np.pi * pitch * t)).astype(np.float32)
        start = lead + n * beat
        frames[start:start + len(click)] += click[:, None]
    return Block(frames, 0.0, 0.0, (lead, beat, beats))


class Renderer:
    """Makes the output audio of an Audio, block by block, at a speed."""

    def __init__(self, audio: Audio):
        self.audio = audio
        self.speed = 1.0
        self.pitch = 0.0  # semitonos
        self.pos = 0.0  # cuadro del archivo que corresponde al próximo cuadro de salida
        self._stretcher: rubberband.Stretcher | None = None
        self._stretching = False  # whether the stretcher holds the stream now
        self._feed = 0  # next frame of the file to give the stretcher
        self._final = False  # the stretcher was given the end of the file
        self._discard = 0  # output frames to drop (the stretcher's delay)
        self._seam = True  # the next block starts after a cut
        self.loop: tuple[int, int] | None = None  # (start, end) of the selection repeated, in frames
        self._xfade = max(16, int(LOOP_FADE * audio.rate))  # cuadros del fundido entre el final y el principio

    def set_loop(self, loop: tuple[int, int] | None) -> None:
        """Repeat the frames from START to END without a gap (None: no longer)."""
        self.loop = loop

    def _read(self, start: int, frames: int) -> np.ndarray:
        """FRAMES frames of the file from START, as they are heard: with a selection repeated, they stop at its
        end, and the last moments of it fade into those before its start, so that the end runs into the start
        with no click and no gap (the caller goes on from the start)."""
        audio = self.audio
        loop = self.loop if self.loop and start < self.loop[1] else None
        if loop:
            frames = min(frames, loop[1] - start)
        data = np.array(audio.frames(start, start + frames), dtype=np.float32)
        if loop and len(data):
            begin, end = loop
            x = self._xfade
            lo, hi = max(start, end - x), start + len(data)
            if hi > lo:
                # Fundido de igual potencia: el final se apaga mientras sube lo que precede al principio.
                k = (np.arange(lo, hi) - (end - x) + 0.5) / x
                fade_in = np.sin(k * np.pi / 2).astype(np.float32)[:, None]
                fade_out = np.cos(k * np.pi / 2).astype(np.float32)[:, None]
                first = lo - end + begin  # (de begin - x a begin)
                other = np.zeros((hi - lo, data.shape[1]), np.float32)
                got = audio.frames(max(0, first), first + (hi - lo))
                other[len(other) - len(got):] = got
                data[lo - start:] = data[lo - start:] * fade_out + other * fade_in
        return data

    def _wraps(self, before: float, after: float) -> bool:
        return bool(self.loop) and before < self.loop[1] <= after + 0.5

    def seek(self, frame: float) -> None:
        self.pos = float(min(max(0.0, frame), max(0, self.audio.length)))
        self._stretching = False
        self._seam = True

    @property
    def plain(self) -> bool:
        """Whether the file is played as it is: at 1×, and at its own pitch."""
        return self.speed == 1.0 and self.pitch == 0.0

    def set_speed(self, speed: float) -> None:
        speed = clamp_speed(speed)
        if speed != self.speed:
            was_plain = self.plain
            self.speed = speed
            self._changed(was_plain)

    def set_pitch(self, semitones: float) -> None:
        semitones = clamp_pitch(semitones)
        if semitones != self.pitch:
            was_plain = self.plain
            self.pitch = semitones
            self._changed(was_plain)

    def _changed(self, was_plain: bool) -> None:
        if self._stretching:
            if self.plain:
                # From Rubber Band to the plain copy, from where the output has got to.
                self._stretching = False
                self._seam = True
            else:
                self._stretcher.time_ratio = 1.0 / self.speed
                self._stretcher.pitch_scale = pitch_scale(self.pitch)
        elif not was_plain:
            self._seam = True

    def render(self, frames: int = BLOCK) -> tuple[Block | None, bool]:
        """The next block of at most FRAMES frames, and whether it starts after a cut.

        The block is None at the end of the file; it is empty while the frames
        it needs are still being decoded.
        """
        if self.plain:
            block = self._copy(frames)
        else:
            block = self._stretch(frames)
        seam = False
        if block is not None and len(block.frames):
            seam, self._seam = self._seam, False
            if seam:
                ramp = min(FADE, len(block.frames))
                block.frames[:ramp] *= np.linspace(0.0, 1.0, ramp, dtype=np.float32)[:, None]
        return block, seam

    def _copy(self, frames: int) -> Block | None:
        start = round(self.pos)
        audio = self.audio
        if start >= audio.decoded:
            return None if audio.done else Block(np.zeros((0, audio.channels), np.float32), start, 1.0)
        data = self._read(start, frames)
        self.pos = start + len(data)
        if self._wraps(start, self.pos):
            self.pos = float(self.loop[0])
        return Block(data, start, 1.0)

    def _restart(self) -> None:
        # El estirador empieza en self.pos: recibe antes el audio que precede a ese punto (o silencio,
        # al principio del archivo), y su salida se descarta hasta el retraso que anuncia; así lo que sale
        # después corresponde justo a self.pos, sin el arranque en falso de un estirador vacío.
        audio = self.audio
        if self._stretcher is None:
            self._stretcher = rubberband.Stretcher(audio.rate, audio.channels, OPTIONS, 1.0 / self.speed)
            self._stretcher.set_max_process_size(4096)
        st = self._stretcher
        st.reset()
        st.time_ratio = 1.0 / self.speed
        st.pitch_scale = pitch_scale(self.pitch)
        start = round(self.pos)
        self.pos = float(start)
        pad = st.get_preferred_start_pad()
        before = audio.frames(start - pad, start)
        lead = np.zeros((pad, audio.channels), np.float32)
        if len(before):
            lead[pad - len(before):] = before
        st.process(np.ascontiguousarray(lead.T))
        self._discard = st.get_start_delay()
        self._feed = start
        self._final = False
        self._stretching = True

    def _stretch(self, frames: int) -> Block | None:
        audio = self.audio
        if not self._stretching:
            if self.pos >= audio.decoded and audio.done:
                return None
            self._restart()
        st = self._stretcher
        while st.available() < frames + self._discard and not self._final:
            need = max(st.get_samples_required(), 256)
            chunk = self._read(self._feed, need)
            looping = bool(self.loop) and self._feed < self.loop[1]
            last = not looping and audio.done and self._feed + len(chunk) >= audio.decoded
            if not len(chunk) and not last:
                break  # todavía se decodifica
            st.process(np.ascontiguousarray(chunk.T), last)
            fed = self._feed
            self._feed += len(chunk)
            if self._wraps(fed, self._feed):
                self._feed = self.loop[0]  # (sin corte: el estirador recibe la selección una vez tras otra)
            self._final = last
        available = st.available()
        if available <= 0:
            if self._final and available < 0:
                return None
            return Block(np.zeros((0, audio.channels), np.float32), self.pos, self.speed)
        if self._discard:
            drop = min(self._discard, available)
            st.retrieve(drop)
            self._discard -= drop
            available -= drop
            if available <= 0:
                return Block(np.zeros((0, audio.channels), np.float32), self.pos, self.speed)
        if self.loop and self.pos < self.loop[1]:
            # Un bloque no pasa del final de la selección: el que sigue empieza en su principio.
            frames = max(1, min(frames, int(np.ceil((self.loop[1] - self.pos) / self.speed))))
        out = st.retrieve(min(frames, available)).T.copy()
        block = Block(out, self.pos, self.speed)
        before = self.pos
        self.pos = min(self.pos + len(out) * self.speed, float(audio.decoded))
        if self._wraps(before, self.pos):
            self.pos = float(self.loop[0])
        return block


def sounddevice():
    """The sounddevice module, with the PortAudio bundled in the package if there is one.

    The AppImage and the Debian package carry their own PortAudio (lib/, made by
    tools/build-libs.py): sounddevice only looks for it by name, with
    ctypes.util.find_library, so it is pointed there while it is imported.
    """
    import sys

    if "sounddevice" in sys.modules:
        return sys.modules["sounddevice"]
    bundled = rubberband.HERE / "lib" / "libportaudio.so.2"
    if not bundled.is_file():
        import sounddevice as module

        return module
    import ctypes.util

    original = ctypes.util.find_library
    ctypes.util.find_library = lambda name: str(bundled) if name == "portaudio" else original(name)
    try:
        import sounddevice as module
    finally:
        ctypes.util.find_library = original
    return module


class Output:
    """Where the audio goes: a sound card through sounddevice."""

    latency = 0.0

    def open(self, rate: int, channels: int, callback: Callable[[np.ndarray], None]) -> None:
        def call(outdata, _frames, _time, _status):
            callback(outdata)

        self._stream = sounddevice().OutputStream(
            samplerate=rate, channels=channels, dtype="float32", callback=call, latency=OUTPUT_LATENCY
        )
        self._stream.start()
        self.latency = float(self._stream.latency)

    def close(self) -> None:
        stream = getattr(self, "_stream", None)
        if stream is not None:
            self._stream = None
            stream.abort()
            stream.close()

    @staticmethod
    def supports(rate: int) -> bool:
        """Whether the default sound card plays RATE samples per second."""
        try:
            sounddevice().check_output_settings(samplerate=rate, channels=2, dtype="float32")
        except Exception:  # noqa: BLE001 (sin PortAudio, o sin tarjeta: cualquier error de sounddevice)
            return False
        return True

    @staticmethod
    def default_rate() -> int:
        try:
            return int(sounddevice().query_devices(kind="output")["default_samplerate"])
        except Exception:  # noqa: BLE001 (sin PortAudio, o sin tarjeta: cualquier error de sounddevice)
            return 48000


class Player:
    """Plays an Audio at a speed, with play, pause and seek."""

    def __init__(self, output: Output | None = None):
        self.output = output or Output()
        self.audio: Audio | None = None
        self.playing = False
        self.ended = False  # llegó al final; la ventana lo lee y lo apaga
        self.volume = 1.0
        self.loop: tuple[float, float] | None = None  # the selection repeated, in seconds
        self._speed = 1.0
        self._pitch = 0.0
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._queue: deque[Block] = deque()
        self._queued = 0  # output frames in the queue
        self._position = 0.0  # file frame playing now
        self._gain = 0.0  # ganancia actual de la rampa de pausa
        self._eof = False
        self._requests: list[tuple[str, float]] = []
        self._thread: threading.Thread | None = None
        self._running = False

    # --- el archivo

    def load(self, audio: Audio) -> None:
        self.unload()
        self.audio = audio
        self._renderer = Renderer(audio)
        self._renderer.set_speed(self._speed)
        self._renderer.set_pitch(self._pitch)
        self.loop = None
        self._position = 0.0
        self._queue.clear()
        self._queued = 0
        self._eof = False
        self.ended = False
        self._running = True
        self._thread = threading.Thread(target=self._produce, name="produce", daemon=True)
        self._thread.start()
        self.output.open(audio.rate, audio.channels, self._callback)

    def unload(self) -> None:
        self.playing = False
        if self._thread is not None:
            with self._lock:
                self._running = False
                self._wake.notify_all()
            self._thread.join(2)
            self._thread = None
        self.output.close()
        self.audio = None

    # --- los mandos

    def play(self, beats: int = 0, bpm: float = 0.0) -> None:
        """Play; with BEATS and BPM, after a count-in of BEATS clicks at BPM."""
        if self.audio is None:
            return
        if self.ended or (self._eof and not self._queue):
            self.seek(0.0)
        with self._lock:
            # Lo que quede de una cuenta anterior (una pausa en medio de ella) no se oye.
            for block in [b for b in self._queue if b.count]:
                self._queue.remove(block)
                self._queued -= len(block.frames) - block.used
            if beats > 0 and bpm > 0:
                block = count_in(self.audio.rate, self.audio.channels, beats, bpm)
                block.start = self._position
                self._queue.appendleft(block)
                self._queued += len(block.frames)
        self.ended = False
        self.playing = True

    def set_loop(self, loop: tuple[float, float] | None) -> None:
        """Repeat the part of the file from START to END seconds, without a gap, while it plays (None: no
        longer). The position goes into it, unless it is there already."""
        self.loop = None
        frames = None
        if loop and self.audio is not None:
            rate = self.audio.rate
            start, end = sorted(loop)
            a, b = int(max(0.0, start) * rate), int(min(end * rate, self.audio.decoded))
            if b - a >= MIN_LOOP * rate:
                frames = (a, b)
                self.loop = (a / rate, b / rate)
        if self.audio is None:
            return
        here = self.position
        with self._lock:
            self._requests.append(("loop", frames))
            self._wake.notify_all()
        # Lo que ya está en la cola se hizo sin la selección: se rehace desde donde suena (o desde su principio).
        inside = frames is not None and frames[0] <= here * self.audio.rate < frames[1]
        self.seek(here if frames is None or inside else frames[0] / self.audio.rate)

    def counting(self) -> tuple[int, int] | None:
        """(the beat that sounds, of how many) while a count-in is heard; None otherwise."""
        with self._lock:
            block = self._queue[0] if self._queue else None
            if not self.playing or block is None or not block.count:
                return None
            lead, beat, beats = block.count
            return min(beats, max(0, block.used - lead) // beat + 1), beats

    def pause(self) -> None:
        self.playing = False

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def stop(self) -> None:
        self.playing = False
        self.seek(0.0)

    def seek(self, seconds: float) -> None:
        if self.audio is None:
            return
        frame = min(max(0.0, seconds * self.audio.rate), float(self.audio.length))
        with self._lock:
            # What is already queued is cut, except a short ramp down that is heard before the jump.
            self._cut_queue(keep=FADE if self.playing else 0)
            self._requests.append(("seek", frame))
            self._position = frame
            self._eof = False
            self.ended = False
            self._wake.notify_all()

    @property
    def pitch(self) -> float:
        """Semitones up (or down, below 0); 0 is the pitch of the recording."""
        return self._pitch

    @pitch.setter
    def pitch(self, value: float) -> None:
        self._pitch = clamp_pitch(value)
        with self._lock:
            self._requests.append(("pitch", self._pitch))
            self._wake.notify_all()

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = clamp_speed(value)
        with self._lock:
            self._requests.append(("speed", self._speed))
            self._wake.notify_all()

    @property
    def position(self) -> float:
        """Seconds: the point of the file that is heard now."""
        if self.audio is None:
            return 0.0
        frame = self._position
        if self.playing and self._queue:
            # What left the queue is heard only after the latency of the sound card.
            frame -= self.output.latency * self.audio.rate * self._queue[0].step
        seconds = max(0.0, frame / self.audio.rate)
        if self.loop and self.loop[0] - 0.25 < seconds < self.loop[0]:
            # (justo después del salto al principio de la selección, la latencia lo dejaría un poco antes)
            seconds = self.loop[0]
        return seconds

    @property
    def duration(self) -> float:
        return self.audio.duration if self.audio else 0.0

    # --- el hilo productor

    def _produce(self) -> None:
        renderer = self._renderer
        while True:
            with self._lock:
                while self._running and (self._eof or self._queued >= self._target()) and not self._requests:
                    self._wake.wait(0.05)
                if not self._running:
                    return
                requests, self._requests = self._requests, []
            for kind, value in requests:
                if kind == "seek":
                    renderer.seek(value)
                elif kind == "speed":
                    renderer.set_speed(value)
                elif kind == "loop":
                    renderer.set_loop(value)
                elif kind == "pitch":
                    renderer.set_pitch(value)
            block, seam = renderer.render()
            with self._lock:
                if any(kind == "seek" for kind, _value in self._requests):
                    continue  # a seek came while this block was made: it is not heard
                if block is None:
                    self._eof = True
                    continue
                if not len(block.frames):
                    self._wake.wait(0.02)  # waiting for the decoder
                    continue
                if seam:
                    self._fade_tail()
                self._queue.append(block)
                self._queued += len(block.frames)

    def _target(self) -> int:
        return int(QUEUE_SECONDS * (self.audio.rate if self.audio else 44100))

    def _cut_queue(self, keep: int) -> None:
        # Deja solo los primeros KEEP cuadros por tocar, que bajan a cero (pueden sonar antes de que el
        # productor alcance a poner el bloque que sigue al corte).
        kept: deque[Block] = deque()
        left = keep
        for block in self._queue:
            if left <= 0:
                break
            rest = block.frames[block.used:]
            take = min(left, len(rest))
            kept.append(Block(rest[:take].copy(), block.position(), block.step))
            left -= take
        self._queue = kept
        self._queued = keep - max(0, left)
        self._fade_tail()

    def _fade_tail(self) -> None:
        # Una rampa de bajada en los últimos FADE cuadros que hay en la cola, antes de un corte: el último
        # cuadro queda en cero.
        total = min(FADE, self._queued)
        done = 0  # cuadros ya rebajados, contados desde el final
        for block in reversed(self._queue):
            if done >= total:
                break
            rest = len(block.frames) - block.used
            take = min(total - done, rest)
            if take:
                gains = (done + np.arange(take - 1, -1, -1, dtype=np.float32)) / total
                block.frames[len(block.frames) - take:] *= gains[:, None]
            done += take

    # --- la tarjeta de sonido

    def _callback(self, out: np.ndarray) -> None:
        out.fill(0.0)
        frames = len(out)
        target = 1.0 if self.playing else 0.0
        if self._gain == 0.0 and target == 0.0:
            return
        with self._lock:
            filled = 0
            while filled < frames and self._queue:
                block = self._queue[0]
                take = min(frames - filled, len(block.frames) - block.used)
                out[filled:filled + take] = block.frames[block.used:block.used + take]
                block.used += take
                filled += take
                self._queued -= take
                self._position = block.position()
                if block.used >= len(block.frames):
                    self._queue.popleft()
            if not self._queue and self._eof and self.playing:
                self.playing = False
                self.ended = True
                self._position = float(self.audio.decoded) if self.audio else 0.0
            self._wake.notify_all()
        # The pause ramp: from the current gain to the new one, along this block.
        if self._gain != target:
            ramp = np.linspace(self._gain, target, frames, dtype=np.float32)
            out *= ramp[:, None]
            self._gain = target
        if self.volume != 1.0:
            out *= self.volume

"""La reproducción: el audio a otra velocidad, sin cambiar su altura.

Renderer produce el audio de salida por bloques, a partir de un Audio y de una
velocidad. A velocidad 1 copia las muestras tal cual (bit a bit); a cualquier
otra, las pasa por el motor R3 («finer») de Rubber Band, en modo de tiempo real,
que estira o encoge el tiempo y conserva la altura y el timbre. Rubber Band no es
transparente a velocidad 1 (deja un error de unos -40 dB en un sonido ruidoso), y
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
import pylibrb

from .audio import Audio

MIN_SPEED = 0.25
MAX_SPEED = 3.0
BLOCK = 1024  # output frames per block
FADE = 192  # cuadros de cada rampa contra chasquidos (unos 4 ms)
QUEUE_SECONDS = 0.15  # audio preparado de antemano: también el retraso de un cambio de velocidad

OPTIONS = (
    pylibrb.Option.PROCESS_REALTIME
    | pylibrb.Option.ENGINE_FINER  # R3, the high-quality engine
    | pylibrb.Option.CHANNELS_TOGETHER  # keeps the stereo image and mono compatibility of a mix
    | pylibrb.Option.WINDOW_STANDARD
)


def clamp_speed(speed: float) -> float:
    return min(MAX_SPEED, max(MIN_SPEED, round(float(speed), 3)))


class Block:
    """Output frames, and where they come from in the file."""

    __slots__ = ("frames", "start", "step", "used")

    def __init__(self, frames: np.ndarray, start: float, step: float):
        self.frames = frames  # n × canales, float32
        self.start = start  # cuadro del archivo donde empieza
        self.step = step  # cuadros del archivo por cuadro de salida (la velocidad)
        self.used = 0  # cuadros ya tocados

    def position(self) -> float:
        return self.start + self.used * self.step


class Renderer:
    """Makes the output audio of an Audio, block by block, at a speed."""

    def __init__(self, audio: Audio):
        self.audio = audio
        self.speed = 1.0
        self.pos = 0.0  # cuadro del archivo que corresponde al próximo cuadro de salida
        self._stretcher: pylibrb.RubberBandStretcher | None = None
        self._stretching = False  # whether the stretcher holds the stream now
        self._feed = 0  # next frame of the file to give the stretcher
        self._final = False  # the stretcher was given the end of the file
        self._discard = 0  # output frames to drop (the stretcher's delay)
        self._seam = True  # the next block starts after a cut

    def seek(self, frame: float) -> None:
        self.pos = float(min(max(0.0, frame), max(0, self.audio.length)))
        self._stretching = False
        self._seam = True

    def set_speed(self, speed: float) -> None:
        speed = clamp_speed(speed)
        if speed == self.speed:
            return
        was_one = self.speed == 1.0
        self.speed = speed
        if self._stretching:
            if speed == 1.0:
                # From Rubber Band to the plain copy, from where the output has got to.
                self._stretching = False
                self._seam = True
            else:
                self._stretcher.time_ratio = 1.0 / speed
        elif not was_one:
            self._seam = True

    def render(self, frames: int = BLOCK) -> tuple[Block | None, bool]:
        """The next block of at most FRAMES frames, and whether it starts after a cut.

        The block is None at the end of the file; it is empty while the frames
        it needs are still being decoded.
        """
        if self.speed == 1.0:
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
        data = np.array(audio.frames(start, start + frames), dtype=np.float32)
        self.pos = start + len(data)
        return Block(data, start, 1.0)

    def _restart(self) -> None:
        # El estirador empieza en self.pos: recibe antes el audio que precede a ese punto (o silencio,
        # al principio del archivo), y su salida se descarta hasta el retraso que anuncia; así lo que sale
        # después corresponde justo a self.pos, sin el arranque en falso de un estirador vacío.
        audio = self.audio
        if self._stretcher is None:
            self._stretcher = pylibrb.RubberBandStretcher(audio.rate, audio.channels, OPTIONS, 1.0 / self.speed)
            self._stretcher.set_max_process_size(4096)
        st = self._stretcher
        st.reset()
        st.time_ratio = 1.0 / self.speed
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
            chunk = audio.frames(self._feed, self._feed + need)
            last = audio.done and self._feed + len(chunk) >= audio.decoded
            if not len(chunk) and not last:
                break  # todavía se decodifica
            st.process(np.ascontiguousarray(chunk.T), last)
            self._feed += len(chunk)
            self._final = last
        available = st.available()
        if available <= 0:
            if self._final and (available < 0 or st.is_done()):
                return None
            return Block(np.zeros((0, audio.channels), np.float32), self.pos, self.speed)
        if self._discard:
            drop = min(self._discard, available)
            st.retrieve(drop)
            self._discard -= drop
            available -= drop
            if available <= 0:
                return Block(np.zeros((0, audio.channels), np.float32), self.pos, self.speed)
        out = st.retrieve(min(frames, available)).T.copy()
        block = Block(out, self.pos, self.speed)
        self.pos = min(self.pos + len(out) * self.speed, float(audio.decoded))
        return block


class Output:
    """Where the audio goes: a sound card through sounddevice."""

    latency = 0.0

    def open(self, rate: int, channels: int, callback: Callable[[np.ndarray], None]) -> None:
        import sounddevice

        def call(outdata, _frames, _time, _status):
            callback(outdata)

        self._stream = sounddevice.OutputStream(
            samplerate=rate, channels=channels, dtype="float32", callback=call, latency="high"
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
            import sounddevice

            sounddevice.check_output_settings(samplerate=rate, channels=2, dtype="float32")
        except Exception:  # noqa: BLE001 (sin PortAudio, o sin tarjeta: cualquier error de sounddevice)
            return False
        return True

    @staticmethod
    def default_rate() -> int:
        try:
            import sounddevice

            return int(sounddevice.query_devices(kind="output")["default_samplerate"])
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
        self._speed = 1.0
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

    def play(self) -> None:
        if self.audio is None:
            return
        if self.ended or (self._eof and not self._queue):
            self.seek(0.0)
        self.ended = False
        self.playing = True

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
        return max(0.0, frame / self.audio.rate)

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

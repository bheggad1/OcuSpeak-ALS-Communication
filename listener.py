"""Listens to the other person through the microphone and turns their speech into text.

Runs entirely on the laptop (faster-whisper), so nothing is sent anywhere.
It mutes itself while the app is speaking, so it doesn't hear its own voice.
"""
import collections
import logging
import queue
import threading
import time

SAMPLE_RATE = 16000
BLOCK = 480  # 30 ms
BLOCK_SECONDS = BLOCK / SAMPLE_RATE
MIN_SPEECH_SECONDS = 0.35
MAX_UTTERANCE_SECONDS = 20

# Things Whisper sometimes "hears" in silence or noise.
HALLUCINATIONS = {
    "", ".", "you", "thank you", "thank you.", "thanks for watching", "thanks for watching!",
    "bye", "bye.", "[music]", "(music)", "[blank_audio]", "okay.", "so",
}


class Segmenter:
    """Splits a stream of audio blocks into utterances using loudness."""

    def __init__(self, min_level=0.01, silence_seconds=0.9):
        self.min_level = min_level
        self.silence_seconds = silence_seconds
        self.noise = min_level / 3
        self.pre = collections.deque(maxlen=10)  # keep 300 ms before speech starts
        self.reset()

    def reset(self):
        self.buf = []
        self.in_speech = False
        self.speech_time = 0.0
        self.silence_time = 0.0
        self.pre.clear()

    def feed(self, block, np):
        """Returns a finished utterance (numpy array) or None."""
        rms = float(np.sqrt(np.mean(block * block)))
        threshold = max(self.min_level, self.noise * 3.0)
        if not self.in_speech:
            self.pre.append(block)
            if rms > threshold:
                self.in_speech = True
                self.buf = list(self.pre)
                self.speech_time = BLOCK_SECONDS
                self.silence_time = 0.0
            else:
                self.noise = 0.95 * self.noise + 0.05 * rms
            return None
        self.buf.append(block)
        if rms > threshold:
            self.speech_time += BLOCK_SECONDS
            self.silence_time = 0.0
        else:
            self.silence_time += BLOCK_SECONDS
        total = len(self.buf) * BLOCK_SECONDS
        if self.silence_time >= self.silence_seconds or total >= MAX_UTTERANCE_SECONDS:
            audio = np.concatenate(self.buf) if self.speech_time >= MIN_SPEECH_SECONDS else None
            self.reset()
            return audio
        return None


def clean_transcript(segments):
    kept = [
        s.text.strip()
        for s in segments
        if getattr(s, "no_speech_prob", 0) < 0.6 and getattr(s, "avg_logprob", 0) > -1.0
    ]
    text = " ".join(t for t in kept if t).strip()
    return "" if text.lower() in HALLUCINATIONS else text


class Listener:
    def __init__(self, settings, on_text, on_status):
        self.settings = settings
        self.on_text = on_text
        self.on_status = on_status
        self.enabled = threading.Event()
        self._muted = False
        self._ignore_until = 0.0
        self.available = False

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="listener").start()

    def set_enabled(self, on):
        (self.enabled.set if on else self.enabled.clear)()

    def mute(self):
        self._muted = True

    def unmute(self, tail_seconds=0.6):
        self._ignore_until = time.time() + tail_seconds
        self._muted = False

    def _is_muted(self):
        return self._muted or time.time() < self._ignore_until

    def _run(self):
        try:
            import numpy as np
            import sounddevice as sd
            from faster_whisper import WhisperModel
        except ImportError:
            logging.exception("Listening packages missing")
            self.on_status("Listening off: run install.bat")
            return
        try:
            self.on_status("Loading listener…")
            model = WhisperModel(self.settings["whisper_model"], device="cpu", compute_type="int8")
            audio_q = queue.Queue()

            def callback(indata, frames, t, status):
                audio_q.put(indata[:, 0].copy())

            seg = Segmenter(self.settings["mic_min_level"], self.settings["silence_seconds"])
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                blocksize=BLOCK, callback=callback):
                self.available = True
                self.on_status("ready")
                while True:
                    block = audio_q.get()
                    if not self.enabled.is_set() or self._is_muted():
                        seg.reset()
                        continue
                    audio = seg.feed(block, np)
                    if audio is not None and not self._is_muted():
                        self._transcribe(model, audio)
        except Exception as e:
            logging.exception("Listener stopped")
            self.on_status(f"Listening error: {e}")

    def _transcribe(self, model, audio):
        try:
            segments, _ = model.transcribe(
                audio,
                language=self.settings["language"],
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            text = clean_transcript(list(segments))
            if text and not self._is_muted():
                logging.info("Heard: %s", text)
                self.on_text(text)
        except Exception:
            logging.exception("Transcription failed")

"""Keeps track of the current conversation (what I said, what they said)."""
import datetime
import logging
import os
import time

ME = "Me"
THEM = "Them"


class Conversation:
    def __init__(self, reset_minutes=15, transcript_dir=None):
        self.reset_minutes = reset_minutes
        self.transcript_dir = transcript_dir
        self.turns = []  # list of (speaker, text, timestamp)
        self.last_activity = 0.0

    def _maybe_reset(self):
        if self.turns and time.time() - self.last_activity > self.reset_minutes * 60:
            self.reset()

    def reset(self):
        self.turns = []

    def add(self, speaker, text):
        text = text.strip()
        if not text:
            return
        self._maybe_reset()
        now = time.time()
        self.turns.append((speaker, text, now))
        self.last_activity = now
        self._save_line(speaker, text)

    def transcript(self, max_turns=30):
        self._maybe_reset()
        return "\n".join(f"{s}: {t}" for s, t, _ in self.turns[-max_turns:])

    def last_speaker(self):
        self._maybe_reset()
        return self.turns[-1][0] if self.turns else None

    def last(self, speaker):
        for s, t, _ in reversed(self.turns):
            if s == speaker:
                return t
        return None

    def _save_line(self, speaker, text):
        if not self.transcript_dir:
            return
        try:
            os.makedirs(self.transcript_dir, exist_ok=True)
            now = datetime.datetime.now()
            path = os.path.join(self.transcript_dir, now.strftime("%Y-%m-%d") + ".txt")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{now:%H:%M}] {speaker}: {text}\n")
        except Exception:
            logging.exception("Could not save transcript")

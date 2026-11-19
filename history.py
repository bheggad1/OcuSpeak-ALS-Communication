"""Remembers every sentence the user has spoken, so it can suggest them again."""
import json
import logging
import os
import re
import threading
import time

WORD_RE = re.compile(r"[a-z0-9']+")


def words(text):
    return WORD_RE.findall(text.lower())


class PhraseHistory:
    def __init__(self, path, import_paths=()):
        self.path = path
        self.lock = threading.Lock()
        self.items = {}  # sentence -> {"count": int, "last": timestamp}
        self._load(import_paths)

    # ---------- storage ----------
    def _load(self, import_paths):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.items = json.load(f)
                return
            except Exception:
                logging.exception("history.json is damaged; starting fresh")
                os.replace(self.path, self.path + ".bad")
        for path in import_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        phrases = json.load(f)
                    for sentence, count in phrases.items():
                        if isinstance(count, int) and sentence.strip():
                            self.items[sentence.strip()] = {"count": count, "last": 0}
                    logging.info("Imported %d phrases from %s", len(self.items), path)
                    self._save()
                    break
                except Exception:
                    logging.exception("Could not import %s", path)

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ---------- public ----------
    def add(self, sentence):
        sentence = sentence.strip()
        if not sentence:
            return
        with self.lock:
            key = next((k for k in self.items if k.lower() == sentence.lower()), sentence)
            entry = self.items.setdefault(key, {"count": 0, "last": 0})
            entry["count"] += 1
            entry["last"] = time.time()
            try:
                self._save()
            except Exception:
                logging.exception("Could not save history")

    def top(self, n=15):
        with self.lock:
            ranked = sorted(self.items.items(), key=lambda kv: (kv[1]["count"], kv[1]["last"]), reverse=True)
        return [s for s, _ in ranked[:n]]

    def match(self, typed, n=3):
        """Past sentences that fit what's been typed so far (instant, no internet)."""
        typed_l = typed.lower()
        tokens = words(typed_l)
        if not tokens:
            return []
        ends_word = typed_l[-1:] in (" ", ".", ",", "?", "!")
        full, partial = (tokens, None) if ends_word else (tokens[:-1], tokens[-1])
        now = time.time()
        scored = []
        with self.lock:
            snapshot = list(self.items.items())
        for sentence, meta in snapshot:
            ws = words(sentence)
            wset = set(ws)
            if not all(t in wset for t in full):
                continue
            if partial and not any(w.startswith(partial) for w in ws):
                continue
            days = (now - meta.get("last", 0)) / 86400
            score = meta.get("count", 1) + 3.0 / (1.0 + days)
            if sentence.lower().startswith(typed_l.strip()):
                score += 5
            scored.append((score, sentence))
        scored.sort(reverse=True)
        return [s for _, s in scored[:n]]

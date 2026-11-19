"""Speaks sentences out loud using the computer's built-in voice."""
import logging
import queue
import shutil
import subprocess
import sys
import threading

_PS_SCRIPT = (
    "Add-Type -AssemblyName System.Speech;"
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$s.Rate = {rate};"
    "{voice}"
    "[Console]::InputEncoding = [Text.Encoding]::UTF8;"
    "$t = [Console]::In.ReadToEnd();"
    "$s.Speak($t)"
)


class Speaker:
    def __init__(self, voice_name="", rate=0, on_start=None, on_end=None):
        self.voice_name = voice_name or ""
        self.rate = max(-10, min(10, int(rate or 0)))
        self.on_start = on_start or (lambda: None)
        self.on_end = on_end or (lambda: None)
        self.q = queue.Queue()
        threading.Thread(target=self._run, daemon=True, name="speaker").start()

    def say(self, text):
        if text and text.strip():
            self.q.put(text.strip())

    def _run(self):
        speak = self._make_backend()
        while True:
            text = self.q.get()
            self.on_start()
            try:
                speak(text)
            except Exception:
                logging.exception("Speech failed")
            finally:
                self.on_end()

    def _make_backend(self):
        if sys.platform == "win32":
            try:
                import pythoncom
                import win32com.client

                pythoncom.CoInitialize()
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                if self.voice_name:
                    for token in voice.GetVoices():
                        if self.voice_name.lower() in token.GetDescription().lower():
                            voice.Voice = token
                            break
                voice.Rate = self.rate
                logging.info("Speech: Windows SAPI")
                return lambda t: voice.Speak(t)
            except Exception:
                logging.exception("SAPI unavailable, using PowerShell speech")
                return self._powershell
        if sys.platform == "darwin":
            return lambda t: subprocess.run(["say", t], check=False)
        if shutil.which("espeak"):
            return lambda t: subprocess.run(["espeak", t], check=False)
        return lambda t: print("SAY:", t)

    def _powershell(self, text):
        voice = ""
        if self.voice_name:
            safe = self.voice_name.replace("'", "''")
            voice = f"try {{ $s.SelectVoice('{safe}') }} catch {{}};"
        script = _PS_SCRIPT.format(rate=self.rate, voice=voice)
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            input=text.encode("utf-8"),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )

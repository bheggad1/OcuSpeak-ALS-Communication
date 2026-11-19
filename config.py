"""Settings, file locations and the Claude API key."""
import json
import logging
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
PROFILE_FILE = os.path.join(APP_DIR, "about_me.txt")
API_KEY_FILE = os.path.join(APP_DIR, "api_key.txt")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
TRANSCRIPT_DIR = os.path.join(DATA_DIR, "conversations")
LOG_FILE = os.path.join(DATA_DIR, "app.log")

# Phrase lists ({"sentence": count}) imported into the history on first run, if present.
IMPORT_PHRASE_FILES = [
    os.path.join(APP_DIR, "sentences.json"),
    os.path.join(DATA_DIR, "sentences.json"),
]

DEFAULTS = {
    # Prediction
    "model": "claude-haiku-5-5",
    "max_words": 7,
    "typing_pause_seconds": 0.6,
    "request_timeout_seconds": 12,
    # Look and feel
    "font_size": 20,
    "dwell_enabled": True,
    "dwell_seconds": 1.0,
    "borderless": True,
    # Keyboard docking (Windows On-Screen Keyboard window class)
    "keyboard_window_classes": ["OSKMainClass"],
    "launch_keyboard_on_start": True,
    "close_keyboard_on_exit": True,
    # Listening to the other person
    "listening_enabled": True,
    "listen_on_start": True,
    "whisper_model": "base.en",
    "language": "en",
    "mic_min_level": 0.01,
    "silence_seconds": 0.9,
    # Voice
    "voice_name": "",
    "voice_rate": 0,
    # Conversation memory
    "new_conversation_after_minutes": 15,
    "save_transcripts": True,
}


def setup_logging():
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def load_settings():
    settings = dict(DEFAULTS)
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=2)
        return settings
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            user = json.load(f)
        for key, value in user.items():
            if key in DEFAULTS:
                settings[key] = value
    except Exception:
        logging.exception("Could not read settings.json; using defaults")
    if sys.platform != "win32":
        # Borderless windows can't take keyboard input on macOS/Linux.
        settings["borderless"] = False
    return settings


def load_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(API_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def save_api_key(key):
    with open(API_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip())

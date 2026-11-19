# OcuSpeak

OcuSpeak puts a bar of AI sentence suggestions directly above the Windows On-Screen Keyboard. It listens to the person you're talking with and suggests three short replies, written in your own voice using your profile. When you pick one, it's spoken out loud.

```
┌──────────────────────────────────────────────────────────────┐
│ They said: How was physical therapy?    [Mic: ON][New chat][✕]│
│ [ typed text box ............................ ] [Speak][Clear] │
│ [ It went really well ] [ Exhausting today ] [ Can we rest? ] │
├──────────────────────────────────────────────────────────────┤
│             Windows On-Screen Keyboard (unchanged)           │
└──────────────────────────────────────────────────────────────┘
```

## One-time setup (Windows laptop)

1. **Install Python 3.12** from python.org. On the first installer screen, tick **"Add python.exe to PATH"**.
2. **Copy this whole OcuSpeak folder** to the laptop, for example to the Desktop.
3. **Double-click `install.bat`.** It takes a few minutes.
4. **Get a Claude API key** at console.anthropic.com → API Keys. The first time you run the app it asks for the key and saves it in `api_key.txt`. Never share that file.
5. **Fill in `about_me.txt`** with names, interests, how you talk, and so on. The more detail, the better the suggestions. You can edit it at any time.
6. **Set up the keyboard:** open On-Screen Keyboard → Options → choose **"Hover over keys"** and set the hover time that works for you.
7. **Double-click `run.bat`** to start.

The first launch downloads the speech-recognition model (about 150 MB), so listening takes a minute to become ready the first time.

**Import an existing phrase list (optional):** put a `sentences.json` file (a list of sentences with how often each is used, e.g. `{"I need water": 3}`) in this folder before the first run. It gets imported automatically.

## Using it

- **Look at a suggestion** until the blue bar fills, and it's spoken. To pick again, look away and back. This stops double-picks.
- **Type** on the On-Screen Keyboard. As you type, suggestions update to include your words. Your own saved phrases appear instantly, and Claude's suggestions follow a moment later.
- **Speak** says whatever you typed. The keyboard's Enter key does the same.
- **Mic: ON/OFF** turns listening on or off. While on, whatever the other person says appears in yellow and the suggestions become replies to it. The mic is muted automatically while OcuSpeak is talking.
- **New chat** clears the conversation context. This also happens on its own after 15 quiet minutes.
- **✕** closes the app and the on-screen keyboard with it. It needs a **double-click** so you can't close it by accident with a glance.

## Settings (`settings.json`)

Open the file with Notepad, change a value, save, and restart the app.

| Setting | What it does |
|---|---|
| `dwell_seconds` | How long to look at a button before it fires (default 1.0) |
| `dwell_enabled` | Set to `false` if your eye-tracking software already clicks for you |
| `font_size` | Text size in the bar (default 20) |
| `max_words` | Longest suggestion length (default 7) |
| `model` | Claude model. `claude-haiku-5-5` is fastest. `claude-sonnet-5-5` is smarter but slower |
| `voice_name` | Part of a Windows voice name, e.g. `Zira` or `David`. Blank uses the default |
| `voice_rate` | Speaking speed from -10 to 10 |
| `listen_on_start` | Whether the mic starts on |
| `mic_min_level` | Raise it (e.g. 0.02) if background noise triggers listening. Lower it if quiet speech is missed |
| `silence_seconds` | How long a pause means the other person has finished talking |
| `whisper_model` | `base.en` (default), `small.en` (more accurate, slower) or `tiny.en` (fastest) |
| `new_conversation_after_minutes` | Quiet time before the conversation context resets |
| `save_transcripts` | Saves each day's conversation in `data/conversations/` |
| `launch_keyboard_on_start` / `close_keyboard_on_exit` | Open the on-screen keyboard with OcuSpeak and close it when OcuSpeak closes |
| `borderless` | Set to `false` if typing doesn't land in the text box (adds a title bar) |

## Files

- `about_me.txt`: your profile
- `data/history.json`: every sentence you've said, used to learn your phrases
- `data/conversations/`: daily transcripts (if turned on)
- `data/app.log`: error log. Send this along if something goes wrong

## Troubleshooting

- **Suggestions say "Can't reach Claude"**: check the internet connection and that the key in `api_key.txt` is correct. Your saved phrases still work offline.
- **Typing doesn't appear in the box**: look at the bar once so it gets focus. If that doesn't help, set `borderless` to `false`.
- **To see errors live**, start with `run_with_log_window.bat` instead of `run.bat`.

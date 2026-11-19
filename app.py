"""OcuSpeak: AI sentence suggestions docked above the Windows On-Screen Keyboard."""
import logging
import queue
import signal
import sys
import threading
import time
import tkinter as tk
from tkinter import simpledialog

import config
import dock
from conversation import ME, THEM, Conversation
from history import PhraseHistory
from listener import Listener
from predictor import Predictor, finalize
from speech import Speaker

IS_MAC = sys.platform == "darwin"

if IS_MAC:
    # Matches the macOS Accessibility Keyboard: black panel, outlined rounded keys.
    COLORS = {
        "bg": "#000000",
        "btn": "#000000",
        "border": "#6b6b6e",
        "btn_hover": "#2c2c2e",
        "text": "#ffffff",
        "sub": "#8e8e93",
        "progress": "#0a84ff",
        "fire": "#30d158",
        "them": "#ffd60a",
        "error": "#ff6961",
        "entry_bg": "#1c1c1e",
        "entry_fg": "#ffffff",
    }
    WEIGHT = "normal"
    RADIUS = 10
else:
    COLORS = {
        "bg": "#101418",
        "btn": "#26303a",
        "border": "",
        "btn_hover": "#2f5d8a",
        "text": "#f2f5f7",
        "sub": "#8d9daa",
        "progress": "#4da3ff",
        "fire": "#3ecf8e",
        "them": "#ffd479",
        "error": "#ff8a7a",
        "entry_bg": "#ffffff",
        "entry_fg": "#000000",
    }
    WEIGHT = "bold"
    RADIUS = 0
DOCK_GAP = 8  # pixels between the bar and the keyboard


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    if r <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **kw)
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


STARTERS = ["Hi, how are you?", "Yes", "No"]

if sys.platform == "win32":
    FONT = "Segoe UI"
elif sys.platform == "darwin":
    FONT = ".AppleSystemUIFont"  # the Mac system font, same as the keyboard
else:
    FONT = "DejaVu Sans"


class DwellButton(tk.Canvas):
    """A button you can press by looking at it. A bar fills up; when it's full, it fires.

    After firing, you have to look away and back before it can fire again,
    so it never triggers twice by accident.
    """

    LEAVE_GRACE_MS = 150  # forgive tiny eye-tracker jitter off the edge

    def __init__(self, master, app, text, command, font, height, width=120, dwell=True, bind_double=False):
        super().__init__(master, height=height, width=width, highlightthickness=0, bd=0,
                         bg=COLORS["bg"], cursor="hand2")
        self.app, self.command, self.font, self.text = app, command, font, text
        self.dwell = dwell
        self.enabled = True
        self.hover = False
        self.armed = True
        self.flash = False
        self.progress = 0.0
        self.start_t = None
        self.tick_id = None
        self.leave_id = None
        self.last_fire = 0.0
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Configure>", lambda e: self.redraw())
        if bind_double:
            self.bind("<Double-Button-1>", lambda e: self.command())
        else:
            self.bind("<Button-1>", self._click)

    def set_text(self, text):
        self.text = text
        self.enabled = bool(text.strip())
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2:
            return
        pad = 4
        fill = COLORS["fire"] if self.flash else (
            COLORS["btn_hover"] if self.hover and self.enabled else COLORS["btn"])
        border = COLORS["border"]
        rounded_rect(self, pad, pad, w - pad, h - pad, RADIUS, fill=fill,
                     outline=border, width=2 if border else 0)
        if self.progress > 0:
            inset = pad + 4
            rounded_rect(self, inset, h - inset - 7, inset + (w - 2 * inset) * self.progress, h - inset,
                         3 if RADIUS else 0, fill=COLORS["progress"], outline="")
        self.create_text(w / 2, h / 2, text=self.text, font=self.font, justify="center",
                         fill=COLORS["text"] if self.enabled else COLORS["sub"],
                         width=max(10, w - 2 * pad - 16))

    def _enter(self, _):
        if self.leave_id:  # came back within the grace period: keep dwelling
            self.after_cancel(self.leave_id)
            self.leave_id = None
        self.hover = True
        if self.dwell and self.app.dwell_enabled and self.armed and self.enabled and self.start_t is None:
            self.start_t = time.time()
            self._tick()
        self.redraw()

    def _leave(self, _):
        self.hover = False
        if self.leave_id:
            self.after_cancel(self.leave_id)
        self.leave_id = self.after(self.LEAVE_GRACE_MS, self._really_left)

    def _really_left(self):
        self.leave_id = None
        self.armed = True
        self._cancel()
        self.redraw()

    def _cancel(self):
        if self.tick_id:
            self.after_cancel(self.tick_id)
            self.tick_id = None
        self.start_t = None
        self.progress = 0.0

    def _tick(self):
        self.tick_id = None
        if self.start_t is None:
            return
        self.progress = min(1.0, (time.time() - self.start_t) / max(0.2, self.app.dwell_seconds))
        self.redraw()
        if self.progress >= 1.0:
            self._fire()
        else:
            self.tick_id = self.after(30, self._tick)

    def _click(self, _):
        if time.time() - self.last_fire > 1.0:  # ignore a click right after a dwell fire
            self._fire()

    def _fire(self):
        self._cancel()
        if not self.enabled:
            return
        self.armed = False
        self.last_fire = time.time()
        self.flash = True
        self.redraw()
        self.after(250, self._unflash)
        try:
            self.command()
        except Exception:
            logging.exception("Button action failed")

    def _unflash(self):
        self.flash = False
        self.redraw()


class App:
    def __init__(self):
        config.setup_logging()
        self.settings = s = config.load_settings()
        dock.enable_dpi_awareness()

        self.root = tk.Tk()
        self.root.title("OcuSpeak")
        self.root.configure(bg=COLORS["bg"])
        self.dwell_enabled = bool(s["dwell_enabled"])
        self.dwell_seconds = float(s["dwell_seconds"])

        api_key = config.load_api_key() or self._ask_for_key()
        self.history = PhraseHistory(config.HISTORY_FILE, config.IMPORT_PHRASE_FILES)
        self.conv = Conversation(s["new_conversation_after_minutes"],
                                 config.TRANSCRIPT_DIR if s["save_transcripts"] else None)
        self.predictor = Predictor(s, api_key, config.PROFILE_FILE, self.history)

        self.ui_q = queue.Queue()
        self.listener = Listener(s, on_text=lambda t: self.ui_q.put(("heard", t)),
                                 on_status=lambda m: self.ui_q.put(("listen_status", m)))
        self.speaker = Speaker(s["voice_name"], s["voice_rate"],
                               on_start=self.listener.mute, on_end=self.listener.unmute)

        self.req_id = 0
        self.typing_after = None
        self.last_text = ""
        self.suggestions = ["", "", ""]
        self.mic_on = bool(s["listening_enabled"] and s["listen_on_start"])
        self.listen_status = ""
        self._geom = None

        self._build_ui()
        if s["borderless"]:
            self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        if s["launch_keyboard_on_start"] and not dock.find_keyboard_rect(s["keyboard_window_classes"]):
            dock.launch_keyboard()
        if s["listening_enabled"]:
            self.listener.set_enabled(self.mic_on)
            self.listener.start()
        else:
            self.mic_btn.set_text("Mic: n/a")

        self._set_suggestions(finalize(self.history.top(3), STARTERS))
        if self.predictor.problem:
            self._status(self.predictor.problem, error=True)
        self._request()
        self.root.after(50, self._poll)
        self.root.after(200, self._dock_loop)
        self.root.after(400, self.entry.focus_force)
        self.root.bind("<Enter>", self._grab_focus)

    # ---------- setup ----------
    def _ask_for_key(self):
        key = simpledialog.askstring(
            "Claude API key",
            "Paste your Claude API key (from console.anthropic.com).\nIt is saved in api_key.txt in this folder.",
            parent=self.root)
        if key and key.strip():
            config.save_api_key(key)
            return key.strip()
        return ""

    def _build_ui(self):
        fs = int(self.settings["font_size"])
        small = (FONT, max(11, int(fs * 0.7)))
        big = (FONT, fs)
        bold = (FONT, fs, WEIGHT)
        tool_h = int(fs * 2.3)

        top = tk.Frame(self.root, bg=COLORS["bg"])
        top.pack(fill="x", padx=6, pady=(4, 0))
        self.heard_label = tk.Label(top, text="", font=small, fg=COLORS["them"], bg=COLORS["bg"], anchor="w")
        self.heard_label.pack(side="left", fill="x", expand=True)
        self.status_label = tk.Label(top, text="", font=small, fg=COLORS["sub"], bg=COLORS["bg"])
        self.status_label.pack(side="left", padx=8)
        btn_font = (FONT, max(11, int(fs * 0.7)), WEIGHT)
        self.mic_btn = DwellButton(top, self, "", self._toggle_mic, btn_font, int(fs * 1.9), width=int(fs * 6.5))
        self.mic_btn.pack(side="left")
        DwellButton(top, self, "New chat", self._new_chat, btn_font, int(fs * 1.9), width=int(fs * 6)).pack(side="left")
        DwellButton(top, self, "✕", self.quit, btn_font, int(fs * 1.9), width=int(fs * 2.4),
                    dwell=False, bind_double=True).pack(side="left")
        self._update_mic_btn()

        mid = tk.Frame(self.root, bg=COLORS["bg"])
        mid.pack(fill="x", padx=6, pady=2)
        self.entry = tk.Entry(mid, font=big, relief="flat", bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                              insertbackground=COLORS["entry_fg"], insertwidth=3,
                              highlightthickness=2, highlightbackground=COLORS["border"] or COLORS["bg"],
                              highlightcolor=COLORS["progress"])
        self.entry.pack(side="left", fill="both", expand=True, padx=4, pady=4, ipady=int(fs * 0.3))
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Return>", lambda e: self.speak(self.entry.get()))
        DwellButton(mid, self, "Speak", lambda: self.speak(self.entry.get()), bold, tool_h,
                    width=int(fs * 6)).pack(side="left")
        DwellButton(mid, self, "Clear", self._clear, bold, tool_h, width=int(fs * 5)).pack(side="left")

        bottom = tk.Frame(self.root, bg=COLORS["bg"])
        bottom.pack(fill="x", padx=6, pady=(0, 6))
        self.sugg_btns = []
        for i in range(3):
            b = DwellButton(bottom, self, "", lambda i=i: self.speak(self.suggestions[i]), bold, int(fs * 3.4))
            b.pack(side="left", fill="x", expand=True)
            self.sugg_btns.append(b)

    # ---------- placement above the keyboard ----------
    def _dock_loop(self):
        try:
            self.root.update_idletasks()
            h = self.root.winfo_reqheight()
            rect = dock.find_keyboard_rect(self.settings["keyboard_window_classes"])
            if rect:
                left, top, right, bottom = rect
                x, w = left, right - left
                # On a Mac the window has a title bar above the content; leave room for it.
                title_bar = max(0, self.root.winfo_rooty() - self.root.winfo_y())
                if IS_MAC and not title_bar and not self.settings["borderless"]:
                    title_bar = 28  # standard Mac title bar height, before the window reports it
                y = top - DOCK_GAP - h - title_bar
                if y < 0:
                    y = bottom + DOCK_GAP
            else:
                area = dock.work_area() or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
                x, w, y = area[0], area[2] - area[0], area[3] - h
            screen_h = self.root.winfo_screenheight()
            y = max(0, min(y, screen_h - h))  # never place the bar off-screen
            geom = f"{w}x{h}+{x}+{y}"
            if geom != self._geom:
                self.root.geometry(geom)
                self._geom = geom
        except Exception:
            logging.exception("Docking failed")
        self.root.after(400, self._dock_loop)

    def _grab_focus(self, _=None):
        # When the eyes come to the bar, make sure keyboard typing lands in our text box.
        if self.root.focus_get() is None:
            self.entry.focus_force()

    # ---------- predictions ----------
    def _context_mode(self):
        if self.conv.last_speaker() == THEM:
            return "reply", self.conv.last(THEM)
        return "next", ""

    def _request(self, mode=None, text=""):
        if mode is None:
            mode, text = self._context_mode()
        if not self.predictor.client:
            return
        self.req_id += 1
        rid = self.req_id
        transcript, last_me = self.conv.transcript(), self.conv.last(ME)
        fallbacks = self.history.match(text, 3) if mode == "keywords" else self.history.top(3)
        self._status("thinking…")

        def work():
            try:
                options = self.predictor.predict(mode, text, transcript, last_me, fallbacks)
                self.ui_q.put(("suggest", rid, options))
            except Exception as e:
                logging.exception("Prediction failed")
                self.ui_q.put(("error", rid, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _on_key(self, _=None):
        text = self.entry.get()
        if text == self.last_text:
            return
        self.last_text = text
        if self.typing_after:
            self.root.after_cancel(self.typing_after)
            self.typing_after = None
        if not text.strip():
            self._request()
            return
        local = self.history.match(text, 3)
        if local:
            self._set_suggestions(finalize(local, self.suggestions))
        delay = 50 if text.endswith(" ") else int(float(self.settings["typing_pause_seconds"]) * 1000)
        self.typing_after = self.root.after(delay, lambda: self._request("keywords", self.entry.get()))

    def _set_suggestions(self, options):
        self.suggestions = list(options)
        for btn, text in zip(self.sugg_btns, self.suggestions):
            btn.set_text(text)

    # ---------- actions ----------
    def speak(self, sentence):
        sentence = (sentence or "").strip()
        if not sentence:
            return
        self.speaker.say(sentence)
        self.conv.add(ME, sentence)
        self.history.add(sentence)
        self.entry.delete(0, tk.END)
        self.last_text = ""
        self._request("next")
        self.entry.focus_force()

    def _clear(self):
        self.entry.delete(0, tk.END)
        self.last_text = ""
        self._request()
        self.entry.focus_force()

    def _new_chat(self):
        self.conv.reset()
        self.heard_label.config(text="")
        self._request("next")
        self.entry.focus_force()

    def _toggle_mic(self):
        if not self.settings["listening_enabled"]:
            return
        self.mic_on = not self.mic_on
        self.listener.set_enabled(self.mic_on)
        self._update_mic_btn()
        self.entry.focus_force()

    def _update_mic_btn(self):
        self.mic_btn.set_text("Mic: ON" if self.mic_on else "Mic: OFF")

    def _on_heard(self, text):
        self.conv.add(THEM, text)
        self.heard_label.config(text=f"They said: {text}")
        typed = self.entry.get()
        if typed.strip():
            self._request("keywords", typed)
        else:
            self._request("reply", text)

    def _status(self, text, error=False):
        self.status_label.config(text=text, fg=COLORS["error"] if error else COLORS["sub"])

    # ---------- background results ----------
    def _poll(self):
        try:
            while True:
                item = self.ui_q.get_nowait()
                kind = item[0]
                if kind == "suggest" and item[1] == self.req_id:
                    self._set_suggestions(item[2])
                    self._status("")
                elif kind == "error" and item[1] == self.req_id:
                    self._status("Can't reach Claude – showing saved phrases", error=True)
                elif kind == "heard":
                    self._on_heard(item[1])
                elif kind == "listen_status":
                    self.listen_status = item[1]
                    if item[1] != "ready":
                        self._status(item[1], error="error" in item[1].lower() or "off" in item[1].lower())
                    else:
                        self._status("")
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def quit(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _shutdown(self):
        if self.settings["close_keyboard_on_exit"]:
            dock.close_keyboard(self.settings["keyboard_window_classes"])

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.quit)  # the window's own close button
        signal.signal(signal.SIGINT, lambda *_: self.root.after(0, self.quit))  # Control + C
        try:
            self.root.mainloop()
        except KeyboardInterrupt:  # Control + C in the terminal
            pass
        finally:
            self._shutdown()


if __name__ == "__main__":
    App().run()

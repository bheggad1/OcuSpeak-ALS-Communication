"""Asks Claude for 3 sentence predictions."""
import datetime
import logging
import os
import re

try:
    import anthropic
except ImportError:  # app still runs with saved phrases only
    anthropic = None

TOOL = {
    "name": "give_options",
    "description": "Return exactly 3 sentence options for the user to pick from.",
    "input_schema": {
        "type": "object",
        "properties": {
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            }
        },
        "required": ["options"],
    },
}

_LEAD_RE = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s*')
_QUOTES = "\"'“”‘’`"


def clean_option(text):
    text = _LEAD_RE.sub("", str(text)).strip().strip(_QUOTES).strip()
    return re.sub(r"\s+", " ", text)


def finalize(options, fallbacks=(), n=3):
    """Clean, de-duplicate and pad to exactly n options."""
    out, seen = [], set()
    for opt in list(options) + list(fallbacks):
        opt = clean_option(opt)
        if opt and opt.lower() not in seen:
            seen.add(opt.lower())
            out.append(opt)
        if len(out) == n:
            break
    while len(out) < n:
        out.append("")
    return out


class Predictor:
    def __init__(self, settings, api_key, profile_path, history):
        self.settings = settings
        self.profile_path = profile_path
        self.history = history
        self._profile = ("", None)
        self.client = None
        self.problem = None
        if anthropic is None:
            self.problem = "The 'anthropic' package isn't installed (run install.bat)"
        elif not api_key:
            self.problem = "No Claude API key"
        else:
            self.client = anthropic.Anthropic(
                api_key=api_key,
                timeout=settings["request_timeout_seconds"],
                max_retries=1,
            )

    # ---------- prompt pieces ----------
    def profile_text(self):
        """Re-reads about_me.txt whenever it changes, so edits apply instantly."""
        try:
            mtime = os.path.getmtime(self.profile_path)
        except OSError:
            return ""
        if self._profile[1] != mtime:
            with open(self.profile_path, "r", encoding="utf-8") as f:
                lines = [l.rstrip() for l in f if not l.lstrip().startswith("#")]
            self._profile = ("\n".join(lines).strip(), mtime)
        return self._profile[0]

    def system_prompt(self):
        profile = self.profile_text() or "(No profile written yet.)"
        top = self.history.top(15)
        phrases = "\n".join(f"- {p}" for p in top) if top else "(none yet)"
        max_words = self.settings["max_words"]
        return f"""You are the sentence-prediction engine inside an AAC (augmentative and alternative communication) app. The user has ALS and types with their eyes, so every letter costs real effort. Your job is to predict the exact sentence they want to say, in their own voice, so they can pick it with one glance.

About the user (written by them or their family):
<profile>
{profile}
</profile>

Phrases the user says most often:
{phrases}

Rules:
- Write in first person as the user, speaking to the person in front of them.
- Each option is at most {max_words} words: short, natural, spoken English, the way this user actually talks.
- Give exactly 3 options with clearly different meanings, not rephrasings of one idea. A good spread is often: one positive or yes, one negative or different direction, one question or added detail.
- Use real names from the profile when they fit. Never invent facts about the user's life that aren't in the profile or the conversation.
- No quotation marks, numbering or emojis."""

    def user_prompt(self, mode, text, transcript, last_me):
        now = datetime.datetime.now()
        parts = [f"It is {now:%A} at {now:%I:%M %p}.".replace(" 0", " ")]
        parts.append("Conversation so far (oldest first):\n" + transcript if transcript else "No conversation yet.")
        if mode == "reply":
            parts.append(f'The other person just said: "{text}"\nGive 3 things I might say back.')
        elif mode == "keywords":
            parts.append(
                f'I have started typing: "{text}"\n'
                "Each option must build on what I typed: keep my words (fix obvious typos), "
                "and if the last word looks unfinished, complete it. Use the conversation for context."
            )
        elif last_me:
            parts.append(
                f'I just said: "{last_me}"\n'
                "Predict what I'll want to say next: a follow-up, or a reply to how they probably responded."
            )
        else:
            parts.append("Suggest 3 natural things I might say to start a conversation, fitting the time of day and my life.")
        return "\n\n".join(parts)

    # ---------- main call ----------
    def predict(self, mode, text, transcript, last_me, fallbacks=()):
        if not self.client:
            raise RuntimeError(self.problem or "Claude is not available")
        response = self.client.messages.create(
            model=self.settings["model"],
            max_tokens=300,
            system=self.system_prompt(),
            tools=[TOOL],
            tool_choice={"type": "tool", "name": TOOL["name"]},
            messages=[{"role": "user", "content": self.user_prompt(mode, text, transcript, last_me)}],
        )
        options = []
        for block in response.content:
            if getattr(block, "type", "") == "tool_use":
                options = block.input.get("options", [])
                break
            if getattr(block, "type", "") == "text":
                options = [l for l in block.text.splitlines() if l.strip()]
        logging.info("Claude (%s, %r) -> %s", mode, text, options)
        return finalize(options, fallbacks)

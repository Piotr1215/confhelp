"""Translate each source's key spelling into one canonical form.

zsh writes alt+shift+g as ^[G, tmux as M-G, vim as <M-G>, Claude Code as
meta+shift+g and alacritty as Shift|Alt+G. A search for one spelling misses the
others, so a binding looks missing when it is not. normalize_key turns all of
them into the short M/C/S form followed by the spelled-out words in brackets:
"M-S-g (alt+shift+g)".

A section opts in with notation = "zsh" | "tmux" | "vim" | "plus". "plus" reads
modifier words joined by + - or | (ctrl+x, ctrl-x, Control+X, Shift|Control+X)
and the short M-/C-/S- prefixes, so it also covers mixed rows such as fzf's
"M-x ctrl-l". A key that does not parse is returned unchanged.
"""

import re
from typing import NamedTuple, Optional

# Short form follows tmux: M-C-S-x. Words follow how a key is spoken:
# super+ctrl+alt+shift+x.
SHORT = {"alt": "M", "ctrl": "C", "shift": "S", "super": "Super"}
SHORT_ORDER = ["alt", "ctrl", "shift", "super"]
WORD_ORDER = ["super", "ctrl", "alt", "shift"]

MODIFIER_WORDS = {
    "m": "alt", "a": "alt", "alt": "alt", "meta": "alt", "opt": "alt", "option": "alt",
    "c": "ctrl", "ctrl": "ctrl", "control": "ctrl", "primary": "ctrl",
    "s": "shift", "shift": "shift",
    "d": "super", "super": "super", "cmd": "super", "command": "super",
    "win": "super", "hyper": "super",
}

NAMED = {
    "tab": "Tab", "space": "Space", "spc": "Space",
    "enter": "Enter", "return": "Enter", "cr": "Enter",
    "escape": "Escape", "esc": "Escape",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "home": "Home", "end": "End",
    "pageup": "PageUp", "pgup": "PageUp", "ppage": "PageUp", "prior": "PageUp",
    "pagedown": "PageDown", "pgdn": "PageDown", "npage": "PageDown", "next": "PageDown",
    "insert": "Insert", "ins": "Insert", "ic": "Insert",
    "delete": "Delete", "del": "Delete", "dc": "Delete",
    "backspace": "BSpace", "bspace": "BSpace", "bs": "BSpace",
    **{f"f{n}": f"F{n}" for n in range(1, 25)},
}
WORD_NAME = {"BSpace": "backspace"}

# xterm CSI sequences: ^[[1;5C is ctrl+right. The modifier parameter minus one
# is a bit field: 1 shift, 2 alt, 4 ctrl.
CSI_FINAL = {"A": "Up", "B": "Down", "C": "Right", "D": "Left", "H": "Home", "F": "End"}
CSI_TILDE = {
    "1": "Home", "2": "Insert", "3": "Delete", "4": "End", "5": "PageUp", "6": "PageDown",
    "7": "Home", "8": "End", "15": "F5", "17": "F6", "18": "F7", "19": "F8",
    "20": "F9", "21": "F10", "23": "F11", "24": "F12",
}
SS3 = {"A": "Up", "B": "Down", "C": "Right", "D": "Left", "H": "Home", "F": "End",
       "P": "F1", "Q": "F2", "R": "F3", "S": "F4"}
# Control characters a terminal sends for a named key rather than ctrl+letter.
CTRL_NAMED = {"m": ("Enter", set()), "i": ("Tab", set()), "@": ("Space", {"ctrl"}),
              "?": ("BSpace", set())}


class Stroke(NamedTuple):
    mods: frozenset
    key: str

    def short(self) -> str:
        return "-".join([SHORT[m] for m in SHORT_ORDER if m in self.mods] + [self.key])

    def words(self) -> str:
        key = WORD_NAME.get(self.key, self.key)
        if key in NAMED.values() or len(key) == 1:
            key = key.lower()
        return "+".join([m for m in WORD_ORDER if m in self.mods] + [key])


def _stroke(mods, key: str, shift_on_upper: bool) -> Stroke:
    """Build a stroke, naming the key and reading an uppercase letter as shift."""
    mods = set(mods)
    named = NAMED.get(key.lower()) if len(key) > 1 else None
    if named:
        key = named
    elif len(key) == 1 and key.isalpha():
        if key.isupper() and shift_on_upper and "ctrl" not in mods:
            mods.add("shift")
        key = key.lower()
    return Stroke(frozenset(mods), key)


def _split_modifiers(token: str) -> tuple[set, str]:
    """Peel modifier prefixes such as ctrl+, C-, Shift| off a token."""
    mods = set()
    while True:
        m = re.match(r"([A-Za-z]+)[-+|](.+)$", token)
        if not m or m.group(1).lower() not in MODIFIER_WORDS:
            return mods, token
        mods.add(MODIFIER_WORDS[m.group(1).lower()])
        token = m.group(2)


def _parse_tmux(raw: str) -> list[Stroke]:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1]
    else:
        raw = re.sub(r"\\(.)", r"\1", raw)
    mods, key = _split_modifiers(raw)
    return [_stroke(mods, key, shift_on_upper=True)]


def _parse_plus(raw: str) -> list[Stroke]:
    # A generated row may already carry its own alias, "ctrl+alt+h (M-C-h)".
    raw = re.sub(r"\s+\([^()]*\)$", "", raw)
    strokes = []
    for token in raw.split():
        mods, key = _split_modifiers(token)
        if len(key) == 1:
            key = key.lower()
        strokes.append(_stroke(mods, key, shift_on_upper=False))
    return strokes


def _zsh_events(raw: str) -> list[tuple[str, str]]:
    """Split a bindkey string into ('esc', ''), ('ctrl', c) and ('char', c)."""
    events, i = [], 0
    while i < len(raw):
        c = raw[i]
        if c == "^" and i + 1 < len(raw):
            nxt = raw[i + 1]
            events.append(("esc", "") if nxt == "[" else ("ctrl", nxt))
            i += 2
        elif c == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt in "eE":
                events.append(("esc", ""))
                i += 2
            elif raw[i + 1:i + 3] in ("C-", "M-") and i + 3 < len(raw):
                if nxt == "M":
                    events.append(("esc", ""))
                    events.append(("char", raw[i + 3]))
                else:
                    events.append(("ctrl", raw[i + 3]))
                i += 4
            else:
                events.append(("char", nxt))
                i += 2
        else:
            events.append(("char", c))
            i += 1
    return events


def _zsh_single(event: tuple[str, str]) -> Stroke:
    kind, c = event
    if kind == "esc":
        return Stroke(frozenset(), "Escape")
    if kind == "ctrl":
        if c.lower() in CTRL_NAMED:
            name, mods = CTRL_NAMED[c.lower()]
            return Stroke(frozenset(mods), name)
        return Stroke(frozenset({"ctrl"}), c.lower())
    return _stroke(set(), c, shift_on_upper=True)


def _parse_zsh(raw: str) -> list[Stroke]:
    events = _zsh_events(raw)
    strokes, i = [], 0
    while i < len(events):
        kind, _ = events[i]
        nxt = events[i + 1] if i + 1 < len(events) else None
        if kind == "esc" and nxt == ("char", "["):
            j = i + 2
            body = ""
            while j < len(events) and events[j][0] == "char" and not re.match(r"[A-Za-z~]", events[j][1]):
                body += events[j][1]
                j += 1
            if j >= len(events) or events[j][0] != "char":
                raise ValueError(f"unterminated CSI in {raw!r}")
            strokes.append(_csi(body, events[j][1]))
            i = j + 1
        elif (kind == "esc" and nxt == ("char", "O") and i + 2 < len(events)
              and events[i + 2][0] == "char" and events[i + 2][1] in SS3):
            strokes.append(Stroke(frozenset(), SS3[events[i + 2][1]]))
            i += 3
        elif kind == "esc" and nxt is not None:
            inner = _zsh_single(nxt)
            strokes.append(Stroke(inner.mods | {"alt"}, inner.key))
            i += 2
        else:
            strokes.append(_zsh_single(events[i]))
            i += 1
    return strokes


def _csi(body: str, final: str) -> Stroke:
    params = body.split(";") if body else []
    if final == "Z":
        return Stroke(frozenset({"shift"}), "Tab")
    if final == "~":
        key = CSI_TILDE.get(params[0] if params else "")
    else:
        key = CSI_FINAL.get(final)
    if key is None:
        raise ValueError(f"unknown CSI {body!r}{final}")
    mods = set()
    if len(params) > 1:
        bits = int(params[1]) - 1
        if bits & 1:
            mods.add("shift")
        if bits & 2:
            mods.add("alt")
        if bits & 4:
            mods.add("ctrl")
    return Stroke(frozenset(mods), key)


def _parse_vim(raw: str) -> list[Stroke]:
    strokes = []
    for m in re.finditer(r"<([^<>]+)>|(.)", raw):
        inner, char = m.group(1), m.group(2)
        if char is not None:
            strokes.append(Stroke(frozenset(), char))
            continue
        mm = re.match(r"((?:[CMASDcmasd]-)+)(.+)$", inner)
        if mm:
            mods = {MODIFIER_WORDS[p.lower()] for p in mm.group(1).split("-") if p}
            strokes.append(_stroke(mods, mm.group(2), shift_on_upper=True))
        elif inner.lower() in NAMED:
            strokes.append(Stroke(frozenset(), NAMED[inner.lower()]))
        else:
            strokes.append(Stroke(frozenset(), f"<{inner}>"))
    return strokes


def _join_vim(parts: list[str], strokes: list[Stroke]) -> str:
    """Glue plain characters together (<leader>dt), space out modified keys."""
    out = ""
    for i, (part, stroke) in enumerate(zip(parts, strokes)):
        glue = i > 0 and not stroke.mods and not strokes[i - 1].mods
        out += part if glue or i == 0 else " " + part
    return out


PARSERS = {"zsh": _parse_zsh, "tmux": _parse_tmux, "vim": _parse_vim, "plus": _parse_plus}


def normalize_key(raw: str, notation: Optional[str]) -> str:
    """Return raw as "M-S-g (alt+shift+g)", or unchanged if it cannot be read."""
    parser = PARSERS.get(notation or "")
    if parser is None:
        return raw
    try:
        strokes = parser(raw.strip())
    except (ValueError, KeyError, IndexError):
        return raw
    if not strokes:
        return raw
    if notation == "vim":
        short = _join_vim([s.short() for s in strokes], strokes)
        words = _join_vim([s.words() for s in strokes], strokes)
    else:
        short = " ".join(s.short() for s in strokes)
        words = " ".join(s.words() for s in strokes)
    return short if words.lower() == short.lower() else f"{short} ({words})"

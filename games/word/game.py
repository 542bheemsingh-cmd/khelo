"""
Khelo Word - a daily word game, in the style of the "-dle" games.

Runs in the browser through Pyodide, like the rest of the Khelo arcade.

Guess a five letter word in six tries. After every guess each tile tells you
what it found:

    green  - the right letter in the right place
    amber  - that letter is in the word, somewhere else
    grey   - the word has no more of that letter

Two ways to play:

    Daily     - one word a day, the same word for everybody
    Practice  - a fresh word every time, as many as you like

The page calls:
    tap(x, y)     -> a click / tap on the canvas
    key(name)     -> a key was pressed: "a".."z", "enter", "back"
    update(dt)    -> advance the animation
    draw()        -> render a frame
    set_words(a, v) -> the answer list and the valid-guess list
"""

import json
import math
import random

import js

# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------
W, H = 480, 820

canvas = js.document.getElementById("game")
DPR = 1.0
try:
    DPR = float(js.devicePixelRatio or 1.0)
except Exception:
    DPR = 1.0
DPR = min(max(DPR, 1.0), 2.0)
canvas.width = int(W * DPR)
canvas.height = int(H * DPR)

# ---------------------------------------------------------------------------
# Screen-adaptive UI - see the other games for the reasoning
# ---------------------------------------------------------------------------
UI = 1.0
MIN_TOUCH = 0.0


def set_ui(scale):
    global UI, MIN_TOUCH
    try:
        s = float(scale)
    except Exception:
        return
    if s <= 0:
        return
    UI = max(1.0, min(1.35, 1.0 / s))
    MIN_TOUCH = min(66.0, 48.0 / s)


def _fit_font(spec):
    if UI <= 1.0 or "px" not in spec:
        return spec
    i = spec.index("px")
    j = i
    while j > 0 and (spec[j - 1].isdigit() or spec[j - 1] == "."):
        j -= 1
    try:
        size = float(spec[j:i])
    except ValueError:
        return spec
    return spec[:j] + str(int(round(size * UI))) + spec[i:]


def _fs(px, cap=1.35):
    return int(round(px * min(UI, cap)))


class _Ctx:
    def __init__(self, real):
        object.__setattr__(self, "_real", real)

    def __setattr__(self, name, value):
        if name == "font" and isinstance(value, str):
            value = _fit_font(value)
        setattr(self._real, name, value)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _touch(rect):
    rx, ry, rw, rh = rect
    if MIN_TOUCH > rw:
        rx -= (MIN_TOUCH - rw) / 2.0
        rw = MIN_TOUCH
    if MIN_TOUCH > rh:
        ry -= (MIN_TOUCH - rh) / 2.0
        rh = MIN_TOUCH
    return rx, ry, rw, rh


def _in(rect, x, y):
    rx, ry, rw, rh = _touch(rect)
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _hit(rect, x, y):
    """A plain hit test, for things that must stay precise (the keyboard)."""
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


ctx = _Ctx(canvas.getContext("2d"))
ctx.scale(DPR, DPR)

FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
BG_TOP = "#101a3a"
BG_BOT = "#05080f"
CORRECT = "#22c55e"
PRESENT = "#fbbf24"
ABSENT = "#39445c"
KEY_ABSENT = "#232b3d"      # clearly dimmer than a key you have not used
KEY_IDLE = "rgba(88, 102, 140, 0.95)"
TILE_EDGE = "rgba(150, 180, 240, 0.28)"
INK = "#eaf2ff"
DIM = "#8fa3c9"

# ---------------------------------------------------------------------------
# Board layout
# ---------------------------------------------------------------------------
TILE = 64
TGAP = 8
GW = 5 * TILE + 4 * TGAP
GX = (W - GW) / 2.0
GY = 84.0

KEY_H = 56
UNIT = 42
KGAP = 4
KB_Y = 556.0
KB_STEP = 66.0
KEY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
SAVE_KEY = "khelo_word_save"
MAX_TRIES = 6
WORD_LEN = 5

ANSWERS = []
VALID = set()

state = "menu"          # menu | play | over
mode = "daily"          # daily | practice
answer = ""
rows = []               # [(word, [marks])]
current = ""
message = ""
won = False
lost = False
reveal = None           # {"row": i, "t": 0.0}
shake = 0.0
bounce = 0.0
_t = 0.0
_menu_hit = []

stats = {"played": 0, "wins": 0, "streak": 0, "best": 0,
         "dist": [0, 0, 0, 0, 0, 0], "day": "", "done": False}

_rng = random.Random()


def _sound(name):
    try:
        js.playSound(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------
def set_words(answers_text, valid_text):
    """Called by the page once both lists have been fetched."""
    global ANSWERS, VALID
    a = [w.strip().lower() for w in (answers_text or "").split()]
    v = [w.strip().lower() for w in (valid_text or "").split()]
    ANSWERS = [w for w in a if len(w) == WORD_LEN and w.isalpha()]
    VALID = {w for w in v if len(w) == WORD_LEN and w.isalpha()} | set(ANSWERS)
    if not ANSWERS:
        ANSWERS = ["about"]
        VALID = {"about"}


# ---------------------------------------------------------------------------
# Days and saving
# ---------------------------------------------------------------------------
def _today():
    try:
        d = js.Date.new()
        return "%04d-%02d-%02d" % (int(d.getFullYear()),
                                   int(d.getMonth()) + 1, int(d.getDate()))
    except Exception:
        return "1970-01-01"


def _seed(s):
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _load():
    global stats
    try:
        raw = js.localStorage.getItem(SAVE_KEY)
        if raw:
            data = json.loads(raw)
            for k in stats:
                if k in data:
                    stats[k] = data[k]
            if not isinstance(stats.get("dist"), list) or len(stats["dist"]) != 6:
                stats["dist"] = [0, 0, 0, 0, 0, 0]
    except Exception:
        pass


def _save():
    try:
        js.localStorage.setItem(SAVE_KEY, json.dumps(stats))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Starting a game
# ---------------------------------------------------------------------------
def new_game(m=None):
    global state, mode, answer, rows, current, message, won, lost
    global reveal, shake, bounce
    if m is not None:
        mode = m
    if not ANSWERS:
        ANSWERS.append("about")

    if mode == "daily":
        answer = ANSWERS[_seed(_today()) % len(ANSWERS)]
    else:
        answer = _rng.choice(ANSWERS)

    state = "play"
    rows = []
    current = ""
    message = ""
    won = lost = False
    reveal = None
    shake = 0.0
    bounce = 0.0
    _sound("start")


def to_menu():
    global state
    state = "menu"


def _daily_left():
    """True when today's daily has already been played."""
    return stats.get("day") == _today() and stats.get("done")


# ---------------------------------------------------------------------------
# Marking a guess
# ---------------------------------------------------------------------------
def mark(guess, target):
    """Return a list of 'correct' / 'present' / 'absent' for each letter."""
    out = ["absent"] * WORD_LEN
    left = {}
    for i in range(WORD_LEN):
        if guess[i] == target[i]:
            out[i] = "correct"
        else:
            left[target[i]] = left.get(target[i], 0) + 1
    for i in range(WORD_LEN):
        if out[i] == "correct":
            continue
        ch = guess[i]
        if left.get(ch, 0) > 0:
            out[i] = "present"
            left[ch] -= 1
    return out


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
def _say(text):
    global message
    message = text


def key(name):
    global current, shake, reveal, won, lost, state, bounce
    if state == "menu":
        if name in ("enter", "1"):
            new_game("daily")
        elif name in ("2", "p"):
            new_game("practice")
        return
    if state == "over":
        if name in ("enter", " "):
            new_game(mode)
        return
    if reveal or shake > 0:
        return

    if name == "enter":
        _submit()
        return
    if name == "back":
        if current:
            current = current[:-1]
            _sound("tap")
        return
    if len(name) == 1 and name.isalpha() and len(current) < WORD_LEN:
        current += name.lower()
        _sound("tap")


def _submit():
    global reveal, shake, won, lost, state, current, bounce
    w = current
    if len(w) < WORD_LEN:
        _say("Not enough letters")
        shake = 1.0
        _sound("deny")
        return
    if w not in VALID:
        _say("Not in the word list")
        shake = 1.0
        _sound("deny")
        return

    rows.append((w, mark(w, answer)))
    current = ""
    _say("")
    reveal = {"row": len(rows) - 1, "t": 0.0}
    _sound("flip")


def _reveal_done():
    global reveal, won, lost, state, bounce
    reveal = None
    w, marks = rows[-1]
    if w == answer:
        won = True
        bounce = 1.0
        state = "over"
        _sound("win")
        _record(True)
    elif len(rows) >= MAX_TRIES:
        lost = True
        state = "over"
        _sound("lose")
        _record(False)


def _record(win):
    stats["played"] = int(stats.get("played", 0)) + 1
    if win:
        stats["wins"] = int(stats.get("wins", 0)) + 1
        stats["streak"] = int(stats.get("streak", 0)) + 1
        stats["best"] = max(int(stats.get("best", 0)), int(stats["streak"]))
        n = len(rows)
        if 1 <= n <= 6:
            stats["dist"][n - 1] = int(stats["dist"][n - 1]) + 1
    else:
        stats["streak"] = 0
    if mode == "daily":
        stats["day"] = _today()
        stats["done"] = True
    _save()


def tap(x, y):
    global state
    if state == "menu":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("tap")
                if tag == "daily":
                    if _daily_left():
                        new_game("practice")
                    else:
                        new_game("daily")
                elif tag == "practice":
                    new_game("practice")
                return
        return

    if state == "over":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("tap")
                if tag == "again":
                    new_game(mode)
                elif tag == "menu":
                    state = "menu"
                elif tag == "share":
                    _share()
                return
        return

    # the keyboard - kept precise so a finger cannot hit two keys at once
    for k, rect in _keys():
        if _hit(rect, x, y):
            key(k)
            return

    if _in((16, 14, 60, 44), x, y):
        _sound("tap")
        state = "menu"


def _keys():
    """Every key rectangle, as (name, rect)."""
    out = []
    for ri, row in enumerate(KEY_ROWS):
        y = KB_Y + ri * KB_STEP
        if ri == 2:
            widths = [UNIT * 1.6] + [UNIT] * 7 + [UNIT * 1.6]
            names = ["enter"] + list(row) + ["back"]
        else:
            widths = [UNIT] * len(row)
            names = list(row)
        total = sum(widths) + KGAP * (len(widths) - 1)
        x = (W - total) / 2.0
        for nm, wd in zip(names, widths):
            out.append((nm, (x, y, wd, KEY_H)))
            x += wd + KGAP
    return out


def _share():
    lines = ["Khelo Word %s  %s" % (_today(),
                                    "%d/%d" % (len(rows), MAX_TRIES) if won else "X/%d" % MAX_TRIES)]
    for _w, marks in rows:
        lines.append("".join("\U0001f7e9" if m == "correct" else
                             ("\U0001f7e8" if m == "present" else "\u2b1b")
                             for m in marks))
    text = "\n".join(lines)
    try:
        js.navigator.clipboard.writeText(text)
        _say("Copied to the clipboard")
    except Exception:
        _say("Could not copy")


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def update(dt):
    global _t, shake, reveal, bounce
    dt = min(max(float(dt), 0.0), 0.05)
    _t += dt

    if shake > 0:
        shake = max(0.0, shake - dt * 2.2)
    if bounce > 0:
        bounce = max(0.0, bounce - dt * 1.4)

    if reveal is not None:
        reveal["t"] += dt / 0.52
        if reveal["t"] >= 1.0:
            _reveal_done()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _panel(x, y, w, h, fill="rgba(14, 22, 46, 0.92)",
           stroke="rgba(150, 180, 240, 0.22)", r=14):
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()
    ctx.fillStyle = fill
    ctx.fill()
    if stroke:
        ctx.lineWidth = 2
        ctx.strokeStyle = stroke
        ctx.stroke()


def _button(x, y, w, h, label, active=False, accent="#7ef0c0", size=16, sub=None):
    _panel(x, y, w, h, accent if active else "rgba(24, 34, 62, 0.94)",
           "#ffffff" if active else "rgba(150, 180, 240, 0.30)", 12)
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillStyle = "#06101f" if active else INK
    ctx.font = "800 %dpx %s" % (size, FONT)
    ctx.fillText(label, x + w / 2, y + h / 2 + (0 if not sub else -8))
    if sub:
        ctx.fillStyle = "#0a2a22" if active else DIM
        ctx.font = "600 11px %s" % FONT
        ctx.fillText(sub, x + w / 2, y + h / 2 + 12)
    ctx.textBaseline = "alphabetic"


def _bg():
    g = ctx.createLinearGradient(0, 0, 0, H)
    g.addColorStop(0, BG_TOP)
    g.addColorStop(1, BG_BOT)
    ctx.fillStyle = g
    ctx.fillRect(0, 0, W, H)


def _wrap(text, x, y, maxw, size=15, color=DIM, center=True):
    ctx.font = "600 %dpx %s" % (size, FONT)
    ctx.fillStyle = color
    ctx.textAlign = "center" if center else "left"
    words, line = text.split(" "), ""
    for wd in words:
        trial = (line + " " + wd).strip()
        if ctx.measureText(trial).width > maxw and line:
            ctx.fillText(line, x, y)
            y += size + 6
            line = wd
        else:
            line = trial
    if line:
        ctx.fillText(line, x, y)
    return y


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------
def _tile(x, y, s, letter, kind, flat=1.0):
    """One square. `flat` squeezes it vertically for the flip."""
    ctx.save()
    ctx.translate(x + s / 2, y + s / 2)
    ctx.scale(1.0, max(0.02, flat))
    ctx.translate(-s / 2, -s / 2)

    if kind == "empty":
        _panel(0, 0, s, s, "rgba(16, 26, 52, 0.55)", TILE_EDGE, 10)
    elif kind == "typing":
        _panel(0, 0, s, s, "rgba(30, 44, 78, 0.95)", "rgba(190, 210, 250, 0.75)", 10)
    else:
        fill = {"correct": CORRECT, "present": PRESENT, "absent": ABSENT}[kind]
        _panel(0, 0, s, s, fill, "rgba(0,0,0,0.18)", 10)

    if letter:
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.fillStyle = "#06101f" if kind in ("correct", "present") else INK
        ctx.font = "800 %dpx %s" % (int(s * 0.52), FONT)
        ctx.fillText(letter.upper(), s / 2, s / 2 + 2)
        ctx.textBaseline = "alphabetic"
    ctx.restore()


def _draw_board():
    rx = 0.0
    if shake > 0:
        rx = math.sin(_t * 46) * 9 * shake

    for r in range(MAX_TRIES):
        for c in range(WORD_LEN):
            x = GX + c * (TILE + TGAP) + rx
            y = GY + r * (TILE + TGAP)

            if r < len(rows):
                word, marks = rows[r]
                kind = marks[c]
                flat = 1.0
                if reveal is not None and reveal["row"] == r:
                    # stagger the flip across the five tiles
                    t = reveal["t"] * 1.0 - c * 0.10
                    t = max(0.0, min(1.0, t / 0.60))
                    flat = abs(math.cos(math.pi * t))
                    if t < 0.5:
                        kind = "typing" if c < len(word) else "empty"
                if won and r == len(rows) - 1:
                    y -= math.sin(bounce * math.pi) * 14
                _tile(x, y, TILE, word[c], kind, flat)
            elif r == len(rows):
                letter = current[c] if c < len(current) else ""
                _tile(x, y, TILE, letter, "typing" if letter else "empty")
            else:
                _tile(x, y, TILE, "", "empty")


def _key_state(ch):
    """The best thing we know about a letter: correct beats present beats absent."""
    best = None
    for word, marks in rows:
        for i, m in enumerate(marks):
            if word[i] == ch:
                if m == "correct":
                    return "correct"
                if m == "present":
                    best = "present"
                elif best is None:
                    best = "absent"
    return best


def _draw_keyboard():
    for nm, (x, y, w, h) in _keys():
        if nm == "enter":
            _panel(x, y, w, h, "rgba(70, 84, 120, 0.95)", TILE_EDGE, 10)
            ctx.textAlign = "center"
            ctx.textBaseline = "middle"
            ctx.fillStyle = INK
            ctx.font = "800 12px %s" % FONT
            ctx.fillText("ENTER", x + w / 2, y + h / 2 + 1)
            ctx.textBaseline = "alphabetic"
        elif nm == "back":
            _panel(x, y, w, h, "rgba(70, 84, 120, 0.95)", TILE_EDGE, 10)
            ctx.textAlign = "center"
            ctx.textBaseline = "middle"
            ctx.fillStyle = INK
            ctx.font = "800 17px %s" % FONT
            ctx.fillText("\u232b", x + w / 2, y + h / 2 + 1)
            ctx.textBaseline = "alphabetic"
        else:
            st = _key_state(nm)
            fill = {"correct": CORRECT, "present": PRESENT,
                    "absent": KEY_ABSENT}.get(st, KEY_IDLE)
            _panel(x, y, w, h, fill, "rgba(150,180,240,0.16)", 9)
            ctx.textAlign = "center"
            ctx.textBaseline = "middle"
            ctx.fillStyle = "#06101f" if st in ("correct", "present") else INK
            ctx.font = "800 16px %s" % FONT
            ctx.fillText(nm.upper(), x + w / 2, y + h / 2 + 1)
            ctx.textBaseline = "alphabetic"


def _draw_header():
    ctx.textAlign = "left"
    ctx.fillStyle = INK
    ctx.font = "800 21px %s" % FONT
    ctx.fillText("KHELO WORD", 84, 44)
    ctx.fillStyle = DIM
    ctx.font = "700 11px %s" % FONT
    ctx.fillText("DAILY" if mode == "daily" else "PRACTICE", 84, 62)

    if stats.get("streak"):
        ctx.textAlign = "right"
        ctx.fillStyle = PRESENT
        ctx.font = "800 13px %s" % FONT
        ctx.fillText("\U0001f525 %d" % int(stats["streak"]), W - 20, 44)

    # the home button
    _panel(16, 14, 60, 44, "rgba(24, 34, 62, 0.94)", "rgba(150,180,240,0.24)", 12)
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillStyle = INK
    ctx.font = "800 18px %s" % FONT
    ctx.fillText("\u2190", 46, 37)
    ctx.textBaseline = "alphabetic"


def _draw_message():
    if message:
        ctx.textAlign = "center"
        ctx.fillStyle = INK
        ctx.font = "800 14px %s" % FONT
        ctx.fillText(message, W / 2, 534)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
def _draw_menu():
    global _menu_hit
    _menu_hit = []
    _bg()
    ctx.textAlign = "center"
    ctx.fillStyle = INK
    ctx.font = "800 38px %s" % FONT
    ctx.fillText("KHELO WORD", W / 2, 112)
    _wrap("Guess the five letter word in six tries.", W / 2, 146, 400, 15)

    # a little legend
    demo = [("c", "correct"), ("a", "present"), ("r", "absent")]
    total = 3 * TILE + 2 * 10
    for i, (ch, kind) in enumerate(demo):
        _tile(W / 2 - total / 2 + i * (TILE + 10), 168, TILE, ch, kind)
    _wrap("green: right place  \u00b7  amber: wrong place  \u00b7  grey: not there",
          W / 2, 268, 440, 11)

    done = _daily_left()
    y = 296
    _card("Daily word", _today() + ("  \u00b7  already played" if done else "  \u00b7  one a day"),
          y, "#7ef0c0", "Play" if not done else "Practice instead", "daily")

    y2 = y + 140
    _card("Practice", "A new word every time", y2, "#4aa8ff", "Play", "practice")

    # stats
    sy = y2 + 140
    _panel(40, sy, W - 80, 150, "rgba(14, 22, 44, 0.9)", "rgba(150,180,240,0.18)", 14)
    played = int(stats.get("played", 0))
    wins = int(stats.get("wins", 0))
    pct = int(round(100.0 * wins / played)) if played else 0
    cells = [("Played", played), ("Win %", pct),
             ("Streak", int(stats.get("streak", 0))),
             ("Best", int(stats.get("best", 0)))]
    cw = (W - 100) / 4.0
    for i, (label, val) in enumerate(cells):
        cx = 50 + i * cw + cw / 2
        ctx.textAlign = "center"
        ctx.fillStyle = INK
        ctx.font = "800 24px %s" % FONT
        ctx.fillText(str(val), cx, sy + 44)
        ctx.fillStyle = DIM
        ctx.font = "700 10px %s" % FONT
        ctx.fillText(label, cx, sy + 64)

    # the guess distribution
    dist = stats.get("dist") or [0] * 6
    top = max([int(v) for v in dist] + [1])
    barx, barw = 68, W - 136
    for i in range(6):
        bh, gap = 7, 3
        yy = sy + 78 + i * (bh + gap)
        ctx.fillStyle = "rgba(60, 74, 108, 0.5)"
        ctx.fillRect(barx, yy, barw, bh)
        frac = int(dist[i]) / float(top)
        if int(dist[i]):
            ctx.fillStyle = CORRECT
            ctx.fillRect(barx, yy, max(10, barw * frac), bh)


def _card(title, sub, y, accent, label, tag):
    """One big mode card, with its button safely inside the border."""
    h = 124
    _panel(40, y, W - 80, h, "rgba(20, 30, 56, 0.94)", accent, 16)
    ctx.textAlign = "center"
    ctx.fillStyle = accent
    ctx.font = "800 23px %s" % FONT
    ctx.fillText(title, W / 2, y + 40)
    ctx.fillStyle = DIM
    ctx.font = "600 13px %s" % FONT
    ctx.fillText(sub, W / 2, y + 62)
    _button(80, y + 72, W - 160, 42, label, True, accent, size=15)
    _menu_hit.append((tag, (40, y, W - 80, h)))


def _draw_over():
    global _menu_hit
    _menu_hit = []
    ctx.fillStyle = "rgba(4, 10, 24, 0.80)"
    ctx.fillRect(0, 0, W, H)

    ph = 250 if won else 300
    py = (H - ph) / 2 - 10
    _panel(40, py, W - 80, ph, "rgba(12, 20, 42, 0.97)",
           CORRECT if won else "#ff5c7a", 20)

    ctx.textAlign = "center"
    ctx.fillStyle = CORRECT if won else "#ff5c7a"
    ctx.font = "800 30px %s" % FONT
    ctx.fillText("GOT IT!" if won else "NO LUCK", W / 2, py + 56)

    ctx.fillStyle = INK
    ctx.font = "600 14px %s" % FONT
    ctx.fillText(("In %d %s" % (len(rows), "try" if len(rows) == 1 else "tries"))
                 if won else "The word was", W / 2, py + 88)

    if not won:
        ctx.fillStyle = PRESENT
        ctx.font = "800 34px %s" % FONT
        ctx.fillText(answer.upper(), W / 2, py + 132)

    by = py + (118 if won else 160)
    _button(70, by, 150, 50, "Play again", True, CORRECT if won else "#4aa8ff")
    _button(W - 220, by, 150, 50, "Share", False)
    _button(70, by + 60, W - 140, 44, "Back to menu", False, size=15)
    _menu_hit = [("again", (70, by, 150, 50)),
                 ("share", (W - 220, by, 150, 50)),
                 ("menu", (70, by + 60, W - 140, 44))]


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
def draw():
    if state == "menu":
        _draw_menu()
        return

    _bg()
    _draw_header()
    _draw_board()
    _draw_message()
    _draw_keyboard()

    if state == "over":
        _draw_over()

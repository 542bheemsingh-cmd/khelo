"""
Khelo Ludo - a full Ludo board game written in Python.

Runs in the browser through Pyodide, like the rest of the Khelo arcade.

The board is the classic 15x15 grid. Four players sit in the corners, each with
four tokens in their yard. Roll a 6 to bring a token out, race it around the
ring, then up your own coloured home column to the centre. Land on an opponent
and it walks all the way back to their yard. First player (or team) to get all
four tokens home wins.

Modes:
    single-single : 2, 3 or 4 players, everyone for themselves
    team-team     : 4 players, Red+Yellow against Green+Blue

The page calls:
    tap(x, y)          -> a click / tap on the canvas
    update(dt)         -> advance the animation
    draw()             -> render a frame
    set_name(c, text)  -> the player typed a name
"""

import json
import math
import random

import js

# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------
W, H = 900, 560

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
# Screen-adaptive UI
#
# The canvas has a fixed logical size, so on a phone it is scaled down and
# everything drawn on it shrinks with it - text becomes unreadable and buttons
# become too small for a finger. The page tells us how big the canvas really
# is on screen, and we grow the type and the touch targets back to a
# comfortable size. Material Design asks for a finger target of at least
# 48 CSS pixels, which is about 9mm.
# ---------------------------------------------------------------------------
UI = 1.0          # type scale, 1.0 on a big screen and larger on a phone
MIN_TOUCH = 0.0   # logical pixels that land on 48 CSS pixels


def set_size(w, h):
    """Lay the board out for the screen we actually have.

    Landscape: board on the left, panel on the right.
    Portrait:  board across the top, panel underneath. A phone held upright
               is mostly height, so a side panel would squeeze the board flat.
    """
    global W, H, CELL, BX, BY, BOARD, HUD_X, HUD_Y, HUD_W, HUD_H
    global DIE_RECT, ROLL_RECT
    try:
        nw, nh = float(w), float(h)
    except Exception:
        return
    if nw < 200 or nh < 200:
        return
    W, H = nw, nh
    pad = max(8.0, min(nw, nh) * 0.022)

    if nh >= nw * 1.08:
        # portrait
        board = min(nw - 2 * pad, nh * 0.58)
        board = max(180.0, board)
        BX = (nw - board) / 2.0
        BY = pad
        HUD_X = pad
        HUD_Y = BY + board + pad
        HUD_W = nw - 2 * pad
        HUD_H = nh - HUD_Y - pad
    else:
        # landscape
        board = min(nh - 2 * pad, nw - 338.0 - 3 * pad)
        board = max(180.0, board)
        BX = pad
        BY = (nh - board) / 2.0
        HUD_X = BX + board + pad
        HUD_Y = BY - pad * 1.2
        HUD_W = 322.0 + pad * 2.0
        HUD_H = board + pad * 2.4

    CELL = board / 15.0
    BOARD = board

    die = max(64.0, min(HUD_W * 0.42, HUD_H * 0.27))
    dx = HUD_X + (HUD_W - die) / 2.0
    dy = HUD_Y + max(96.0, HUD_H * 0.19)
    DIE_RECT = (dx, dy, die, die)
    ROLL_RECT = (HUD_X + HUD_W * 0.07, dy + die + HUD_H * 0.045,
                 HUD_W * 0.86, max(38.0, min(52.0, HUD_H * 0.085)))


def set_ui(scale):
    """Called by the page with canvasHeightOnScreen / logicalHeight."""
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
    """Grow a '700 15px family' font string so text stays readable."""
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
    """A font size scaled for the screen, but never past `cap`."""
    return int(round(px * min(UI, cap)))



class _Ctx:
    """A pass-through around the 2D context that rescales every font we set."""

    def __init__(self, real):
        object.__setattr__(self, "_real", real)

    def __setattr__(self, name, value):
        if name == "font" and isinstance(value, str):
            value = _fit_font(value)
        setattr(self._real, name, value)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _touch(rect):
    """Grow a rectangle so it is at least a finger wide."""
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


ctx = _Ctx(canvas.getContext("2d"))
ctx.scale(DPR, DPR)

FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"

# ---------------------------------------------------------------------------
# Board geometry
# ---------------------------------------------------------------------------
CELL = 33
BX, BY = 26, 32                 # top-left of the 15x15 board
BOARD = CELL * 15               # 495

RED, GREEN, YELLOW, BLUE = 0, 1, 2, 3
COLORS = ["red", "green", "yellow", "blue"]

PAL = {
    RED:    {"main": "#ff3b5c", "dark": "#c01f3d", "lite": "#ff8199", "soft": "#5c1526"},
    GREEN:  {"main": "#22c55e", "dark": "#15803d", "lite": "#7ee2a4", "soft": "#123d24"},
    YELLOW: {"main": "#fbbf24", "dark": "#b45309", "lite": "#fde08a", "soft": "#4d3512"},
    BLUE:   {"main": "#3b82f6", "dark": "#1d4ed8", "lite": "#9cc3fd", "soft": "#132a54"},
}
NAME = {RED: "Red", GREEN: "Green", YELLOW: "Yellow", BLUE: "Blue"}

# The ring of track squares, clockwise - the classic 52. At the four inner
# corners of the cross the path turns a corner, exactly as it does on a real
# board, so the centre square stays clear of the track.
TRACK = [
    (6, 13), (6, 12), (6, 11), (6, 10), (6, 9),                       # 0-4
    (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),                   # 5-10
    (0, 7),                                                           # 11 arm tip
    (0, 6), (1, 6), (2, 6), (3, 6), (4, 6), (5, 6),                   # 12-17
    (6, 5), (6, 4), (6, 3), (6, 2), (6, 1), (6, 0),                   # 18-23
    (7, 0),                                                           # 24 arm tip
    (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5),                   # 25-30
    (9, 6), (10, 6), (11, 6), (12, 6), (13, 6), (14, 6),              # 31-36
    (14, 7),                                                          # 37 arm tip
    (14, 8), (13, 8), (12, 8), (11, 8), (10, 8), (9, 8),              # 38-43
    (8, 9), (8, 10), (8, 11), (8, 12), (8, 13), (8, 14),              # 44-49
    (7, 14),                                                          # 50 arm tip
    (6, 14),                                                          # 51
]
TRACK_LEN = len(TRACK)
LAST_TRACK = 50                   # the arm tip a token turns off the ring at

START = {RED: 13, GREEN: 26, YELLOW: 39, BLUE: 0}

# a token walks 0..50 on the ring, then 51..55 up its home column, then 56 = home
HOME_LEN = 5
HOME_POS = LAST_TRACK + HOME_LEN + 1

HOME_PATH = {
    RED:    [(1, 7), (2, 7), (3, 7), (4, 7), (5, 7)],
    GREEN:  [(7, 1), (7, 2), (7, 3), (7, 4), (7, 5)],
    YELLOW: [(13, 7), (12, 7), (11, 7), (10, 7), (9, 7)],
    BLUE:   [(7, 13), (7, 12), (7, 11), (7, 10), (7, 9)],
}

# Safe squares: the four coloured starts plus four stars, each nine squares on
# from a start - the positions the classic board marks with a star.
SAFE = set(START.values()) | {(START[c] + 8) % TRACK_LEN for c in range(4)}

YARD = {RED: (0, 0), GREEN: (9, 0), YELLOW: (9, 9), BLUE: (0, 9)}
YARD_SLOTS = [(1.5, 1.5), (4.5, 1.5), (1.5, 4.5), (4.5, 4.5)]

CENTRE = (6, 6)
# where a finished token sits inside the centre - one row per colour, so four
# home tokens are always all visible instead of piling up on one another
HOME_SLOTS = {}
for _k in range(4):
    _off = 6.8 + _k * 0.47
    HOME_SLOTS.setdefault(RED, []).append((6.55, _off))
    HOME_SLOTS.setdefault(GREEN, []).append((_off, 6.55))
    HOME_SLOTS.setdefault(YELLOW, []).append((8.45, _off))
    HOME_SLOTS.setdefault(BLUE, []).append((_off, 8.45))


def cell_px(cx, cy):
    """Centre of a point given in continuous cell units."""
    return BX + (cx + 0.5) * CELL, BY + (cy + 0.5) * CELL


def path_cell(c, pos):
    """The grid cell a token of colour `c` sits on at path position `pos`."""
    if pos < 0:
        return None
    if pos <= LAST_TRACK:
        return TRACK[(START[c] + pos) % TRACK_LEN]
    if pos < HOME_POS:
        return HOME_PATH[c][pos - LAST_TRACK - 1]
    return None


def token_xy(c, idx, pos):
    """Pixel centre for token `idx` of colour `c`."""
    if pos < 0:
        ox, oy = YARD[c]
        sx, sy = YARD_SLOTS[idx]
        return cell_px(ox + sx - 0.5, oy + sy - 0.5)
    if pos >= HOME_POS:
        sx, sy = HOME_SLOTS[c][idx]
        return cell_px(sx - 0.5, sy - 0.5)
    cx, cy = path_cell(c, pos)
    return cell_px(cx, cy)


# ---------------------------------------------------------------------------
# Token designs
# ---------------------------------------------------------------------------
DESIGNS = ["ball", "gem", "ring", "star", "hex"]
DESIGN_LABEL = {"ball": "Ball", "gem": "Gem", "ring": "Ring",
                "star": "Star", "hex": "Hex"}
design = "ball"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
state = "mode"            # mode | count | setup | play | over
mode = "single"           # single | team
player_count = 4
players = []
teams = {}
names = {RED: "Red", GREEN: "Green", YELLOW: "Yellow", BLUE: "Blue"}
turn = 0
dice = 6
dice_show = 6
rolling = 0.0
roll_t = 1.0
moves = []
can_roll = True
message = ""
tokens = []
anims = []                # every running token animation
flash = []
winner = None
_rng = random.Random()
_t = 0.0
_menu_hit = []
_name_fields = []
_confetti = []

# ---------------------------------------------------------------------------
# Multiplayer
#
# One device is the host and runs the whole game. The others are guests: they
# draw whatever the host says is true, and ask the host to roll or move for
# them. Turn based games do not need anything cleverer than that.
# ---------------------------------------------------------------------------
net_on = False
net_host = True
net_seat = 0
net_seats = {}

ROLL_DUR = 2.0          # the die takes its time

# The die is not fair. A 6 is twice as likely as a plain number, 1 and 4 are a
# little likelier than the rest, and 2, 3 and 5 share what is left equally:
#     6 -> 30%,  1 -> 15%,  4 -> 15%,  2, 3, 5 -> 13.33% each
DICE_PCT = {
    1: 15.0,
    2: 40.0 / 3.0,
    3: 40.0 / 3.0,
    4: 15.0,
    5: 40.0 / 3.0,
    6: 30.0,
}


def _sound(name):
    try:
        js.playSound(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Setting up a game
# ---------------------------------------------------------------------------
def start_game(m=None, count=None):
    global state, mode, player_count, players, teams, turn, tokens
    global dice, dice_show, moves, can_roll, message, winner, rolling, roll_t
    if m is not None:
        mode = m
    if count is not None:
        player_count = count
    if mode == "team":
        player_count = 4
        players = [RED, GREEN, YELLOW, BLUE]
        teams = {RED: 0, YELLOW: 0, GREEN: 1, BLUE: 1}
    else:
        players = {2: [RED, YELLOW], 3: [RED, GREEN, YELLOW],
                   4: [RED, GREEN, YELLOW, BLUE]}[player_count]
        teams = {}

    tokens = []
    for c in players:
        for i in range(4):
            x, y = token_xy(c, i, -1)
            tokens.append({"c": c, "i": i, "pos": -1, "x": x, "y": y})

    turn = 0
    dice = dice_show = 6
    rolling = 0.0
    roll_t = 1.0
    moves = []
    anims[:] = []
    can_roll = True
    winner = None
    message = "Tap the dice to roll."
    state = "play"
    _sound("start")


def to_mode():
    global state
    state = "mode"


def to_count():
    global state
    state = "count"


def to_setup():
    global state
    state = "setup"


def restart():
    start_game()


def set_design(d):
    global design
    if d in DESIGNS:
        design = d


def set_name(c, text):
    global names
    c = int(c)
    if c in NAME:
        text = (text or "").strip()[:12]
        names[c] = text if text else NAME[c]


def focus_name(c):
    """Ask the page to open its text field so the player can type a name."""
    try:
        js.focusName(int(c), names.get(int(c), ""))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def snapshot():
    """Everything a guest needs to draw the board, and nothing more."""
    return json.dumps({
        "mode": mode,
        "players": list(players),
        "turn": turn,
        "dice": dice,
        "dice_show": dice_show,
        "moves": [[t["c"], t["i"], target] for t, target in moves],
        "can_roll": can_roll,
        "message": message,
        "winner": winner,
        "state": state,
        "names": {k: v for k, v in names.items()},
        "tokens": [[t["c"], t["i"], t["pos"]] for t in tokens],
    })


def apply_net(js):
    """A guest adopts the host's board."""
    global mode, players, turn, dice, dice_show, moves, can_roll
    global message, winner, state, tokens
    try:
        d = json.loads(js)
    except Exception:
        return
    mode = d.get("mode", mode)
    players = list(d.get("players", players))
    turn = int(d.get("turn", turn))
    dice = int(d.get("dice", dice))
    dice_show = int(d.get("dice_show", dice_show))
    can_roll = bool(d.get("can_roll", can_roll))
    message = d.get("message", message)
    winner = d.get("winner")
    state = d.get("state", state)
    if d.get("names"):
        names.update(d["names"])

    # rebuild the tokens where the host says they are
    want = d.get("tokens") or []
    have = {(t["c"], t["i"]): t for t in tokens}
    fresh = []
    for c, i, pos in want:
        t = have.get((c, i))
        if t is None:
            t = {"c": c, "i": i, "pos": -1}
        if t["pos"] != pos:
            t["pos"] = pos
            t["x"], t["y"] = token_xy(c, i, pos)
        fresh.append(t)
    if fresh:
        tokens = fresh

    # and which moves are on offer
    by_key = {(t["c"], t["i"]): t for t in tokens}
    moves = []
    for c, i, target in (d.get("moves") or []):
        t = by_key.get((c, i))
        if t is not None:
            moves.append((t, target))


def net_apply_action(js):
    """Host: a guest asked for a roll or a move. Only their own turn counts."""
    if not (net_on and net_host):
        return
    try:
        d = json.loads(js)
    except Exception:
        return
    who = d.get("from")
    seat = net_seats.get(who)
    if seat is not None and players:
        if seat != turn % len(players):
            return                      # not your turn
    a = d.get("a")
    if a == "roll":
        roll()
    elif a == "move":
        c, i = d.get("c"), int(d.get("i", -1))
        for t, target in moves:
            if t["c"] == c and t["i"] == i:
                _choose(t, target)
                break


def set_net_ludo(on, host, seat):
    global net_on, net_host, net_seat
    net_on = bool(on)
    net_host = bool(host)
    net_seat = int(seat or 0)


def set_seats(js, my_id=""):
    """Who is playing which colour, decided by the host."""
    global net_seats, net_seat
    try:
        d = json.loads(js)
    except Exception:
        return
    if not isinstance(d, dict):
        return
    net_seats = {str(k): int(v) for k, v in d.items()}
    if my_id in net_seats:
        net_seat = net_seats[my_id]


def cur():
    return players[turn % len(players)]


def my_tokens(c):
    return [t for t in tokens if t["c"] == c]


def legal_moves(c, d):
    out = []
    for t in my_tokens(c):
        p = t["pos"]
        if p >= HOME_POS:
            continue
        if p < 0:
            if d == 6:
                out.append((t, 0))
        elif p + d <= HOME_POS:
            out.append((t, p + d))
    return out


def _roll_face():
    """Pick a face using the table above rather than an even 1-in-6."""
    faces = sorted(DICE_PCT)
    return _rng.choices(faces, weights=[DICE_PCT[f] for f in faces])[0]


def roll():
    global rolling, roll_t, dice, can_roll
    if state != "play" or anims or rolling > 0 or not can_roll:
        return
    dice = _roll_face()
    rolling = ROLL_DUR
    roll_t = 0.0
    can_roll = False
    _sound("dice")


def _after_roll():
    global moves, can_roll, message
    c = cur()
    moves = legal_moves(c, dice)
    if not moves:
        message = "%s rolled %d - no move." % (names[c], dice)
        _sound("deny")
        _pass_turn()
        return
    can_roll = False
    message = "%s rolled %d - tap a token." % (names[c], dice)
    _sound("click")


def _pass_turn():
    global turn, can_roll, moves, message
    if dice == 6:
        can_roll = True          # a 6 always earns another go
        moves = []
        return
    turn = (turn + 1) % len(players)
    moves = []
    can_roll = True
    message = "%s to roll." % names[cur()]


def _captures_at(cell, moving_color):
    if cell is None:
        return []
    try:
        idx = TRACK.index(cell)
    except ValueError:
        return []
    if idx in SAFE:
        return []
    hits = []
    for t in tokens:
        if t["c"] == moving_color or t["pos"] < 0 or t["pos"] > LAST_TRACK:
            continue
        if path_cell(t["c"], t["pos"]) == cell:
            hits.append(t)
    return hits


def _choose(t, target):
    global moves
    if anims:
        return
    if not any(m[0] is t and m[1] == target for m in moves):
        return
    moves = []
    _anim_to(t, list(range(t["pos"] + 1, target + 1)), "move", dice=dice)
    _sound("hop")


def _anim_to(t, positions, kind, dice=0, speed=8.5):
    """Walk `t` through a list of path positions, animating each square."""
    cells = [(p, *token_xy(t["c"], t["i"], p)) for p in positions]
    if not cells:
        return None
    a = {"t": t, "cells": cells, "i": 0, "p": 0.0, "kind": kind,
         "dice": dice, "speed": speed}
    t["pos"] = cells[0][0]
    anims.append(a)
    return a


def _finish_move(a):
    """Resolve captures, extra turns and the win once a token stops."""
    global turn, can_roll, moves, message, winner, state
    t = a["t"]
    c = t["c"]
    extra = (a["dice"] == 6)

    if t["pos"] <= LAST_TRACK:
        hits = _captures_at(path_cell(c, t["pos"]), c)
        for h in hits:
            # the captured token walks all the way back, square by square
            back = list(range(h["pos"] - 1, -1, -1)) + [-1]
            _anim_to(h, back, "capture", speed=13.0)
            _sound("capture")
            extra = True
        if hits:
            message = "%s captured %s!" % (
                names[c], ", ".join(names[h["c"]] for h in hits))

    if t["pos"] >= HOME_POS:
        extra = True
        _sound("home")
        _burst(*token_xy(c, t["i"], HOME_POS), PAL[c]["lite"])
        message = "%s got a token home!" % names[c]

    if _won(c):
        winner = c
        state = "over"
        _sound("win")
        _confetti[:] = [{"x": _rng.uniform(0, W), "y": _rng.uniform(-H, 0),
                         "vy": _rng.uniform(60, 160), "vx": _rng.uniform(-30, 30),
                         "r": _rng.uniform(3, 7),
                         "col": _rng.choice([PAL[k]["main"] for k in PAL])}
                        for _ in range(90)]
        return

    if extra:
        can_roll = True
        moves = []
    else:
        turn = (turn + 1) % len(players)
        can_roll = True
        moves = []
        message = "%s to roll." % names[cur()]


def _won(c):
    if all(t["pos"] >= HOME_POS for t in my_tokens(c)):
        if mode == "team":
            mate = [k for k, v in teams.items() if v == teams[c] and k != c][0]
            return all(t["pos"] >= HOME_POS for t in my_tokens(mate))
        return True
    return False


def _burst(x, y, col):
    for _ in range(12):
        a = _rng.uniform(0, 6.283)
        s = _rng.uniform(40, 140)
        flash.append({"x": x, "y": y, "vx": math.cos(a) * s, "vy": math.sin(a) * s,
                      "life": 0.6, "col": col, "r": _rng.uniform(2, 4)})


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
# HUD rects - the drawing and the tap handling both read these, so a button can
# never be drawn somewhere the finger cannot reach.
HUD_X, HUD_Y = 552, 20
HUD_W, HUD_H = 322, 519
DIE_RECT = (HUD_X + 85, BY + 74, 152, 152)
ROLL_RECT = (HUD_X + 76, BY + 262, 170, 44)


def tap(x, y):
    global state
    if state == "mode":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("click")
                if tag == "single":
                    state = "count"
                elif tag == "team":
                    globals()["mode"] = "team"
                    state = "setup"
                elif tag == "design":
                    state = "setup"
                return
        return

    if state == "count":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("click")
                if tag == "back":
                    state = "mode"
                else:
                    globals()["mode"] = "single"
                    globals()["player_count"] = int(tag)
                    state = "setup"
                return
        return

    if state == "setup":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("click")
                if tag == "back":
                    state = "count" if mode == "single" else "mode"
                elif tag == "start":
                    start_game()
                elif tag.startswith("d:"):
                    set_design(tag[2:])
                return
        for c, r in _name_fields:
            if _in(r, x, y):
                focus_name(c)
                return
        return

    if state == "over":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("click")
                if tag == "again":
                    restart()
                elif tag == "menu":
                    state = "mode"
                return
        return

    # --- playing ---
    if net_on and not net_host:
        # a guest does not run the game: it asks the host
        if _in(ROLL_RECT, x, y) or _in(DIE_RECT, x, y):
            _sound("click")
            js.netAction(json.dumps({"a": "roll"}))
            return
        if anims or not moves:
            return
        best, bestd = None, 26
        offs = _stack_offsets()
        for t, target in moves:
            tx, ty = token_xy(t["c"], t["i"], t["pos"])
            ox, oy = offs.get(id(t), (0, 0))
            dd = math.hypot(x - (tx + ox), y - (ty + oy))
            if dd < bestd:
                best, bestd = (t, target), dd
        if best:
            js.netAction(json.dumps({"a": "move", "c": best[0]["c"],
                                     "i": best[0]["i"]}))
        return

    if _in(ROLL_RECT, x, y) or _in(DIE_RECT, x, y):
        roll()
        return
    if _in((16, 16, 110, 38), x, y):
        state = "mode"
        _sound("click")
        return

    if anims or not moves:
        return
    best, bestd = None, 26
    offs = _stack_offsets()
    for t, target in moves:
        tx, ty = token_xy(t["c"], t["i"], t["pos"])
        ox, oy = offs.get(id(t), (0, 0))
        d = math.hypot(x - (tx + ox), y - (ty + oy))
        if d < bestd:
            best, bestd = (t, target), d
    if best:
        _choose(best[0], best[1])


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def _stack_offsets():
    """Small offsets so tokens sharing a square are all visible."""
    groups = {}
    for t in tokens:
        if t["pos"] < 0 or t["pos"] >= HOME_POS:
            continue
        cell = path_cell(t["c"], t["pos"])
        if cell is not None:
            groups.setdefault(cell, []).append(t)
    offs = {}
    for grp in groups.values():
        n = len(grp)
        if n == 1:
            offs[id(grp[0])] = (0.0, 0.0)
            continue
        r = CELL * 0.20
        for k, t in enumerate(grp):
            a = -math.pi / 2 + k * 2 * math.pi / n
            offs[id(t)] = (math.cos(a) * r, math.sin(a) * r)
    return offs


def update(dt):
    global rolling, roll_t, _t, dice_show, message, can_roll
    dt = min(max(float(dt), 0.0), 0.05)
    _t += dt

    for f in flash:
        f["x"] += f["vx"] * dt
        f["y"] += f["vy"] * dt
        f["vy"] += 260 * dt
        f["life"] -= dt
    flash[:] = [f for f in flash if f["life"] > 0]

    for p in _confetti:
        p["y"] += p["vy"] * dt
        p["x"] += p["vx"] * dt
        if p["y"] > H + 20:
            p["y"] = -20
            p["x"] = _rng.uniform(0, W)

    if rolling > 0:
        rolling -= dt
        roll_t = min(1.0, roll_t + dt / ROLL_DUR)
        if roll_t < 0.78:
            dice_show = _rng.randint(1, 6)
        else:
            dice_show = dice
        if rolling <= 0:
            rolling = 0.0
            roll_t = 1.0
            dice_show = dice
            _after_roll()

    for a in anims[:]:
        a["p"] += dt * a["speed"]
        while a["p"] >= 1.0:
            a["p"] -= 1.0
            a["i"] += 1
            if a["i"] >= len(a["cells"]):
                a["t"]["pos"] = a["cells"][-1][0]
                anims.remove(a)
                if a["kind"] == "move":
                    _finish_move(a)
                break
            a["t"]["pos"] = a["cells"][a["i"]][0]

    offs = _stack_offsets()
    for t in tokens:
        tx, ty = token_xy(t["c"], t["i"], t["pos"])
        ox, oy = offs.get(id(t), (0.0, 0.0))
        tx += ox
        ty += oy
        for a in anims:
            if a["t"] is t:
                ty -= math.sin(math.pi * min(1.0, a["p"])) * CELL * 0.85
                break
        k = min(1.0, dt * 16)
        t["x"] += (tx - t["x"]) * k
        t["y"] += (ty - t["y"]) * k


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
    ctx.fillStyle = "#06101f" if active else "#eaf2ff"
    ctx.font = "800 %dpx %s" % (size, FONT)
    ctx.fillText(label, x + w / 2, y + h / 2 + (0 if not sub else -8))
    if sub:
        ctx.fillStyle = "#0a2a22" if active else "#93a4c8"
        ctx.font = "600 11px %s" % FONT
        ctx.fillText(sub, x + w / 2, y + h / 2 + 12)
    ctx.textBaseline = "alphabetic"


def _title(t, y, size=30, color="#ffffff"):
    ctx.textAlign = "center"
    ctx.fillStyle = color
    ctx.font = "800 %dpx %s" % (size, FONT)
    ctx.fillText(t, W / 2, y)


def _wrap(text, x, y, maxw, size=15, color="#9fb3d9", center=True):
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


def _bg():
    g = ctx.createLinearGradient(0, 0, 0, H)
    g.addColorStop(0, "#121d3e")
    g.addColorStop(1, "#05080f")
    ctx.fillStyle = g
    ctx.fillRect(0, 0, W, H)


def _poly(x, y, r, n, rot=0.0):
    ctx.beginPath()
    for i in range(n):
        a = rot + i * 2 * math.pi / n
        px, py = x + math.cos(a) * r, y + math.sin(a) * r
        ctx.moveTo(px, py) if i == 0 else ctx.lineTo(px, py)
    ctx.closePath()


# ---------------------------------------------------------------------------
# Drawing the board
# ---------------------------------------------------------------------------
def _draw_board():
    _panel(BX - 12, BY - 12, BOARD + 24, BOARD + 24,
           "rgba(9, 15, 32, 0.95)", "rgba(150, 180, 240, 0.18)", 16)

    for c in (RED, GREEN, YELLOW, BLUE):
        ox, oy = YARD[c]
        px, py = BX + ox * CELL, BY + oy * CELL
        p = PAL[c]
        _panel(px + 3, py + 3, CELL * 6 - 6, CELL * 6 - 6, p["soft"], p["main"], 12)
        _panel(px + CELL + 6, py + CELL + 6, CELL * 4 - 12, CELL * 4 - 12,
               "rgba(8, 14, 30, 0.55)", "rgba(255,255,255,0.10)", 10)
        for sx, sy in YARD_SLOTS:
            cx, cy = cell_px(ox + sx - 0.5, oy + sy - 0.5)
            ctx.beginPath()
            ctx.arc(cx, cy, CELL * 0.52, 0, 6.2832)
            ctx.fillStyle = "rgba(255,255,255,0.07)"
            ctx.fill()
            ctx.lineWidth = 2
            ctx.strokeStyle = "rgba(255,255,255,0.16)"
            ctx.stroke()

    for idx, (cx, cy) in enumerate(TRACK):
        px, py = BX + cx * CELL, BY + cy * CELL
        owner = None
        for c in (RED, GREEN, YELLOW, BLUE):
            if START[c] == idx:
                owner = c
        if owner is not None:
            fill = PAL[owner]["main"]
        elif idx in SAFE:
            fill = "rgba(226, 236, 255, 0.95)"
        else:
            fill = "rgba(238, 244, 255, 0.90)"
        ctx.fillStyle = fill
        ctx.fillRect(px, py, CELL, CELL)
        ctx.lineWidth = 1
        ctx.strokeStyle = "rgba(20, 30, 60, 0.45)"
        ctx.strokeRect(px + 0.5, py + 0.5, CELL - 1, CELL - 1)
        if idx in SAFE and owner is None:
            _star(px + CELL / 2, py + CELL / 2, CELL * 0.30, "#8b98b5")

    for c in (RED, GREEN, YELLOW, BLUE):
        p = PAL[c]
        for k, (cx, cy) in enumerate(HOME_PATH[c]):
            px, py = BX + cx * CELL, BY + cy * CELL
            ctx.fillStyle = p["main"]
            ctx.globalAlpha = 0.85 - k * 0.06
            ctx.fillRect(px, py, CELL, CELL)
            ctx.globalAlpha = 1.0
            ctx.lineWidth = 1
            ctx.strokeStyle = "rgba(20, 30, 60, 0.35)"
            ctx.strokeRect(px + 0.5, py + 0.5, CELL - 1, CELL - 1)

    # the centre, four coloured triangles
    cx0, cy0 = BX + 6 * CELL, BY + 6 * CELL
    size = CELL * 3
    mid = (cx0 + size / 2, cy0 + size / 2)
    corners = [(cx0, cy0), (cx0 + size, cy0), (cx0 + size, cy0 + size), (cx0, cy0 + size)]
    order = [GREEN, YELLOW, BLUE, RED]      # top, right, bottom, left
    for i, col in enumerate(order):
        a, b = corners[i], corners[(i + 1) % 4]
        ctx.beginPath()
        ctx.moveTo(*mid)
        ctx.lineTo(*a)
        ctx.lineTo(*b)
        ctx.closePath()
        ctx.fillStyle = PAL[col]["main"]
        ctx.fill()
        ctx.lineWidth = 1.5
        ctx.strokeStyle = "rgba(10, 18, 40, 0.5)"
        ctx.stroke()
    ctx.beginPath()
    ctx.arc(mid[0], mid[1], CELL * 0.66, 0, 6.2832)
    ctx.fillStyle = "rgba(8, 14, 30, 0.72)"
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = "rgba(255,255,255,0.22)"
    ctx.stroke()


def _star(x, y, r, col):
    ctx.beginPath()
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        px, py = x + math.cos(a) * rr, y + math.sin(a) * rr
        ctx.moveTo(px, py) if i == 0 else ctx.lineTo(px, py)
    ctx.closePath()
    ctx.fillStyle = col
    ctx.fill()


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def _shape_ball(x, y, r, p):
    g = ctx.createRadialGradient(x - r * 0.35, y - r * 0.4, r * 0.15, x, y, r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(0.55, p["main"])
    g.addColorStop(1, p["dark"])
    ctx.beginPath()
    ctx.arc(x, y, r, 0, 6.2832)
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = "rgba(255,255,255,0.55)"
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(x - r * 0.32, y - r * 0.38, r * 0.26, 0, 6.2832)
    ctx.fillStyle = "rgba(255,255,255,0.78)"
    ctx.fill()


def _shape_gem(x, y, r, p):
    _poly(x, y, r, 6, -math.pi / 2)
    g = ctx.createLinearGradient(x - r, y - r, x + r, y + r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(0.5, p["main"])
    g.addColorStop(1, p["dark"])
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.7
    ctx.strokeStyle = "rgba(255,255,255,0.65)"
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(x, y - r * 0.92)
    ctx.lineTo(x - r * 0.46, y + r * 0.34)
    ctx.lineTo(x + r * 0.46, y + r * 0.34)
    ctx.closePath()
    ctx.fillStyle = "rgba(255,255,255,0.30)"
    ctx.fill()


def _shape_ring(x, y, r, p):
    ctx.beginPath()
    ctx.arc(x, y, r, 0, 6.2832)
    ctx.fillStyle = p["dark"]
    ctx.fill()
    ctx.beginPath()
    ctx.arc(x, y, r * 0.46, 0, 6.2832)
    ctx.fillStyle = "#0b1224"
    ctx.fill()
    ctx.lineWidth = 1.6
    ctx.strokeStyle = "rgba(255,255,255,0.55)"
    ctx.beginPath()
    ctx.arc(x, y, r, 0, 6.2832)
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(x, y, r * 0.46, 0, 6.2832)
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(x - r * 0.30, y - r * 0.62, r * 0.20, 0, 6.2832)
    ctx.fillStyle = "rgba(255,255,255,0.55)"
    ctx.fill()


def _shape_star(x, y, r, p):
    ctx.beginPath()
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.48
        px, py = x + math.cos(a) * rr, y + math.sin(a) * rr
        ctx.moveTo(px, py) if i == 0 else ctx.lineTo(px, py)
    ctx.closePath()
    g = ctx.createRadialGradient(x, y, r * 0.1, x, y, r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(1, p["main"])
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.5
    ctx.strokeStyle = "rgba(255,255,255,0.6)"
    ctx.stroke()


def _shape_hex(x, y, r, p):
    _poly(x, y, r, 6, math.pi / 6)
    g = ctx.createLinearGradient(x - r, y - r, x + r, y + r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(0.6, p["main"])
    g.addColorStop(1, p["dark"])
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.8
    ctx.strokeStyle = "rgba(255,255,255,0.55)"
    ctx.stroke()
    _poly(x, y, r * 0.55, 6, math.pi / 6)
    ctx.fillStyle = "rgba(255,255,255,0.22)"
    ctx.fill()


SHAPES = {"ball": _shape_ball, "gem": _shape_gem, "ring": _shape_ring,
          "star": _shape_star, "hex": _shape_hex}


def _draw_token(t, highlight=False, movable=False, label=True):
    x, y, c = t["x"], t["y"], t["c"]
    p = PAL[c]
    r = CELL * 0.40

    if highlight:
        glow = 0.5 + 0.5 * math.sin(_t * 4)
        ctx.beginPath()
        ctx.arc(x, y, r + 6 + glow * 3, 0, 6.2832)
        ctx.fillStyle = p["main"]
        ctx.globalAlpha = 0.18 + glow * 0.18
        ctx.fill()
        ctx.globalAlpha = 1.0

    ctx.beginPath()
    ctx.ellipse(x, y + r * 0.72, r * 0.85, r * 0.36, 0, 0, 6.2832)
    ctx.fillStyle = "rgba(0,0,0,0.35)"
    ctx.fill()

    SHAPES[design](x, y, r, p)

    if movable:
        ctx.beginPath()
        ctx.arc(x, y, r + 4, 0, 6.2832)
        ctx.lineWidth = 2.5
        ctx.strokeStyle = "#ffffff"
        ctx.setLineDash([4, 4])
        ctx.lineDashOffset = -_t * 14
        ctx.stroke()
        ctx.setLineDash([])

    if label:
        nm = names[c]
        if nm:
            # drawn unscaled on purpose: 16 name tags on one board would
            # collide if they grew as much as the rest of the type
            raw = ctx._real
            raw.textAlign = "center"
            raw.font = "800 %dpx %s" % (_fs(8, 1.10), FONT)
            raw.lineWidth = 2.4
            raw.strokeStyle = "rgba(4, 8, 18, 0.85)"
            raw.strokeText(nm, x, y - r - 3)
            raw.fillStyle = "#ffffff"
            raw.fillText(nm, x, y - r - 3)


def _draw_tokens():
    c = cur() if state == "play" else None
    movable = {id(m[0]) for m in moves}
    order = sorted(tokens, key=lambda t: 1 if any(a["t"] is t for a in anims) else 0)
    for t in order:
        _draw_token(t, highlight=(c is not None and t["c"] == c),
                    movable=(id(t) in movable),
                    label=(t["pos"] >= 0 and t["pos"] < HOME_POS))


# ---------------------------------------------------------------------------
# The dice
# ---------------------------------------------------------------------------
PIPS = {
    1: [(0, 0)],
    2: [(-1, -1), (1, 1)],
    3: [(-1, -1), (0, 0), (1, 1)],
    4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
    5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
    6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)],
}


def _die_face(cx, cy, s, n):
    x, y = cx - s / 2, cy - s / 2
    _panel(x, y, s, s, "#f8fbff", "rgba(20, 30, 60, 0.40)", 14)
    r = s * 0.105
    step = s * 0.25
    for dx, dy in PIPS[n]:
        ctx.beginPath()
        ctx.arc(cx + dx * step, cy + dy * step, r, 0, 6.2832)
        ctx.fillStyle = "#243252"
        ctx.fill()
        ctx.beginPath()
        ctx.arc(cx + dx * step - r * 0.3, cy + dy * step - r * 0.3, r * 0.32, 0, 6.2832)
        ctx.fillStyle = "rgba(255,255,255,0.55)"
        ctx.fill()


def _blit_dice3d(x, y, w, h):
    """Draw the three.js die onto the board. False if it is not available."""
    try:
        # roll_t runs 0..1 during the roll and rests at 1 when settled
        js.dice3d.frame(float(roll_t), int(dice))
        ctx.drawImage(js.dice3d.canvas, x, y, w, h)
        return True
    except Exception:
        return False


def _draw_die():
    x, y, w, h = DIE_RECT
    s = min(w, h)
    cx, cy = x + w / 2, y + h / 2

    glow = 0.5 + 0.5 * math.sin(_t * 3)
    if state == "play" and rolling <= 0:
        _panel(x - 6, y - 6, s + 12, s + 12, "rgba(255,255,255,0.05)",
               "rgba(255,255,255,%.2f)" % (0.10 + glow * 0.12), 18)

    # the real 3D die, if the page managed to build one
    if _blit_dice3d(x, y, w, h):
        return

    e = roll_t if rolling > 0 else 1.0
    ease = 1 - (1 - e) ** 3                       # ease-out
    off = -(1 - ease) * 210                       # falls in from above
    scl = 1 + (1 - ease) * 0.55
    rot = (1 - ease) * math.pi * 2.4

    if rolling > 0:
        # the shadow on the table grows as the die comes down
        ctx.beginPath()
        ctx.ellipse(cx, y + s + 8, s * (0.30 + ease * 0.18), s * (0.10 + ease * 0.04),
                    0, 0, 6.2832)
        ctx.fillStyle = "rgba(0,0,0,%.2f)" % (0.10 + ease * 0.30)
        ctx.fill()

    ctx.save()
    ctx.translate(cx, cy + off)
    ctx.rotate(rot)
    ctx.scale(scl, scl)
    _die_face(0, 0, s, dice_show)
    ctx.restore()


# ---------------------------------------------------------------------------
# HUD panel
# ---------------------------------------------------------------------------
def _draw_hud():
    x, y0, hw, hh = HUD_X, HUD_Y, HUD_W, HUD_H
    _panel(x, y0, hw, hh, "rgba(11, 18, 38, 0.92)",
           "rgba(150, 180, 240, 0.20)", 16)

    k = min(1.30, hw / 322.0)            # scale the type, but never blow it up
    mid = x + hw / 2.0

    c = cur() if state == "play" else None
    ctx.textAlign = "center"
    ctx.fillStyle = "#8fa3c9"
    ctx.font = "800 %dpx %s" % (max(9, int(11 * k)), FONT)
    ctx.fillText("TURN", mid, y0 + 22)
    if c is not None:
        ctx.fillStyle = PAL[c]["main"]
        ctx.font = "800 %dpx %s" % (max(16, int(24 * k)), FONT)
        ctx.fillText(names[c], mid, y0 + 52)
        if mode == "team" and teams:
            ctx.fillStyle = "#8fa3c9"
            ctx.font = "700 %dpx %s" % (max(9, int(12 * k)), FONT)
            ctx.fillText("Team A" if teams.get(c, 0) == 0 else "Team B",
                         mid, y0 + 72)

    _draw_die()

    if state == "play":
        ready = can_roll and rolling <= 0 and not anims
        _button(*ROLL_RECT[:2], ROLL_RECT[2], ROLL_RECT[3],
                "ROLL" if ready else "\u2026", ready, PAL[c]["main"],
                size=max(13, int(17 * k)))
        if not ready and rolling <= 0 and not anims and moves:
            _wrap("tap a token", mid, ROLL_RECT[1] + ROLL_RECT[3] + 16 * k,
                  hw * 0.8, max(9, int(12 * k)), "#8fa3c9")

    # one row per player, filling whatever room is left above the message
    ry = ROLL_RECT[1] + ROLL_RECT[3] + hh * 0.075
    foot = hh * 0.11 if message else hh * 0.04
    room = (y0 + hh - foot) - ry
    row_h = max(20.0, min(30.0 * k, room / max(1, len(players)) - 3))
    for i, col in enumerate(players):
        active = (state == "play" and i == turn % len(players))
        _panel(x + hw * 0.055, ry, hw * 0.89, row_h,
               PAL[col]["soft"] if active else "rgba(20, 30, 56, 0.6)",
               PAL[col]["main"] if active else "rgba(150,180,240,0.14)", 9)
        ctx.beginPath()
        ctx.arc(x + hw * 0.115, ry + row_h / 2, row_h * 0.27, 0, 6.2832)
        ctx.fillStyle = PAL[col]["main"]
        ctx.fill()
        ctx.textAlign = "left"
        ctx.fillStyle = "#eaf2ff"
        ctx.font = "700 %dpx %s" % (max(9, int(12 * k)), FONT)
        label = names[col]
        if mode == "team" and teams:
            label += "  (A)" if teams.get(col, 0) == 0 else "  (B)"
        ctx.fillText(label, x + hw * 0.175, ry + row_h * 0.68)
        home = sum(1 for t in my_tokens(col) if t["pos"] >= HOME_POS)
        out = sum(1 for t in my_tokens(col) if 0 <= t["pos"] < HOME_POS)
        ctx.textAlign = "right"
        ctx.fillStyle = "#9fb3d9"
        ctx.font = "700 %dpx %s" % (max(8, int(11 * k)), FONT)
        ctx.fillText("%d home \u00b7 %d out" % (home, out),
                     x + hw * 0.9, ry + row_h * 0.68)
        ry += row_h + 3

    if message:
        _wrap(message, mid, ry + 12 * k, hw * 0.88,
              max(9, int(12 * k)), "#cfe0ff")


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
def _draw_mode():
    global _menu_hit
    _menu_hit = []
    _bg()
    pad = 14.0
    narrow = W < 520

    # the back chip first, so the title never lands on top of it
    _button(pad, pad, 96, 36, "\u2190 Games", size=13)
    _menu_hit.append(("games", (pad, pad, 96, 36)))

    _title("KHELO LUDO", 84 if narrow else 78, 30 if narrow else 42)
    _wrap("The classic race home - pick how you want to play.",
          W / 2, (110 if narrow else 108), min(640, W - 30), 14)

    cards = [
        ("single", "Single-Single", "Everyone for themselves", "#4aa8ff",
         "Choose 2, 3 or 4 players"),
        ("team", "Team-Team", "2 players against 2", "#fbbf24",
         "Red + Yellow vs Green + Blue"),
    ]
    gap = max(12.0, W * 0.03)
    if narrow:
        cw = W - 2 * pad
        ch = 132.0
        oy = 112.0
    else:
        cw = min(340.0, (W - 2 * pad - gap) / 2.0)
        ch = 196.0
        oy = max(150.0, H * 0.24)
    k = min(1.0, cw / 330.0)

    for i, (tag, name, sub, accent, note) in enumerate(cards):
        if narrow:
            x, y = pad, oy + i * (ch + 12)
        else:
            x = (W - (2 * cw + gap)) / 2.0 + i * (cw + gap)
            y = oy
        _panel(x, y, cw, ch, "rgba(20, 30, 56, 0.94)", accent, 18)
        ctx.textAlign = "center"
        ctx.fillStyle = accent
        ctx.font = "800 %dpx %s" % (max(17, int(26 * k)), FONT)
        ctx.fillText(name, x + cw / 2, y + ch * 0.28)
        ctx.fillStyle = "#eaf2ff"
        ctx.font = "700 %dpx %s" % (max(12, int(15 * k)), FONT)
        ctx.fillText(sub, x + cw / 2, y + ch * 0.45)
        ctx.fillStyle = "#93a4c8"
        ctx.font = "600 %dpx %s" % (max(10, int(13 * k)), FONT)
        ctx.fillText(note, x + cw / 2, y + ch * 0.58)
        bw = min(cw - 60, 220.0)
        _button(x + (cw - bw) / 2, y + ch * 0.70, bw, max(38.0, ch * 0.22),
                "Play", True, accent, size=max(13, int(16 * k)))
        _menu_hit.append((tag, (x, y, cw, ch)))

    base = oy + (2 * ch + 12) if narrow else oy + ch
    ly = base + 26
    _wrap("Roll a 6 to bring a token out. Land on an opponent to send it home.",
          W / 2, ly, min(700, W - 30), 13)
    _wrap("First to get all four tokens to the centre wins.",
          W / 2, ly + 36, min(700, W - 30), 13)
    dw = min(240.0, W - 2 * pad)
    _button(W / 2 - dw / 2, ly + 62, dw, 42, "Token design & names", False)
    _menu_hit.append(("design", (W / 2 - dw / 2, ly + 62, dw, 42)))


def _draw_count():
    global _menu_hit
    _menu_hit = []
    _bg()
    _title("SINGLE-SINGLE", 70, 34)
    _wrap("How many players?", W / 2, 110, min(640, W - 40), 16)

    pad = 16.0
    gap = max(10.0, W * 0.028)
    cw = min(210.0, (W - 2 * pad - 2 * gap) / 3.0)
    ch = cw * 0.96
    k = cw / 190.0                      # the card's contents scale with it
    ox = (W - (3 * cw + 2 * gap)) / 2.0
    oy = max(140.0, H * 0.16)
    info = [
        ("2", "2 Players", "Red vs Yellow", "#ff3b5c"),
        ("3", "3 Players", "Red, Green, Yellow", "#22c55e"),
        ("4", "4 Players", "All four corners", "#fbbf24"),
    ]
    for i, (tag, name, sub, accent) in enumerate(info):
        x = ox + i * (cw + gap)
        _panel(x, oy, cw, ch, "rgba(20, 30, 56, 0.94)", accent, 18)
        ctx.textAlign = "center"
        ctx.fillStyle = accent
        ctx.font = "800 %dpx %s" % (max(28, int(52 * k)), FONT)
        ctx.fillText(tag, x + cw / 2, oy + ch * 0.39)
        ctx.fillStyle = "#eaf2ff"
        ctx.font = "800 %dpx %s" % (max(13, int(17 * k)), FONT)
        ctx.fillText(name, x + cw / 2, oy + ch * 0.57)
        ctx.fillStyle = "#93a4c8"
        ctx.font = "600 %dpx %s" % (max(9, int(12 * k)), FONT)
        ctx.fillText(sub, x + cw / 2, oy + ch * 0.68)
        _button(x + cw * 0.15, oy + ch * 0.77, cw * 0.7, max(32, 36 * k),
                "Next", True, accent, size=max(11, int(14 * k)))
        _menu_hit.append((tag, (x, oy, cw, ch)))

    bw = min(200.0, W * 0.6)
    by = oy + ch + max(28.0, H * 0.05)
    _button(W / 2 - bw / 2, by, bw, 46, "\u2190 Back")
    _menu_hit.append(("back", (W / 2 - bw / 2, by, bw, 46)))


def _draw_setup():
    global _menu_hit, _name_fields
    _menu_hit = []
    _name_fields = []
    _bg()
    _title("SET UP", 54, 30)
    _wrap("Pick a token design, then tap a name to type your own.",
          W / 2, 84, min(720, W - 40), 13)

    pad = 14.0
    n = len(DESIGNS)
    cols = max(3, min(n, int((W - 2 * pad) // 104)))
    gap = max(8.0, W * 0.018)
    sw = (W - 2 * pad - (cols - 1) * gap) / cols
    sh = max(70.0, sw * 0.84)
    oy = 104.0
    rows = int(math.ceil(n / float(cols)))
    for i, d in enumerate(DESIGNS):
        x = pad + (i % cols) * (sw + gap)
        y = oy + (i // cols) * (sh + gap)
        sel = (d == design)
        _panel(x, y, sw, sh, "rgba(20, 30, 56, 0.94)",
               "#ffb703" if sel else "rgba(150,180,240,0.20)", 14)
        _draw_token({"x": x + sw / 2, "y": y + sh * 0.42, "c": RED}, label=False)
        ctx.textAlign = "center"
        ctx.fillStyle = "#ffd23f" if sel else "#9fb3d9"
        ctx.font = "700 %dpx %s" % (max(9, int(12 * min(1.0, sw / 116.0))), FONT)
        ctx.fillText(DESIGN_LABEL[d], x + sw / 2, y + sh - 10)
        _menu_hit.append(("d:" + d, (x, y, sw, sh)))

    # names, in one column on a narrow screen and two when there is room
    ny = oy + rows * (sh + gap) + 22
    _wrap("Player names", W / 2, ny, min(400, W - 40), 13, "#8fa3c9")
    cols2 = 1 if W < 520 else 2
    fgap = gap
    fw = (W - 2 * pad - (cols2 - 1) * fgap) / cols2
    fh = 44.0
    fy0 = ny + 14
    # the names to edit: the round's colours, or the default set before one starts
    if players:
        seated = list(players)
    elif mode == "team":
        seated = [RED, GREEN, YELLOW, BLUE]
    else:
        seated = {2: [RED, YELLOW], 3: [RED, GREEN, YELLOW],
                  4: [RED, GREEN, YELLOW, BLUE]}.get(player_count, [RED, YELLOW])
    for kk, col in enumerate(seated):
        cx = pad + (kk % cols2) * (fw + fgap)
        cy = fy0 + (kk // cols2) * (fh + 10)
        _panel(cx, cy, fw, fh, "rgba(20, 30, 56, 0.9)", PAL[col]["main"], 11)
        ctx.beginPath()
        ctx.arc(cx + 24, cy + fh / 2, 9, 0, 6.2832)
        ctx.fillStyle = PAL[col]["main"]
        ctx.fill()
        ctx.textAlign = "left"
        ctx.fillStyle = "#eaf2ff"
        ctx.font = "700 %dpx %s" % (max(12, int(15 * min(1.0, fw / 300.0))), FONT)
        ctx.fillText(names[col], cx + 42, cy + fh / 2 + 5)
        ctx.textAlign = "right"
        ctx.fillStyle = "#7f8fb3"
        ctx.font = "600 10px %s" % FONT
        if fw > 220:
            ctx.fillText("tap to edit", cx + fw - 12, cy + fh / 2 + 4)
        _name_fields.append((col, (cx, cy, fw, fh)))

    # the buttons sit at the bottom, clear of everything above
    bw = min(220.0, (W - 3 * pad) / 2.0)
    by = H - 62
    _button(pad, by, bw, 46, "\u2190 Back")
    _button(W - pad - bw, by, bw, 46, "Start game", True)
    _menu_hit = [("back", (pad, by, bw, 46)),
                 ("start", (W - pad - bw, by, bw, 46))] + _menu_hit


def _draw_over():
    global _menu_hit
    _menu_hit = []
    for p in _confetti:
        ctx.beginPath()
        ctx.arc(p["x"], p["y"], p["r"], 0, 6.2832)
        ctx.fillStyle = p["col"]
        ctx.globalAlpha = 0.85
        ctx.fill()
        ctx.globalAlpha = 1.0
    ctx.fillStyle = "rgba(4, 10, 24, 0.80)"
    ctx.fillRect(0, 0, W, H)

    pad = 16.0
    cw = min(560.0, W - 2 * pad)
    ch = min(300.0, H * 0.44)
    cx = (W - cw) / 2.0
    cy = (H - ch) / 2.0
    _panel(cx, cy, cw, ch, "rgba(12, 20, 42, 0.97)", PAL[winner]["main"], 22)

    ctx.textAlign = "center"
    ctx.fillStyle = PAL[winner]["main"]
    ctx.font = "800 %dpx %s" % (max(24, int(34 * min(1.0, cw / 600.0))), FONT)
    ctx.fillText("WINNER!", W / 2, cy + ch * 0.24)

    if mode == "team" and teams:
        tname = "Team A" if teams.get(winner, 0) == 0 else "Team B"
        mate = [k for k, v in teams.items() if v == teams.get(winner) and k != winner]
        sub_ = "  (%s + %s)" % (names[winner], names[mate[0]]) if mate else ""
        label = tname + sub_
    else:
        label = names[winner]
    ctx.fillStyle = "#eaf2ff"
    ctx.font = "800 %dpx %s" % (max(17, int(26 * min(1.0, cw / 600.0))), FONT)
    ctx.fillText(label, W / 2, cy + ch * 0.45)

    _wrap("All four tokens are home.", W / 2, cy + ch * 0.60, cw - 40, 15,
          "#cfe0ff")

    bw = min(210.0, (cw - 3 * pad) / 2.0)
    by = cy + ch - 62
    _button(cx + pad, by, bw, 46, "Play again", True)
    _button(cx + cw - pad - bw, by, bw, 46, "Main menu", False)
    _menu_hit = [("again", (cx + pad, by, bw, 46)),
                 ("menu", (cx + cw - pad - bw, by, bw, 46))]


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
def draw():
    if state == "mode":
        _draw_mode()
        return
    if state == "count":
        _draw_count()
        return
    if state == "setup":
        _draw_setup()
        return

    _bg()
    _draw_board()
    _draw_tokens()
    _draw_hud()

    for f in flash:
        ctx.beginPath()
        ctx.arc(f["x"], f["y"], f["r"], 0, 6.2832)
        ctx.fillStyle = f["col"]
        ctx.globalAlpha = max(0.0, f["life"] / 0.6)
        ctx.fill()
        ctx.globalAlpha = 1.0

    if state == "over":
        _draw_over()

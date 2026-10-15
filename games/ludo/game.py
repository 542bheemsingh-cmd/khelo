"""
Khelo Ludo - a full Ludo board game written in Python.

Runs in the browser through Pyodide, like the rest of the Khelo arcade.

The board is the classic 15x15 grid. Four players sit in the corners, each with
four tokens in their yard. Roll a 6 to bring a token out, race it around the
52-square ring, then up your own coloured home column to the centre. Land on an
opponent and it goes back to their yard. First player (or team) to get all four
tokens home wins.

Modes:
    single-single : 2, 3 or 4 players, everyone for themselves
    team-team     : 4 players, Red+Yellow against Green+Blue

The page calls:
    tap(x, y)   -> a click / tap on the canvas
    update(dt)  -> advance the animation
    draw()      -> render a frame
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
ctx = canvas.getContext("2d")
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

# the four colours, tuned to look good on the dark board
PAL = {
    RED:    {"main": "#ff3b5c", "dark": "#c01f3d", "lite": "#ff8199", "soft": "#5c1526"},
    GREEN:  {"main": "#22c55e", "dark": "#15803d", "lite": "#7ee2a4", "soft": "#123d24"},
    YELLOW: {"main": "#fbbf24", "dark": "#b45309", "lite": "#fde08a", "soft": "#4d3512"},
    BLUE:   {"main": "#3b82f6", "dark": "#1d4ed8", "lite": "#9cc3fd", "soft": "#132a54"},
}
NAME = {RED: "Red", GREEN: "Green", YELLOW: "Yellow", BLUE: "Blue"}

# The ring of track squares, in clockwise order. Every step is to an
# orthogonally adjacent square, so a token always walks a real path - including
# round the four inner corners of the cross.
TRACK = [
    (6, 13), (6, 12), (6, 11), (6, 10), (6, 9),                       # 0-4
    (6, 8),                                                           # 5  inner corner
    (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),                   # 6-11
    (0, 7),                                                           # 12 arm tip
    (0, 6), (1, 6), (2, 6), (3, 6), (4, 6), (5, 6),                   # 13-18
    (6, 6),                                                           # 19 inner corner
    (6, 5), (6, 4), (6, 3), (6, 2), (6, 1), (6, 0),                   # 20-25
    (7, 0),                                                           # 26 arm tip
    (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5),                   # 27-32
    (8, 6),                                                           # 33 inner corner
    (9, 6), (10, 6), (11, 6), (12, 6), (13, 6), (14, 6),              # 34-39
    (14, 7),                                                          # 40 arm tip
    (14, 8), (13, 8), (12, 8), (11, 8), (10, 8), (9, 8),              # 41-46
    (8, 8),                                                           # 47 inner corner
    (8, 9), (8, 10), (8, 11), (8, 12), (8, 13), (8, 14),              # 48-53
    (7, 14),                                                          # 54 arm tip
    (6, 14),                                                          # 55
]
TRACK_LEN = len(TRACK)
LAST_TRACK = TRACK_LEN - 2        # the arm tip a token turns off the ring at

START = {RED: 14, GREEN: 28, YELLOW: 42, BLUE: 0}

# a token walks 0..54 on the ring, then 55..59 up its home column, then 60 = home
HOME_LEN = 5
HOME_POS = LAST_TRACK + HOME_LEN + 1

HOME_PATH = {
    RED:    [(1, 7), (2, 7), (3, 7), (4, 7), (5, 7)],
    GREEN:  [(7, 1), (7, 2), (7, 3), (7, 4), (7, 5)],
    YELLOW: [(13, 7), (12, 7), (11, 7), (10, 7), (9, 7)],
    BLUE:   [(7, 13), (7, 12), (7, 11), (7, 10), (7, 9)],
}

# safe squares: the four start squares plus the four star squares
SAFE = {START[RED], START[GREEN], START[YELLOW], START[BLUE],
        (START[RED] + 8) % TRACK_LEN, (START[GREEN] + 8) % TRACK_LEN,
        (START[YELLOW] + 8) % TRACK_LEN, (START[BLUE] + 8) % TRACK_LEN}

YARD = {RED: (0, 0), GREEN: (9, 0), YELLOW: (9, 9), BLUE: (0, 9)}
YARD_SLOTS = [(1.5, 1.5), (4.5, 1.5), (1.5, 4.5), (4.5, 4.5)]

# the centre triangles, one per colour (drawn as a 3x3 block)
CENTRE = (6, 6)


def cell_px(cx, cy):
    """Centre of grid cell (cx, cy) in pixels."""
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
        # tucked into the centre, fanned out a little per token
        cx, cy = cell_px(CENTRE[0] + 1, CENTRE[1] + 1)
        ang = math.radians(90 * c + 25 * idx - 40)
        return cx + math.cos(ang) * 11, cy + math.sin(ang) * 11
    cx, cy = path_cell(c, pos)
    return cell_px(cx, cy)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
state = "mode"            # mode | count | play | over
mode = "single"           # single | team
player_count = 4
players = []              # the colours in play, in turn order
teams = {}                # colour -> team index (team mode only)
turn = 0                  # index into `players`
dice = 6
dice_show = 6
rolling = 0.0
moves = []                # [(token_index, target_pos)] for the current roll
can_roll = True
message = ""
tokens = []               # one dict per token: {c, i, pos, x, y}
anim = None
flash = []                # floating "+1" style effects
winner = None
_rng = random.Random()
_t = 0.0                  # seconds, for the pulsing glow
_menu_hit = []
_confetti = []


def _sound(name):
    try:
        js.playSound(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Setting up a game
# ---------------------------------------------------------------------------
def start_game(m, count=4):
    global state, mode, player_count, players, teams, turn, tokens
    global dice, dice_show, moves, can_roll, message, anim, winner, rolling
    mode = m
    if m == "team":
        player_count = 4
        players = [RED, GREEN, YELLOW, BLUE]
        teams = {RED: 0, YELLOW: 0, GREEN: 1, BLUE: 1}
    else:
        player_count = count
        players = {2: [RED, YELLOW], 3: [RED, GREEN, YELLOW],
                   4: [RED, GREEN, YELLOW, BLUE]}[count]
        teams = {}

    tokens = []
    for c in players:
        for i in range(4):
            x, y = token_xy(c, i, -1)
            tokens.append({"c": c, "i": i, "pos": -1, "x": x, "y": y})

    turn = 0
    dice = dice_show = 6
    rolling = 0.0
    moves = []
    can_roll = True
    anim = None
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


def restart():
    start_game(mode, player_count)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def cur():
    return players[turn % len(players)]


def my_tokens(c):
    return [t for t in tokens if t["c"] == c]


def legal_moves(c, d):
    """Every (token, target_pos) the current player may choose."""
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


def roll():
    """Roll the dice (animated) - only when it is the player's turn to roll."""
    global rolling, dice, can_roll
    if state != "play" or anim or rolling > 0 or not can_roll:
        return
    dice = _rng.randint(1, 6)
    rolling = 0.65
    can_roll = False
    _sound("roll")


def _after_roll():
    """Work out what the player may do with the number they rolled."""
    global moves, can_roll, message
    c = cur()
    moves = legal_moves(c, dice)
    if not moves:
        message = "%s rolled %d - no move." % (NAME[c], dice)
        _sound("deny")
        _pass_turn()
        return
    can_roll = False
    message = "%s rolled %d - tap a token." % (NAME[c], dice)
    _sound("click")


def _pass_turn(delay=0.9):
    global turn, can_roll, moves, message
    if dice == 6:
        # a 6 always earns another go, even with nothing to move
        can_roll = True
        moves = []
        return
    turn = (turn + 1) % len(players)
    moves = []
    can_roll = True
    message = "%s to roll." % NAME[cur()]


def _captures_at(cell, moving_color):
    """Opponent tokens standing on `cell` that this move would send home."""
    if cell is None:
        return []
    idx = TRACK.index(cell) if cell in TRACK else None
    if idx is None or idx in SAFE:
        return []
    hits = []
    for t in tokens:
        if t["c"] == moving_color or t["pos"] < 0 or t["pos"] > LAST_TRACK:
            continue
        if path_cell(t["c"], t["pos"]) == cell:
            hits.append(t)
    return hits


def _choose(t, target):
    """Commit to moving token `t` to `target` (starts the animation)."""
    global moves, message
    if anim:
        return
    if not any(m[0] is t and m[1] == target for m in moves):
        return
    moves = []
    _animate_move(t, target)
    _sound("hop")


def _animate_move(t, target):
    global anim
    cells = []
    for p in range(t["pos"] + 1, target + 1):
        xy = token_xy(t["c"], t["i"], p)
        cells.append((p, xy[0], xy[1]))
    anim = {"t": t, "cells": cells, "i": 0, "p": 0.0,
            "dice": dice, "captured": 0, "finished": False}
    if cells:
        t["pos"] = cells[0][0]


def _finish_move(a):
    """Resolve captures, extra turns and the win once a token stops."""
    global turn, can_roll, moves, message, winner, state
    t = a["t"]
    c = t["c"]
    extra = (a["dice"] == 6)

    # capture anyone standing on the landing square
    if t["pos"] <= LAST_TRACK:
        cell = path_cell(c, t["pos"])
        hits = _captures_at(cell, c)
        for h in hits:
            h["pos"] = -1
            hx, hy = token_xy(h["c"], h["i"], -1)
            h["x"], h["y"] = hx, hy
            _burst(hx, hy, PAL[h["c"]]["main"])
            extra = True
        if hits:
            _sound("capture")
            message = "%s captured %d!" % (NAME[c], len(hits))

    if t["pos"] >= HOME_POS:
        extra = True
        _sound("home")
        _burst(*token_xy(c, t["i"], HOME_POS), PAL[c]["lite"])
        message = "%s got a token home!" % NAME[c]

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
        message = "%s to roll." % NAME[cur()]


def _won(c):
    if all(t["pos"] >= HOME_POS for t in my_tokens(c)):
        if mode == "team":
            mate = [k for k, v in teams.items() if v == teams[c] and k != c][0]
            return all(t["pos"] >= HOME_POS for t in my_tokens(mate))
        return True
    return False


def _burst(x, y, col):
    for _ in range(10):
        a = _rng.uniform(0, 6.283)
        s = _rng.uniform(40, 130)
        flash.append({"x": x, "y": y, "vx": math.cos(a) * s, "vy": math.sin(a) * s,
                      "life": 0.6, "col": col, "r": _rng.uniform(2, 4)})


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
def _in(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def tap(x, y):
    global state
    if state == "mode":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("click")
                if tag == "single":
                    state = "count"
                elif tag == "team":
                    start_game("team")
                return
        return

    if state == "count":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("click")
                if tag == "back":
                    state = "mode"
                else:
                    start_game("single", int(tag))
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
    if _in((700, 250, 150, 46), x, y) or _in((640, 100, 170, 130), x, y):
        roll()
        return
    if _in((16, 16, 110, 38), x, y):
        state = "mode"
        _sound("click")
        return

    # tap a token to move it
    if anim or not moves:
        return
    best, bestd = None, 26
    for t, target in moves:
        tx, ty = token_xy(t["c"], t["i"], t["pos"])
        d = math.hypot(x - tx, y - ty)
        if d < bestd:
            best, bestd = (t, target), d
    if best:
        _choose(best[0], best[1])


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def update(dt):
    global rolling, anim, _t, message, can_roll
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
        global dice_show
        rolling -= dt
        dice_show = _rng.randint(1, 6)
        if rolling <= 0:
            dice_show = dice
            _after_roll()

    if anim:
        anim["p"] += dt * 8.5
        while anim["p"] >= 1.0:
            anim["p"] -= 1.0
            anim["i"] += 1
            if anim["i"] >= len(anim["cells"]):
                anim["t"]["pos"] = anim["cells"][-1][0] if anim["cells"] else anim["t"]["pos"]
                done, anim = anim, None
                _finish_move(done)
                break
            p, cx, cy = anim["cells"][anim["i"]]
            anim["t"]["pos"] = p

    # tokens ease toward wherever they belong
    for t in tokens:
        tx, ty = token_xy(t["c"], t["i"], t["pos"])
        if anim and anim["t"] is t:
            tx, ty = token_xy(t["c"], t["i"], t["pos"])
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


# ---------------------------------------------------------------------------
# Drawing the board
# ---------------------------------------------------------------------------
def _draw_board():
    # the plate the whole board sits on
    _panel(BX - 12, BY - 12, BOARD + 24, BOARD + 24,
           "rgba(9, 15, 32, 0.95)", "rgba(150, 180, 240, 0.18)", 16)

    # four yards
    for c in (RED, GREEN, YELLOW, BLUE):
        ox, oy = YARD[c]
        px, py = BX + ox * CELL, BY + oy * CELL
        p = PAL[c]
        _panel(px + 3, py + 3, CELL * 6 - 6, CELL * 6 - 6, p["soft"], p["main"], 12)
        _panel(px + CELL + 6, py + CELL + 6, CELL * 4 - 12, CELL * 4 - 12,
               "rgba(8, 14, 30, 0.55)", "rgba(255,255,255,0.10)", 10)
        # four token slots
        for sx, sy in YARD_SLOTS:
            cx, cy = cell_px(ox + sx - 0.5, oy + sy - 0.5)
            ctx.beginPath()
            ctx.arc(cx, cy, CELL * 0.52, 0, 6.2832)
            ctx.fillStyle = "rgba(255,255,255,0.07)"
            ctx.fill()
            ctx.lineWidth = 2
            ctx.strokeStyle = "rgba(255,255,255,0.16)"
            ctx.stroke()

    # every square of the ring
    for idx, (cx, cy) in enumerate(TRACK):
        px, py = BX + cx * CELL, BY + cy * CELL
        owner = None
        for c in (RED, GREEN, YELLOW, BLUE):
            if START[c] == idx:
                owner = c
        if owner is not None:
            fill = PAL[owner]["main"]
        elif idx in SAFE:
            fill = "rgba(226, 236, 255, 0.92)"
        else:
            fill = "rgba(238, 244, 255, 0.90)"
        ctx.fillStyle = fill
        ctx.fillRect(px, py, CELL, CELL)
        ctx.lineWidth = 1
        ctx.strokeStyle = "rgba(20, 30, 60, 0.45)"
        ctx.strokeRect(px + 0.5, py + 0.5, CELL - 1, CELL - 1)
        if idx in SAFE and owner is None:
            _star(px + CELL / 2, py + CELL / 2, CELL * 0.28, "#7c8aa8")

    # the four home columns
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
    order = [GREEN, YELLOW, BLUE, RED]      # top-left, top-right, bottom-right, bottom-left
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
    # a small ring in the middle
    ctx.beginPath()
    ctx.arc(mid[0], mid[1], CELL * 0.62, 0, 6.2832)
    ctx.fillStyle = "rgba(8, 14, 30, 0.75)"
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = "rgba(255,255,255,0.25)"
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


def _draw_token(t, highlight=False, movable=False):
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

    # soft shadow
    ctx.beginPath()
    ctx.ellipse(x, y + r * 0.75, r * 0.85, r * 0.38, 0, 0, 6.2832)
    ctx.fillStyle = "rgba(0,0,0,0.35)"
    ctx.fill()

    # body
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

    # specular highlight
    ctx.beginPath()
    ctx.arc(x - r * 0.32, y - r * 0.38, r * 0.26, 0, 6.2832)
    ctx.fillStyle = "rgba(255,255,255,0.75)"
    ctx.fill()

    if movable:
        ctx.beginPath()
        ctx.arc(x, y, r + 4, 0, 6.2832)
        ctx.lineWidth = 2.5
        ctx.strokeStyle = "#ffffff"
        ctx.setLineDash([4, 4])
        ctx.lineDashOffset = -_t * 14
        ctx.stroke()
        ctx.setLineDash([])


def _draw_tokens():
    c = cur() if state == "play" else None
    movable = {id(m[0]) for m in moves}          # dicts are not hashable
    # the moving token on top, then everyone else
    order = sorted(tokens, key=lambda t: 1 if (anim and anim["t"] is t) else 0)
    for t in order:
        _draw_token(t, highlight=(c is not None and t["c"] == c),
                    movable=(id(t) in movable))


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


def _draw_die(x, y, s, n, col="#ffffff", dark="#c9d6ef"):
    _panel(x, y, s, s, col, "rgba(20, 30, 60, 0.35)", 14)
    r = s * 0.115
    step = s * 0.26
    cx, cy = x + s / 2, y + s / 2
    for dx, dy in PIPS[n]:
        ctx.beginPath()
        ctx.arc(cx + dx * step, cy + dy * step, r, 0, 6.2832)
        ctx.fillStyle = dark
        ctx.fill()


# ---------------------------------------------------------------------------
# HUD panel
# ---------------------------------------------------------------------------
def _draw_hud():
    x = 552
    _panel(x, BY - 12, 322, BOARD + 24, "rgba(11, 18, 38, 0.92)",
           "rgba(150, 180, 240, 0.20)", 16)

    c = cur() if state == "play" else None
    ctx.textAlign = "center"
    ctx.fillStyle = "#8fa3c9"
    ctx.font = "800 11px %s" % FONT
    ctx.fillText("TURN", x + 161, BY + 12)
    if c is not None:
        ctx.fillStyle = PAL[c]["main"]
        ctx.font = "800 26px %s" % FONT
        ctx.fillText(NAME[c], x + 161, BY + 42)
        if mode == "team":
            ctx.fillStyle = "#8fa3c9"
            ctx.font = "700 12px %s" % FONT
            ctx.fillText("Team A" if teams[c] == 0 else "Team B", x + 161, BY + 62)

    # the die
    dx, dy, ds = x + 85, BY + 74, 152
    if state == "play":
        glow = 0.5 + 0.5 * math.sin(_t * 3)
        _panel(dx - 6, dy - 6, ds + 12, ds + 12,
               "rgba(255,255,255,0.05)", "rgba(255,255,255,%.2f)" % (0.10 + glow * 0.12), 18)
    _draw_die(dx, dy, ds, dice_show)

    if state == "play":
        ready = can_roll and rolling <= 0 and not anim
        _button(x + 76, BY + 262, 170, 44, "ROLL" if ready else "…",
                ready, PAL[c]["main"], size=17)
        if not ready and rolling <= 0 and not anim and moves:
            _wrap("tap a token", x + 161, BY + 322, 260, 12, "#8fa3c9")

    # every player's progress
    y = BY + 344
    for i, col in enumerate(players):
        active = (state == "play" and i == turn % len(players))
        _panel(x + 18, y, 286, 30,
               PAL[col]["soft"] if active else "rgba(20, 30, 56, 0.6)",
               PAL[col]["main"] if active else "rgba(150,180,240,0.14)", 9)
        ctx.beginPath()
        ctx.arc(x + 38, y + 15, 8, 0, 6.2832)
        ctx.fillStyle = PAL[col]["main"]
        ctx.fill()
        ctx.textAlign = "left"
        ctx.fillStyle = "#eaf2ff"
        ctx.font = "700 12px %s" % FONT
        label = NAME[col]
        if mode == "team":
            label += "  (A)" if teams[col] == 0 else "  (B)"
        ctx.fillText(label, x + 56, y + 20)
        home = sum(1 for t in my_tokens(col) if t["pos"] >= HOME_POS)
        out = sum(1 for t in my_tokens(col) if 0 <= t["pos"] < HOME_POS)
        ctx.textAlign = "right"
        ctx.fillStyle = "#9fb3d9"
        ctx.font = "700 11px %s" % FONT
        ctx.fillText("%d home · %d out" % (home, out), x + 292, y + 20)
        y += 33

    if message:
        _wrap(message, x + 161, y + 9, 286, 12, "#cfe0ff")


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
def _draw_mode():
    global _menu_hit
    _menu_hit = []
    _bg()
    _title("KHELO LUDO", 76, 40)
    _wrap("The classic race home - pick how you want to play.", W / 2, 112, 640, 16)

    cw, ch, gap = 330, 210, 40
    ox = W / 2 - cw - gap / 2
    oy = 168
    cards = [
        ("single", "Single-Single", "Everyone for themselves", "#4aa8ff",
         "Choose 2, 3 or 4 players"),
        ("team", "Team-Team", "2 players against 2", "#fbbf24",
         "Red + Yellow vs Green + Blue"),
    ]
    for i, (tag, name, sub, accent, note) in enumerate(cards):
        x = ox + i * (cw + gap)
        _panel(x, oy, cw, ch, "rgba(20, 30, 56, 0.94)", accent, 18)
        ctx.textAlign = "center"
        ctx.fillStyle = accent
        ctx.font = "800 26px %s" % FONT
        ctx.fillText(name, x + cw / 2, oy + 58)
        ctx.fillStyle = "#eaf2ff"
        ctx.font = "700 15px %s" % FONT
        ctx.fillText(sub, x + cw / 2, oy + 92)
        ctx.fillStyle = "#93a4c8"
        ctx.font = "600 13px %s" % FONT
        ctx.fillText(note, x + cw / 2, oy + 118)
        _button(x + 55, oy + 148, cw - 110, 44, "Play", True, accent)
        _menu_hit.append((tag, (x, oy, cw, ch)))

    _wrap("Roll a 6 to bring a token out. Land on an opponent to send it home.",
          W / 2, 430, 720, 14)
    _wrap("First to get all four tokens to the centre wins.", W / 2, 456, 720, 14)
    _button(16, 16, 110, 38, "\u2190 Games")


def _draw_count():
    global _menu_hit
    _menu_hit = []
    _bg()
    _title("SINGLE-SINGLE", 76, 34)
    _wrap("How many players?", W / 2, 116, 640, 17)

    cw, ch, gap = 190, 190, 24
    ox = W / 2 - (3 * cw + 2 * gap) / 2
    oy = 172
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
        ctx.font = "800 52px %s" % FONT
        ctx.fillText(tag, x + cw / 2, oy + 74)
        ctx.fillStyle = "#eaf2ff"
        ctx.font = "800 17px %s" % FONT
        ctx.fillText(name, x + cw / 2, oy + 108)
        ctx.fillStyle = "#93a4c8"
        ctx.font = "600 12px %s" % FONT
        ctx.fillText(sub, x + cw / 2, oy + 130)
        _button(x + 30, oy + 146, cw - 60, 36, "Start", True, accent, size=14)
        _menu_hit.append((tag, (x, oy, cw, ch)))

    _button(W / 2 - 90, 430, 180, 44, "\u2190 Back")
    _menu_hit.append(("back", (W / 2 - 90, 430, 180, 44)))


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
    ctx.fillStyle = "rgba(4, 10, 24, 0.78)"
    ctx.fillRect(0, 0, W, H)
    _panel(W / 2 - 300, 130, 600, 300, "rgba(12, 20, 42, 0.96)",
           PAL[winner]["main"], 22)
    _title("WINNER!", 196, 34, PAL[winner]["main"])
    if mode == "team":
        tname = "Team A" if teams[winner] == 0 else "Team B"
        _title("%s  (%s + %s)" % (tname, NAME[winner],
               NAME[[k for k, v in teams.items() if v == teams[winner] and k != winner][0]]),
               244, 24)
    else:
        _title(NAME[winner], 244, 26)
    _wrap("All four tokens are home.", W / 2, 288, 520, 16, "#cfe0ff")
    _button(W / 2 - 250, H - 150, 230, 52, "Play again", True)
    _button(W / 2 + 20, H - 150, 230, 52, "Main menu", False)
    _menu_hit = [("again", (W / 2 - 250, H - 150, 230, 52)),
                 ("menu", (W / 2 + 20, H - 150, 230, 52))]


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

    _bg()
    _draw_board()
    _draw_tokens()
    _draw_hud()

    # sparkles
    for f in flash:
        ctx.beginPath()
        ctx.arc(f["x"], f["y"], f["r"], 0, 6.2832)
        ctx.fillStyle = f["col"]
        ctx.globalAlpha = max(0.0, f["life"] / 0.6)
        ctx.fill()
        ctx.globalAlpha = 1.0

    if state == "over":
        _draw_over()

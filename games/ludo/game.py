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

    global BACK_RECT
    BACK_RECT = (HUD_X + HUD_W - 92.0, HUD_Y + 8.0, 84.0, 28.0)

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
DESIGNS = ["pawn", "ball", "crown", "rocket", "plane", "car",
           "gem", "ring", "star", "hex"]
DESIGN_LABEL = {"pawn": "Pawn", "ball": "Ball", "crown": "Crown",
                "rocket": "Rocket", "plane": "Plane", "car": "Car",
                "gem": "Gem", "ring": "Ring", "star": "Star", "hex": "Hex"}
design = "pawn"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
state = "mode"            # mode | count | setup | play | over
# ---------------------------------------------------------------------------
# House rules
#
# Ludo is not one game, it is a board with a dozen dials. Every one of these is
# a real difference between tables - the presets below are just starting points.
# ---------------------------------------------------------------------------
RULES = {
    "exit": "six",          # six | any       - what brings a token out
    "six_bonus": True,      # roll again on a six
    "six_limit": 3,         # a third six in a row voids the turn (0 = off)
    "capture_bonus": True,  # roll again after sending somebody home
    "home_bonus": True,     # roll again after bringing a token home
    "exact_home": True,     # False lets a token bounce back off the centre
    "safe_squares": True,   # the stars and the start squares are shelter
    "blocks": False,        # a pair of one colour is a wall nobody passes
    "kill_to_enter": False, # you must capture once before you may go home
    "capture_forced": False,# capture whenever you can
    "tokens": 4,            # 2 to 4 tokens each
    "first_home_wins": False,
    # --- how it looks and feels (accessibility) ---
    "marks": True,          # every colour also carries its own shape
    "reduced_motion": False,# no confetti, shorter hops, no pulsing
    "high_contrast": False, # heavier outlines, brighter text
    "theme": "classic",     # classic | night | mint
    "turn_timer": 0,        # 0 = off, otherwise seconds before it rolls for you
}

MODES = {
    "classic": {},
    "quick": {"tokens": 2, "exit": "any", "first_home_wins": True},
    "master": {"kill_to_enter": True},
    "onekill": {"first_home_wins": True},
    "plain": {"safe_squares": False, "capture_bonus": False,
              "home_bonus": False},
    "wild": {"safe_squares": False, "capture_forced": True, "blocks": True},
}
MODE_LABEL = {
    "classic": "Classic", "quick": "Quick", "master": "Master",
    "onekill": "One Kill", "plain": "Plain", "wild": "Wild",
}
MODE_NOTE = {
    "classic": "The full game, four tokens each",
    "quick": "Two tokens, any roll opens, first home wins",
    "master": "Capture once before any token may go home",
    "onekill": "The first token home takes it",
    "plain": "No shelter, no bonuses - just the race",
    "wild": "No shelter, blocks, and captures are compulsory",
}
sixes_in_a_row = 0        # a third six voids the turn
rule_mode = "classic"     # which preset the mode screen has chosen
_rules_loaded = False
captured_any = {}         # colour -> how many it has captured
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
last_move = None          # {"x","y","c","t"} - a ring left where a token stopped
turn_clock = 0.0          # seconds the current player has been thinking
shake = 0.0               # brief camera kick on a capture

# ---------------------------------------------------------------------------
# Multiplayer
#
# One device is the host and runs the whole game. The others are guests: they
# draw whatever the host says is true, and ask the host to roll or move for
# them. Turn based games do not need anything cleverer than that.
# ---------------------------------------------------------------------------
net_on = False
net_host = True
net_seat = -1
net_present = []        # seat indices that still have somebody behind them
net_seats = {}

ROLL_DUR = 2.0          # the die takes its time
# -1 means nothing pending; 0 means "play it on the next frame"
auto_move_t = -1.0

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
    global auto_move_t, sixes_in_a_row
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
    captured_any.clear()
    sixes_in_a_row = 0
    for c in players:
        for i in range(max(1, min(4, int(RULES.get("tokens") or 4)))):
            x, y = token_xy(c, i, -1)
            tokens.append({"c": c, "i": i, "pos": -1, "x": x, "y": y})

    turn = 0
    dice = dice_show = 6
    rolling = 0.0
    roll_t = 1.0
    auto_move_t = -1.0
    turn_clock = 0.0
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


def set_rules(js):
    """Adopt a whole rule set from the settings screen."""
    global RULES
    try:
        d = json.loads(js)
    except Exception:
        return
    if not isinstance(d, dict):
        return
    for k, v in d.items():
        if k in RULES:
            RULES[k] = v


def rules_json():
    return json.dumps(RULES)


STATS = {"games": 0, "wins": 0, "by_mode": {}}


def _load_stats():
    try:
        v = js.localStorage.getItem("khelo_ludo_stats")
        if v:
            d = json.loads(v)
            STATS["games"] = int(d.get("games", 0))
            STATS["wins"] = int(d.get("wins", 0))
            STATS["by_mode"] = dict(d.get("by_mode", {}))
    except Exception:
        pass


def _bump_stats(won):
    STATS["games"] += 1
    if won:
        STATS["wins"] += 1
        STATS["by_mode"][rule_mode] = STATS["by_mode"].get(rule_mode, 0) + 1
    try:
        js.localStorage.setItem("khelo_ludo_stats", json.dumps(STATS))
    except Exception:
        pass


def _save_rules():
    try:
        js.localStorage.setItem("khelo_ludo_rules", json.dumps(RULES))
        js.localStorage.setItem("khelo_ludo_rule_mode", rule_mode)
    except Exception:
        pass


def load_rules():
    """Bring back whatever was set last time."""
    global RULES, rule_mode, _rules_loaded
    _rules_loaded = True
    try:
        v = js.localStorage.getItem("khelo_ludo_rules")
        if v:
            d = json.loads(v)
            for k in list(RULES):
                if k in d:
                    RULES[k] = d[k]
        m = js.localStorage.getItem("khelo_ludo_rule_mode")
        if m:
            rule_mode = m
    except Exception:
        pass


def set_rule_mode(m):
    global rule_mode
    if m in MODES:
        rule_mode = m
        apply_mode(m)
        _save_rules()


def toggle_rule(key):
    """Flip one dial from the custom rules screen."""
    global _rules_loaded
    if key in RULES:
        v = RULES[key]
        if isinstance(v, bool):
            RULES[key] = not v
        elif key == "exit":
            RULES[key] = "any" if v == "six" else "six"
        elif key == "six_limit":
            RULES[key] = 0 if v else 3
        elif key == "tokens":
            RULES[key] = 2 if v >= 4 else v + 1
        elif key == "turn_timer":
            RULES[key] = 0 if v else 30
        elif key == "theme":
            i = THEME_ORDER.index(v) if v in THEME_ORDER else 0
            RULES[key] = THEME_ORDER[(i + 1) % len(THEME_ORDER)]
        rule_mode = "custom"
        _save_rules()


def apply_mode(m):
    """Reset every dial, then apply the preset."""
    global RULES
    if m not in MODES:
        return
    RULES = {
        "exit": "six", "six_bonus": True, "six_limit": 3,
        "capture_bonus": True, "home_bonus": True, "exact_home": True,
        "safe_squares": True, "blocks": False, "kill_to_enter": False,
        "capture_forced": False, "tokens": 4, "first_home_wins": False,
        "marks": True, "reduced_motion": False, "high_contrast": False,
        "theme": "classic", "turn_timer": 0,
    }
    RULES.update(MODES[m])


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
        "teams": {str(k): v for k, v in teams.items()},
        "design": design,
        "player_count": player_count,
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
    global rolling, roll_t, dice_show
    mode = d.get("mode", mode)
    players = list(d.get("players", players))
    turn = int(d.get("turn", turn))
    was_dice = dice
    dice = int(d.get("dice", dice))
    if dice != was_dice and rolling <= 0 and state == "play":
        rolling = ROLL_DUR          # a roll from the host tumbles here too
        roll_t = 0.0
        dice_show = dice
    dice_show = int(d.get("dice_show", dice_show))
    can_roll = bool(d.get("can_roll", can_roll))
    message = d.get("message", message)
    winner = d.get("winner")
    state = d.get("state", state)
    if d.get("names"):
        names.update(d["names"])
    global teams, design
    if d.get("teams"):
        teams = {int(k): int(v) for k, v in d["teams"].items()}
    if d.get("design"):
        design = d["design"]

    # rebuild the tokens where the host says they are
    want = d.get("tokens") or []
    have = {(t["c"], t["i"]): t for t in tokens}
    fresh = []
    for c, i, pos in want:
        t = have.get((c, i))
        if t is None:
            t = {"c": c, "i": i, "pos": -1}
        # a token that has never been placed has no x/y yet, so check for that
        # too - otherwise anything still in the yard is never drawn
        if t["pos"] != pos or "x" not in t or "y" not in t:
            tx, ty = token_xy(c, i, pos)
            if "x" in t and t["pos"] != pos and abs(tx - t["x"]) < CELL * 12:
                # slide from where it is drawn to where it now belongs
                t["glide"] = {"x0": t["x"], "y0": t["y"], "x1": tx, "y1": ty,
                              "p": 0.0}
            else:
                t.pop("glide", None)
                t["x"], t["y"] = tx, ty
            t["pos"] = pos
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
    who = str(d.get("from") or "")
    seat = net_seats.get(who)
    if seat is None:
        return                          # we do not know who this is
    if players and seat != turn % len(players):
        return                          # not your turn
    a = d.get("a")
    if a == "roll":
        roll()
    elif a == "move":
        c, i = d.get("c"), int(d.get("i", -1))
        for t, target in moves:
            if t["c"] == c and t["i"] == i:
                _choose(t, target)
                break


def set_present(js):
    """Which seats still have a player.

    If the dice is sitting with somebody who has left, hand it on straight
    away - otherwise the room waits for a roll that can never come.
    """
    global net_present, turn, can_roll, moves, message
    try:
        v = json.loads(js)
        net_present = [int(x) for x in v]
    except Exception:
        net_present = []
        return
    if not (net_on and players and net_present):
        return
    if rolling > 0 or anims:
        return
    if turn % len(players) in net_present:
        return
    for _ in range(len(players)):
        turn = (turn + 1) % len(players)
        if turn in net_present:
            break
    moves = []
    can_roll = True
    message = "%s to roll." % names[cur()]


def set_net_ludo(on, host, seat):
    """A seat of -1 means "not decided yet", so the room's seat list wins."""
    global net_on, net_host, net_seat
    net_on = bool(on)
    net_host = bool(host)
    try:
        n = int(seat)
    except Exception:
        n = -1
    if n >= 0:
        net_seat = n
    elif host:
        net_seat = 0                    # a fresh host plays the first colour


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


def _net_id():
    """Our own id in the room, so the host knows who is asking."""
    try:
        return str(js.netMe())
    except Exception:
        return ""


def my_turn():
    """True when it is the colour this device is playing.

    While the room has not told us our colour yet we answer True, so the tap
    still reaches the host, which is the one that actually decides.
    """
    if not net_on or not players or net_seat < 0:
        return True
    return net_seat == turn % len(players)


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
            if d == 6 or RULES["exit"] == "any":
                out.append((t, 0))
            continue
        if RULES["kill_to_enter"] and not captured_any.get(c):
            # you cannot start up the home column without a scalp
            if p + d > LAST_TRACK:
                continue
        if p + d <= HOME_POS:
            out.append((t, p + d))
        elif not RULES["exact_home"]:
            back = (p + d) - HOME_POS          # bounce off the centre
            if HOME_POS - back >= 0:
                out.append((t, HOME_POS - back))

    # a pair of one colour is a wall you may not land on
    if RULES["blocks"]:
        blocked = set()
        for a in tokens:
            for b in tokens:
                if a is b or a["c"] != b["c"]:
                    continue
                if 0 <= a["pos"] <= LAST_TRACK and 0 <= b["pos"] <= LAST_TRACK:
                    blocked.add(path_cell(a["c"], a["pos"]))
        if blocked:
            out = [(t, q) for t, q in out
                   if q > LAST_TRACK or path_cell(c, q) not in blocked]

    # some tables insist you take a capture when one is on offer
    if RULES["capture_forced"] and out:
        takes = [(t, q) for t, q in out
                 if q <= LAST_TRACK and _captures_at(path_cell(c, q), c)]
        if takes:
            out = takes
    return out


def _roll_face():
    """Pick a face using the table above rather than an even 1-in-6."""
    faces = sorted(DICE_PCT)
    return _rng.choices(faces, weights=[DICE_PCT[f] for f in faces])[0]


def roll():
    global rolling, roll_t, dice, can_roll, sixes_in_a_row
    if state != "play" or anims or rolling > 0 or not can_roll:
        return
    dice = _roll_face()
    sixes_in_a_row = sixes_in_a_row + 1 if dice == 6 else 0
    rolling = ROLL_DUR
    roll_t = 0.0
    can_roll = False
    _sound("dice")


def _void_turn():
    """The third six in a row: the turn ends with nothing moved."""
    global dice
    saved = dice
    dice = 0                     # so _pass_turn does not hand out another go
    _pass_turn()
    dice = saved


def _after_roll():
    global moves, can_roll, message, sixes_in_a_row
    c = cur()
    lim = int(RULES.get("six_limit") or 0)
    if lim and dice == 6 and sixes_in_a_row >= lim:
        sixes_in_a_row = 0
        moves = []
        message = "%s rolled %d sixes - turn void." % (names[c], lim)
        _sound("deny")
        _void_turn()
        return
    moves = legal_moves(c, dice)
    if not moves:
        message = "%s rolled %d - no move." % (names[c], dice)
        _sound("deny")
        _pass_turn()
        return
    can_roll = False
    if len(moves) == 1:
        message = "%s rolled %d." % (names[c], dice)
    else:
        message = "%s rolled %d - tap a token." % (names[c], dice)
    _sound("click")
    # with a single legal move there is nothing to choose, so just play it
    if len(moves) == 1 and (not net_on or net_host):
        globals()["auto_move_t"] = 0.0


def _pass_turn():
    global turn, can_roll, moves, message, sixes_in_a_row, turn_clock
    sixes_in_a_row = 0
    turn_clock = 0.0
    if dice == 6:
        can_roll = True          # a 6 always earns another go
        moves = []
        return
    turn = (turn + 1) % len(players)
    # somebody may have left; do not hand the dice to an empty seat
    if net_on and net_present:
        for _ in range(len(players)):
            if turn in net_present:
                break
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
    if RULES["safe_squares"] and idx in SAFE:
        return []
    hits = []
    for t in tokens:
        if t["c"] == moving_color or t["pos"] < 0 or t["pos"] > LAST_TRACK:
            continue
        if path_cell(t["c"], t["pos"]) == cell:
            hits.append(t)
    return hits


def _choose(t, target):
    globals()["auto_move_t"] = -1.0
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
    extra = (a["dice"] == 6) and RULES["six_bonus"]

    if t["pos"] <= LAST_TRACK:
        hits = _captures_at(path_cell(c, t["pos"]), c)
        for h in hits:
            # the captured token walks all the way back, square by square
            back = list(range(h["pos"] - 1, -1, -1)) + [-1]
            _anim_to(h, back, "capture", speed=13.0)
            _sound("capture")
            if not RULES.get("reduced_motion"):
                _burst(h["x"], h["y"], PAL[h["c"]]["main"])
                globals()["shake"] = 1.0
            captured_any[c] = captured_any.get(c, 0) + 1
            if RULES["capture_bonus"]:
                extra = True
        if hits:
            message = "%s captured %s!" % (
                names[c], ", ".join(names[h["c"]] for h in hits))

    if t["pos"] >= 0:
        globals()["last_move"] = {"x": t["x"], "y": t["y"], "c": c, "t": _t}

    if t["pos"] >= HOME_POS:
        if RULES["home_bonus"]:
            extra = True
        _sound("home")
        _burst(*token_xy(c, t["i"], HOME_POS), PAL[c]["lite"])
        message = "%s got a token home!" % names[c]

    if _won(c):
        winner = c
        state = "over"
        _sound("win")
        _bump_stats(True)
        # confetti is lovely and it is also motion; let people turn it off
        _confetti[:] = [] if RULES.get("reduced_motion") else [
            {"x": _rng.uniform(0, W), "y": _rng.uniform(-H, 0),
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
    mine = my_tokens(c)
    if not mine:
        return False
    done = (any(t["pos"] >= HOME_POS for t in mine) if RULES["first_home_wins"]
            else all(t["pos"] >= HOME_POS for t in mine))
    if done:
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
BACK_RECT = (16.0, 16.0, 110.0, 38.0)
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
                if tag == "games":
                    _leave_game()
                elif tag.startswith("m:"):
                    set_rule_mode(tag[2:])
                elif tag.startswith("n:"):
                    globals()["player_count"] = int(tag[2:])
                    globals()["mode"] = "single"
                elif tag == "team":
                    globals()["mode"] = "team"
                    globals()["player_count"] = 4
                elif tag == "play":
                    start_game()
                elif tag == "custom":
                    state = "rules"
                return
        return

    if state == "rules":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("click")
                if tag == "back":
                    state = "mode"
                elif tag.startswith("r:"):
                    toggle_rule(tag[2:])
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
                    if net_on and not net_host:
                        return          # the host deals the next round
                    restart()
                elif tag == "menu":
                    state = "mode"
                return
        return

    # --- playing ---
    if net_on and not net_host:
        # a guest does not run the game: it asks the host, every time.
        # the host is the one that knows whose turn it really is.
        if _in(ROLL_RECT, x, y) or _in(DIE_RECT, x, y):
            _sound("click")
            js.netAction(json.dumps({"a": "roll", "from": _net_id()}))
            return
        if anims or not moves:
            return
        best, bestd = None, max(26.0, 30.0 * UI)
        offs = _stack_offsets()
        for t, target in moves:
            tx, ty = token_xy(t["c"], t["i"], t["pos"])
            ox, oy = offs.get(id(t), (0, 0))
            dd = math.hypot(x - (tx + ox), y - (ty + oy))
            if dd < bestd:
                best, bestd = (t, target), dd
        if best:
            js.netAction(json.dumps({"a": "move", "c": best[0]["c"],
                                     "i": best[0]["i"], "from": _net_id()}))
        return

    if _in(ROLL_RECT, x, y) or _in(DIE_RECT, x, y):
        if net_on and not my_turn():
            return                      # not your colour, not your dice
        roll()
        return
    if _in(BACK_RECT, x, y):
        state = "mode"
        _sound("click")
        return

    if anims or not moves:
        return
    if net_on and not my_turn():
        return                          # only move your own tokens
    best, bestd = None, max(26.0, 30.0 * UI)
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
    global rolling, roll_t, _t, dice_show, message, can_roll, auto_move_t
    global turn_clock, shake
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

    if (state == "play" and RULES.get("turn_timer") and can_roll
            and rolling <= 0 and not anims and (not net_on or net_host)):
        turn_clock += dt
        if turn_clock >= float(RULES["turn_timer"]):
            turn_clock = 0.0
            message = "%s ran out of time." % names[cur()]
            roll()
    else:
        turn_clock = 0.0

    if auto_move_t >= 0.0:
        auto_move_t -= dt
        if auto_move_t <= 0.0:
            auto_move_t = -1.0
            if len(moves) == 1 and not anims:
                t0, target0 = moves[0]
                _choose(t0, target0)

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

    for t in tokens:
        gl = t.get("glide")
        if gl:
            gl["p"] = min(1.0, gl["p"] + dt * 5.5)
            e = 1 - (1 - gl["p"]) ** 3
            t["x"] = gl["x0"] + (gl["x1"] - gl["x0"]) * e
            t["y"] = gl["y0"] + (gl["y1"] - gl["y0"]) * e
            if gl["p"] >= 1.0:
                t["x"], t["y"] = gl["x1"], gl["y1"]
                t.pop("glide", None)

    # pieces flatten as they land, then spring back
    for t in tokens:
        sq = t.get("squash", 0.0)
        if sq > 0:
            t["squash"] = max(0.0, sq - dt * 5.0)

    if shake > 0:
        shake = max(0.0, shake - dt * 4.0)

    for a in anims[:]:
        a["p"] += dt * a["speed"]
        while a["p"] >= 1.0:
            a["p"] -= 1.0
            a["i"] += 1
            if a["i"] >= len(a["cells"]):
                a["t"]["pos"] = a["cells"][-1][0]
                a["t"]["squash"] = 1.0
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
def _rrect(x, y, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()


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


THEMES = {
    "classic": {"bg0": "#121d3e", "bg1": "#05080f",
                "tile": "rgba(255,255,255,0.07)", "grid": "rgba(255,255,255,0.16)",
                "star": "#8fa3c9"},
    "night":   {"bg0": "#0b0b16", "bg1": "#000000",
                "tile": "rgba(150,170,255,0.06)", "grid": "rgba(140,160,230,0.22)",
                "star": "#7f8fc4"},
    "mint":    {"bg0": "#0d2b24", "bg1": "#04120f",
                "tile": "rgba(200,255,235,0.09)", "grid": "rgba(160,255,220,0.22)",
                "star": "#8fd8c0"},
}


def _theme():
    return THEMES.get(RULES.get("theme", "classic"), THEMES["classic"])


def _bg():
    th = _theme()
    g = ctx.createLinearGradient(0, 0, 0, H)
    g.addColorStop(0, th["bg0"])
    g.addColorStop(1, th["bg1"])
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
            ctx.fillStyle = _theme()["tile"]
            ctx.fill()
            ctx.lineWidth = 2
            ctx.strokeStyle = ("rgba(255,255,255,0.42)"
                               if RULES.get("high_contrast")
                               else _theme()["grid"])
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
        g = CELL * 0.055                      # air around each tile
        _rrect(px + g, py + g, CELL - 2 * g, CELL - 2 * g, CELL * 0.26)
        ctx.fillStyle = fill
        ctx.fill()
        if owner is not None:
            # a chevron showing which way this colour sets off
            nx, ny = TRACK[(idx + 1) % len(TRACK)]
            ang = math.atan2(ny - cy, nx - cx)
            _chevron(px + CELL / 2, py + CELL / 2, CELL * 0.26, ang,
                     "rgba(255,255,255,0.75)")
        elif idx in SAFE:
            _star(px + CELL / 2, py + CELL / 2, CELL * 0.31, "#8b98b5")

    for c in (RED, GREEN, YELLOW, BLUE):
        p = PAL[c]
        for k, (cx, cy) in enumerate(HOME_PATH[c]):
            px, py = BX + cx * CELL, BY + cy * CELL
            g = CELL * 0.055
            _rrect(px + g, py + g, CELL - 2 * g, CELL - 2 * g, CELL * 0.26)
            ctx.fillStyle = p["main"]
            ctx.globalAlpha = 0.88 - k * 0.06
            ctx.fill()
            ctx.globalAlpha = 1.0

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


# --- the pieces people actually know ---------------------------------------
def _piece_fill(p):
    g = ctx.createLinearGradient(0, -1, 0, 1)
    return g


def _shape_pawn(x, y, r, p):
    """The classic Ludo pawn: round head, tapered body, wide base."""
    body = ctx.createLinearGradient(x - r, y - r, x + r, y + r)
    body.addColorStop(0, p["lite"])
    body.addColorStop(0.55, p["main"])
    body.addColorStop(1, p["dark"])
    # base
    ctx.beginPath()
    ctx.ellipse(x, y + r * 0.78, r * 0.86, r * 0.30, 0, 0, 6.2832)
    ctx.fillStyle = body
    ctx.fill()
    # body: a skirt flaring out
    ctx.beginPath()
    ctx.moveTo(x - r * 0.30, y + r * 0.10)
    ctx.quadraticCurveTo(x - r * 0.78, y + r * 0.52, x - r * 0.70, y + r * 0.70)
    ctx.lineTo(x + r * 0.70, y + r * 0.70)
    ctx.quadraticCurveTo(x + r * 0.78, y + r * 0.52, x + r * 0.30, y + r * 0.10)
    ctx.closePath()
    ctx.fillStyle = body
    ctx.fill()
    # neck + head
    ctx.beginPath()
    ctx.arc(x, y - r * 0.42, r * 0.46, 0, 6.2832)
    ctx.fillStyle = body
    ctx.fill()
    ctx.beginPath()
    ctx.arc(x - r * 0.16, y - r * 0.56, r * 0.16, 0, 6.2832)
    ctx.fillStyle = "rgba(255,255,255,0.72)"
    ctx.fill()
    ctx.beginPath()
    ctx.arc(x, y - r * 0.42, r * 0.46, 0, 6.2832)
    ctx.lineWidth = 1.6
    ctx.strokeStyle = "rgba(255,255,255,0.45)"
    ctx.stroke()


def _shape_crown(x, y, r, p):
    """A crown: five points over a band."""
    g = ctx.createLinearGradient(x, y - r, x, y + r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(0.6, p["main"])
    g.addColorStop(1, p["dark"])
    ctx.beginPath()
    ctx.moveTo(x - r * 0.86, y + r * 0.52)
    ctx.lineTo(x - r * 0.74, y - r * 0.52)
    ctx.lineTo(x - r * 0.30, y - r * 0.02)
    ctx.lineTo(x, y - r * 0.74)
    ctx.lineTo(x + r * 0.30, y - r * 0.02)
    ctx.lineTo(x + r * 0.74, y - r * 0.52)
    ctx.lineTo(x + r * 0.86, y + r * 0.52)
    ctx.closePath()
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.6
    ctx.strokeStyle = "rgba(255,255,255,0.55)"
    ctx.stroke()
    ctx.beginPath()
    ctx.ellipse(x, y + r * 0.58, r * 0.86, r * 0.16, 0, 0, 6.2832)
    ctx.fillStyle = p["dark"]
    ctx.fill()


def _shape_rocket(x, y, r, p):
    """A rocket: pointed nose, fins, a warm exhaust."""
    g = ctx.createLinearGradient(x - r, y - r, x + r, y + r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(1, p["dark"])
    ctx.beginPath()
    ctx.moveTo(x, y - r * 1.02)
    ctx.quadraticCurveTo(x + r * 0.56, y - r * 0.20, x + r * 0.40, y + r * 0.62)
    ctx.lineTo(x - r * 0.40, y + r * 0.62)
    ctx.quadraticCurveTo(x - r * 0.56, y - r * 0.20, x, y - r * 1.02)
    ctx.closePath()
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.5
    ctx.strokeStyle = "rgba(255,255,255,0.55)"
    ctx.stroke()
    # fins
    ctx.beginPath()
    ctx.moveTo(x - r * 0.40, y + r * 0.10)
    ctx.lineTo(x - r * 0.88, y + r * 0.66)
    ctx.lineTo(x - r * 0.40, y + r * 0.62)
    ctx.closePath()
    ctx.moveTo(x + r * 0.40, y + r * 0.10)
    ctx.lineTo(x + r * 0.88, y + r * 0.66)
    ctx.lineTo(x + r * 0.40, y + r * 0.62)
    ctx.closePath()
    ctx.fillStyle = p["dark"]
    ctx.fill()
    # porthole
    ctx.beginPath()
    ctx.arc(x, y - r * 0.20, r * 0.20, 0, 6.2832)
    ctx.fillStyle = "rgba(255,255,255,0.80)"
    ctx.fill()


def _shape_plane(x, y, r, p):
    """A little plane, seen from above."""
    g = ctx.createLinearGradient(x, y - r, x, y + r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(1, p["dark"])
    ctx.beginPath()
    ctx.moveTo(x, y - r * 0.98)
    ctx.lineTo(x + r * 0.24, y - r * 0.30)
    ctx.lineTo(x + r * 0.96, y + r * 0.10)
    ctx.lineTo(x + r * 0.96, y + r * 0.34)
    ctx.lineTo(x + r * 0.22, y + r * 0.20)
    ctx.lineTo(x + r * 0.16, y + r * 0.66)
    ctx.lineTo(x + r * 0.46, y + r * 0.86)
    ctx.lineTo(x + r * 0.44, y + r * 1.0)
    ctx.lineTo(x, y + r * 0.82)
    ctx.lineTo(x - r * 0.44, y + r * 1.0)
    ctx.lineTo(x - r * 0.46, y + r * 0.86)
    ctx.lineTo(x - r * 0.16, y + r * 0.66)
    ctx.lineTo(x - r * 0.22, y + r * 0.20)
    ctx.lineTo(x - r * 0.96, y + r * 0.34)
    ctx.lineTo(x - r * 0.96, y + r * 0.10)
    ctx.lineTo(x - r * 0.24, y - r * 0.30)
    ctx.closePath()
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.4
    ctx.strokeStyle = "rgba(255,255,255,0.50)"
    ctx.stroke()


def _shape_car(x, y, r, p):
    """A racing car: low body, a cabin, two wheels."""
    g = ctx.createLinearGradient(x, y - r, x, y + r)
    g.addColorStop(0, p["lite"])
    g.addColorStop(0.6, p["main"])
    g.addColorStop(1, p["dark"])
    ctx.beginPath()
    ctx.moveTo(x - r * 0.96, y + r * 0.18)
    ctx.quadraticCurveTo(x - r * 0.92, y - r * 0.16, x - r * 0.52, y - r * 0.20)
    ctx.lineTo(x - r * 0.26, y - r * 0.62)
    ctx.lineTo(x + r * 0.34, y - r * 0.62)
    ctx.lineTo(x + r * 0.62, y - r * 0.18)
    ctx.quadraticCurveTo(x + r * 0.94, y - r * 0.10, x + r * 0.96, y + r * 0.18)
    ctx.closePath()
    ctx.fillStyle = g
    ctx.fill()
    ctx.lineWidth = 1.5
    ctx.strokeStyle = "rgba(255,255,255,0.50)"
    ctx.stroke()
    # windscreen
    ctx.beginPath()
    ctx.moveTo(x - r * 0.20, y - r * 0.52)
    ctx.lineTo(x + r * 0.26, y - r * 0.52)
    ctx.lineTo(x + r * 0.42, y - r * 0.22)
    ctx.lineTo(x - r * 0.34, y - r * 0.22)
    ctx.closePath()
    ctx.fillStyle = "rgba(255,255,255,0.55)"
    ctx.fill()
    # wheels
    for wx in (x - r * 0.52, x + r * 0.54):
        ctx.beginPath()
        ctx.arc(wx, y + r * 0.34, r * 0.26, 0, 6.2832)
        ctx.fillStyle = "#12182a"
        ctx.fill()
        ctx.beginPath()
        ctx.arc(wx, y + r * 0.34, r * 0.11, 0, 6.2832)
        ctx.fillStyle = "rgba(255,255,255,0.55)"
        ctx.fill()

SHAPES = {"pawn": _shape_pawn, "ball": _shape_ball, "crown": _shape_crown,
          "rocket": _shape_rocket, "plane": _shape_plane, "car": _shape_car,
          "gem": _shape_gem, "ring": _shape_ring, "star": _shape_star,
          "hex": _shape_hex}


MARKS = {RED: "circle", GREEN: "triangle", YELLOW: "square", BLUE: "diamond"}


def _player_mark(x, y, s, c, col="#ffffff"):
    """A small white shape, one per colour: circle, triangle, square, diamond."""
    m = MARKS.get(c, "circle")
    ctx.beginPath()
    if m == "circle":
        ctx.arc(x, y, s, 0, 6.2832)
    elif m == "triangle":
        ctx.moveTo(x, y - s * 1.15)
        ctx.lineTo(x + s, y + s * 0.75)
        ctx.lineTo(x - s, y + s * 0.75)
        ctx.closePath()
    elif m == "square":
        ctx.rect(x - s * 0.82, y - s * 0.82, s * 1.64, s * 1.64)
    else:
        ctx.moveTo(x, y - s * 1.15)
        ctx.lineTo(x + s * 1.15, y)
        ctx.lineTo(x, y + s * 1.15)
        ctx.lineTo(x - s * 1.15, y)
        ctx.closePath()
    ctx.fillStyle = col
    ctx.fill()


def _draw_token(t, highlight=False, movable=False, label=True, rad=None):
    x, y, c = t["x"], t["y"], t["c"]
    p = PAL[c]
    r = CELL * 0.46 if rad is None else rad

    # a piece flattens as it lands and springs back: squash and stretch
    sq = t.get("squash", 0.0) if not RULES.get("reduced_motion") else 0.0
    if sq > 0:
        ctx.save()
        base = y + r * 0.62
        ctx.translate(x, base)
        ctx.scale(1.0 + sq * 0.26, 1.0 - sq * 0.20)
        ctx.translate(-x, -base)

    if highlight:
        glow = 0.5 if RULES.get("reduced_motion") else 0.5 + 0.5 * math.sin(_t * 4)
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

    if sq > 0:
        ctx.restore()


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
def _chevron(x, y, s, ang, col):
    """A small arrow, so the direction of travel is never a guess."""
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(ang)
    ctx.beginPath()
    ctx.moveTo(-s * 0.55, -s * 0.75)
    ctx.lineTo(s * 0.65, 0)
    ctx.lineTo(-s * 0.55, s * 0.75)
    ctx.lineWidth = max(1.6, s * 0.42)
    ctx.lineCap = "round"
    ctx.lineJoin = "round"
    ctx.strokeStyle = col
    ctx.stroke()
    ctx.restore()


def _draw_last_move():
    """A short-lived ring where the last token came to rest."""
    if not last_move or state != "play":
        return
    age = _t - last_move["t"]
    if age < 0 or age > 1.8:
        return
    fade = 1.0 - age / 1.8
    ctx.beginPath()
    ctx.arc(last_move["x"], last_move["y"], CELL * (0.40 + age * 0.30), 0, 6.2832)
    ctx.lineWidth = max(2.0, CELL * 0.09)
    ctx.strokeStyle = PAL[last_move["c"]]["main"]
    ctx.globalAlpha = fade * 0.8
    ctx.stroke()
    ctx.globalAlpha = 1.0


def _draw_move_hints():
    """A pulsing ring on every square you could move to, so the choice is obvious."""
    if state != "play" or anims or not moves:
        return
    if net_on and not net_host:
        pass                                  # guests see the host's board anyway
    pulse = 0.5 if RULES.get("reduced_motion") else 0.5 + 0.5 * math.sin(_t * 4.5)
    for t, target in moves:
        x, y = token_xy(t["c"], t["i"], target)
        a = 0.45 + 0.45 * pulse
        # a white halo first, so the ring reads on any square colour
        for col, w in (("rgba(255,255,255,%.2f)" % a, max(3.0, CELL * 0.15)),
                       (PAL[t["c"]]["main"], max(2.0, CELL * 0.085))):
            ctx.beginPath()
            ctx.arc(x, y, CELL * 0.44, 0, 6.2832)
            ctx.lineWidth = w
            ctx.strokeStyle = col
            ctx.globalAlpha = 1.0 if col.startswith("rgba") else a
            ctx.stroke()
        ctx.globalAlpha = 1.0


def _leave_game():
    """Back to the mode screen from anywhere in a round."""
    global state, winner
    winner = None
    anims[:] = []
    state = "mode"


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
    mine = (not net_on) or my_turn()
    ctx.fillText("YOUR TURN" if (net_on and mine) else "TURN", mid, y0 + 22)
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
        ready = can_roll and rolling <= 0 and not anims and (mine or not net_host)
        if ready:
            label = "ROLL"
        elif not mine:
            label = names[cur()] + "'s turn"
        elif rolling > 0 or not moves:
            label = "\u2026"
        else:
            label = "TAP A TOKEN"
        _button(*ROLL_RECT[:2], ROLL_RECT[2], ROLL_RECT[3],
                label, ready, PAL[c]["main"],
                size=max(11, int((12 if label != "ROLL" else 17) * k)))

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
        if RULES.get("marks"):
            _player_mark(x + hw * 0.115, ry + row_h / 2, row_h * 0.13, col,
                         "rgba(10,16,30,0.85)")
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

    # a way out of a round, drawn where it cannot cover the board
    bx, by_, bw_, bh_ = BACK_RECT
    _button(bx, by_, bw_, bh_, "\u2190 Menu", False, size=max(10, int(11 * k)))

    if message:
        _wrap(message, mid, ry + 12 * k, hw * 0.88,
              max(9, int(12 * k)), "#cfe0ff")

    # in a room, say plainly which side of it you are
    if net_on:
        role = "host" if net_host else "guest"
        if net_seat < 0:
            colour = "colour not set"
        elif net_seat < len(players):
            colour = "you are " + names[players[net_seat]]
        else:
            colour = "watching"
        ctx.textAlign = "center"
        ctx.fillStyle = "#5f7093"
        ctx.font = "700 %dpx %s" % (max(8, int(9 * k)), FONT)
        ctx.fillText("%s \u00b7 %s" % (role, colour), mid, y0 + hh - 8)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
def _draw_mode():
    global _menu_hit
    if not _rules_loaded:
        load_rules()
        _load_stats()
    _menu_hit = []
    _bg()
    pad = 14.0
    narrow = W < 520

    _button(pad, pad, 96, 36, "\u2190 Games", size=13)
    _menu_hit.append(("games", (pad, pad, 96, 36)))

    _title("KHELO LUDO", 78 if narrow else 74, 28 if narrow else 40)
    _wrap("Pick a way to play - every card is a different rule set.",
          W / 2, (100 if narrow else 100), min(640, W - 30), 13)

    # the six rule presets, laid out as a grid
    names_ = ["classic", "quick", "master", "onekill", "plain", "wild"]
    tint = {"classic": "#4aa8ff", "quick": "#22c55e", "master": "#fbbf24",
            "onekill": "#ff3b5c", "plain": "#9fb3d9", "wild": "#a855f7"}
    gap = max(10.0, W * 0.022)
    cols = 2 if narrow else 3
    cw = (W - 2 * pad - (cols - 1) * gap) / cols
    ch = min(96.0, cw * 0.52)
    oy = 126.0
    k = min(1.0, cw / 250.0)
    for i, m in enumerate(names_):
        x = pad + (i % cols) * (cw + gap)
        y = oy + (i // cols) * (ch + gap)
        sel = (rule_mode == m)
        _panel(x, y, cw, ch, "rgba(20, 30, 56, 0.94)" if not sel else
               "rgba(40, 56, 96, 0.98)", tint[m], 14)
        ctx.textAlign = "left"
        ctx.fillStyle = tint[m]
        ctx.font = "800 %dpx %s" % (max(13, int(17 * k)), FONT)
        ctx.fillText(MODE_LABEL[m], x + 13, y + ch * 0.38)
        ctx.fillStyle = "#93a4c8"
        ctx.font = "600 %dpx %s" % (max(9, int(11 * k)), FONT)
        _wrap(MODE_NOTE[m], x + 13, y + ch * 0.58, cw - 26,
              max(9, int(11 * k)), "#93a4c8", center=False)
        if sel:
            ctx.textAlign = "right"
            ctx.fillStyle = tint[m]
            ctx.font = "800 %dpx %s" % (max(9, int(11 * k)), FONT)
            ctx.fillText("CHOSEN", x + cw - 12, y + ch * 0.38)
        _menu_hit.append(("m:" + m, (x, y, cw, ch)))

    rows = 3 if narrow else 2
    by = oy + rows * (ch + gap) + 6

    # how many are playing, and are they in teams
    _wrap("Players", W / 2, by + 12, 200, 12, "#8fa3c9")
    cwid = min(84.0, (W - 2 * pad - 2 * gap) / 4)
    total = 3 * cwid + 2 * gap
    ox = (W - total) / 2.0
    for i, n in enumerate((2, 3, 4)):
        x = ox + i * (cwid + gap)
        sel = (player_count == n and mode != "team")
        _panel(x, by + 20, cwid, 38, "rgba(20, 30, 56, 0.94)" if not sel else
               "rgba(74, 168, 255, 0.22)", "#4aa8ff" if sel else
               "rgba(150,180,240,0.18)", 11)
        ctx.textAlign = "center"
        ctx.fillStyle = "#eaf2ff" if sel else "#9fb3d9"
        ctx.font = "800 15px %s" % FONT
        ctx.fillText(str(n), x + cwid / 2, by + 45)
        _menu_hit.append(("n:%d" % n, (x, by + 20, cwid, 38)))

    tw = cwid + 26
    tx = ox + total + gap
    sel_t = (mode == "team")
    _panel(tx, by + 20, tw, 38, "rgba(20, 30, 56, 0.94)" if not sel_t else
           "rgba(251, 191, 36, 0.22)", "#fbbf24" if sel_t else
           "rgba(150,180,240,0.18)", 11)
    ctx.textAlign = "center"
    ctx.fillStyle = "#eaf2ff" if sel_t else "#9fb3d9"
    ctx.font = "800 13px %s" % FONT
    ctx.fillText("Team", tx + tw / 2, by + 45)
    _menu_hit.append(("team", (tx, by + 20, tw, 38)))

    py = by + 72
    _button(W / 2 - min(120.0, W * 0.32), py, min(240.0, W * 0.64), 50,
            "Play", True, tint[rule_mode], size=18)
    _menu_hit.append(("play", (W / 2 - min(120.0, W * 0.32), py,
                               min(240.0, W * 0.64), 50)))
    dw = min(220.0, W - 2 * pad)
    _button(W / 2 - dw / 2, py + 58, dw, 40, "Custom rules", False, size=13)
    _menu_hit.append(("custom", (W / 2 - dw / 2, py + 58, dw, 40)))

    if STATS["games"]:
        won = STATS["wins"]
        _wrap("%d games played \u00b7 %d won" % (STATS["games"], won),
              W / 2, py + 116, min(400, W - 30), 11, "#6f82a8")


DIALS = [
    ("exit", "Bring a token out", "On a six", "Any roll"),
    ("six_bonus", "Roll again on a six", "Yes", "No"),
    ("six_limit", "Three sixes in a row", "Turn void", "Just sixes"),
    ("capture_bonus", "Roll again on a capture", "Yes", "No"),
    ("home_bonus", "Roll again reaching home", "Yes", "No"),
    ("exact_home", "Getting a token home", "Exact roll", "Bounce back"),
    ("safe_squares", "Star squares", "Safe", "Open"),
    ("blocks", "Two of a colour together", "No wall", "A wall"),
    ("kill_to_enter", "Entering the home column", "Any time", "After a kill"),
    ("capture_forced", "Capturing", "Optional", "Compulsory"),
    ("tokens", "Tokens each", None, None),
    ("first_home_wins", "The game ends when", "All home", "One home"),
    ("marks", "Colour-blind marks", "Shapes on", "Colour only"),
    ("reduced_motion", "Gentle motion", "Calm", "Full"),
    ("high_contrast", "High contrast", "On", "Off"),
    ("theme", "Board style", None, None),
    ("turn_timer", "Turn timer", "Off", "30 seconds"),
]


THEME_LABEL = {"classic": "Classic", "night": "Night", "mint": "Mint"}
THEME_ORDER = ["classic", "night", "mint"]


def _dial_value(key):
    v = RULES[key]
    for k, _label, a_, b_ in DIALS:
        if k == key:
            if k == "tokens":
                return "%d" % v
            if k == "theme":
                return THEME_LABEL.get(v, v)
            return a_ if v else b_
    return str(v)


def _draw_rules():
    global _menu_hit
    _menu_hit = []
    _bg()
    pad = 14.0
    narrow = W < 520
    _button(pad, pad, 96, 36, "\u2190 Back", size=13)
    _menu_hit.append(("back", (pad, pad, 96, 36)))
    _title("HOUSE RULES", 76 if narrow else 72, 24 if narrow else 32)
    _wrap("Every table plays it differently. Tap a row to change it.",
          W / 2, 98, min(640, W - 30), 12)

    top = 118.0
    bottom = H - 62
    row_h = max(30.0, min(52.0, (bottom - top) / len(DIALS)))
    for i, (key, label, a_, b_) in enumerate(DIALS):
        y = top + i * row_h
        hit = (pad, y + 2, W - 2 * pad, row_h - 4)
        _panel(hit[0], hit[1], hit[2], hit[3],
               "rgba(20, 30, 56, 0.82)", "rgba(150,180,240,0.12)", 10)
        ctx.textAlign = "left"
        ctx.fillStyle = "#dbe6fb"
        ctx.font = "700 %dpx %s" % (max(10, int(min(13, row_h * 0.40))), FONT)
        ctx.fillText(label, pad + 12, y + row_h * 0.60)
        val = _dial_value(key)
        ctx.textAlign = "right"
        ctx.fillStyle = "#ffd23f"
        ctx.font = "800 %dpx %s" % (max(9, int(min(12, row_h * 0.38))), FONT)
        ctx.fillText(val, W - pad - 12, y + row_h * 0.60)
        _menu_hit.append(("r:" + key, hit))

    _button(W / 2 - min(110.0, W * 0.3), H - 50, min(220.0, W * 0.6), 40,
            "Done", True, size=14)
    _menu_hit.append(("back", (W / 2 - min(110.0, W * 0.3), H - 50,
                               min(220.0, W * 0.6), 40)))


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
        _draw_token({"x": x + sw / 2, "y": y + sh * 0.40, "c": RED},
                    label=False, rad=min(sw, sh) * 0.27)
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
    if net_on and not net_host:
        # only the host can deal a new round
        _button(cx + pad, by, bw, 46, "Waiting for host", False, size=13)
    else:
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
    if state == "rules":
        _draw_rules()
        return

    _bg()

    kick = shake if not RULES.get("reduced_motion") else 0.0
    if kick > 0:
        amp = CELL * 0.30 * kick
        ctx.save()
        ctx.translate(_rng.uniform(-amp, amp), _rng.uniform(-amp, amp))

    _draw_board()
    _draw_move_hints()
    _draw_last_move()
    _draw_tokens()

    if kick > 0:
        ctx.restore()

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

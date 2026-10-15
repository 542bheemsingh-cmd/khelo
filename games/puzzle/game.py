"""
Khelo Puzzles - a 10-level puzzle game written in Python.

Runs in the browser through Pyodide, same as the rest of the Khelo arcade.
Every level is a DIFFERENT kind of puzzle, and each one gets harder:

   1 Lights Out (3x3)     6 Tower of Hanoi (3 discs)
   2 Memory Match         7 Code Breaker (Mastermind)
   3 Number Sequence      8 Mini Sudoku (4x4)
   4 Riddle               9 Nonogram (5x5)
   5 Sliding Puzzle      10 N-Queens (6x6)

Each level carries a one-line hint. Levels unlock one at a time.

The page calls:
    tap(x, y)   -> a click / tap on the canvas
    key(k)      -> a key press ("a", "7", "Backspace", "Enter")
    update(dt)  -> advance timers/animations
    draw()      -> render a frame
"""

import copy
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

SAVE_KEY = "khelo_puzzle_save"
FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"

# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------
LEVELS = [
    # --- the first ten ---
    {"name": "Lights Out", "kind": "lights", "n": 3,
     "goal": "Switch every light off.",
     "hint": "Pressing a tile flips it AND its four neighbours. Work from the top row down: for each lit tile, press the one directly below it."},
    {"name": "Memory Match", "kind": "memory", "pairs": 3,
     "goal": "Find all 3 matching pairs.",
     "hint": "Flip two tiles at a time - a matching pair stays open. Say each symbol out loud as you reveal it so you remember where it was."},
    {"name": "Number Sequence", "kind": "seq",
     "goal": "Work out the next number in the list.",
     "hint": "Look at the GAP between each pair of terms first. If the gaps are not equal, check whether each term is the one before it multiplied by something."},
    {"name": "Riddle", "kind": "riddle",
     "goal": "Answer the riddle.",
     "hint": "It is brown, it has a head and a tail, and it has no legs. Type a single word."},
    {"name": "Sliding Puzzle", "kind": "slide", "n": 3,
     "goal": "Put the tiles in order, with the blank in the bottom-right corner.",
     "hint": "Only a tile next to the blank can move. Place tile 1 first, then 2, then 3 in the top-right corner - never disturb a finished tile."},
    {"name": "Tower of Hanoi", "kind": "hanoi", "n": 3,
     "goal": "Move the whole stack to the third peg.",
     "hint": "Move the smallest disc out of the way first, and never put a bigger disc on a smaller one. 3 discs need at least 7 moves."},
    {"name": "Crack the Code", "kind": "crack",
     "goal": "Deduce the 3-digit code from the clues - no guessing needed.",
     "hint": "Each clue shows a guess and its score: a filled dot = a digit that is right AND in the right place, a hollow dot = a digit that is in the code but in the wrong place. Cross out every code that breaks a clue."},
    {"name": "Mini Sudoku", "kind": "sudoku",
     "goal": "Fill 1-4 into every row, column and 2x2 box - each exactly once.",
     "hint": "Find a row, column or box that already shows three numbers - the missing one is forced. Fill those singles first."},
    {"name": "Nonogram", "kind": "nonogram", "n": 5,
     "goal": "Fill the cells the clues describe to reveal the picture.",
     "hint": "A clue of 5 fills the whole line. A clue of 4 always covers the middle cells wherever it sits - those are certain, so start there."},
    {"name": "N-Queens", "kind": "queens", "n": 6,
     "goal": "Place 6 queens so that no two attack each other.",
     "hint": "One queen per column. Work left to right, and when a column has no safe square, back up and move the queen before it."},

    # --- the next ten: harder, and two brand-new kinds of puzzle ---
    {"name": "Futoshiki", "kind": "futoshiki", "n": 4,
     "goal": "Fill 1-4 into every row and column, obeying the < and > signs.",
     "hint": "Every row and column needs 1-4 once each. A '<' means the left/top cell is SMALLER than its neighbour - start with a cell only one number can fit."},
    {"name": "Lights Out +", "kind": "lights", "n": 4,
     "goal": "Switch every light off on the bigger board.",
     "hint": "Same rule, bigger board. Clear one row at a time: press the tile directly below every lit tile, then move down a row."},
    {"name": "Memory Match +", "kind": "memory", "pairs": 5,
     "goal": "Find all 5 matching pairs.",
     "hint": "Ten tiles now. Go left to right and never flip a tile you have not already seen - a miss is only worth it when it shows you a NEW tile."},
    {"name": "Sliding Puzzle +", "kind": "slide", "n": 4,
     "goal": "Order the tiles 1-15, with the blank in the bottom-right corner.",
     "hint": "Solve the top row first, then the second row, then the third. Slide tiles in a loop around the blank instead of dragging one tile back and forth."},
    {"name": "Tower of Hanoi +", "kind": "hanoi", "n": 4,
     "goal": "Move all 4 discs to the third peg.",
     "hint": "4 discs need at least 15 moves - almost exactly double the 3-disc puzzle. Move the top three discs onto the spare peg first."},
    {"name": "Logic Grid", "kind": "logic", "n": 3,
     "goal": "Work out which person owns which pet.",
     "hint": "Tick the cell you are sure about, and cross out the ones a clue rules out. A crossed-out cell is just as useful as a tick."},
    {"name": "Nonogram +", "kind": "nonogram", "n": 6,
     "goal": "Fill the cells the clues describe to reveal the bigger picture.",
     "hint": "Count how far a run can slide. In a line of 6, a run of 4 always covers the two middle cells no matter where it sits - fill those first."},
    {"name": "N-Queens +", "kind": "queens", "n": 7,
     "goal": "Place 7 queens so that no two attack each other.",
     "hint": "Seven columns, seven queens. Place them one column at a time; if you get stuck, the mistake is almost always in the last two queens."},
    {"name": "Futoshiki +", "kind": "futoshiki", "n": 5,
     "goal": "Fill 1-5 into every row and column, obeying the < and > signs.",
     "hint": "Scan for a cell where the signs and its row both rule out all but one number. Those forced cells break the puzzle open."},
    {"name": "Logic Grid +", "kind": "logic", "n": 4,
     "goal": "Work out which of the four friends owns which pet.",
     "hint": "Four of each now. Apply every clue to the whole grid, then look for a row or column with only one cell left undecided."},
]

RIDDLES = [
    {"q": "What has a head, a tail, is brown, and has no legs?",
     "a": ["penny", "a penny", "coin", "a coin"]},
    {"q": "What gets wetter the more it dries?",
     "a": ["towel", "a towel"]},
    {"q": "What has hands but cannot clap?",
     "a": ["clock", "a clock", "watch", "a watch"]},
    {"q": "What has many keys but cannot open a single lock?",
     "a": ["piano", "a piano", "keyboard"]},
    {"q": "Feed me and I live, give me a drink and I die. What am I?",
     "a": ["fire"]},
    {"q": "I have forests but no trees, roads but no cars. What am I?",
     "a": ["map", "a map"]},
    {"q": "What has to be broken before you can use it?",
     "a": ["egg", "an egg"]},
    {"q": "What gets bigger the more you take away from it?",
     "a": ["hole", "a hole"]},
]

NONOGRAM_PATTERNS = [
    ["..X..",
     "..X..",
     "XXXXX",
     "..X..",
     "..X.."],
    ["XX.XX",
     "XXXXX",
     "XXXXX",
     ".XXX.",
     "..X.."],
    ["X...X",
     "X...X",
     "X...X",
     "XXXXX",
     ".XXX."],
]

SUDOKU_SOL = [
    [1, 2, 3, 4],
    [3, 4, 1, 2],
    [2, 1, 4, 3],
    [4, 3, 2, 1],
]

# 6x6 nonogram pictures (used by the harder Nonogram level)
NONOGRAM6 = [
    ["..X...",
     ".XXX..",
     "XXXXX.",
     "..X...",
     "..X...",
     "..X..."],
    ["XX..XX",
     "XX..XX",
     "XXXXXX",
     "XXXXXX",
     "XX..XX",
     "XX..XX"],
    ["..XX..",
     ".XXXX.",
     "XXXXXX",
     "XXXXXX",
     ".XXXX.",
     "..XX.."],
]

# Logic-grid puzzles: a set of people, a set of pets, the answer, and the clues.
# The tests check that each one has exactly ONE arrangement.
LOGIC_PUZZLES = {
    3: {
        "people": ["Aarav", "Bhavna", "Chetan"],
        "pets": ["cat", "dog", "fish"],
        "sol": [1, 0, 2],
        "clues": [
            "Aarav does not keep the cat.",
            "Bhavna does not keep the dog.",
            "Chetan keeps the fish.",
        ],
    },
    4: {
        "people": ["Diya", "Eshan", "Farah", "Gaurav"],
        "pets": ["parrot", "rabbit", "turtle", "fish"],
        "sol": [2, 0, 3, 1],
        "clues": [
            "Eshan keeps the parrot.",
            "Farah keeps neither the turtle nor the rabbit.",
            "Diya does not keep the rabbit.",
            "Gaurav does not keep the parrot.",
        ],
    },
}

TICK, CROSS = 1, 2          # the two marks a player can put in a logic-grid cell

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
screen = "menu"          # menu | play | solved
level_index = 0
solved = []
show_hint = False
P = {}                   # the active puzzle's state
_message = ""
_rng = random.Random()


def _sound(name):
    try:
        js.playSound(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------
def _save():
    try:
        js.window.localStorage.setItem(SAVE_KEY, json.dumps({"solved": solved}))
    except Exception:
        pass


def _load():
    global solved
    try:
        raw = js.window.localStorage.getItem(SAVE_KEY)
    except Exception:
        raw = None
    if not raw:
        return
    try:
        solved = [int(i) for i in json.loads(raw).get("solved", [])]
    except Exception:
        pass


def _unlocked(i):
    return i == 0 or (i - 1) in solved


def keyboard_mode():
    """Which on-screen keyboard the page should show: 'none' | 'digits' | 'letters'.

    The Riddle and Number Sequence levels need typing, which a phone has no
    physical keyboard for - the page draws a soft keyboard for those.
    """
    if screen != "play":
        return "none"
    kind = LEVELS[level_index]["kind"]
    if kind in ("seq", "crack"):
        return "digits"
    if kind == "riddle":
        return "letters"
    return "none"


# ---------------------------------------------------------------------------
# Stuck detection: after this many wrong tries the solution is shown
# ---------------------------------------------------------------------------
MAX_WRONG = 10
wrong_tries = 0
_preview = False          # while drawing the solution preview, skip caption text
_stash = None             # the board as it was when the solution was shown


def _lights_solve(g0, n):
    """Brute-force the set of tiles that clears a 3x3 Lights Out board."""
    for mask in range(1 << (n * n)):
        g = [row[:] for row in g0]
        for i in range(n * n):
            if mask >> i & 1:
                _press_lights(g, i % n, i // n, n)
        if not any(any(row) for row in g):
            return [i for i in range(n * n) if mask >> i & 1]
    return []


def _queens_solve(n):
    """Backtrack one valid n-queens layout, as a list of (x, y)."""
    def place(cols):
        if len(cols) == n:
            return cols
        x = len(cols)
        for y in range(n):
            if all(y != qy and abs(x - qx) != abs(y - qy)
                   for qx, qy in enumerate(cols)):
                got = place(cols + [y])
                if got:
                    return got
        return None

    sol = place([]) or []
    return list(enumerate(sol))


def _note_wrong():
    """Record a wrong try; reveal the solution once the player is clearly stuck."""
    global wrong_tries
    if screen != "play":
        return
    wrong_tries += 1
    if wrong_tries >= MAX_WRONG:
        _show_solution()


def _show_solution():
    global screen, show_hint, _stash
    # remember exactly where the player was, so "Keep trying" can put it back
    _stash = copy.deepcopy(P)
    screen = "solution"
    show_hint = False
    _apply_solution()
    _sound("deny")


def keep_trying():
    """Dismiss the solution and carry on from the board as it was."""
    global screen, wrong_tries, P, _stash
    if _stash is not None:
        P.clear()
        P.update(_stash)
        _stash = None
    wrong_tries = 0
    screen = "play"


def _apply_solution():
    """Put the puzzle into its solved state so it can be shown as the answer."""
    kind = LEVELS[level_index]["kind"]
    if kind == "lights":
        P["g"] = [[False] * P["n"] for _ in range(P["n"])]
    elif kind == "memory":
        P["matched"] = set(range(len(P["deck"])))
        P["open"] = []
    elif kind == "seq":
        P["input"] = str(P["answer"])
    elif kind == "riddle":
        P["input"] = P["r"]["a"][0]
    elif kind == "slide":
        n = P["n"]
        P["g"] = list(range(1, n * n)) + [0]
    elif kind == "hanoi":
        P["pegs"] = [[], [], list(range(P["n"], 0, -1))]
        P["sel"] = None
    elif kind == "code":
        P["cur"] = list(P["secret"])
    elif kind == "sudoku":
        P["grid"] = [row[:] for row in SUDOKU_SOL]
        P["sel"] = None
    elif kind == "nonogram":
        P["grid"] = [row[:] for row in P["target"]]
    elif kind == "queens":
        P["q"] = set(P["sol"])
    elif kind == "crack":
        P["input"] = "".join(str(d) for d in P["secret"])
    elif kind == "futoshiki":
        P["grid"] = [row[:] for row in P["sol"]]
    elif kind == "logic":
        P["marks"] = [[TICK if P["sol"][r] == c else 0 for c in range(P["n"])]
                      for r in range(P["n"])]


def _solution_lines():
    """The plain-language explanation shown under the answer."""
    kind = LEVELS[level_index]["kind"]

    if kind == "lights":
        presses = P.get("sol", [])
        n = P["n"]
        cells = ", ".join("row %d col %d" % (i // n + 1, i % n + 1) for i in presses)
        return [
            "Every press flips the tile you touch AND its four neighbours, so a "
            "tile you flip now may be flipped again later. Order never matters, and "
            "pressing the same tile twice simply undoes it - so the only question is "
            "WHICH tiles to press.",
            "One set of presses that clears this board (marked with a ring): " + cells + ".",
            "A reliable method is 'light chasing': go row by row and, for every tile "
            "still lit in a row, press the tile directly BELOW it. That clears each "
            "row down to the last one, which then needs a short fix-up.",
        ]

    if kind == "memory":
        pairs = len(P["deck"]) // 2
        seen, order = {}, []
        for i, s in enumerate(P["deck"]):
            if s not in seen:
                seen[s] = []
                order.append(s)
            seen[s].append(i + 1)
        rows = "; ".join("%s in tiles %s" % (s, " and ".join(str(v) for v in seen[s]))
                         for s in order)
        return [
            "Flip two tiles at a time. If the symbols match, the pair stays open; if "
            "they do not, both flip back after a moment - so a miss is only "
            "expensive because it wastes a peek.",
            "There are " + str(pairs) + " pairs, and the whole deck is now face up. "
            "The pairs are: " + rows + ".",
            "The trick is to work the board in a fixed order and say each symbol out "
            "loud as you reveal it, so the second of a pair is never a surprise.",
        ]

    if kind == "seq":
        t = P["terms"]
        k = P.get("rule", "arith")
        if k == "arith":
            d = t[1] - t[0]
            how = ("The gap between neighbouring terms is always " + str(d) +
                   ", so this is an arithmetic sequence: add " + str(d) + " each step.")
        elif k == "geo":
            r = t[1] // t[0]
            how = ("Each term is the one before it multiplied by " + str(r) +
                   ", so this is a geometric sequence.")
        elif k == "square":
            how = ("These are perfect squares: " +
                   ", ".join(str(v) for v in t) + " is " +
                   ", ".join(str(int(v ** 0.5)) for v in t) + " squared.")
        else:
            how = ("Each term is the sum of the two before it (" + str(t[0]) + " + " +
                   str(t[1]) + " = " + str(t[2]) + "), the Fibonacci rule.")
        return [
            how,
            "Working it out: " + " , ".join(str(v) for v in t) + " , " +
            str(P["answer"]) + ".",
            "The answer was " + str(P["answer"]) + ". The general habit that cracks "
            "most sequences: look at the gaps first, then at the ratios, then at "
            "whether the numbers are squares or cubes.",
        ]

    if kind == "riddle":
        ans = P["r"]["a"][0]
        return [
            "The riddle: \u201c" + P["r"]["q"] + "\u201d",
            "The answer was \u201c" + ans + "\u201d.",
            "Riddles like this one describe an everyday object through one "
            "deliberately misleading feature. Take the words literally, one at a "
            "time, and test cheap objects around you: 'head', 'tail', 'hands', "
            "'keys', 'face' are the usual giveaways.",
        ]

    if kind == "slide":
        return [
            "Only a tile next to the blank can move, and it moves into the blank. "
            "The goal is 1-8 in order with the blank at the bottom right.",
            "Solve it in layers. First place tile 1 and then tile 2 along the top "
            "row; then place 3 in the top-right corner. Do the same for the middle "
            "row, and the last row falls into place by itself.",
            "If you get stuck, never disturb finished tiles - shuffle only the "
            "unfinished corner, and slide tiles in a loop around the blank rather "
            "than dragging one tile back and forth.",
        ]

    if kind == "hanoi":
        n = P["n"]
        moves = []

        def plan(k, a, c, b):
            if k == 0:
                return
            plan(k - 1, a, b, c)
            moves.append((a, c))
            plan(k - 1, b, c, a)

        plan(n, 0, 2, 1)
        seq = " then ".join("peg %d \u2192 peg %d" % (a + 1, c + 1) for a, c in moves)
        return [
            "The one rule: a disc may sit on an empty peg or on a LARGER disc, never "
            "on a smaller one. Only the topmost disc of a peg can move.",
            "With " + str(n) + " discs the minimum is " + str(2 ** n - 1) + " moves, and "
            "the sequence is: " + seq + ".",
            "The idea to hold in your head: to move a stack, first move everything "
            "above the bottom disc out of the way to the spare peg, move the bottom "
            "disc to the target, then bring the stack back on top of it.",
        ]

    if kind == "code":
        sec = "-".join(str(d) for d in P["secret"])
        return [
            "You are guessing a 3-digit code, digits 1-6. After each guess: a green "
            "\u25cf counts digits that are correct AND in the right place; a yellow \u25cb "
            "counts digits that are in the code but in the wrong place.",
            "The code was " + sec + ".",
            "How to crack it: start with 1-1-1, then 2-2-2 and so on. The replies tell "
            "you which digits exist at all. Once you know the digits, reorder them - "
            "a guess scoring \u25cb means the digits are right but the order is wrong, so "
            "swap them until the \u25cb turns into a \u25cf.",
        ]

    if kind == "sudoku":
        return [
            "Every row, every column and every 2x2 box must hold 1, 2, 3 and 4 "
            "exactly once - no repeats anywhere.",
            "The completed grid is shown on the left.",
            "How to solve it: find a row, column or box that already has three "
            "numbers - the missing one is forced. Fill those singles first; each one "
            "you place makes the next one easier, and the whole grid unravels without "
            "any guessing.",
        ]

    if kind == "nonogram":
        rows = "; ".join("row %d: %s" % (i + 1, " ".join(str(v) for v in P["rows"][i]))
                         for i in range(5))
        return [
            "Each clue is the length of a run of filled cells in that line, listed in "
            "order. '4 2' means four filled, at least one gap, then two filled.",
            "The row clues were " + rows + ".",
            "How to solve it: start with the biggest clue in a line. In a line of 5, "
            "a clue of 5 fills everything, and a clue of 4 must cover the middle cells "
            "wherever it sits - those forced cells are your foothold. Then cross out "
            "cells the clues rule out and keep going.",
        ]

    if kind == "crack":
        codes = [(a, b, c) for a in range(10) for b in range(10) for c in range(10)
                 if len({a, b, c}) == 3]
        lines = ["Begin with every 3-digit code that has no repeated digit - 720 of "
                 "them. A clue is simply a filter: it wipes out every code that would "
                 "not score exactly what the clue shows."]
        left = codes
        for i, cl in enumerate(P["clues"]):
            left = [c for c in left
                    if _crack_score(c, cl["g"]) == (cl["exact"], cl["partial"])]
            lines.append("After clue %d (%s \u2192 \u25cf%d \u25cb%d): %d code%s left."
                         % (i + 1, "-".join(str(d) for d in cl["g"]), cl["exact"],
                            cl["partial"], len(left),
                            "" if len(left) == 1 else "s"))
        lines.append("The only code that survives every clue is " +
                     "-".join(str(d) for d in P["secret"]) + ".")
        lines.append("Shortcut: a clue of \u25cf0 \u25cb0 rules all three of its digits "
                     "out entirely, and \u25cf3 means you are already done.")
        return lines

    if kind == "futoshiki":
        n = P["n"]
        rows = "; ".join("row %d: %s" % (i + 1, " ".join(str(v) for v in P["sol"][i]))
                         for i in range(n))
        return [
            "Every row and every column must hold 1-%d exactly once, like a Latin "
            "square. On top of that each sign fixes the order of two neighbours: "
            "'<' means the left/top cell is smaller, '>' means it is bigger." % n,
            "The finished grid - " + rows + ".",
            "How to get there: hunt for a cell where the signs plus the digits already "
            "in its row and column leave only ONE number that fits. Fill those forced "
            "cells first - each one you place creates another.",
        ]

    if kind == "logic":
        pairs = ", ".join("%s \u2192 %s" % (P["people"][i], P["pets"][P["sol"][i]])
                          for i in range(P["n"]))
        return [
            "Each person keeps exactly one pet, and each pet has exactly one owner. "
            "A clue saying someone does NOT keep something lets you cross that cell "
            "out - and crossing out is how these puzzles are solved.",
            "The answer: " + pairs + ".",
            "How to solve it: apply every clue to the whole grid, ticking what it "
            "confirms and crossing out what it rules out. Then look for a row or "
            "column with only one cell still undecided - that cell must be the "
            "answer, and it unlocks the next one.",
        ]

    if kind == "queens":
        n = P["n"]
        sol = P.get("sol", [])
        where = ", ".join("column %d \u2192 row %d" % (x + 1, y + 1) for x, y in sol)
        return [
            "Place " + str(n) + " queens so that no two share a row, a column or a "
            "diagonal. Because there is one queen per column, think of it as choosing "
            "a row for each column.",
            "One valid layout: " + where + ".",
            "How to solve it: place a queen in the first column, then for each next "
            "column try the rows in order and reject any row that is attacked. If a "
            "column has no safe row, back up and move the previous queen - that "
            "backtracking always finds a layout.",
        ]

    return ["The puzzle is shown solved on the left."]


# ---------------------------------------------------------------------------
# Puzzle set-up
# ---------------------------------------------------------------------------
def _press_lights(g, x, y, n):
    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < n and 0 <= ny < n:
            g[ny][nx] = not g[ny][nx]


def _setup_lights(n, presses):
    g = [[False] * n for _ in range(n)]
    for _ in range(presses):
        _press_lights(g, _rng.randrange(n), _rng.randrange(n), n)
    if not any(any(row) for row in g):          # never hand out a solved board
        _press_lights(g, 0, 0, n)
    # remember one press-set that clears THIS board, for the solution screen
    return {"n": n, "g": g, "moves": 0, "sol": _lights_solve(g, n)}


def _setup_memory(pairs):
    symbols = ["★", "◆", "●", "▲", "■", "✦", "☾", "♥"]
    picked = _rng.sample(symbols, pairs)
    deck = picked + picked
    _rng.shuffle(deck)
    return {"deck": deck, "open": [], "matched": set(), "wrong": 0.0}


def _setup_seq():
    a = _rng.randint(2, 6)
    kind = _rng.choice(["arith", "geo", "square", "fib"])
    if kind == "arith":
        d = _rng.randint(2, 6)
        terms = [a + d * i for i in range(4)]
        nxt = a + d * 4
    elif kind == "geo":
        r = _rng.randint(2, 3)
        terms = [a * (r ** i) for i in range(4)]
        nxt = a * (r ** 4)
    elif kind == "square":
        s = _rng.randint(2, 5)
        terms = [(s + i) ** 2 for i in range(4)]
        nxt = (s + 4) ** 2
    else:
        f = [_rng.randint(1, 4), _rng.randint(2, 5)]
        terms = f[:]
        while len(terms) < 4:
            terms.append(terms[-1] + terms[-2])
        nxt = terms[-1] + terms[-2]
    return {"terms": terms, "answer": nxt, "input": "", "rule": kind}


def _setup_riddle():
    return {"r": _rng.choice(RIDDLES), "input": ""}


def _setup_slide(n):
    target = list(range(1, n * n)) + [0]       # 0 is the blank
    while True:
        g = list(target)
        blank = n * n - 1
        for _ in range(70 * n):                # scramble with legal moves only
            opts = []
            bx, by = blank % n, blank // n
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = bx + dx, by + dy
                if 0 <= nx < n and 0 <= ny < n:
                    opts.append(ny * n + nx)
            pick = _rng.choice(opts)
            g[blank], g[pick] = g[pick], g[blank]
            blank = pick
        if g != target:                        # never hand out a solved board
            return {"n": n, "g": g, "moves": 0}


def _setup_hanoi(n):
    return {"n": n, "pegs": [list(range(n, 0, -1)), [], []], "sel": None, "moves": 0}


def _setup_code():
    return {"secret": [_rng.randint(1, 6) for _ in range(3)],
            "guesses": [], "cur": [1, 1, 1], "slot": 0, "max": 99}


def _setup_sudoku():
    grid = [[0] * 4 for _ in range(4)]
    fixed = [[False] * 4 for _ in range(4)]
    cells = [(x, y) for y in range(4) for x in range(4)]
    _rng.shuffle(cells)
    for x, y in cells[:7]:                     # 7 of the 16 cells are given
        grid[y][x] = SUDOKU_SOL[y][x]
        fixed[y][x] = True
    return {"grid": grid, "fixed": fixed, "sel": None}


def _setup_nonogram(n):
    pat = _rng.choice(NONOGRAM_PATTERNS if n == 5 else NONOGRAM6)
    target = [[c == "X" for c in row] for row in pat]
    rows = [_runs([1 if target[y][x] else 0 for x in range(n)]) for y in range(n)]
    cols = [_runs([1 if target[y][x] else 0 for y in range(n)]) for x in range(n)]
    return {"n": n, "target": target, "grid": [[False] * n for _ in range(n)],
            "rows": rows, "cols": cols}


def _runs(line):
    out, run = [], 0
    for v in line:
        if v:
            run += 1
        elif run:
            out.append(run)
            run = 0
    if run:
        out.append(run)
    return out or [0]


def _setup_queens(n):
    return {"n": n, "q": set(), "sol": _queens_solve(n)}


# --- Futoshiki: a Latin square with < and > between some neighbours ----------
def _latin_square(n):
    base = list(range(1, n + 1))
    sh = _rng.randrange(n)
    rows = [base[(y + sh) % n:] + base[:(y + sh) % n] for y in range(n)]
    _rng.shuffle(rows)
    perm = list(range(n))
    _rng.shuffle(perm)
    rows = [[r[c] for c in perm] for r in rows]
    lab = list(range(1, n + 1))
    _rng.shuffle(lab)
    return [[lab[v - 1] for v in r] for r in rows]


def _futoshiki_count(n, ineq, given, limit=2):
    """How many complete grids satisfy the signs (stops early at `limit`)."""
    grid = [[0] * n for _ in range(n)]
    for (x, y), v in given.items():
        grid[y][x] = v
    found = [0]

    def fits(x, y, v):
        for i in range(n):
            if i != x and grid[y][i] == v:
                return False
            if i != y and grid[i][x] == v:
                return False
        for (a, b), sign in ineq.items():
            va, vb = grid[a[1]][a[0]], grid[b[1]][b[0]]
            if va and vb and ((sign == "<" and va >= vb) or (sign == ">" and va <= vb)):
                return False
        return True

    def solve(pos):
        if found[0] >= limit:
            return
        if pos == n * n:
            found[0] += 1
            return
        x, y = pos % n, pos // n
        if grid[y][x]:
            solve(pos + 1)
            return
        for v in range(1, n + 1):
            grid[y][x] = v
            if fits(x, y, v):
                solve(pos + 1)
            grid[y][x] = 0
            if found[0] >= limit:
                return

    solve(0)
    return found[0]


def _setup_futoshiki(n):
    full = {}
    sol = _latin_square(n)
    for _ in range(60):
        sol = _latin_square(n)
        full = {}
        for y in range(n):
            for x in range(n - 1):
                full[((x, y), (x + 1, y))] = "<" if sol[y][x] < sol[y][x + 1] else ">"
        for x in range(n):
            for y in range(n - 1):
                full[((x, y), (x, y + 1))] = "<" if sol[y][x] < sol[y + 1][x] else ">"
        keys = list(full.keys())
        _rng.shuffle(keys)
        keep = keys[:max(1, int(len(keys) * 0.62))]
        ineq = {k: full[k] for k in keep}
        if _futoshiki_count(n, ineq, {}, 2) == 1:
            return {"n": n, "grid": [[0] * n for _ in range(n)],
                    "ineq": ineq, "sel": None, "sol": sol}
    # extremely unlikely: keep every sign, which is almost always unique
    return {"n": n, "grid": [[0] * n for _ in range(n)],
            "ineq": full, "sel": None, "sol": sol}


# --- Logic grid: deduce who owns which pet --------------------------------
def _setup_logic(n):
    pz = LOGIC_PUZZLES[n]
    return {"n": n, "people": pz["people"], "pets": pz["pets"],
            "sol": pz["sol"], "clues": pz["clues"],
            "marks": [[0] * n for _ in range(n)]}


# --- Crack the Code: a code that is deducible, with no guessing -----------
def _crack_score(guess, code):
    exact = sum(1 for i in range(3) if guess[i] == code[i])
    partial = len(set(guess) & set(code)) - exact
    return exact, partial


def _setup_crack():
    codes = [(a, b, c) for a in range(10) for b in range(10) for c in range(10)
             if len({a, b, c}) == 3]
    for _ in range(200):
        secret = _rng.choice(codes)
        clues, left = [], codes
        while len(clues) < 6 and len(left) > 1:
            g = _rng.choice(codes)
            if any(cl["g"] == list(g) for cl in clues):
                continue
            e, p = _crack_score(g, secret)
            clues.append({"g": list(g), "exact": e, "partial": p})
            left = [c for c in left if _crack_score(c, g) == (e, p)]
        if len(left) == 1 and len(clues) >= 3:
            return {"secret": list(secret), "clues": clues, "input": ""}
    return None


def _setup():
    global P, _message, show_hint, wrong_tries, _stash
    show_hint = False
    _message = ""
    wrong_tries = 0
    _stash = None
    lv = LEVELS[level_index]
    kind = lv["kind"]
    if kind == "lights":
        P = _setup_lights(lv["n"], lv["n"] + 2)
    elif kind == "memory":
        P = _setup_memory(lv["pairs"])
    elif kind == "seq":
        P = _setup_seq()
    elif kind == "riddle":
        P = _setup_riddle()
    elif kind == "slide":
        P = _setup_slide(lv["n"])
    elif kind == "hanoi":
        P = _setup_hanoi(lv["n"])
    elif kind == "crack":
        P = _setup_crack() or _setup_crack()
    elif kind == "sudoku":
        P = _setup_sudoku()
    elif kind == "nonogram":
        P = _setup_nonogram(lv["n"])
    elif kind == "queens":
        P = _setup_queens(lv["n"])
    elif kind == "futoshiki":
        P = _setup_futoshiki(lv["n"])
    elif kind == "logic":
        P = _setup_logic(lv["n"])


# ---------------------------------------------------------------------------
# Solved checks
# ---------------------------------------------------------------------------
def _is_solved():
    kind = LEVELS[level_index]["kind"]
    if kind == "lights":
        return not any(any(row) for row in P["g"])
    if kind == "memory":
        return len(P["matched"]) == len(P["deck"])
    if kind in ("seq", "riddle", "crack"):
        return P.get("done", False)
    if kind == "slide":
        n = P["n"]
        return P["g"] == list(range(1, n * n)) + [0]
    if kind == "hanoi":
        return P["pegs"][2] == list(range(P["n"], 0, -1))
    if kind == "sudoku":
        return all(P["grid"][y][x] == SUDOKU_SOL[y][x] for y in range(4) for x in range(4))
    if kind == "nonogram":
        return P["grid"] == P["target"]
    if kind == "queens":
        return len(P["q"]) == P["n"]
    if kind == "futoshiki":
        return P["grid"] == P["sol"]
    if kind == "logic":
        return all((P["marks"][r][c] == TICK) == (P["sol"][r] == c)
                   for r in range(P["n"]) for c in range(P["n"]))
    return False


def _win():
    global screen
    if level_index not in solved:
        solved.append(level_index)
        _save()
    screen = "solved"
    _sound("win")


# ---------------------------------------------------------------------------
# Input: menu + puzzle taps
# ---------------------------------------------------------------------------
_menu_hit = []


def start_level(i):
    global level_index, screen
    if not (0 <= i < len(LEVELS)) or not _unlocked(i):
        _sound("deny")
        return
    level_index = i
    _setup()
    screen = "play"
    _sound("click")


def back_to_menu():
    global screen
    screen = "menu"


def next_level():
    if level_index + 1 < len(LEVELS) and _unlocked(level_index + 1):
        start_level(level_index + 1)
    else:
        back_to_menu()


def retry():
    _setup()
    screen = "play"


_GRID_KINDS = ("lights", "slide", "sudoku", "nonogram", "queens", "futoshiki", "logic")


def _grid_geo(n, top, bottom, max_cell, max_w=560, min_gap=0):
    """Centre an n x n grid in the given band; returns (ox, oy, cell, gap).

    The drawing and the tap handling both call this, so they can never disagree
    about where a cell is - even as the boards get bigger.
    """
    avail_h = bottom - top
    gap = max(4, min_gap, int(max_cell * 0.11))
    cell = int(min(max_cell, (max_w - (n - 1) * gap) / n, (avail_h - (n - 1) * gap) / n))
    size = n * cell + (n - 1) * gap
    return W / 2 - size / 2, top + (avail_h - size) / 2, cell, gap


def tap(x, y):
    global show_hint, _message
    if screen == "menu":
        for i, r in _menu_hit:
            if _in(r, x, y):
                start_level(i)
                return
        return

    if screen == "solved":
        if _in((W / 2 - 250, H - 110, 230, 56), x, y):
            retry()
        elif _in((W / 2 + 20, H - 110, 230, 56), x, y):
            next_level()
        return

    if screen == "solution":
        if _in((W / 2 - 250, H - 96, 230, 52), x, y):
            keep_trying()
            _sound("click")
        elif _in((W / 2 + 20, H - 96, 230, 52), x, y):
            back_to_menu()
            _sound("click")
        return

    # --- in a level: the shared chrome ---
    if _in((W - 190, 16, 174, 40), x, y):
        show_hint = not show_hint
        _sound("click")
        return
    if _in((16, 16, 120, 40), x, y):
        back_to_menu()
        _sound("click")
        return
    if _in((W - 190, H - 56, 174, 40), x, y):
        retry()
        _sound("click")
        return

    kind = LEVELS[level_index]["kind"]

    if kind in _GRID_KINDS:
        ox, oy, cell, gap = _geo(kind)
        n = _grid_n(kind)
        for gy in range(n):
            for gx in range(n):
                r = (ox + gx * (cell + gap), oy + gy * (cell + gap), cell, cell)
                if _in(r, x, y):
                    _tap_cell(kind, gx, gy)
                    return
        if kind == "sudoku":
            for d in range(4):
                if _in((W / 2 - 140 + d * 74, 460, 66, 54), x, y):
                    _sudoku_put(d + 1)
                    return
        elif kind == "futoshiki":
            bw, bg = 56, 10
            bx = W / 2 - (n * bw + (n - 1) * bg) / 2
            for d in range(n):
                if _in((bx + d * (bw + bg), 468, bw, 48), x, y):
                    _futo_put(d + 1)
                    return
        return

    if kind == "memory":
        cols = 3 if len(P["deck"]) <= 6 else 4
        cw, ch, gap = 130, 118, 16
        ox = W / 2 - (cols * cw + (cols - 1) * gap) / 2
        oy = 150
        for i in range(len(P["deck"])):
            gx, gy = i % cols, i // cols
            r = (ox + gx * (cw + gap), oy + gy * (ch + gap), cw, ch)
            if _in(r, x, y):
                if i in P["matched"] or i in P["open"] or len(P["open"]) >= 2:
                    return
                P["open"].append(i)
                _sound("click")
                if len(P["open"]) == 2:
                    a, b = P["open"]
                    if P["deck"][a] == P["deck"][b]:
                        P["matched"].update((a, b))
                        P["open"] = []
                        _sound("coin")
                        if _is_solved():
                            _win()
                    else:
                        P["wrong"] = 0.55
                        _sound("deny")
                        _note_wrong()
                return

    elif kind == "hanoi":
        peg_w, peg_gap = 190, 60
        ox = W / 2 - (3 * peg_w + 2 * peg_gap) / 2
        for i in range(3):
            if _in((ox + i * (peg_w + peg_gap), 150, peg_w, 300), x, y):
                _hanoi_click(i)
                return


def _grid_n(kind):
    """How many rows/columns the current grid puzzle has."""
    if kind == "sudoku":
        return 4
    return P.get("n", 3)


def _geo(kind):
    """Grid geometry, shared by the drawing and the tap handling."""
    n = _grid_n(kind)
    if kind in ("lights", "slide"):
        return _grid_geo(n, 152, 448, 78)
    if kind == "sudoku":
        return _grid_geo(4, 160, 420, 66)
    if kind == "queens":
        return _grid_geo(n, 150, 450, 60)
    if kind == "futoshiki":
        return _grid_geo(n, 162, 436, 68, min_gap=22)
    if kind == "nonogram":
        ox, oy, cell, gap = _grid_geo(n, 176, 470, 58, max_w=420)
        return ox + 46, oy, cell, gap
    if kind == "logic":
        ox, oy, cell, gap = _grid_geo(n, 182, 452, 60, max_w=420)
        return ox + 62, oy, cell, gap
    return _grid_geo(n, 150, 450, 70)


def _tap_cell(kind, gx, gy):
    if kind == "lights":
        n = P["n"]
        before = sum(row.count(True) for row in P["g"])
        _press_lights(P["g"], gx, gy, n)
        after = sum(row.count(True) for row in P["g"])
        P["moves"] += 1
        _sound("click")
        if _is_solved():
            _win()
        elif after > before:                 # that press made the board worse
            _note_wrong()
    elif kind == "slide":
        n = P["n"]
        i = gy * n + gx
        blank = P["g"].index(0)
        if abs(gx - blank % n) + abs(gy - blank // n) == 1:
            before = _slide_dist(P["g"], n)
            P["g"][blank], P["g"][i] = P["g"][i], P["g"][blank]
            after = _slide_dist(P["g"], n)
            P["moves"] += 1
            _sound("click")
            if _is_solved():
                _win()
            elif after > before:             # moved a tile further from home
                _note_wrong()
    elif kind == "sudoku":
        if not P["fixed"][gy][gx]:
            P["sel"] = (gx, gy)
            _sound("click")
    elif kind == "nonogram":
        P["grid"][gy][gx] = not P["grid"][gy][gx]
        _sound("click")
        if _is_solved():
            _win()
        elif P["grid"][gy][gx] != P["target"][gy][gx]:
            _note_wrong()
    elif kind == "queens":
        if (gx, gy) in P["q"]:
            P["q"].discard((gx, gy))
        elif _queens_ok(P["q"], gx, gy):
            P["q"].add((gx, gy))
            _sound("click")
            if _is_solved():
                _win()
        else:
            _sound("deny")
            _note_wrong()
    elif kind == "futoshiki":
        P["sel"] = (gx, gy)
        _sound("click")
    elif kind == "logic":
        m = P["marks"][gy][gx]
        m = 0 if m == CROSS else m + 1
        P["marks"][gy][gx] = m
        _sound("click")
        if _is_solved():
            _win()
        else:
            truth = P["sol"][gy] == gx
            if (m == TICK and not truth) or (m == CROSS and truth):
                _note_wrong()


def _sudoku_put(d):
    if not P["sel"]:
        return
    gx, gy = P["sel"]
    P["grid"][gy][gx] = d
    _sound("click")
    if _is_solved():
        _win()
    elif d != SUDOKU_SOL[gy][gx]:
        _note_wrong()


def _futo_bad():
    """True if the grid currently breaks a Futoshiki rule."""
    n, g = P["n"], P["grid"]
    for y in range(n):
        vals = [v for v in g[y] if v]
        if len(vals) != len(set(vals)):
            return True
    for x in range(n):
        vals = [g[y][x] for y in range(n) if g[y][x]]
        if len(vals) != len(set(vals)):
            return True
    for (a, b), sign in P["ineq"].items():
        va, vb = g[a[1]][a[0]], g[b[1]][b[0]]
        if va and vb and ((sign == "<" and va >= vb) or (sign == ">" and va <= vb)):
            return True
    return False


def _futo_put(d):
    if not P["sel"]:
        return
    gx, gy = P["sel"]
    P["grid"][gy][gx] = d
    _sound("click")
    if _is_solved():
        _win()
    elif _futo_bad():
        _note_wrong()

def _hanoi_click(peg):
    global _message
    pegs, sel = P["pegs"], P["sel"]
    if sel is None:
        if pegs[peg]:
            P["sel"] = peg
            _sound("click")
        else:
            _sound("deny")
        return
    if sel == peg:
        P["sel"] = None
        return
    if pegs[peg] and pegs[sel] and pegs[peg][-1] < pegs[sel][-1]:
        _message = "A bigger disc cannot sit on a smaller one."
        _sound("deny")
        _note_wrong()
        return
    pegs[peg].append(pegs[sel].pop())
    P["sel"] = None
    P["moves"] += 1
    _message = ""
    _sound("click")
    if _is_solved():
        _win()


def _code_guess():
    sec, g = P["secret"], list(P["cur"])
    exact = sum(1 for i in range(3) if g[i] == sec[i])
    sleft = [sec[i] for i in range(3) if g[i] != sec[i]]
    partial = 0
    for i in range(3):
        if g[i] != sec[i] and g[i] in sleft:
            sleft.remove(g[i])
            partial += 1
    P["guesses"].append({"g": g, "exact": exact, "partial": partial})
    P["slot"] = 0
    if exact == 3:
        _sound("win")
        _win()
    else:
        _sound("deny")
        _note_wrong()


def _queens_ok(q, x, y):
    for (qx, qy) in q:
        if qx == x or qy == y or abs(qx - x) == abs(qy - y):
            return False
    return True


def _slide_dist(g, n):
    """Total Manhattan distance of the tiles from their home squares."""
    d = 0
    for i, v in enumerate(g):
        if v:
            home = v - 1
            d += abs(i % n - home % n) + abs(i // n - home // n)
    return d


def key(k):
    """Typed input: used by the Riddle and Number Sequence levels."""
    global _message
    if screen != "play":
        return
    kind = LEVELS[level_index]["kind"]
    if kind not in ("riddle", "seq", "crack"):
        return
    if k == "Backspace":
        P["input"] = P["input"][:-1]
        return
    if k == "Enter":
        text = P["input"].strip().lower()
        if not text:
            return
        if kind == "crack":
            got = [int(c) for c in text if c.isdigit()]
            if len(got) != 3:
                _message = "Type exactly three digits, then press Enter."
                return
            if got == P["secret"]:
                P["done"] = True
                _win()
            else:
                _message = "That code breaks one of the clues - re-check each row."
                P["input"] = ""
                _sound("deny")
                _note_wrong()
            return
        if kind == "seq":
            try:
                val = int(text)
            except ValueError:
                _message = "Type a number, then press Enter."
                return
            if val == P["answer"]:
                P["done"] = True
                _win()
            else:
                _message = "Not it - look at the gaps again."
                P["input"] = ""
                _sound("deny")
                _note_wrong()
        else:
            if text in P["r"]["a"]:
                P["done"] = True
                _win()
            else:
                _message = "Not quite - try again."
                P["input"] = ""
                _sound("deny")
                _note_wrong()
        return
    if len(k) == 1 and (k.isalnum() or k in " -'"):
        P["input"] = (P["input"] + k)[:24]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def update(dt):
    dt = min(max(float(dt), 0.0), 0.05)
    if screen == "play" and LEVELS[level_index]["kind"] == "memory" and P.get("wrong", 0) > 0:
        P["wrong"] = max(0.0, P["wrong"] - dt)
        if P["wrong"] == 0.0 and len(P["open"]) == 2:
            P["open"] = []


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _panel(x, y, w, h, fill="rgba(12, 22, 46, 0.92)", stroke="rgba(140, 180, 255, 0.25)", r=16):
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


def _button(x, y, w, h, label, active=False, accent="#7ef0c0", size=15):
    _panel(x, y, w, h, "#7ef0c0" if active else "rgba(24, 34, 62, 0.92)",
           "#ffffff" if active else "rgba(150, 180, 240, 0.30)", 12)
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillStyle = "#06101f" if active else "#eaf2ff"
    ctx.font = "700 %dpx %s" % (size, FONT)
    ctx.fillText(label, x + w / 2, y + h / 2 + 1)
    ctx.textBaseline = "alphabetic"


def _title(t, y, size=30, color="#ffffff"):
    ctx.textAlign = "center"
    ctx.fillStyle = color
    ctx.font = "800 %dpx %s" % (size, FONT)
    ctx.fillText(t, W / 2, y)


def _wrap(text, x, y, maxw, size=15, color="#9fb3d9", center=True, cap=None):
    """Wrap text. With `cap`, the size stops growing sooner - for tight boxes."""
    if _preview:            # the solution preview draws the board, not its captions
        return y
    if cap is None:
        c, px = ctx, size
    else:
        c, px = ctx._real, int(round(size * min(UI, cap)))
    c.font = "600 %dpx %s" % (int(round(px)), FONT)
    c.fillStyle = color
    c.textAlign = "center" if center else "left"
    words, line = text.split(" "), ""
    for wd in words:
        trial = (line + " " + wd).strip()
        if c.measureText(trial).width > maxw and line:
            c.fillText(line, x, y)
            y += px + 6
            line = wd
        else:
            line = trial
    if line:
        c.fillText(line, x, y)
    return y


# ---------------------------------------------------------------------------
# Drawing: menu + chrome
# ---------------------------------------------------------------------------
def _draw_menu():
    global _menu_hit
    _menu_hit = []
    grad = ctx.createLinearGradient(0, 0, 0, H)
    grad.addColorStop(0, "#101a3a")
    grad.addColorStop(1, "#05080f")
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, W, H)

    _title("KHELO PUZZLES", 46, 32)
    _wrap("20 levels - a different puzzle each time, getting harder as you go",
          W / 2, 72, 620, 14)
    _wrap("Solved: %d / %d" % (len(solved), len(LEVELS)), W / 2, 94, 520, 13, "#7ef0c0")

    cols, cw, ch, gap = 5, 162, 86, 13
    ox = W / 2 - (cols * cw + (cols - 1) * gap) / 2
    oy = 112
    for i, lv in enumerate(LEVELS):
        gx, gy = i % cols, i // cols
        x = ox + gx * (cw + gap)
        y = oy + gy * (ch + gap)
        locked = not _unlocked(i)
        done = i in solved
        _panel(x, y, cw, ch,
               "rgba(20, 30, 56, 0.92)" if not locked else "rgba(14, 20, 36, 0.75)",
               "#7ef0c0" if done else "rgba(150, 180, 240, 0.22)", 12)
        ctx.textAlign = "center"
        ctx.fillStyle = "#7ef0c0" if done else ("#8794b3" if locked else "#9fb3d9")
        ctx._real.font = "800 %dpx %s" % (_fs(11, 1.15), FONT)
        ctx._real.textAlign = "center"
        ctx._real.fillStyle = "#7ef0c0" if done else ("#8794b3" if locked else "#9fb3d9")
        ctx._real.fillText("LEVEL %d" % (i + 1), x + cw / 2, y + 20)
        _wrap(lv["name"], x + cw / 2, y + 42, cw - 14, 14,
              "#ffffff" if not locked else "#5d6a85", cap=1.12)
        ctx.font = "800 17px %s" % FONT
        ctx.fillStyle = "#7ef0c0" if done else "#5d6a85"
        ctx.fillText("\u2713" if done else ("\U0001f512" if locked else "\u2022"),
                     x + cw / 2, y + ch - 12)
        if not locked:
            _menu_hit.append((i, (x, y, cw, ch)))


def _hint_popup(text):
    """A floating card that sits directly above the Hint button."""
    bw, bh = 420, 84
    bx, by = W - 190 + 174 - bw, 62
    _panel(bx, by, bw, bh, "rgba(255, 210, 63, 0.16)",
           "rgba(255, 210, 63, 0.62)", 12)
    cx = W - 190 + 87                                   # centre of the Hint button
    ctx.beginPath()                                     # little pointer up to it
    ctx.moveTo(cx - 11, by)
    ctx.lineTo(cx + 11, by)
    ctx.lineTo(cx, by - 8)
    ctx.closePath()
    ctx.fillStyle = "rgba(255, 210, 63, 0.62)"
    ctx.fill()
    _wrap(text, bx + bw / 2, by + 26, bw - 30, 13, "#ffe9a3")


def _draw_chrome():
    lv = LEVELS[level_index]
    ctx.textAlign = "left"
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 12px %s" % FONT
    ctx.fillText("LEVEL %d / %d" % (level_index + 1, len(LEVELS)), 150, 30)
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 22px %s" % FONT
    ctx.fillText(lv["name"], 150, 54)

    _button(16, 16, 120, 40, "\u2190 Levels")
    _button(W - 190, 16, 174, 40, "Hint" if not show_hint else "Hide hint",
            show_hint, "#ffd23f")
    _button(W - 190, H - 52, 174, 36, "Restart")

    # the goal, always on screen, so the player knows what is being asked
    _panel(16, 64, 440, 44, "rgba(126, 240, 192, 0.10)",
           "rgba(126, 240, 192, 0.38)", 10)
    ctx.textAlign = "left"
    ctx.fillStyle = "#7ef0c0"
    ctx.font = "800 11px %s" % FONT
    ctx.fillText("GOAL", 30, 84)
    _wrap(lv["goal"], 74, 82, 366, 13, "#dff7ee", False)

    # how many wrong tries before the solution is shown
    if wrong_tries:
        left = MAX_WRONG - wrong_tries
        ctx.textAlign = "left"
        ctx.fillStyle = "#ff9aa2" if left <= 3 else "#7f8fb3"
        ctx.font = "700 12px %s" % FONT
        ctx.fillText("wrong tries %d / %d" % (wrong_tries, MAX_WRONG), 24, H - 22)

    if show_hint:
        _hint_popup(lv["hint"])

    if _message:
        _wrap(_message, W / 2, H - 66, 700, 15, "#ff9aa2")


# ---------------------------------------------------------------------------
# Drawing: puzzles
# ---------------------------------------------------------------------------
def _draw_lights():
    n, g = P["n"], P["g"]
    ox, oy, cell, gap = _geo("lights")
    for y in range(n):
        for x in range(n):
            px, py = ox + x * (cell + gap), oy + y * (cell + gap)
            lit = g[y][x]
            _panel(px, py, cell, cell,
                   "#ffd23f" if lit else "rgba(24, 34, 62, 0.95)",
                   "#fff2bd" if lit else "rgba(150, 180, 240, 0.25)", 12)
            if _preview and (y * n + x) in P.get("sol", []):
                ctx.beginPath()          # ring the tiles the solution presses
                ctx.arc(px + cell / 2, py + cell / 2, cell * 0.28, 0, 6.2832)
                ctx.lineWidth = 5
                ctx.strokeStyle = "#7ef0c0"
                ctx.stroke()


def _draw_memory():
    cols = 3 if len(P["deck"]) <= 6 else 4
    cw, ch, gap = 130, 118, 16
    ox = W / 2 - (cols * cw + (cols - 1) * gap) / 2
    oy = 150
    for i, sym in enumerate(P["deck"]):
        gx, gy = i % cols, i // cols
        px, py = ox + gx * (cw + gap), oy + gy * (ch + gap)
        shown = i in P["matched"] or i in P["open"]
        _panel(px, py, cw, ch,
               "rgba(126, 240, 192, 0.20)" if i in P["matched"] else "rgba(24, 34, 62, 0.95)",
               "#7ef0c0" if i in P["matched"] else "rgba(150, 180, 240, 0.25)", 14)
        ctx.textAlign = "center"
        ctx.fillStyle = "#ffffff"
        ctx.font = "800 42px %s" % FONT
        ctx.fillText(sym if shown else "?", px + cw / 2, py + ch / 2 + 15)


def _draw_typed(prompt_lines, unit):
    y = 172 if show_hint else 130
    for line in prompt_lines:
        _wrap(line, W / 2, y, 700, 18, "#eaf2ff")
        y += 30
    box = (W / 2 - 260, y + 30, 520, 64)
    _panel(box[0], box[1], box[2], box[3], "rgba(24, 34, 62, 0.95)",
           "rgba(150, 180, 240, 0.35)", 12)
    ctx.textAlign = "left"
    ctx.fillStyle = "#ffffff"
    ctx.font = "700 26px %s" % FONT
    ctx.fillText((P["input"] + "|") if P["input"] else "|", box[0] + 18, box[1] + 42)
    _wrap(unit, W / 2, box[1] + box[3] + 34, 600, 14)


def _draw_seq():
    _draw_typed([", ".join(str(t) for t in P["terms"]) + ",  ?"],
                "Type the next number and press Enter")


def _draw_riddle():
    _wrap(P["r"]["q"], W / 2, 190 if show_hint else 150, 660, 19, "#eaf2ff")
    _draw_typed([], "Type your answer and press Enter")


def _draw_slide():
    n = P["n"]
    ox, oy, cell, gap = _geo("slide")
    for i, v in enumerate(P["g"]):
        gx, gy = i % n, i // n
        px, py = ox + gx * (cell + gap), oy + gy * (cell + gap)
        if v == 0:
            _panel(px, py, cell, cell, "rgba(10, 16, 32, 0.6)",
                   "rgba(150, 180, 240, 0.15)", 10)
        else:
            _panel(px, py, cell, cell, "rgba(36, 52, 92, 0.95)",
                   "rgba(150, 180, 240, 0.35)", 10)
            ctx.textAlign = "center"
            ctx.fillStyle = "#ffffff"
            ctx.font = "800 %dpx %s" % (int(cell * 0.42), FONT)
            ctx.fillText(str(v), px + cell / 2, py + cell / 2 + cell * 0.15)


def _draw_hanoi():
    n, pegs = P["n"], P["pegs"]
    peg_w, peg_gap = 190, 60
    ox = W / 2 - (3 * peg_w + 2 * peg_gap) / 2
    base_y = 420
    for i in range(3):
        px = ox + i * (peg_w + peg_gap)
        _panel(px, 150, peg_w, base_y - 150, "rgba(14, 22, 44, 0.6)",
               "#7ef0c0" if P["sel"] == i else "rgba(150, 180, 240, 0.22)", 12)
        ctx.fillStyle = "rgba(150, 180, 240, 0.35)"
        ctx.fillRect(px + peg_w / 2 - 4, 190, 8, base_y - 210)
        for k, disc in enumerate(pegs[i]):
            dw = 20 + disc * (240 / max(1, n))
            dy = base_y - 20 - k * (230 / (n + 1))
            col = ["#e63946", "#f59e0b", "#2dd4bf", "#a78bfa", "#60a5fa"][disc % 5]
            _panel(px + peg_w / 2 - dw / 2, dy, dw, 20, col,
                   "rgba(255,255,255,0.35)", 7)


def _draw_crack():
    y = 132
    for cl in P["clues"][:6]:
        for i, d in enumerate(cl["g"]):
            bx = W / 2 - 200 + i * 44
            _panel(bx, y, 36, 36, "rgba(36, 52, 92, 0.95)",
                   "rgba(150, 180, 240, 0.35)", 8)
            ctx.textAlign = "center"
            ctx.fillStyle = "#ffffff"
            ctx.font = "800 19px %s" % FONT
            ctx.fillText(str(d), bx + 18, y + 25)
        ctx.textAlign = "left"
        ctx.font = "800 17px %s" % FONT
        ctx.fillStyle = "#7ef0c0"
        ctx.fillText("\u25cf %d" % cl["exact"], W / 2 + 6, y + 25)
        ctx.fillStyle = "#ffd23f"
        ctx.fillText("\u25cb %d" % cl["partial"], W / 2 + 96, y + 25)
        y += 40
    box = (W / 2 - 160, y + 14, 320, 54)
    _panel(box[0], box[1], box[2], box[3], "rgba(24, 34, 62, 0.95)", "#7ef0c0", 12)
    ctx.textAlign = "center"
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 26px %s" % FONT
    ctx.fillText((P["input"] + "|") if P["input"] else "|",
                 box[0] + box[2] / 2, box[1] + 37)
    _wrap("Type the three digits, then press Enter", W / 2, box[1] + box[3] + 24, 620, 14)


def _draw_sudoku():
    ox, oy, cell, gap = _geo("sudoku")
    for gy in range(4):
        for gx in range(4):
            px, py = ox + gx * (cell + gap), oy + gy * (cell + gap)
            sel = P["sel"] == (gx, gy)
            fixed = P["fixed"][gy][gx]
            _panel(px, py, cell, cell,
                   "#2a3a66" if sel else ("rgba(18, 26, 48, 0.95)" if fixed else "rgba(26, 36, 64, 0.95)"),
                   "#7ef0c0" if sel else "rgba(150, 180, 240, 0.25)", 8)
            v = P["grid"][gy][gx]
            if v:
                ctx.textAlign = "center"
                ctx.fillStyle = "#9fb3d9" if fixed else "#ffffff"
                ctx.font = "800 %dpx %s" % (int(cell * 0.44), FONT)
                ctx.fillText(str(v), px + cell / 2, py + cell / 2 + cell * 0.15)
    for d in range(4):
        _button(W / 2 - 140 + d * 74, 460, 66, 54, str(d + 1), False, size=22)


def _draw_nonogram():
    n = P["n"]
    ox, oy, cell, gap = _geo("nonogram")
    for y in range(n):
        for x in range(n):
            px, py = ox + x * (cell + gap), oy + y * (cell + gap)
            _panel(px, py, cell, cell,
                   "#7ef0c0" if P["grid"][y][x] else "rgba(22, 30, 54, 0.95)",
                   "rgba(150, 180, 240, 0.25)", 5)
    ctx.textAlign = "right"
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 15px %s" % FONT
    for y in range(n):
        ctx.fillText(" ".join(str(v) for v in P["rows"][y]),
                     ox - 10, oy + y * (cell + gap) + cell / 2 + 5)
    ctx.textAlign = "center"
    for x in range(n):
        ctx.fillText(" ".join(str(v) for v in P["cols"][x]),
                     ox + x * (cell + gap) + cell / 2, oy - 10)


def _draw_queens():
    n, cell = P["n"], _geo("queens")[2]
    ox, oy, cell, gap = _geo("queens")
    for y in range(n):
        for x in range(n):
            dark = (x + y) % 2 == 0
            _panel(ox + x * (cell + gap), oy + y * (cell + gap), cell, cell,
                   "rgba(30, 40, 70, 0.95)" if dark else "rgba(22, 30, 56, 0.95)",
                   "rgba(150, 180, 240, 0.18)", 4)
    for (x, y) in P["q"]:
        ctx.textAlign = "center"
        ctx.fillStyle = "#ffd23f"
        ctx.font = "800 %dpx %s" % (int(cell * 0.55), FONT)
        ctx.fillText("\u265b", ox + x * (cell + gap) + cell / 2,
                     oy + y * (cell + gap) + cell / 2 + cell * 0.19)


def _draw_futoshiki():
    n = P["n"]
    ox, oy, cell, gap = _geo("futoshiki")
    for gy in range(n):
        for gx in range(n):
            px, py = ox + gx * (cell + gap), oy + gy * (cell + gap)
            sel = P["sel"] == (gx, gy)
            _panel(px, py, cell, cell,
                   "#2a3a66" if sel else "rgba(24, 34, 62, 0.95)",
                   "#7ef0c0" if sel else "rgba(150, 180, 240, 0.3)", 8)
            v = P["grid"][gy][gx]
            if v:
                ctx.textAlign = "center"
                ctx.fillStyle = "#ffffff"
                ctx.font = "800 %dpx %s" % (int(cell * 0.46), FONT)
                ctx.fillText(str(v), px + cell / 2, py + cell / 2 + cell * 0.16)
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillStyle = "#ffd23f"
    ctx.font = "800 %dpx %s" % (max(13, int(gap * 0.9)), FONT)
    for (a, b), sign in P["ineq"].items():
        (ax, ay), (bx, by) = a, b
        if ax == bx:                                    # stacked vertically
            mx = ox + ax * (cell + gap) + cell / 2
            my = oy + ay * (cell + gap) + cell + gap / 2
        else:                                           # side by side
            mx = ox + ax * (cell + gap) + cell + gap / 2
            my = oy + ay * (cell + gap) + cell / 2
        ctx.fillText(sign, mx, my)
    ctx.textBaseline = "alphabetic"
    bw, bg = 56, 10
    bx = W / 2 - (n * bw + (n - 1) * bg) / 2
    for d in range(n):
        _button(bx + d * (bw + bg), 468, bw, 48, str(d + 1), False, size=20)


def _draw_logic():
    n = P["n"]
    ox, oy, cell, gap = _geo("logic")
    for gy in range(n):
        for gx in range(n):
            px, py = ox + gx * (cell + gap), oy + gy * (cell + gap)
            _panel(px, py, cell, cell, "rgba(24, 34, 62, 0.95)",
                   "rgba(150, 180, 240, 0.3)", 8)
            m = P["marks"][gy][gx]
            if m:
                ctx.textAlign = "center"
                ctx.font = "800 %dpx %s" % (int(cell * 0.5), FONT)
                ctx.fillStyle = "#7ef0c0" if m == TICK else "#ff8b8b"
                ctx.fillText("\u2713" if m == TICK else "\u2717",
                             px + cell / 2, py + cell / 2 + cell * 0.17)
    ctx.textAlign = "right"
    ctx.fillStyle = "#eaf2ff"
    ctx.font = "700 15px %s" % FONT
    for gy in range(n):
        ctx.fillText(P["people"][gy], ox - 12,
                     oy + gy * (cell + gap) + cell / 2 + 5)
    ctx.textAlign = "center"
    ctx.font = "700 13px %s" % FONT
    for gx in range(n):
        ctx.fillText(P["pets"][gx], ox + gx * (cell + gap) + cell / 2, oy - 10)
    y = oy + n * (cell + gap) + 24
    for c in P["clues"]:
        _wrap(c, W / 2, y, 780, 14, "#9fb3d9")
        y += 19


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
def _draw_solved():
    ctx.fillStyle = "rgba(4, 10, 24, 0.72)"
    ctx.fillRect(0, 0, W, H)
    _panel(W / 2 - 290, 130, 580, 300, stroke="#7ef0c0", r=20)
    _title("SOLVED!", 200, 42, "#7ef0c0")
    _title(LEVELS[level_index]["name"], 244, 24)
    _wrap("Level %d of %d cleared." % (level_index + 1, len(LEVELS)), W / 2, 288, 500, 16)
    last = level_index + 1 >= len(LEVELS)
    _wrap("All 10 puzzles beaten - nicely done!" if last else
          "Next up: " + LEVELS[level_index + 1]["name"], W / 2, 320, 520, 16, "#ffd23f")
    _button(W / 2 - 250, H - 110, 230, 56, "Replay", False)
    _button(W / 2 + 20, H - 110, 230, 56,
            "Levels" if last else "Next level →", True)


# which drawing routine renders each puzzle kind
_PUZZLE_DRAW = {
    "lights": _draw_lights, "memory": _draw_memory, "seq": _draw_seq,
    "riddle": _draw_riddle, "slide": _draw_slide, "hanoi": _draw_hanoi,
    "crack": _draw_crack, "sudoku": _draw_sudoku, "nonogram": _draw_nonogram,
    "queens": _draw_queens, "futoshiki": _draw_futoshiki, "logic": _draw_logic,
}


def _sol_region(kind):
    """The slice of the canvas the current board occupies, for the preview."""
    if kind == "memory":
        cols = 3 if len(P["deck"]) <= 6 else 4
        rows = (len(P["deck"]) + cols - 1) // cols
        w = cols * 130 + (cols - 1) * 16
        h = rows * 118 + (rows - 1) * 16
        return (W / 2 - w / 2 - 12, 138, W / 2 + w / 2 + 12, 138 + h + 12)
    if kind == "hanoi":
        return (95, 140, 805, 435)
    if kind in ("seq", "riddle", "crack"):
        return (180, 100, 720, 500)
    ox, oy, cell, gap = _geo(kind)
    n = _grid_n(kind)
    size = n * cell + (n - 1) * gap
    x0, y0 = ox - 12, oy - 12
    x1, y1 = ox + size + 12, oy + size + 12
    if kind in ("nonogram", "logic"):
        x0 -= 78
        y0 -= 30
    if kind in ("sudoku", "futoshiki"):
        y1 += 72
    return (x0, y0, x1, y1)


def _draw_solution():
    """The stuck screen: the answer on the left, how to get there on the right."""
    global _preview
    ctx.fillStyle = "rgba(4, 10, 24, 0.95)"
    ctx.fillRect(0, 0, W, H)
    _panel(36, 20, W - 72, H - 40, stroke="#7ef0c0", r=20)

    _title("SOLUTION", 60, 30, "#7ef0c0")
    ctx.textAlign = "center"
    ctx.fillStyle = "#ffd23f"
    ctx.font = "800 17px %s" % FONT
    ctx.fillText("%s  ·  level %d of %d" %
                 (LEVELS[level_index]["name"], level_index + 1, len(LEVELS)), W / 2, 86)

    kind = LEVELS[level_index]["kind"]
    px, py, pw, ph = 60, 104, 400, 360
    _panel(px, py, pw, ph, "rgba(10, 18, 38, 0.92)", "rgba(150, 180, 240, 0.22)", 12)

    if kind in ("seq", "riddle", "code"):
        # a word/number answer reads better big than as a board
        ctx.textAlign = "center"
        ctx.fillStyle = "#9fb3d9"
        ctx.font = "700 14px %s" % FONT
        ctx.fillText("THE ANSWER", px + pw / 2, py + 52)
        ans = "-".join(str(d) for d in P["secret"]) if kind == "code" else str(P.get("input", "?"))
        ctx.fillStyle = "#7ef0c0"
        ctx.font = "800 %dpx %s" % (38 if len(ans) < 12 else 22, FONT)
        ctx.fillText(ans, px + pw / 2, py + ph / 2 + 6)
    else:
        x0, y0, x1, y1 = _sol_region(kind)
        s = min(pw / (x1 - x0), ph / (y1 - y0)) * 0.94
        ctx.save()
        ctx.beginPath()
        ctx.rect(px, py, pw, ph)
        ctx.clip()
        ctx.translate(px + (pw - (x1 - x0) * s) / 2 - x0 * s,
                      py + (ph - (y1 - y0) * s) / 2 - y0 * s)
        ctx.scale(s, s)
        _preview = True
        _PUZZLE_DRAW[kind]()
        _preview = False
        ctx.restore()
        ctx.textAlign = "center"
        ctx.fillStyle = "#7f8fb3"
        ctx.font = "700 12px %s" % FONT
        ctx.fillText("the answer", px + pw / 2, py + ph - 12)

    tx, ty = 486, 116
    for line in _solution_lines():
        ty = _wrap(line, tx, ty, 372, 15, "#dbe6ff", False) + 22

    _button(W / 2 - 250, H - 96, 230, 52, "Keep trying", False)
    _button(W / 2 + 20, H - 96, 230, 52, "Back to levels", True)


def draw():
    if screen == "menu":
        _draw_menu()
        return

    if screen == "solution":
        _draw_solution()
        return

    grad = ctx.createLinearGradient(0, 0, 0, H)
    grad.addColorStop(0, "#101a3a")
    grad.addColorStop(1, "#05080f")
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, W, H)

    _draw_chrome()
    _PUZZLE_DRAW[LEVELS[level_index]["kind"]]()

    if screen == "solved":
        _draw_solved()


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
_load()
screen = "menu"

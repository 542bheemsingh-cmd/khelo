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

SAVE_KEY = "khelo_puzzle_save"
FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"

# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------
LEVELS = [
    {"name": "Lights Out", "kind": "lights",
     "hint": "Pressing a tile flips it and its four neighbours. Work top to bottom."},
    {"name": "Memory Match", "kind": "memory",
     "hint": "Flip two tiles. A matching pair stays open - remember the rest."},
    {"name": "Number Sequence", "kind": "seq",
     "hint": "Look at the gap between each term."},
    {"name": "Riddle", "kind": "riddle",
     "hint": "It is brown, has a head and a tail, and no legs."},
    {"name": "Sliding Puzzle", "kind": "slide",
     "hint": "Put 1-8 in order with the blank at the bottom right."},
    {"name": "Tower of Hanoi", "kind": "hanoi",
     "hint": "Move the whole stack to peg 3. Never a big disc on a small one."},
    {"name": "Code Breaker", "kind": "code",
     "hint": "Exact = right digit in the right place. Partial = right digit, wrong place."},
    {"name": "Mini Sudoku", "kind": "sudoku",
     "hint": "Every row, column and 2x2 box needs 1-4 exactly once."},
    {"name": "Nonogram", "kind": "nonogram",
     "hint": "Each clue is a run of filled cells, in order."},
    {"name": "N-Queens", "kind": "queens",
     "hint": "No two queens may share a row, column or diagonal."},
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
    if kind == "seq":
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
    global screen, show_hint
    screen = "solution"
    show_hint = False
    _apply_solution()
    _sound("deny")


def keep_trying():
    """Dismiss the solution screen and go back to the board with a fresh count."""
    global screen, wrong_tries
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
        P["g"] = [1, 2, 3, 4, 5, 6, 7, 8, 0]
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


def _setup_slide():
    g = [1, 2, 3, 4, 5, 6, 7, 8, 0]           # 0 is the blank
    blank = 8
    for _ in range(120):                       # scramble with legal moves only
        opts = []
        bx, by = blank % 3, blank // 3
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = bx + dx, by + dy
            if 0 <= nx < 3 and 0 <= ny < 3:
                opts.append(ny * 3 + nx)
        pick = _rng.choice(opts)
        g[blank], g[pick] = g[pick], g[blank]
        blank = pick
    if g == [1, 2, 3, 4, 5, 6, 7, 8, 0]:
        g[7], g[8] = g[8], g[7]
    return {"g": g, "moves": 0}


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


def _setup_nonogram():
    pat = _rng.choice(NONOGRAM_PATTERNS)
    target = [[c == "X" for c in row] for row in pat]
    rows = []
    for y in range(5):
        rows.append(_runs([1 if target[y][x] else 0 for x in range(5)]))
    cols = []
    for x in range(5):
        cols.append(_runs([1 if target[y][x] else 0 for y in range(5)]))
    return {"target": target, "grid": [[False] * 5 for _ in range(5)],
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


def _setup_queens():
    return {"n": 6, "q": set(), "sol": _queens_solve(6)}


def _setup():
    global P, _message, show_hint, wrong_tries
    show_hint = False
    _message = ""
    wrong_tries = 0
    kind = LEVELS[level_index]["kind"]
    if kind == "lights":
        P = _setup_lights(3, _rng.randint(3, 5))
    elif kind == "memory":
        P = _setup_memory(3)
    elif kind == "seq":
        P = _setup_seq()
    elif kind == "riddle":
        P = _setup_riddle()
    elif kind == "slide":
        P = _setup_slide()
    elif kind == "hanoi":
        P = _setup_hanoi(3)
    elif kind == "code":
        P = _setup_code()
    elif kind == "sudoku":
        P = _setup_sudoku()
    elif kind == "nonogram":
        P = _setup_nonogram()
    elif kind == "queens":
        P = _setup_queens()


# ---------------------------------------------------------------------------
# Solved checks
# ---------------------------------------------------------------------------
def _is_solved():
    kind = LEVELS[level_index]["kind"]
    if kind == "lights":
        return not any(any(row) for row in P["g"])
    if kind == "memory":
        return len(P["matched"]) == len(P["deck"])
    if kind in ("seq", "riddle"):
        return P.get("done", False)
    if kind == "slide":
        return P["g"] == [1, 2, 3, 4, 5, 6, 7, 8, 0]
    if kind == "hanoi":
        return P["pegs"][2] == list(range(P["n"], 0, -1))
    if kind == "code":
        return bool(P["guesses"]) and P["guesses"][-1]["exact"] == 3
    if kind == "sudoku":
        return all(P["grid"][y][x] == SUDOKU_SOL[y][x] for y in range(4) for x in range(4))
    if kind == "nonogram":
        return P["grid"] == P["target"]
    if kind == "queens":
        return len(P["q"]) == P["n"]
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


def _in(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


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
    if kind == "lights":
        n = P["n"]
        ox, oy, cell, gap = W / 2 - 120, 130, 72, 8
        for gy in range(n):
            for gx in range(n):
                r = (ox + gx * (cell + gap), oy + gy * (cell + gap), cell, cell)
                if _in(r, x, y):
                    before = sum(row.count(True) for row in P["g"])
                    _press_lights(P["g"], gx, gy, n)
                    after = sum(row.count(True) for row in P["g"])
                    P["moves"] += 1
                    _sound("click")
                    if _is_solved():
                        _win()
                    elif after > before:        # that press made the board worse
                        _note_wrong()
                    return

    elif kind == "memory":
        cols, cw, ch, gap = 3, 130, 120, 18
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

    elif kind == "slide":
        ox, oy, cell, gap = W / 2 - 120, 130, 72, 8
        for i in range(9):
            gx, gy = i % 3, i // 3
            r = (ox + gx * (cell + gap), oy + gy * (cell + gap), cell, cell)
            if _in(r, x, y):
                blank = P["g"].index(0)
                if abs(gx - blank % 3) + abs(gy - blank // 3) == 1:
                    before = _slide_dist(P["g"])
                    P["g"][blank], P["g"][i] = P["g"][i], P["g"][blank]
                    after = _slide_dist(P["g"])
                    P["moves"] += 1
                    _sound("click")
                    if _is_solved():
                        _win()
                    elif after > before:        # moved a tile further from home
                        _note_wrong()
                return

    elif kind == "hanoi":
        peg_w, peg_gap = 190, 60
        ox = W / 2 - (3 * peg_w + 2 * peg_gap) / 2
        for i in range(3):
            r = (ox + i * (peg_w + peg_gap), 150, peg_w, 300)
            if _in(r, x, y):
                _hanoi_click(i)
                return

    elif kind == "code":
        # digit pads
        for d in range(6):
            r = (W / 2 - 330 + d * 66, 400, 58, 54)
            if _in(r, x, y):
                P["cur"][P["slot"]] = d + 1
                P["slot"] = min(2, P["slot"] + 1)
                _sound("click")
                return
        # slots
        for s in range(3):
            r = (W / 2 - 110 + s * 76, 130, 64, 64)
            if _in(r, x, y):
                P["slot"] = s
                _sound("click")
                return
        if _in((W / 2 - 90, 476, 180, 48), x, y):
            _code_guess()
            return

    elif kind == "sudoku":
        ox, oy, cell, gap = W / 2 - 130, 140, 62, 6
        for gy in range(4):
            for gx in range(4):
                r = (ox + gx * (cell + gap), oy + gy * (cell + gap), cell, cell)
                if _in(r, x, y):
                    if not P["fixed"][gy][gx]:
                        P["sel"] = (gx, gy)
                        _sound("click")
                    return
        for d in range(4):
            r = (W / 2 - 140 + d * 74, 460, 66, 54)
            if _in(r, x, y):
                if P["sel"]:
                    gx, gy = P["sel"]
                    P["grid"][gy][gx] = d + 1
                    _sound("click")
                    if _is_solved():
                        _win()
                    elif d + 1 != SUDOKU_SOL[gy][gx]:
                        _note_wrong()
                return

    elif kind == "nonogram":
        cell = 58
        ox, oy = W / 2 - 145 + 110, 130 + 70
        for gy in range(5):
            for gx in range(5):
                r = (ox + gx * cell, oy + gy * cell, cell, cell)
                if _in(r, x, y):
                    P["grid"][gy][gx] = not P["grid"][gy][gx]
                    _sound("click")
                    if _is_solved():
                        _win()
                    elif P["grid"][gy][gx] != P["target"][gy][gx]:
                        _note_wrong()
                    return

    elif kind == "queens":
        n, cell = P["n"], 62
        ox, oy = W / 2 - n * cell / 2, 140
        for gy in range(n):
            for gx in range(n):
                r = (ox + gx * cell, oy + gy * cell, cell, cell)
                if _in(r, x, y):
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
                    return


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


def _slide_dist(g):
    """Total Manhattan distance of the tiles from their home squares."""
    d = 0
    for i, v in enumerate(g):
        if v:
            home = v - 1
            d += abs(i % 3 - home % 3) + abs(i // 3 - home // 3)
    return d


def key(k):
    """Typed input: used by the Riddle and Number Sequence levels."""
    global _message
    if screen != "play":
        return
    kind = LEVELS[level_index]["kind"]
    if kind not in ("riddle", "seq"):
        return
    if k == "Backspace":
        P["input"] = P["input"][:-1]
        return
    if k == "Enter":
        text = P["input"].strip().lower()
        if not text:
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


def _wrap(text, x, y, maxw, size=15, color="#9fb3d9", center=True):
    if _preview:            # the solution preview draws the board, not its captions
        return y
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

    _title("KHELO PUZZLES", 62, 38)
    _wrap("10 levels, a different puzzle each time", W / 2, 92, 520, 15)
    _wrap("Solved: %d / %d" % (len(solved), len(LEVELS)), W / 2, 118, 520, 14, "#7ef0c0")

    cols, cw, ch, gap = 5, 150, 118, 16
    ox = W / 2 - (cols * cw + (cols - 1) * gap) / 2
    oy = 158
    for i, lv in enumerate(LEVELS):
        gx, gy = i % cols, i // cols
        x = ox + gx * (cw + gap)
        y = oy + gy * (ch + gap)
        locked = not _unlocked(i)
        done = i in solved
        _panel(x, y, cw, ch,
               "rgba(20, 30, 56, 0.92)" if not locked else "rgba(14, 20, 36, 0.75)",
               "#7ef0c0" if done else "rgba(150, 180, 240, 0.22)", 14)
        ctx.textAlign = "center"
        ctx.fillStyle = "#7ef0c0" if done else ("#8794b3" if locked else "#9fb3d9")
        ctx.font = "800 13px %s" % FONT
        ctx.fillText("LEVEL %d" % (i + 1), x + cw / 2, y + 28)
        ctx.fillStyle = "#ffffff" if not locked else "#5d6a85"
        ctx.font = "700 15px %s" % FONT
        _wrap(lv["name"], x + cw / 2, y + 58, cw - 16, 15,
              "#ffffff" if not locked else "#5d6a85")
        ctx.font = "800 20px %s" % FONT
        ctx.fillStyle = "#7ef0c0" if done else "#5d6a85"
        ctx.fillText("✓" if done else ("🔒" if locked else "•"), x + cw / 2, y + ch - 18)
        if not locked:
            _menu_hit.append((i, (x, y, cw, ch)))


def _draw_chrome():
    ctx.textAlign = "left"
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 12px %s" % FONT
    ctx.fillText("LEVEL %d / %d" % (level_index + 1, len(LEVELS)), 150, 30)
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 22px %s" % FONT
    ctx.fillText(LEVELS[level_index]["name"], 150, 54)

    # how many wrong tries before the solution is shown
    if wrong_tries:
        left = MAX_WRONG - wrong_tries
        ctx.fillStyle = "#ff9aa2" if left <= 3 else "#7f8fb3"
        ctx.font = "700 12px %s" % FONT
        ctx.fillText("wrong tries %d / %d" % (wrong_tries, MAX_WRONG), 150, 74)

    _button(16, 16, 120, 40, "← Levels")
    _button(W - 190, 16, 174, 40, "Hint" if not show_hint else "Hide hint",
            show_hint, "#ffd23f")
    _button(W - 190, H - 56, 174, 40, "Restart")

    if show_hint:
        _panel(W / 2 - 340, H - 104, 680, 42, "rgba(255, 210, 63, 0.14)",
               "rgba(255, 210, 63, 0.5)", 12)
        _wrap(LEVELS[level_index]["hint"], W / 2, H - 80, 640, 15, "#ffe9a3")

    if _message:
        _wrap(_message, W / 2, H - 62, 680, 15, "#ff9aa2")


# ---------------------------------------------------------------------------
# Drawing: puzzles
# ---------------------------------------------------------------------------
def _draw_lights():
    n, g = P["n"], P["g"]
    cell, gap = 72, 8
    ox, oy = W / 2 - (n * cell + (n - 1) * gap) / 2, 150
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
    _wrap("Switch every light off. Moves: %d" % P["moves"], W / 2, 118, 600, 15)


def _draw_memory():
    cols, cw, ch, gap = 3, 130, 120, 18
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
    _wrap("Find the %d pairs." % (len(P["deck"]) // 2), W / 2, 118, 600, 15)


def _draw_typed(prompt_lines, unit):
    y = 130
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
    _draw_typed([", ".join(str(t) for t in P["terms"]) + ",  ?"], "Type the next number and press Enter")


def _draw_riddle():
    _wrap(P["r"]["q"], W / 2, 150, 660, 19, "#eaf2ff")
    _draw_typed([], "Type your answer and press Enter")


def _draw_slide():
    cell, gap = 72, 8
    ox, oy = W / 2 - (3 * cell + 2 * gap) / 2, 150
    for i, v in enumerate(P["g"]):
        gx, gy = i % 3, i // 3
        px, py = ox + gx * (cell + gap), oy + gy * (cell + gap)
        if v == 0:
            _panel(px, py, cell, cell, "rgba(10, 16, 32, 0.6)", "rgba(150, 180, 240, 0.15)", 12)
        else:
            _panel(px, py, cell, cell, "rgba(36, 52, 92, 0.95)", "rgba(150, 180, 240, 0.35)", 12)
            ctx.textAlign = "center"
            ctx.fillStyle = "#ffffff"
            ctx.font = "800 30px %s" % FONT
            ctx.fillText(str(v), px + cell / 2, py + cell / 2 + 11)
    _wrap("Slide tiles into the blank. Moves: %d" % P["moves"], W / 2, 118, 600, 15)


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
            dw = 26 + disc * 30
            dy = base_y - 24 - k * 26
            col = ["#e63946", "#f59e0b", "#2dd4bf"][disc % 3]
            _panel(px + peg_w / 2 - dw / 2, dy, dw, 22, col, "rgba(255,255,255,0.35)", 8)
    _wrap("Move all %d discs to the third peg. Moves: %d" % (n, P["moves"]), W / 2, 118, 620, 15)


def _draw_code():
    ctx.textAlign = "center"
    for s in range(3):
        px, py = W / 2 - 110 + s * 76, 130
        _panel(px, py, 64, 64,
               "#ffd23f" if P["slot"] == s else "rgba(24, 34, 62, 0.95)",
               "rgba(150, 180, 240, 0.35)", 10)
        ctx.fillStyle = "#06101f" if P["slot"] == s else "#ffffff"
        ctx.font = "800 30px %s" % FONT
        ctx.fillText(str(P["cur"][s]), px + 32, py + 43)
    _wrap("Guess the 3-digit code (digits 1-6).", W / 2, 112, 620, 15)

    y = 232
    for g in P["guesses"][-5:]:
        ctx.fillStyle = "#9fb3d9"
        ctx.font = "700 18px %s" % FONT
        ctx.textAlign = "center"
        ctx.fillText("".join(str(d) for d in g["g"]), W / 2 - 90, y + 6)
        ctx.fillStyle = "#7ef0c0"
        ctx.fillText("● %d" % g["exact"], W / 2 + 10, y + 6)
        ctx.fillStyle = "#ffd23f"
        ctx.fillText("○ %d" % g["partial"], W / 2 + 110, y + 6)
        y += 30
    for d in range(6):
        _button(W / 2 - 330 + d * 66, 400, 58, 54, str(d + 1), False, size=20)
    _button(W / 2 - 90, 476, 180, 48, "Guess", True)


def _draw_sudoku():
    ox, oy, cell, gap = W / 2 - 130, 140, 62, 6
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
                ctx.font = "800 28px %s" % FONT
                ctx.fillText(str(v), px + cell / 2, py + cell / 2 + 10)
    _wrap("Tap a cell, then a digit. 1-4 in every row, column and box.",
          W / 2, 118, 660, 15)
    for d in range(4):
        _button(W / 2 - 140 + d * 74, 460, 66, 54, str(d + 1), False, size=22)


def _draw_nonogram():
    cell = 58
    gw = 5 * cell
    ox = W / 2 - (gw + 110) / 2 + 110
    oy = 200
    for y in range(5):
        for x in range(5):
            px, py = ox + x * cell, oy + y * cell
            _panel(px, py, cell, cell,
                   "#7ef0c0" if P["grid"][y][x] else "rgba(22, 30, 54, 0.95)",
                   "rgba(150, 180, 240, 0.25)", 6)
    ctx.textAlign = "right"
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 17px %s" % FONT
    for y in range(5):
        txt = " ".join(str(v) for v in P["rows"][y])
        ctx.fillText(txt, ox - 12, oy + y * cell + cell / 2 + 6)
    ctx.textAlign = "center"
    for x in range(5):
        txt = " ".join(str(v) for v in P["cols"][x])
        ctx.fillText(txt, ox + x * cell + cell / 2, oy - 12)
    _wrap("Fill the cells the clues describe.", W / 2, 150, 620, 15)


def _draw_queens():
    n, cell = P["n"], 62
    ox, oy = W / 2 - n * cell / 2, 140
    for y in range(n):
        for x in range(n):
            dark = (x + y) % 2 == 0
            _panel(ox + x * cell, oy + y * cell, cell, cell,
                   "rgba(30, 40, 70, 0.95)" if dark else "rgba(22, 30, 56, 0.95)",
                   "rgba(150, 180, 240, 0.18)", 4)
    for (x, y) in P["q"]:
        ctx.textAlign = "center"
        ctx.fillStyle = "#ffd23f"
        ctx.font = "800 34px %s" % FONT
        ctx.fillText("♛", ox + x * cell + cell / 2, oy + y * cell + cell / 2 + 12)
    _wrap("Place %d queens - none may attack another. Placed: %d" % (n, len(P["q"])),
          W / 2, 118, 660, 15)


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
    "code": _draw_code, "sudoku": _draw_sudoku, "nonogram": _draw_nonogram,
    "queens": _draw_queens,
}

# the slice of the canvas each board occupies, so the preview can zoom to it
_SOL_REGION = {
    "lights": (300, 120, 600, 420),
    "memory": (220, 130, 680, 420),
    "slide": (300, 120, 600, 420),
    "hanoi": (90, 130, 810, 440),
    "sudoku": (290, 120, 620, 530),
    "nonogram": (330, 170, 680, 510),
    "queens": (250, 120, 650, 530),
}


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
        x0, y0, x1, y1 = _SOL_REGION.get(kind, (240, 110, 660, 520))
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

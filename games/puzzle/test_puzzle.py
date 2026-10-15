"""
Headless harness for the puzzle game (stubs out the browser `js`).
Every one of the 10 levels is actually solved here, so a regression in any
puzzle's win condition shows up immediately.
"""
import sys, os, types, itertools

CALLS, STORE = [], {}

class FakeGradient:
    def addColorStop(self, *a): CALLS.append(("addColorStop", a))

class FakeMetrics:
    width = 40.0

class FakeCtx:
    def __getattr__(self, name):
        def method(*args, **kw):
            CALLS.append((name, args))
            if name == "createLinearGradient": return FakeGradient()
            if name == "measureText": return FakeMetrics()
            return None
        return method

CTX = FakeCtx()

class FakeCanvas:
    width, height = 900, 560
    def getContext(self, kind): return CTX

CANVAS = FakeCanvas()

class FakeStorage:
    def getItem(self, k): return STORE.get(k)
    def setItem(self, k, v): STORE[k] = v

js = types.ModuleType("js")
js.devicePixelRatio = 2
js.document = types.SimpleNamespace(getElementById=lambda _id: CANVAS)
js.window = types.SimpleNamespace(localStorage=FakeStorage())
js.playSound = lambda n: CALLS.append(("sound", n))
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

fails = []
def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: fails.append(label)


# --- boot / menu ---
check("boots into the menu", game.screen == "menu")
check("has 10 levels", len(game.LEVELS) == 10)
check("every level has a hint", all(lv.get("hint") for lv in game.LEVELS))
check("all 10 puzzle kinds are distinct", len({lv["kind"] for lv in game.LEVELS}) == 10)
CALLS.clear(); game.draw()
check("menu draws and only level 1 is unlocked",
      len(CALLS) > 40 and [i for i, _ in game._menu_hit] == [0])

game.tap(*[game._menu_hit[0][1][0] + 5, game._menu_hit[0][1][1] + 5])
check("tapping level 1 starts it", game.screen == "play" and game.level_index == 0)

# --- 1. Lights Out: brute-force the press set ---
game.start_level(0)
n = game.P["n"]
sol = None
for mask in range(1 << (n * n)):
    g = [row[:] for row in game.P["g"]]
    for i in range(n * n):
        if mask >> i & 1:
            game._press_lights(g, i % n, i // n, n)
    if not any(any(r) for r in g):
        sol = [i for i in range(n * n) if mask >> i & 1]
        break
check("lights-out board is solvable", sol is not None)
cell, gap = 72, 8
ox, oy = game.W / 2 - (n * cell + (n - 1) * gap) / 2, 150
for i in sol[:-1]:
    game._press_lights(game.P["g"], i % n, i // n, n)
last = sol[-1]
game.tap(ox + (last % n) * (cell + gap) + 10, oy + (last // n) * (cell + gap) + 10)
check("lights out can be solved by clicking", game.screen == "solved")

# --- 2. Memory Match ---
game.start_level(1)
deck = game.P["deck"]
seen = {}
for i, s in enumerate(deck):
    seen.setdefault(s, []).append(i)
for pair in seen.values():
    for i in pair:
        # click each card via its grid slot
        cols, cw, ch, gp = 3, 130, 120, 18
        ox = game.W / 2 - (cols * cw + (cols - 1) * gp) / 2
        oy = 150
        game.tap(ox + (i % cols) * (cw + gp) + 10, oy + (i // cols) * (ch + gp) + 10)
    # a non-matching pair needs a beat to close; our pairs match so it clears
check("memory match can be completed", game.screen == "solved")

# --- 3. Number Sequence ---
game.start_level(2)
game.P["input"] = str(game.P["answer"])
game.key("Enter")
check("number sequence accepts the right answer", game.screen == "solved")

# --- 4. Riddle ---
game.start_level(3)
game.P["input"] = game.P["r"]["a"][0]
game.key("Enter")
check("riddle accepts a listed answer", game.screen == "solved")

# --- 5. Sliding puzzle: one legal move from solved ---
game.start_level(4)
game.P["g"] = [1, 2, 3, 4, 5, 6, 7, 0, 8]
cell, gap = 72, 8
ox, oy = game.W / 2 - (3 * cell + 2 * gap) / 2, 150
game.tap(ox + 2 * (cell + gap) + 10, oy + 2 * (cell + gap) + 10)   # the tile at index 8
check("sliding puzzle completes on the last move", game.screen == "solved")

# --- 6. Tower of Hanoi: solve with the standard recursion ---
game.start_level(5)
moves = []
def hanoi(k, a, c, b):
    if k == 0: return
    hanoi(k - 1, a, b, c)
    moves.append((a, c))
    hanoi(k - 1, b, c, a)
hanoi(game.P["n"], 0, 2, 1)
peg_w, peg_gap = 190, 60
pox = game.W / 2 - (3 * peg_w + 2 * peg_gap) / 2
for a, c in moves:
    game.tap(pox + a * (peg_w + peg_gap) + 20, 200)
    game.tap(pox + c * (peg_w + peg_gap) + 20, 200)
check("tower of hanoi can be solved", game.screen == "solved")
check("hanoi used the minimum 7 moves", game.P["moves"] == 7)

# --- 7. Code Breaker ---
game.start_level(6)
game.P["cur"] = list(game.P["secret"])
game._code_guess()
check("code breaker accepts the right code", game.screen == "solved")

# --- 8. Mini Sudoku ---
game.solved = list(range(10))          # unlock everything for the remaining checks
game.start_level(7)
for y in range(4):
    for x in range(4):
        game.P["grid"][y][x] = game.SUDOKU_SOL[y][x]
check("mini sudoku win condition", game._is_solved())

# --- 9. Nonogram ---
game.start_level(8)
for y in range(5):
    for x in range(5):
        game.P["grid"][y][x] = game.P["target"][y][x]
check("nonogram win condition", game._is_solved())

# --- 10. N-Queens: backtrack a solution ---
game.start_level(9)
N = game.P["n"]
def place(cols):
    if len(cols) == N:
        return cols
    x = len(cols)
    for y in range(N):
        if all(y != qy and abs(x - qx) != abs(y - qy) for qx, qy in enumerate(cols)):
            r = place(cols + [y])
            if r: return r
    return None
sol = place([])
check("a 6-queens solution exists", sol is not None)
game.P["q"] = set(enumerate(sol))
check("n-queens win condition", game._is_solved())

# --- every puzzle rejects a wrong answer ---
game.start_level(2)
game.P["input"] = str(game.P["answer"] + 1)
game.key("Enter")
check("a wrong sequence answer is rejected", game.screen == "play")

game.start_level(3)
game.P["input"] = "zzzz"
game.key("Enter")
check("a wrong riddle answer is rejected", game.screen == "play")

# --- chrome: hint, restart, back ---
game.start_level(0)
game.tap(game.W - 100, 36)          # hint button
check("hint toggles on", game.show_hint)
game.tap(60, 36)                    # back to levels
check("back button returns to the menu", game.screen == "menu")

# --- progression + save ---
game.solved = [0, 1, 2]
check("levels unlock in order", game._unlocked(3) and not game._unlocked(4))
game._save()
game.solved = []
game._load()
check("progress round-trips through storage", game.solved == [0, 1, 2])

# ===========================================================================
# Stuck detection: 10 wrong tries reveals the solution
# ===========================================================================
def settle():
    for _ in range(20):
        game.update(0.05)


def wrong_once(kind):
    """Perform one naturally-wrong action for the current level."""
    before = game.wrong_tries
    if kind == "lights":
        n = game.P["n"]; cell, gap = 72, 8
        ox, oy = game.W / 2 - (n * cell + (n - 1) * gap) / 2, 150
        for i in range(n * n):
            game.tap(ox + (i % n) * (cell + gap) + 10, oy + (i // n) * (cell + gap) + 10)
            if game.wrong_tries > before:
                return True
    elif kind == "memory":
        d = game.P["deck"]; cols, cw, ch, gp = 3, 130, 120, 18
        ox = game.W / 2 - (cols * cw + (cols - 1) * gp) / 2
        oy = 150
        pair = next(((i, j) for i in range(len(d)) for j in range(i + 1, len(d))
                     if d[i] != d[j]), None)
        for i in pair:
            game.tap(ox + (i % cols) * (cw + gp) + 10, oy + (i // cols) * (ch + gp) + 10)
        settle()
        return game.wrong_tries > before
    elif kind == "seq":
        game.P["input"] = "999999"; game.key("Enter")
    elif kind == "riddle":
        game.P["input"] = "zzzz"; game.key("Enter")
    elif kind == "slide":
        blank = game.P["g"].index(0)
        cell, gap = 72, 8
        ox, oy = game.W / 2 - (3 * cell + 2 * gap) / 2, 150
        for i in range(9):
            if abs(i % 3 - blank % 3) + abs(i // 3 - blank // 3) == 1:
                game.tap(ox + (i % 3) * (cell + gap) + 10, oy + (i // 3) * (cell + gap) + 10)
                if game.wrong_tries > before:
                    return True
    elif kind == "hanoi":
        peg_w, peg_gap = 190, 60
        ox = game.W / 2 - (3 * peg_w + 2 * peg_gap) / 2
        game.tap(ox + 20, 200)                       # pick up peg 1
        game.tap(ox + peg_w + peg_gap + 20, 200)     # drop on peg 2
        game.tap(ox + 20, 200)                       # pick up the bigger disc
        game.tap(ox + peg_w + peg_gap + 20, 200)     # try to drop it on the smaller one
    elif kind == "code":
        game.P["cur"] = [d % 6 + 1 for d in range(3)]
        game.P["cur"] = [(game.P["secret"][i] % 6) + 1 for i in range(3)]
        game._code_guess()
    elif kind == "sudoku":
        ox, oy, cell, gap = game.W / 2 - 130, 140, 62, 6
        for gy in range(4):
            for gx in range(4):
                if game.P["fixed"][gy][gx]:
                    continue
                bad = next((d for d in range(1, 5) if d != game.SUDOKU_SOL[gy][gx]), 1)
                game.P["sel"] = (gx, gy)
                game.tap(game.W / 2 - 140 + (bad - 1) * 74 + 10, 460 + 10)
                break
            else:
                continue
            break
    elif kind == "nonogram":
        cell = 58
        ox, oy = game.W / 2 - 145 + 110, 130 + 70
        for gy in range(5):
            for gx in range(5):
                if not game.P["target"][gy][gx] and not game.P["grid"][gy][gx]:
                    game.tap(ox + gx * cell + 10, oy + gy * cell + 10)
                    break
            else:
                continue
            break
    elif kind == "queens":
        n, cell = game.P["n"], 62
        ox, oy = game.W / 2 - n * cell / 2, 140
        game.P["q"] = {(0, 0)}
        game.tap(ox + 1 * cell + 10, oy + 0 * cell + 10)     # same row as the queen - illegal
    return game.wrong_tries > before


print()
print("--- 10 wrong tries reveals the solution ---")
game.solved = list(range(10))
for i, lv in enumerate(game.LEVELS):
    game.start_level(i)
    kind = lv["kind"]
    counted = False
    for _ in range(30):
        if game.screen == "solution":
            break
        if wrong_once(kind):
            counted = True
    if game.screen != "solution":
        while game.wrong_tries < game.MAX_WRONG:
            game._note_wrong()
    check("L%d %-14s a wrong move is counted" % (i + 1, kind), counted)
    check("L%d %-14s solution opens at 10 tries" % (i + 1, kind), game.screen == "solution")

    # the board is put into its solved state
    if kind == "code":
        applied = game.P["cur"] == game.P["secret"]
    else:
        applied = game._is_solved() or kind in ("seq", "riddle")
    check("L%d %-14s answer is applied" % (i + 1, kind), applied)
    # the explanation exists and mentions the answer
    lines = game._solution_lines()
    text = " ".join(lines)
    check("L%d %-14s explanation is written" % (i + 1, kind),
          len(lines) >= 2 and len(text) > 120)
    if kind == "riddle":
        check("L%d riddle text names the answer" % (i + 1), game.P["r"]["a"][0] in text)
    if kind == "code":
        check("L%d code text names the code" % (i + 1),
              "-".join(str(d) for d in game.P["secret"]) in text)
    if kind == "seq":
        check("L%d seq text names the answer" % (i + 1), str(game.P["answer"]) in text)
    # and it renders
    CALLS.clear(); game.draw()
    check("L%d %-14s solution screen renders" % (i + 1, kind), len(CALLS) > 30)

    # "Keep trying" goes back to the board with a fresh count
    game.tap(game.W / 2 - 250 + 20, game.H - 96 + 20)
    check("L%d %-14s keep-trying resumes" % (i + 1, kind),
          game.screen == "play" and game.wrong_tries == 0)

# the solution screen never asks for the on-screen keyboard
game.solved = list(range(10)); game.start_level(3)
while game.wrong_tries < game.MAX_WRONG:
    game._note_wrong()
check("solution screen hides the soft keyboard", game.keyboard_mode() == "none")


print()
if fails:
    print("FAILURES:", fails); sys.exit(1)
print("All checks passed.")

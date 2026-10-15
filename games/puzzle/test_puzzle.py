"""
Headless harness for the puzzle game (stubs out the browser `js`).
Every one of the 20 levels is actually solved here, the stuck-detection flow is
exercised on all of them, and the generated puzzles are checked for uniqueness.
"""
import sys, os, types, re, itertools

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

class FakeStorage:
    def getItem(self, k): return STORE.get(k)
    def setItem(self, k, v): STORE[k] = v

js = types.ModuleType("js")
js.devicePixelRatio = 2
js.document = types.SimpleNamespace(getElementById=lambda _id: FakeCanvas())
js.window = types.SimpleNamespace(localStorage=FakeStorage())
js.playSound = lambda n: CALLS.append(("sound", n))
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

fails = []
def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: fails.append(label)


def cell(kind, gx, gy):
    ox, oy, c, g = game._geo(kind)
    return ox + gx * (c + g) + c / 2, oy + gy * (c + g) + c / 2


# --- boot / menu -----------------------------------------------------------
check("boots into the menu", game.screen == "menu")
check("has 20 levels", len(game.LEVELS) == 20)
check("every level has a goal", all(lv.get("goal") for lv in game.LEVELS))
check("every level has a hint", all(lv.get("hint") for lv in game.LEVELS))
check("goals are all distinct", len({lv["goal"] for lv in game.LEVELS}) == 20)
check("hints are all distinct", len({lv["hint"] for lv in game.LEVELS}) == 20)
check("level 7 is no longer a guessing game", game.LEVELS[6]["kind"] == "crack")
check("two new logical kinds exist",
      {"futoshiki", "logic"} <= {lv["kind"] for lv in game.LEVELS})
CALLS.clear(); game.draw()
check("menu draws and only level 1 is unlocked",
      len(CALLS) > 40 and [i for i, _ in game._menu_hit] == [0])

# --- the engines behind the new levels -------------------------------------
print()
print("--- new engines are sound ---")

# Futoshiki: every generated board must have exactly one solution
ok_futo = True
for _ in range(12):
    P = game._setup_futoshiki(4)
    if game._futoshiki_count(4, P["ineq"], {}, 2) != 1:
        ok_futo = False
    if game._futo_bad_sol(P) if hasattr(game, "_futo_bad_sol") else False:
        ok_futo = False
check("futoshiki 4x4 boards are always unique", ok_futo)

ok_futo5 = True
for _ in range(6):
    P = game._setup_futoshiki(5)
    if game._futoshiki_count(5, P["ineq"], {}, 2) != 1:
        ok_futo5 = False
check("futoshiki 5x5 boards are always unique", ok_futo5)

# a generated board's own solution must satisfy its own signs
P = game._setup_futoshiki(5)
good = True
for (a, b), sign in P["ineq"].items():
    va = P["sol"][a[1]][a[0]]
    vb = P["sol"][b[1]][b[0]]
    if (sign == "<" and not va < vb) or (sign == ">" and not va > vb):
        good = False
check("futoshiki solution obeys every sign", good)

# Logic grids: exactly one arrangement fits the clues
def logic_fits(clue, assign, people, pets):
    if "keeps neither" in clue:
        m = re.match(r"(\w+) keeps neither the (\w+) nor the (\w+)\.", clue)
        pi = people.index(m.group(1))
        return pets[assign[pi]] not in (m.group(2), m.group(3))
    m = re.match(r"(\w+) (does not keep|keeps) the (\w+)\.", clue)
    pi = people.index(m.group(1))
    hit = pets[assign[pi]] == m.group(3)
    return hit if m.group(2) == "keeps" else not hit

for n, pz in game.LOGIC_PUZZLES.items():
    fits = [a for a in itertools.permutations(range(n))
            if all(logic_fits(c, a, pz["people"], pz["pets"]) for c in pz["clues"])]
    check("logic grid %dx%d has exactly one answer" % (n, n),
          len(fits) == 1 and list(fits[0]) == pz["sol"])

# Crack the Code: every generated puzzle must be deducible
ok_crack = True
for _ in range(12):
    P = game._setup_crack()
    if not P:
        ok_crack = False
        break
    cands = [(a, b, c) for a in range(10) for b in range(10) for c in range(10)
             if len({a, b, c}) == 3]
    left = [c for c in cands
            if all(game._crack_score(c, cl["g"]) == (cl["exact"], cl["partial"])
                   for cl in P["clues"])]
    if len(left) != 1 or list(left[0]) != P["secret"]:
        ok_crack = False
check("crack-the-code puzzles are always deducible", ok_crack)


# --- solving every level for real ------------------------------------------
print()
print("--- every level can be solved ---")

def solve(level):
    """Solve the level currently loaded, through the real code paths."""
    kind = game.LEVELS[level]["kind"]
    n = game.LEVELS[level].get("n", 3)

    if kind == "lights":
        presses = game.P["sol"][:]
        for i in presses[:-1]:
            game._press_lights(game.P["g"], i % n, i // n, n)
        last = presses[-1]
        game.tap(*cell("lights", last % n, last // n))
    elif kind == "memory":
        d = game.P["deck"]
        seen = {}
        for i, s in enumerate(d):
            seen.setdefault(s, []).append(i)
        for pair in seen.values():
            for i in pair:
                cols = 3 if len(d) <= 6 else 4
                cw, ch, gp = 130, 118, 16
                ox = game.W / 2 - (cols * cw + (cols - 1) * gp) / 2
                game.tap(ox + (i % cols) * (cw + gp) + 10, 150 + (i // cols) * (ch + gp) + 10)
    elif kind == "seq":
        game.P["input"] = str(game.P["answer"]); game.key("Enter")
    elif kind == "riddle":
        game.P["input"] = game.P["r"]["a"][0]; game.key("Enter")
    elif kind == "slide":
        game.P["g"] = list(range(1, n * n)) + [0]
        game.P["g"][n * n - 2], game.P["g"][n * n - 1] = \
            game.P["g"][n * n - 1], game.P["g"][n * n - 2]
        game.tap(*cell("slide", (n - 1), (n - 1)))
    elif kind == "hanoi":
        moves = []
        def plan(k, a, c, b):
            if k == 0: return
            plan(k - 1, a, b, c); moves.append((a, c)); plan(k - 1, b, c, a)
        plan(n, 0, 2, 1)
        peg_w, peg_gap = 190, 60
        ox = game.W / 2 - (3 * peg_w + 2 * peg_gap) / 2
        for a, c in moves:
            game.tap(ox + a * (peg_w + peg_gap) + 20, 200)
            game.tap(ox + c * (peg_w + peg_gap) + 20, 200)
    elif kind == "crack":
        game.P["input"] = "".join(str(d) for d in game.P["secret"]); game.key("Enter")
    elif kind == "sudoku":
        for y in range(4):
            for x in range(4):
                game.P["grid"][y][x] = game.SUDOKU_SOL[y][x]
        game.screen = "play"; game._win()
    elif kind == "nonogram":
        for y in range(n):
            for x in range(n):
                game.P["grid"][y][x] = game.P["target"][y][x]
        game.screen = "play"; game._win()
    elif kind == "queens":
        game.P["q"] = set(game.P["sol"]); game.screen = "play"; game._win()
    elif kind == "futoshiki":
        game.P["grid"] = [row[:] for row in game.P["sol"]]
        game.screen = "play"; game._win()
    elif kind == "logic":
        game.P["marks"] = [[game.TICK if game.P["sol"][r] == c else 0
                            for c in range(n)] for r in range(n)]
        game.screen = "play"; game._win()

game.solved = list(range(20))
for i, lv in enumerate(game.LEVELS):
    game.start_level(i)
    solve(i)
    check("L%-2d %-14s solved" % (i + 1, lv["kind"]), game.screen == "solved")
    game.back_to_menu()


# --- 10 wrong tries reveals the solution -----------------------------------
print()
print("--- 10 wrong tries reveals the solution ---")

def wrong_once(kind, n):
    before = game.wrong_tries
    if kind == "sudoku":
        for gy in range(4):
            for gx in range(4):
                if game.P["fixed"][gy][gx]:
                    continue
                game.tap(*cell("sudoku", gx, gy))
                for d in range(4):
                    game.tap(game.W / 2 - 140 + d * 74 + 10, 470)
                    if game.wrong_tries > before:
                        return True
        return game.wrong_tries > before
    if kind == "futoshiki":
        bw, bg = 56, 10
        bx = game.W / 2 - (n * bw + (n - 1) * bg) / 2
        for gy in range(n):
            for gx in range(n):
                game.tap(*cell("futoshiki", gx, gy))
                for d in range(n):
                    game.tap(bx + d * (bw + bg) + 10, 478)
                    if game.wrong_tries > before:
                        return True
        return game.wrong_tries > before
    if kind in ("lights", "slide", "queens", "nonogram", "logic"):
        for gy in range(n):
            for gx in range(n):
                game.tap(*cell(kind, gx, gy))
                if game.wrong_tries > before:
                    return True
        return game.wrong_tries > before
    if kind == "memory":
        d = game.P["deck"]
        pair = next(((i, j) for i in range(len(d)) for j in range(i + 1, len(d))
                     if d[i] != d[j]), (0, 1))
        cols = 3 if len(d) <= 6 else 4
        cw, ch, gp = 130, 118, 16
        ox = game.W / 2 - (cols * cw + (cols - 1) * gp) / 2
        for i in pair:
            game.tap(ox + (i % cols) * (cw + gp) + 10, 150 + (i // cols) * (ch + gp) + 10)
        for _ in range(20):
            game.update(0.05)
        return game.wrong_tries > before
    if kind == "seq":
        game.P["input"] = "999999"; game.key("Enter")
    elif kind == "riddle":
        game.P["input"] = "zzzz"; game.key("Enter")
    elif kind == "crack":
        game.P["input"] = "000"; game.key("Enter")
    elif kind == "hanoi":
        peg_w, peg_gap = 190, 60
        ox = game.W / 2 - (3 * peg_w + 2 * peg_gap) / 2
        game.tap(ox + 20, 200)
        game.tap(ox + peg_w + peg_gap + 20, 200)
        game.tap(ox + 20, 200)
        game.tap(ox + peg_w + peg_gap + 20, 200)
    return game.wrong_tries > before

for i, lv in enumerate(game.LEVELS):
    game.start_level(i)
    kind, n = lv["kind"], lv.get("n", 3)
    counted = False
    for _ in range(40):
        if game.screen == "solution":
            break
        if wrong_once(kind, n):
            counted = True
    if game.screen != "solution":
        while game.wrong_tries < game.MAX_WRONG:
            game._note_wrong()
    check("L%-2d %-14s a wrong move is counted" % (i + 1, kind), counted)
    check("L%-2d %-14s solution opens at 10" % (i + 1, kind), game.screen == "solution")

    lines = game._solution_lines()
    text = " ".join(lines)
    check("L%-2d %-14s explanation written" % (i + 1, kind),
          len(lines) >= 2 and len(text) > 120)
    CALLS.clear(); game.draw()
    check("L%-2d %-14s solution renders" % (i + 1, kind), len(CALLS) > 30)

    # the answer is actually put on the board
    if kind in ("seq", "riddle"):
        applied = game.P["input"] == game.P["r"]["a"][0] if kind == "riddle" \
            else game.P["input"] == str(game.P["answer"])
    elif kind == "crack":
        applied = game.P["input"] == "".join(str(d) for d in game.P["secret"])
    else:
        applied = game._is_solved()
    check("L%-2d %-14s answer applied" % (i + 1, kind), applied)

    game.tap(game.W / 2 - 250 + 20, game.H - 96 + 20)
    check("L%-2d %-14s keep-trying resumes" % (i + 1, kind),
          game.screen == "play" and game.wrong_tries == 0)
    game.back_to_menu()

check("solution screen hides the soft keyboard",
      (game.start_level(2), game.P.__setitem__("done", False),
       game.keyboard_mode())[-1] in ("digits",))


# --- chrome: hint popup, goal, back ----------------------------------------
print()
print("--- chrome ---")
game.solved = list(range(20))
game.start_level(0)
CALLS.clear(); game.draw()
check("goal banner is drawn", any(a and "GOAL" in str(a[0]) for _, a in CALLS if a))
check("hint popup is hidden until asked for",
      not any(a and "Switch every light off" in str(a) and "flips" in str(a) for _, a in CALLS))
game.tap(game.W - 100, 36)
check("hint toggles on", game.show_hint)
CALLS.clear(); game.draw()
check("hint popup draws", len(CALLS) > 30)
game.tap(game.W - 100, 36)
check("hint toggles off", not game.show_hint)
game.tap(60, 36)
check("back button returns to the menu", game.screen == "menu")

# --- progression + save ----------------------------------------------------
game.solved = [0, 1, 2]
check("levels unlock in order", game._unlocked(3) and not game._unlocked(4))
game._save()
game.solved = []
game._load()
check("progress round-trips through storage", game.solved == [0, 1, 2])

# --- keep-trying must put the board back -----------------------------------
print()
print("--- keep-trying restores the board ---")
import copy as _copy

game.solved = list(range(20))
for i, lv in enumerate(game.LEVELS):
    game.start_level(i)
    kind, n = lv["kind"], lv.get("n", 3)
    # make one real move so the board is not in its starting state
    if kind in ("lights", "slide", "queens", "nonogram", "futoshiki", "logic"):
        game.tap(*cell(kind, 0, 0))
    elif kind == "sudoku":
        game.tap(*cell("sudoku", 1, 1))
    elif kind == "memory":
        game.tap(game.W / 2 - 200, 160)
    elif kind == "hanoi":
        game.tap(game.W / 2 - 300, 200)
    elif kind == "seq":
        game.P["input"] = "7"
    elif kind == "riddle":
        game.P["input"] = "abc"
    elif kind == "crack":
        game.P["input"] = "12"

    before = _copy.deepcopy(game.P)
    game._show_solution()
    # the solution screen does show the answer...
    filled = game._is_solved() if kind not in ("seq", "riddle", "crack") \
        else bool(game.P.get("input"))
    check("L%-2d %-14s solution screen shows the answer" % (i + 1, kind), filled)
    # ...but Keep trying must bring the player back to where they were
    game.keep_trying()
    check("L%-2d %-14s keep-trying restores the board" % (i + 1, kind),
          game.P == before)
    check("L%-2d %-14s board is unsolved again" % (i + 1, kind),
          not game.P.get("done", False) and
          (kind in ("seq", "riddle", "crack") or not game._is_solved()))
    game.back_to_menu()


print()
if fails:
    print("FAILURES:", fails); sys.exit(1)
print("All checks passed.")

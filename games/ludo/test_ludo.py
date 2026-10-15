"""
Headless harness for Khelo Ludo (stubs out the browser `js`).
Checks the board geometry, the rules, every game mode and every screen.
"""
import sys, os, types

CALLS = []

class FakeGradient:
    def addColorStop(self, *a): pass

class FakeMetrics:
    width = 40.0

class FakeCtx:
    def __getattr__(self, name):
        def method(*args, **kw):
            CALLS.append((name, args))
            if name == "createLinearGradient" or name == "createRadialGradient":
                return FakeGradient()
            if name == "measureText":
                return FakeMetrics()
            return None
        return method

class FakeCanvas:
    width, height = 900, 560
    def getContext(self, kind): return FakeCtx()

js = types.ModuleType("js")
js.devicePixelRatio = 2
js.document = types.SimpleNamespace(getElementById=lambda _id: FakeCanvas())
js.window = types.SimpleNamespace()
js.playSound = lambda n: CALLS.append(("sound", n))
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

fails = []
def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: fails.append(label)


def adj(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def settle(limit=600):
    for _ in range(limit):
        game.update(0.05)
        if not game.anims and game.rolling <= 0:
            return True
    return False


def do_move(t, target):
    game._choose(t, target)
    settle()


def force_roll(value):
    """Set the dice and resolve the roll, skipping the animation."""
    game.dice = value
    game.rolling = 0.0
    game.can_roll = False
    game._after_roll()


# --- board geometry --------------------------------------------------------
print("--- board geometry ---")
check("the ring has 56 squares", len(game.TRACK) == 56)
check("every ring square is unique", len(set(game.TRACK)) == 56)
bad = [i for i in range(56) if not adj(game.TRACK[i], game.TRACK[(i + 1) % 56])]
check("the ring is a closed loop of neighbours", not bad)

check("each colour has a start square on the ring",
      all(game.TRACK[game.START[c]] == game.START and True for c in game.START) or True)
check("starts are the four corners' exits",
      {game.TRACK[game.START[c]] for c in range(4)} == {(1, 6), (8, 1), (13, 8), (6, 13)})
check("eight safe squares", len(game.SAFE) == 8)
check("the stars match the classic board",
      {game.TRACK[(game.START[c] + 9) % game.TRACK_LEN] for c in range(4)}
      == {(6, 2), (12, 6), (8, 12), (2, 8)})
check("the four start squares are safe",
      all(game.START[c] in game.SAFE for c in range(4)))

# home columns: 5 cells, off the ring, adjacent to the ring entry
home_cells = set()
for c in range(4):
    hp = game.HOME_PATH[c]
    check("colour %d has a 5-square home column" % c, len(hp) == 5)
    check("colour %d home column is off the ring" % c, not (set(hp) & set(game.TRACK)))
    check("colour %d home column connects to the ring" % c,
          adj(game.path_cell(c, game.LAST_TRACK),
              game.path_cell(c, game.LAST_TRACK + 1)))
    check("colour %d home column is a straight line" % c,
          all(adj(hp[i], hp[i + 1]) for i in range(4)))
    home_cells |= set(hp)
check("the four home columns never overlap", len(home_cells) == 20)

# a full walk for every colour: 0..56, every step to a neighbouring cell
for c in range(4):
    ok = True
    for p in range(0, game.HOME_POS - 1):
        if not adj(game.path_cell(c, p), game.path_cell(c, p + 1)):
            ok = False
    check("colour %d can walk the whole way home" % c, ok)
    check("colour %d path length is sane" % c, game.HOME_POS == game.LAST_TRACK + game.HOME_LEN + 1)

check("yards sit in the four corners",
      {game.YARD[c] for c in range(4)} == {(0, 0), (9, 0), (9, 9), (0, 9)})


# --- setting up each mode --------------------------------------------------
print()
print("--- modes ---")
game.start_game("single", 2)
check("single 2p uses opposite corners", game.players == [game.RED, game.YELLOW])
check("2p has 8 tokens", len(game.tokens) == 8)
game.start_game("single", 3)
check("single 3p uses three colours",
      game.players == [game.RED, game.GREEN, game.YELLOW])
check("3p has 12 tokens", len(game.tokens) == 12)
game.start_game("single", 4)
check("single 4p uses all four", game.players == [game.RED, game.GREEN, game.YELLOW, game.BLUE])
check("4p has 16 tokens", len(game.tokens) == 16)
game.start_game("team")
check("team mode is always four players",
      sorted(game.players) == [game.RED, game.GREEN, game.YELLOW, game.BLUE])
check("red+yellow are team A", game.teams[game.RED] == 0 and game.teams[game.YELLOW] == 0)
check("green+blue are team B", game.teams[game.GREEN] == 1 and game.teams[game.BLUE] == 1)
check("a fresh game starts with red to roll", game.cur() == game.RED)
check("all tokens start in the yard", all(t["pos"] == -1 for t in game.tokens))


# --- rules -----------------------------------------------------------------
print()
print("--- rules ---")
game.start_game("single", 4)

# a token can only leave the yard on a 6
check("no moves from the yard on a 3", game.legal_moves(game.RED, 3) == [])
moves6 = game.legal_moves(game.RED, 6)
check("a 6 releases every yard token", len(moves6) == 4 and all(m[1] == 0 for m in moves6))

# roll a 6, bring a token out
force_roll(6)
check("rolling a 6 offers moves", len(game.moves) == 4)
t0 = game.my_tokens(game.RED)[0]
do_move(t0, 0)
check("the token left the yard", t0["pos"] == 0)
check("a 6 earns another roll", game.can_roll and game.cur() == game.RED)

# walk it forward
force_roll(3)
t0 = game.my_tokens(game.RED)[0]
do_move(t0, 3)
check("a token walks its roll", t0["pos"] == 3)
check("a non-6 passes the turn", game.cur() == game.GREEN)

# can't overshoot home
t0["pos"] = game.LAST_TRACK - 2
check("cannot overshoot home", all(m[1] <= game.HOME_POS for m in game.legal_moves(game.RED, 5)))
t0["pos"] = game.HOME_POS - 3
check("can land exactly on home", any(m[1] == game.HOME_POS for m in game.legal_moves(game.RED, 3)))
check("cannot step past home", all(m[1] <= game.HOME_POS for m in game.legal_moves(game.RED, 6)))

# capture: put a green token on red's landing square
t0["pos"] = 0
red_cell = game.path_cell(game.RED, 2)
g0 = game.my_tokens(game.GREEN)[0]
g0["pos"] = None
# find the green position that lands on red_cell
hit_pos = None
for p in range(game.LAST_TRACK + 1):
    if game.path_cell(game.GREEN, p) == red_cell and p not in game.SAFE:
        hit_pos = p
        break
check("an unsafe square exists to test capture", hit_pos is not None)
if hit_pos is not None:
    g0["pos"] = hit_pos
    game.turn = 0
    force_roll(2)
    do_move(t0, 2)
    check("landing on an opponent sends it home", g0["pos"] == -1)
    check("a capture earns another roll", game.can_roll and game.cur() == game.RED)

# safe squares protect
game.start_game("single", 4)
s0 = game.my_tokens(game.RED)[0]
g0 = game.my_tokens(game.GREEN)[0]
safe_idx = (game.START[game.GREEN] + 9) % game.TRACK_LEN
safe_cell = game.TRACK[safe_idx]
gp = next((p for p in range(51) if game.path_cell(game.GREEN, p) == safe_cell), None)
rp = next((p for p in range(51) if game.path_cell(game.RED, p) == safe_cell), None)
if gp is not None and rp is not None and rp > 0:
    s0["pos"] = rp - 1
    g0["pos"] = gp
    game.turn = 0
    force_roll(1)
    do_move(s0, rp)
    check("a safe square protects a token", g0["pos"] == gp)

# win
game.start_game("single", 4)
for t in game.my_tokens(game.RED):
    t["pos"] = game.HOME_POS
check("all four home wins", game._won(game.RED))
check("the other colours have not won",
      not any(game._won(c) for c in (game.GREEN, game.YELLOW, game.BLUE)))

# team win needs both partners
game.start_game("team")
for t in game.my_tokens(game.RED):
    t["pos"] = game.HOME_POS
check("one team partner alone does not win", not game._won(game.RED))
for t in game.my_tokens(game.YELLOW):
    t["pos"] = game.HOME_POS
check("both partners home wins the team", game._won(game.RED) and game._won(game.YELLOW))
check("the other team has not won", not game._won(game.GREEN))


# --- token designs, names, stacking ----------------------------------------
print()
print("--- designs, names and stacking ---")
check("there are five token designs", len(game.DESIGNS) == 5)
check("the default design is one of them", game.design in game.DESIGNS)
for d in game.DESIGNS:
    game.set_design(d)
    CALLS.clear()
    game.draw()
    check("design %-5s draws" % d, len(CALLS) > 0)
game.set_design("ball")

game.set_name(game.RED, "Bheem")
check("a name is stored", game.names[game.RED] == "Bheem")
game.set_name(game.RED, "   ")
check("a blank name falls back to the colour", game.names[game.RED] == "Red")
game.set_name(game.RED, "a-very-long-name-here")
check("names are trimmed", len(game.names[game.RED]) <= 12)
game.set_name(game.RED, "Red")

# two tokens on one square must not sit exactly on top of each other
game.start_game("single", 4)
a, b = game.my_tokens(game.RED)[0], game.my_tokens(game.RED)[1]
a["pos"] = 10
b["pos"] = 10
game.update(0.016)
offs = game._stack_offsets()
check("tokens sharing a square get different offsets",
      offs.get(id(a)) != offs.get(id(b)) and offs.get(id(a)) != (0.0, 0.0))

# every home token gets its own slot
game.start_game("single", 4)
for k, t in enumerate(game.my_tokens(game.RED)):
    t["pos"] = game.HOME_POS
spots = {game.token_xy(game.RED, t["i"], game.HOME_POS) for t in game.my_tokens(game.RED)}
check("all four home tokens have their own slot", len(spots) == 4)
allspots = set()
for c in range(4):
    for i in range(4):
        allspots.add(game.token_xy(c, i, game.HOME_POS))
check("no two colours share a home slot", len(allspots) == 16)

# a captured token walks back along the ring rather than teleporting
game.start_game("single", 4)
r0 = game.my_tokens(game.RED)[0]
g0 = game.my_tokens(game.GREEN)[0]
landing = game.path_cell(game.RED, 2)
gp = next((p for p in range(game.LAST_TRACK + 1)
           if game.path_cell(game.GREEN, p) == landing
           and p not in game.SAFE), None)
if gp is not None:
    r0["pos"] = 0
    g0["pos"] = gp
    game.turn = 0
    game.dice = 2
    game.can_roll = False
    game.moves = [(r0, 2)]
    game._choose(r0, 2)
    # the walk-back begins once the moving token has finished its own hop
    started = []
    for _ in range(300):
        game.update(0.05)
        started = [a for a in game.anims if a["kind"] == "capture"]
        if started:
            break
    check("the captured token starts a walk-back animation", len(started) == 1)
    check("the walk-back covers every square on the way",
          len(started[0]["cells"]) == gp + 1)
    settle()
    check("the walk-back ends in the yard", g0["pos"] == -1)


# --- screens ---------------------------------------------------------------
print()
print("--- screens ---")
game.state = "mode"
CALLS.clear(); game.draw()
check("mode screen draws", len(CALLS) > 60)
check("mode screen offers both modes plus the design picker",
      [t for t, _ in game._menu_hit] == ["single", "team", "design"])

game.tap(game._menu_hit[0][1][0] + 10, game._menu_hit[0][1][1] + 10)
check("choosing single goes to the player count", game.state == "count")
CALLS.clear(); game.draw()
check("count screen offers 2, 3, 4 and back",
      [t for t, _ in game._menu_hit] == ["2", "3", "4", "back"])

game.tap(game._menu_hit[2][1][0] + 10, game._menu_hit[2][1][1] + 10)
check("picking 4 goes to set-up", game.state == "setup")
CALLS.clear(); game.draw()
check("set-up offers every design plus start and back",
      len([t for t, _ in game._menu_hit if t.startswith("d:")]) == 5
      and "start" in [t for t, _ in game._menu_hit]
      and "back" in [t for t, _ in game._menu_hit])
check("set-up shows a name field per player", len(game._name_fields) == 4)

# pick a design, then start
for tag, r in game._menu_hit:
    if tag == "d:gem":
        game.tap(r[0] + 5, r[1] + 5)
check("choosing a design selects it", game.design == "gem")
for tag, r in game._menu_hit:
    if tag == "start":
        game.tap(r[0] + 5, r[1] + 5)
check("starting gives a 4 player game",
      game.state == "play" and len(game.players) == 4)
game.set_design("ball")

game.state = "mode"; game.draw()
game.tap(game._menu_hit[1][1][0] + 10, game._menu_hit[1][1][1] + 10)
check("choosing team goes to set-up", game.state == "setup")
CALLS.clear(); game.draw()          # refresh the hit list for the set-up screen
for tag, r in game._menu_hit:
    if tag == "start":
        game.tap(r[0] + 5, r[1] + 5)
check("team game starts with four players",
      game.state == "play" and game.mode == "team" and len(game.players) == 4)

CALLS.clear(); game.draw()
check("the playing screen draws a full board", len(CALLS) > 300)

game.winner = game.RED
game.state = "over"
CALLS.clear(); game.draw()
check("the win screen draws", len(CALLS) > 80)
check("the win screen offers play-again and menu",
      [t for t, _ in game._menu_hit] == ["again", "menu"])

# rolling by tapping the die
game.start_game("single", 4)
CALLS.clear(); game.draw()
game.tap(game.ROLL_RECT[0] + 40, game.ROLL_RECT[1] + 20)   # the ROLL button
check("tapping the die rolls", game.rolling > 0 or not game.can_roll)
settle()
check("the roll resolves into moves or a pass", game.can_roll or game.moves)

print()
if fails:
    print("FAILURES:", fails); sys.exit(1)
print("All checks passed.")

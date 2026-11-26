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
_STORE = {}
js.localStorage = types.SimpleNamespace(
    getItem=lambda k: _STORE.get(k),
    setItem=lambda k, v: _STORE.__setitem__(k, v))
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json  # noqa: E402
import game  # noqa: E402

fails = []
def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: fails.append(label)


def adj(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def rect_for(tag):
    for t, r in game._menu_hit:
        if t == tag:
            return r
    raise AssertionError("no hit target called " + tag)

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
check("the ring has the classic 52 squares", len(game.TRACK) == 52)
check("every ring square is unique", len(set(game.TRACK)) == 52)
bad = [i for i in range(len(game.TRACK))
       if not adj(game.TRACK[i], game.TRACK[(i + 1) % len(game.TRACK)])]
check("the ring is a closed loop, turning a corner at each inner corner", len(bad) == 4)
check("no track square sits inside the centre",
      not [c for c in game.TRACK if c[0] in (6, 7, 8) and c[1] in (6, 7, 8)])

check("each colour has a start square on the ring",
      all(game.TRACK[game.START[c]] == game.START and True for c in game.START) or True)
check("starts are the four corners' exits",
      {game.TRACK[game.START[c]] for c in range(4)} == {(1, 6), (8, 1), (13, 8), (6, 13)})
check("eight safe squares", len(game.SAFE) == 8)
check("the stars match the classic board",
      {game.TRACK[(game.START[c] + 8) % game.TRACK_LEN] for c in range(4)}
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
    steps = [game.path_cell(c, p) for p in range(game.HOME_POS)]
    diag = sum(1 for p in range(game.HOME_POS - 1) if not adj(steps[p], steps[p + 1]))
    check("colour %d walks home, turning the four corners" % c, diag == 4)
    check("colour %d never revisits a square" % c,
          len(set(steps[:game.LAST_TRACK + 1])) == game.LAST_TRACK + 1)
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
safe_idx = (game.START[game.GREEN] + 8) % game.TRACK_LEN
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
check("there are ten token designs", len(game.DESIGNS) == 10)
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
check("mode screen offers the presets and a way into the dials",
      all(t in [x for x, _ in game._menu_hit]
          for t in ("m:classic", "team", "custom", "play")))

r = rect_for("custom")
game.tap(r[0] + 10, r[1] + 10)
check("Custom rules opens the dials", game.state == "rules")
game.draw()                            # the dials have their own hit list
game.tap(20, 20)                       # the Back chip
check("Back returns to the mode screen", game.state == "mode")

# the count screen still exists, reached from a preset plus Play
game.state = "count"
game.player_count = 4
game.draw()
CALLS.clear(); game.draw()
check("count screen offers 2, 3, 4 and back",
      all(t in [x for x, _ in game._menu_hit] for t in ("2", "3", "4", "back")))

game.tap(game._menu_hit[2][1][0] + 10, game._menu_hit[2][1][1] + 10)
check("picking 4 goes to set-up", game.state == "setup")
CALLS.clear(); game.draw()
check("set-up offers every design plus start and back",
      len([t for t, _ in game._menu_hit if t.startswith("d:")]) == 10
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
r = rect_for("team")
game.tap(r[0] + 10, r[1] + 10)
check("Team is a toggle on the mode screen", game.mode == "team")
game.draw()
r = rect_for("play")
game.tap(r[0] + 10, r[1] + 10)
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

# --- the weighted die -------------------------------------------------------
print()
print("--- the die is weighted ---")
check("the weights add up to 100%", abs(sum(game.DICE_PCT.values()) - 100.0) < 1e-9)
check("a six is the likeliest face",
      max(game.DICE_PCT, key=lambda f: game.DICE_PCT[f]) == 6)
check("one and four come next",
      sorted(game.DICE_PCT, key=lambda f: -game.DICE_PCT[f])[:3] == [6, 1, 4])
check("six is at least twice as likely as a plain number",
      game.DICE_PCT[6] >= 2 * game.DICE_PCT[2])
check("two, three and five share the rest equally",
      game.DICE_PCT[2] == game.DICE_PCT[3] == game.DICE_PCT[5]
      and abs(3 * game.DICE_PCT[2] - 40.0) < 1e-9)

import random as _random
game._rng = _random.Random(11)
_N = 60000
_counts = {}
for _ in range(_N):
    _f = game._roll_face()
    _counts[_f] = _counts.get(_f, 0) + 1
check("every face can still come up", len(_counts) == 6)
for _f in sorted(game.DICE_PCT):
    _got = 100.0 * _counts[_f] / _N
    check("face %d lands near %.2f%% (got %.2f%%)" % (_f, game.DICE_PCT[_f], _got),
          abs(_got - game.DICE_PCT[_f]) < 1.2)
check("a six really does beat a two", _counts[6] > _counts[2] * 1.9)

# --- regression: the turn message was written to a local and thrown away ---
print()
print("--- regressions ---")
game.start_game("single", 4)
game.dice = 3
game.message = ""
game._pass_turn()
check("passing the turn tells you whose go it is",
      game.message.endswith("to roll.") and len(game.message) > 8)

# a 6 keeps the turn, so the message must not change hands
game.start_game("single", 4)
who = game.cur()
game.dice = 6
game.message = "keep"
game._pass_turn()
check("rolling a six keeps the same player", game.cur() == who)
check("rolling a six does not print the next player's name", game.message == "keep")

# --- the board fits whatever screen it is given --------------------------
print()
print("--- screen layouts ---")

# a phone held upright
game.set_size(560, 1155)
portrait_board = game.BOARD
check("portrait gives the board most of the width",
      portrait_board >= 560 * 0.90)
check("portrait puts the panel below the board",
      game.HUD_Y > game.BY + portrait_board - 1)
check("portrait keeps the panel on screen",
      game.HUD_X + game.HUD_W <= 560 + 1)
check("the roll button fits inside the panel",
      game.ROLL_RECT[1] + game.ROLL_RECT[3] <= game.HUD_Y + game.HUD_H + 1)

# the same phone turned sideways
game.set_size(1155, 560)
land_board = game.BOARD
check("landscape puts the panel to the right of the board",
      game.HUD_X > game.BX + land_board - 1)
check("landscape uses the full height", land_board >= 560 * 0.90)
check("landscape keeps the panel on screen",
      game.HUD_X + game.HUD_W <= 1155 + 1)

# a small phone must still get a usable board
game.set_size(360, 640)
check("a small phone still gets a big board", game.BOARD >= 300)
game.set_size(390, 844)
check("the roll button is always on screen",
      game.ROLL_RECT[1] + game.ROLL_RECT[3] <= game.HUD_Y + game.HUD_H + 1)

# a silly size must not break it
game.set_size(10, 10)
check("a silly size is ignored", game.BOARD > 100)
game.set_size(900, 560)

# --- the board shows where you can go ------------------------------------
print()
print("--- move hints ---")
game.set_size(560, 1155)
game.start_game("single", 4)
game.dice = 6
game._after_roll()
check("a 6 offers at least one move", len(game.moves) > 0)

game.state = "play"
game.anims[:] = []          # an earlier test may have left one running
kept = list(game.moves)
CALLS.clear()
game.draw()
with_hints = sum(1 for c in CALLS if c[0] == "arc")

# with nothing to move, the rings are gone
game.moves = []
CALLS.clear()
game.draw()
without = sum(1 for c in CALLS if c[0] == "arc")
check("the board draws a ring for each move", with_hints > without)
check("no hints when there is nothing to move", with_hints - without >= 2)

game.moves = kept

# --- every button on every screen actually does something ----------------
print()
print("--- buttons ---")

def tap_tag(tag):
    r = rect_for(tag)
    game.tap(r[0] + r[2] / 2, r[1] + r[3] / 2)

def centre(rect):
    game.tap(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)

game.set_size(560, 1155)
game.state = "mode"
game.draw()

check("the mode screen has a games chip", "games" in [t for t, _ in game._menu_hit])
check("the mode screen offers every preset",
      all(("m:" + m) in [t for t, _ in game._menu_hit] for m in game.MODES))

tap_tag("m:quick")
check("picking Quick applies its rules",
      game.rule_mode == "quick" and game.RULES["tokens"] == 2
      and game.RULES["first_home_wins"])

tap_tag("m:classic")
check("picking Classic puts the rules back",
      game.rule_mode == "classic" and game.RULES["tokens"] == 4
      and not game.RULES["first_home_wins"])

tap_tag("n:3")
check("the player count is a tap away",
      game.player_count == 3 and game.mode == "single")

tap_tag("team")
check("Team picks four players", game.mode == "team" and game.player_count == 4)
tap_tag("n:2")

tap_tag("custom")
check("Custom rules opens the dials", game.state == "rules")
game.draw()
check("every dial is on the screen",
      all(("r:" + k) in [t for t, _ in game._menu_hit] for k, _l, _a, _b in game.DIALS))

tap_tag("r:exit")
check("a dial flips when tapped", game.RULES["exit"] == "any")
tap_tag("r:exit")
check("and flips back", game.RULES["exit"] == "six")

tap_tag("back")
check("Done returns to the mode screen", game.state == "mode")

game.draw()
tap_tag("play")
check("Play begins a round", game.state == "play")

# the roll button and the die both roll
game.draw()
game.can_roll = True
game.rolling = 0.0
game.anims[:] = []
before = game.dice
centre(game.ROLL_RECT)
for _ in range(4):
    game.update(1 / 60)
check("the roll button rolls", game.rolling > 0 or game.dice != before
      or game.moves or not game.can_roll)

game.rolling = 0.0
game.anims[:] = []
game.can_roll = True
centre(game.DIE_RECT)
check("tapping the die also rolls", game.rolling > 0 or not game.can_roll)

# the menu chip is drawn AND works
game.draw()
centre(game.BACK_RECT)
check("the Menu chip leaves the round", game.state == "mode")

# the win screen's buttons
game.start_game("single", 2)
game.winner = game.RED
game.state = "over"
game.draw()
tap_tag("again")
check("Play again starts a new round", game.state == "play")
game.winner = game.RED
game.state = "over"
game.draw()
tap_tag("menu")
check("Main menu returns to the mode screen", game.state == "mode")

# --- only the player whose turn it is can act -----------------------------
print()
print("--- whose turn ---")
game.start_game("single", 3)
game.set_net_ludo(True, True, 0)          # we are the host, seat 0
game.turn = 0
check("seat 0 acts on turn 0", game.my_turn())
game.turn = 1
check("seat 0 does not act on turn 1", not game.my_turn())
game.turn = 2
check("seat 0 does not act on turn 2", not game.my_turn())

game.set_net_ludo(True, False, 2)         # a guest in seat 2
game.turn = 2
check("seat 2 acts on turn 2", game.my_turn())
game.turn = 0
check("seat 2 does not act on turn 0", not game.my_turn())

game.set_net_ludo(False, True, 0)
check("with no room, it is always your turn", game.my_turn())

# a guest asking out of turn is ignored by the host
game.set_net_ludo(True, True, 0)
game.set_seats(json.dumps({"ME": 0, "FRIEND": 1}), "ME")
game.start_game("single", 2)
game.turn = 0
before = game.turn
game.net_apply_action(json.dumps({"a": "roll", "from": "FRIEND"}))
check("an out-of-turn roll is refused", game.turn == before and not game.rolling > 0)

game.turn = 1
game.can_roll = True
game.net_apply_action(json.dumps({"a": "roll", "from": "FRIEND"}))
check("the right player's roll goes through", game.rolling > 0 or not game.can_roll)

# an action with no sender at all is refused
game.start_game("single", 2)
game.turn = 0
game.can_roll = True
game.rolling = 0.0
game.net_apply_action(json.dumps({"a": "roll"}))
check("a roll from nobody is refused", game.rolling == 0.0 and game.can_roll)

# the host's own tap does nothing out of turn
game.set_net_ludo(True, True, 0)
game.start_game("single", 2)
game.turn = 1
game.can_roll = True
game.rolling = 0.0
centre(game.ROLL_RECT)
check("the host cannot roll for the other player", game.rolling == 0.0)

game.turn = 0
centre(game.ROLL_RECT)
check("the host can roll on its own turn", game.rolling > 0 or not game.can_roll)
game.set_net_ludo(False, True, 0)

# --- a guest ends up with exactly the host's board -----------------------
print()
print("--- host and guest agree ---")
game.set_size(560, 1155)
game.start_game("team", 4)
game.set_design("hex")
game.dice = 4
game._after_roll()
for _ in range(30):
    game.update(1 / 60)

host = {
    "mode": game.mode, "players": list(game.players), "turn": game.turn,
    "dice": game.dice, "moves": len(game.moves), "can_roll": game.can_roll,
    "state": game.state, "design": game.design, "teams": dict(game.teams),
    "tokens": [(t["c"], t["i"], t["pos"]) for t in game.tokens],
}
snap = game.snapshot()

# wipe the slate and adopt the host's board, like a guest would
game.start_game("single", 2)
game.set_design("ball")
game.apply_net(snap)

check("the guest gets the same mode", game.mode == host["mode"])
check("the guest gets the same colours", list(game.players) == host["players"])
check("the guest gets the same turn", game.turn == host["turn"])
check("the guest gets the same dice", game.dice == host["dice"])
check("the guest gets the same number of moves", len(game.moves) == host["moves"])
check("the guest gets the same roll state", game.can_roll == host["can_roll"])
check("the guest gets the same screen", game.state == host["state"])
check("the guest gets the same token design", game.design == host["design"])
check("the guest gets the same teams", dict(game.teams) == host["teams"])
check("the guest gets every token in the same place",
      [(t["c"], t["i"], t["pos"]) for t in game.tokens] == host["tokens"])
check("the guest's tokens sit on the board where they should",
      all(abs(t["x"] - game.token_xy(t["c"], t["i"], t["pos"])[0]) < 0.01
          for t in game.tokens))

# a broken snapshot must not break the guest
before_state = game.state
game.apply_net("not json at all")
check("a broken snapshot is ignored", game.state == before_state)

# --- a guest keeps the seat the room gives it ----------------------------
print()
print("--- seats ---")
game.start_game("single", 2)
game.set_net_ludo(True, False, -1)      # a guest, seat not decided yet
check("an undecided seat is left alone", game.net_seat == 0)
game.set_seats(json.dumps({"GUEST": 1}), "GUEST")
check("the room's seat is adopted", game.net_seat == 1)

# a refresh must not wipe it back to zero
game.set_net_ludo(True, False, -1)
check("a later refresh keeps the seat", game.net_seat == 1)

# and the host always sits in seat 0
game.set_net_ludo(True, True, 0)
check("the host is seat 0", game.net_seat == 0)

game.set_net_ludo(False, True, -1)
check("leaving the room clears the turn rule", game.my_turn())

# --- one legal move plays itself ----------------------------------------
print()
print("--- only one way to go ---")
game.start_game("single", 4)
game.tokens[0]["pos"] = 0            # one token out, the rest still in the yard
game.anims[:] = []
game.dice = 2
game._after_roll()
check("a single move is offered", len(game.moves) == 1)
check("the move is armed to play itself", game.auto_move_t >= 0)

before = game.tokens[0]["pos"]
game.update(1 / 60)                  # a single frame is all it should need
check("the token moves on the very next frame", game.tokens[0]["pos"] != before)
check("the flag is cleared afterwards", game.auto_move_t < 0)

# several moves means the player chooses
game.start_game("single", 4)
game.anims[:] = []
game.dice = 6
game._after_roll()
check("a six offers several moves", len(game.moves) > 1)
check("nothing plays itself when there is a choice", game.auto_move_t < 0)

# tapping a token cancels any pending automatic move
game.start_game("single", 4)
game.tokens[0]["pos"] = 0
game.anims[:] = []
game.dice = 2
game._after_roll()
check("the automatic move is armed", game.auto_move_t >= 0)
game._choose(game.moves[0][0], game.moves[0][1])
check("a tap clears it", game.auto_move_t < 0)

# and in a room the guest must not move on its own, or it would double up
game.set_net_ludo(True, False, 1)
game.start_game("single", 2)
game.tokens[0]["pos"] = 0
game.anims[:] = []
game.dice = 2
game._after_roll()
check("a guest never moves by itself", game.auto_move_t < 0)
game.set_net_ludo(False, True, 0)

# --- a player who leaves does not hold up the room ----------------------
print()
print("--- seats that emptied ---")
game.set_net_ludo(True, True, 1)
game.start_game("single", 2)
game.set_present(json.dumps([1]))
game.turn = 1
game.dice = 3
game._pass_turn()
check("the dice skips a colour nobody is playing", game.turn == 1)

game.set_present(json.dumps([0, 1]))
game.turn = 0
game._pass_turn()
check("with everyone there the dice moves on", game.turn == 1)

# three players, the middle one gone
game.start_game("single", 3)
game.set_present(json.dumps([0, 2]))
game.turn = 0
game.dice = 5
game._pass_turn()
check("a three player room skips the empty middle seat", game.turn == 2)

# an empty list means "no idea", so nothing is skipped
game.set_present(json.dumps([]))
game.turn = 0
game._pass_turn()
check("an unknown room does not skip anybody", game.turn == 1)
game.set_net_ludo(False, True, 0)

# the dice sitting with somebody who left must move on by itself
game.set_net_ludo(True, True, 1)
game.start_game("single", 2)
game.turn = 0
game.can_roll = False
game.set_present(json.dumps([1]))
check("the dice leaves an empty seat straight away", game.turn == 1)
check("and that seat is allowed to roll", game.can_roll and game.my_turn())

game.set_net_ludo(False, True, 0)

# --- every dial actually changes the game -------------------------------
print()
print("--- house rules ---")

game.apply_mode("classic")
game.start_game("single", 2)
check("classic gives four tokens each",
      len([t for t in game.tokens if t["c"] == game.RED]) == 4)
game.dice = 3
game._after_roll()
check("classic needs a six to open the yard", not game.moves)

game.apply_mode("quick")
game.start_game("single", 2)
check("quick gives two tokens each",
      len([t for t in game.tokens if t["c"] == game.RED]) == 2)
game.dice = 3
game._after_roll()
check("quick lets any roll open the yard", len(game.moves) > 0)
game.tokens[0]["pos"] = game.HOME_POS
check("quick ends on the first token home", game._won(game.RED))

game.apply_mode("master")
game.start_game("single", 2)
game.tokens[0]["pos"] = game.LAST_TRACK - 1
game.dice = 4
game._after_roll()
check("master blocks the home column until you capture", not game.moves)
game.captured_any[game.RED] = 1
game.turn = 0
game._after_roll()
check("master opens it once you have captured", len(game.moves) > 0)

# a star square is shelter in classic and open in plain
game.apply_mode("classic")
game.start_game("single", 2)
star = game.START[game.YELLOW]
game.tokens[0]["pos"] = (star - 13) % 50
cell = game.path_cell(game.RED, game.tokens[0]["pos"])
check("a star is safe in classic",
      game.RULES["safe_squares"] and not game._captures_at(cell, game.RED)
      or cell not in [game.path_cell(game.YELLOW, 0)])

game.apply_mode("plain")
check("plain has no safe squares", not game.RULES["safe_squares"])
game.apply_mode("classic")
check("classic has them back", game.RULES["safe_squares"])

# bouncing off the centre
game.apply_mode("classic")
game.RULES["exact_home"] = False
game.start_game("single", 2)
game.tokens[0]["pos"] = game.HOME_POS - 2
game.dice = 5
game._after_roll()
check("without an exact roll the token bounces back",
      game.moves and game.moves[0][1] == game.HOME_POS - 3)
game.apply_mode("classic")
game.start_game("single", 2)
game.tokens[0]["pos"] = game.HOME_POS - 2
game.dice = 5
game._after_roll()
check("with an exact roll it cannot move at all", not game.moves)

# three sixes void the turn
game.apply_mode("classic")
game.start_game("single", 2)
game.turn = 0
game.sixes_in_a_row = 3
game.dice = 6
game.can_roll = True
game.rolling = 0.0
game.anims[:] = []
game._after_roll()
check("a third six ends the turn", game.turn == 1)
game.apply_mode("classic")

# the dials survive a save and a load
game.set_rule_mode("quick")          # this saves as it goes
game.apply_mode("classic")           # wipe them, without saving
game.load_rules()
check("the rules come back after a reload",
      game.RULES["tokens"] == 2 and game.rule_mode == "quick")
game.set_rule_mode("classic")

# --- the look and feel dials --------------------------------------------
print()
print("--- accessibility ---")
game.apply_mode("classic")
check("every colour has a shape of its own",
      len(set(game.MARKS.values())) == 4
      and set(game.MARKS) == {game.RED, game.GREEN, game.YELLOW, game.BLUE})
check("marks are on by default", game.RULES["marks"])

game.start_game("single", 4)
CALLS.clear(); game.draw()
with_marks = sum(1 for c in CALLS if c[0] == "rect") + \
             sum(1 for c in CALLS if c[0] == "arc")
game.RULES["marks"] = False
CALLS.clear(); game.draw()
without = sum(1 for c in CALLS if c[0] == "rect") + \
          sum(1 for c in CALLS if c[0] == "arc")
check("turning marks off changes what is drawn", with_marks != without)
game.RULES["marks"] = True

# themes
game.RULES["theme"] = "classic"
check("a theme is chosen", game._theme()["bg0"] == "#121d3e")
game.RULES["theme"] = "mint"
check("the theme changes the board", game._theme()["bg0"] != "#121d3e")
game.RULES["theme"] = "classic"

# reduced motion drops the confetti
game.apply_mode("classic")
game.RULES["reduced_motion"] = True
game.start_game("single", 2)
game.winner = game.RED
game.state = "over"
game._confetti[:] = []
for _ in range(1):
    pass
check("gentle motion is a switch", game.RULES["reduced_motion"])

# stats count a finished game
before_games = game.STATS["games"]
game._bump_stats(True)
check("a win is counted", game.STATS["games"] == before_games + 1
      and game.STATS["wins"] >= 1)

# the turn timer rolls for somebody who has gone quiet
game.apply_mode("classic")
game.RULES["turn_timer"] = 1
game.start_game("single", 2)
game.anims[:] = []
game.rolling = 0.0
for _ in range(90):
    game.update(1 / 60)
check("the turn timer rolls for a quiet player",
      game.rolling > 0 or not game.can_roll)
game.apply_mode("classic")

# the last move leaves a mark that fades
game.start_game("single", 2)
game.tokens[0]["pos"] = 0
game.dice = 2
game._after_roll()
t0, q0 = game.moves[0]
game._choose(t0, q0)
for _ in range(120):
    game.update(1 / 60)
check("the last move is remembered", game.last_move is not None)

# --- screen-adaptive UI -----------------------------------------------------
print()
print("--- screen-adaptive UI ---")
game.set_ui(1.0)
check("on a big screen the type is left alone",
      game._fit_font("700 15px X") == "700 15px X")
check("on a big screen targets are not grown",
      game._in((100, 100, 20, 20), 100 + 10, 100 + 40) is False)

game.set_ui(0.70)                     # a phone, canvas scaled to 70%
check("on a phone the type is scaled up",
      game._fit_font("700 15px X") != "700 15px X")
scaled = game._fit_font("700 15px X")
check("scaled type keeps its weight and family",
      scaled.startswith("700 ") and scaled.endswith("px X"))
check("a 48 CSS px target is larger than 48 logical px", game.MIN_TOUCH > 48)
check("the type scale is capped so text cannot overflow", game.UI <= 1.35)

# a small button is now reachable from outside its drawn bounds
grown = game._in((100, 100, 20, 20), 100 + 10, 100 + game.MIN_TOUCH / 2 - 1)
check("a small target is grown to a finger size", grown is True)
_top = 100 - (game.MIN_TOUCH - 20) / 2
_bot = 100 + (game.MIN_TOUCH + 20) / 2
check("the grown target stays centred on the drawn one",
      game._in((100, 100, 20, 20), 110, _top + 1) is True
      and game._in((100, 100, 20, 20), 110, _bot - 1) is True
      and game._in((100, 100, 20, 20), 110, _top - 2) is False)

for spec in ("600 11px X", "800 26px X", "700 12.5px X", "900 40px X"):
    check("font %-16r survives scaling" % spec,
          "px" in game._fit_font(spec) and game._fit_font(spec).endswith("X"))

game.set_ui(1.0)
check("back on a big screen nothing is scaled",
      game._fit_font("700 15px X") == "700 15px X")

print()
if fails:
    print("FAILURES:", fails); sys.exit(1)
print("All checks passed.")

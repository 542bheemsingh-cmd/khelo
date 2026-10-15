"""
Headless harness for the upgraded hill-climb game (stubs out the browser `js`).
"""
import sys, os, types, math

CALLS, STORE = [], {}

class FakeGradient:
    def addColorStop(self, *a): CALLS.append(("addColorStop", a))

class FakeCtx:
    def __getattr__(self, name):
        def method(*args, **kw):
            CALLS.append((name, args))
            return FakeGradient() if name == "createLinearGradient" else None
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


def begin():
    """Start the level, skipping the new-obstacle intro if one appears."""
    game.start_game()
    if game.screen == "intro":
        game._end_intro()


fails = []
def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: fails.append(label)

FRAME = 1.0 / 60.0

# --- boot ---
check("boots into the menu", game.screen == "menu")
check("has 5 locations", len(game.LEVELS) == 5)
check("has 4 vehicles", len(game.VEHICLES) == 4)
check("only the first location starts unlocked", game.unlocked == [0])
check("only the first vehicle starts owned", game.owned == [0])
CALLS.clear(); game.draw()
check("menu draws (buttons hit-tested)", len(CALLS) > 30 and len(game._menu_hit) >= 6)

# --- level / vehicle selection rules ---
game.select_level(2)
check("cannot select a locked location", game.level_index == 0)
game.select_level(0)
check("can select the unlocked location", game.level_index == 0)

game.wallet = 0
game.select_vehicle(2)
check("cannot buy a vehicle without coins", 2 not in game.owned)
game.wallet = 1000
game.select_vehicle(2)
check("buying a vehicle deducts its price",
      game.wallet == 1000 - game.VEHICLES[2]["price"] and 2 in game.owned and game.vehicle_index == 2)

# --- start + drive ---
begin()
check("start enters playing", game.screen == "playing" and game.playing())
check("track items were built",
      len(game.coins) > 0 and len(game.fuels) > 0 and len(game.rocks) > 0)
x0 = game._car_x()
game.gas(True)
for _ in range(600):
    game.update(FRAME)
    if game.screen != "playing": break
check("car drives forward under gas", game._car_x() - x0 > 300)
check("fuel drained while driving", game.fuel < game.FUEL_MAX)

# --- coins ---
begin()
game.wallet = 0; game.run_coins = 0
c = game.coins[0]
c["x"] = game._car_x(); c["y"] = game._car_y(); c["got"] = False
game._collect()
check("driving over a coin adds it to the wallet",
      c["got"] and game.run_coins == 1 and game.wallet == game.COIN_VALUE)
game._collect()
check("a coin is only collected once", game.wallet == game.COIN_VALUE)

# --- fuel refill ---
begin()
game.fuel = 20.0
f = game.fuels[0]
f["x"] = game._car_x(); f["y"] = game._car_y(); f["got"] = False
game._collect()
check("fuel can refills the tank", game.fuel == game.FUEL_MAX and f["got"])

# --- obstacles ---
begin()
game.rocks = [{"x": game._car_x() + 150.0, "w": 40.0, "h": 18.0, "shape": "hill", "style": "rock"}]
rock = game.rocks[0]
game.gas(True)
for _ in range(420):
    game.update(FRAME)
    if game.screen != "playing": break
check("the car rides over a small rock bump without getting stuck",
      game.screen == "playing" and game._car_x() > rock["x"] + 80.0)

begin()
game.rocks = [{"x": game._car_x() + 150.0, "w": 70.0, "h": 34.0, "shape": "hill", "style": "boulder"}]
rock = game.rocks[0]
game.gas(True)
for _ in range(420):
    game.update(FRAME)
    if game.screen != "playing": break
check("a boulder is passable too, not a wall",
      game.screen == "playing" and game._car_x() > rock["x"] + 80.0)

# --- reaching the target wins + unlocks the next location ---
begin()
game.wallet = 0
lv = game.LEVELS[game.level_index]
game.rear["x"] = game.START_X + lv["target"] * game.PIXELS_PER_METER + 10
game.front["x"] = game.rear["x"] + game.VEHICLES[game.vehicle_index]["wheelbase"]
game.update(FRAME)
check("reaching the target wins the level", game.screen == "won")
check("winning pays a bonus", game.wallet >= 50)
check("winning unlocks the next location", 1 in game.unlocked)

# --- crash ---
begin()
game.rear["x"] = 300.0
game.rear["y"] = game.terrain(300.0) - game.VEHICLES[game.vehicle_index]["wheel_r"]
game.front["x"] = 300.0 - game.VEHICLES[game.vehicle_index]["wheelbase"]
game.front["y"] = game.rear["y"]
for w in (game.rear, game.front): w["vx"] = 0.0; w["vy"] = 0.0
game.update(FRAME)
check("flipping ends the run as a crash", game.screen == "over" and game.over_reason == "crash")

# --- out of fuel ---
begin()
game.fuel = 0.001
game.gas(True)
game.update(FRAME)
check("running out of fuel ends the run", game.screen == "over" and game.over_reason == "fuel")

# --- every location generates a playable track ---
ok_tracks = True
for i in range(len(game.LEVELS)):
    game.unlocked = list(range(len(game.LEVELS)))
    game.level_index = i
    begin()
    if not (len(game.coins) and len(game.fuels) and len(game.rocks)):
        ok_tracks = False
    for _ in range(120):
        game.gas(True)
        game.update(FRAME)
        if game.screen != "playing": break
check("all 5 locations build tracks and run", ok_tracks)

# --- persistence round trip ---
game.wallet = 777; game.owned = [0, 1]; game.unlocked = [0, 1, 2]
game.best = {0: 123}; game.level_index = 1; game.vehicle_index = 1
game._save()
game.wallet = 0; game.owned = [0]; game.unlocked = [0]; game.best = {}
game._load()
check("save/load round-trips the wallet, garage and progress",
      game.wallet == 777 and game.owned == [0, 1] and game.unlocked == [0, 1, 2]
      and game.best.get(0) == 123 and game.level_index == 1)

# --- menu tap hit-testing ---
game.screen = "menu"
game.wallet = 0; game.owned = [0]; game.unlocked = [0]; game.level_index = 0
game.draw()                       # populates _menu_hit
start_btn = [h for h in game._menu_hit if h[0] == "start"][0]
game.tap(start_btn[2] + 5, start_btn[3] + 5)
check("tapping START begins the game", game.screen == "playing")
game.back_to_menu()
game.draw()
lvl_btn = [h for h in game._menu_hit if h[0] == "level"][0]
game.tap(lvl_btn[2] + 5, lvl_btn[3] + 5)
check("tapping a location selects it", game.level_index == lvl_btn[1])

# --- per-level obstacle sets ---
sets = [tuple(game.LEVELS[i]["obstacles"]) for i in range(5)]
check("each level has 2-5 obstacle types", all(2 <= len(s) <= 5 for s in sets))
check("the levels use different obstacle sets", len(set(sets)) == 5)
check("every obstacle id has a spec", all(o in game.OBSTACLES for s in sets for o in s))
check("new obstacle types are introduced as levels progress",
      all(len(game._new_obstacles(i)) >= 1 for i in range(1, 5)))
check("level 2 introduces cacti and ramps",
      set(game._new_obstacles(1)) == {"cactus", "ramp"})

# --- intro demo before a level with new obstacles ---
game.screen = "menu"; game.level_index = 0; game.intro_seen = []
game.start_game()
check("a new level shows the obstacle intro first", game.screen == "intro")
check("the intro lists the new obstacles", len(game._intro_new) >= 1)
CALLS.clear(); game.draw()
check("the intro screen draws", len(CALLS) > 30)
game.update(FRAME)
check("the intro demo animates", game._intro_t > 0)
game.gas(True)
check("gas starts the level from the intro", game.screen == "playing")
check("the intro is remembered", 0 in game.intro_seen)
game.back_to_menu(); game.start_game()
check("the intro does not repeat once seen", game.screen == "playing")

# --- spike strips: the real crash hazard ---
game.unlocked = list(range(5)); game.level_index = 0
begin()
sp = {"x": game._car_x(), "w": 25.0, "h": 18.0, "shape": "peak", "style": "spike", "id": "spike"}
game.rocks = [sp]
game.rear["vx"] = 400.0; game.rear["vy"] = 0.0
game._collect()
check("a spike strip ends the run when hit fast",
      game.screen == "over" and game.over_reason == "spike")

begin()
sp = {"x": game._car_x(), "w": 25.0, "h": 18.0, "shape": "peak", "style": "spike", "id": "spike"}
game.rocks = [sp]
game.rear["vx"] = 60.0; game.rear["vy"] = 0.0
game._collect()
check("a spike strip can be crawled over slowly", game.screen == "playing")

# --- every obstacle shape can be driven over (spikes excepted - they are fatal) ---
bad = []
for oid, spec in game.OBSTACLES.items():
    if oid == "spike":
        continue
    game.unlocked = list(range(5)); game.level_index = 0
    begin()
    game.rocks = [{"x": game._car_x() + 170.0, "w": 70.0, "h": 24.0,
                   "shape": spec["shape"], "style": spec["style"]}]
    game.gas(True)
    for _ in range(560):
        game.update(FRAME)
        if game.screen != "playing": break
    if not (game.screen == "playing" and game._car_x() > game.rocks[0]["x"] + 90.0):
        bad.append((oid, game.screen))
check("every obstacle type is traversable", not bad)
if bad:
    print("   not traversable:", bad)
check("at least one obstacle can end the run",
      any(game.OBSTACLES[o]["style"] == "spike" for s in sets for o in s))

# --- speedometer ---
game.screen = "playing"; game.rear["vx"] = 400.0; game.rear["vy"] = 0.0
CALLS.clear(); game._draw_speedo()
check("the speedometer draws a readout", any(c[0] == "fillText" for c in CALLS))

# --- no obstacle silhouette may dip below the ground line ---
def profile_dips(ob):
    CALLS.clear()
    game._cam = 0.0
    game._profile_path(ob)
    for name, args in CALLS:
        if name in ("lineTo", "moveTo") and args:
            x, y = args[0], args[1]
            if y > game.terrain(x + game._cam) + 0.6:
                return True
    return False

game.level_index = 2
xs = [x for x in range(1500, 8000) if abs(game.slope(x)) > 0.30]
base_x = xs[0] if xs else 3000.0
dippers = []
for oid, spec in game.OBSTACLES.items():
    ob = {"x": base_x, "w": 60.0, "h": 40.0,
          "shape": spec["shape"], "style": spec["style"], "id": oid}
    if profile_dips(ob):
        dippers.append(oid)
check("no obstacle silhouette dips below the ground line", not dippers)
if dippers:
    print("   dips below ground:", dippers)

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

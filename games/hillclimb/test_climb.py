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
game.start_game()
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
game.start_game()
game.wallet = 0; game.run_coins = 0
c = game.coins[0]
c["x"] = game._car_x(); c["y"] = game._car_y(); c["got"] = False
game._collect()
check("driving over a coin adds it to the wallet",
      c["got"] and game.run_coins == 1 and game.wallet == game.COIN_VALUE)
game._collect()
check("a coin is only collected once", game.wallet == game.COIN_VALUE)

# --- fuel refill ---
game.start_game()
game.fuel = 20.0
f = game.fuels[0]
f["x"] = game._car_x(); f["y"] = game._car_y(); f["got"] = False
game._collect()
check("fuel can refills the tank", game.fuel == game.FUEL_MAX and f["got"])

# --- obstacles ---
game.start_game()
game.rocks = [{"x": game._car_x() + 150.0, "w": 40.0, "h": 18.0}]
rock = game.rocks[0]
game.gas(True)
for _ in range(420):
    game.update(FRAME)
    if game.screen != "playing": break
check("the car rides over a small rock bump without getting stuck",
      game.screen == "playing" and game._car_x() > rock["x"] + 80.0)

game.start_game()
game.rocks = [{"x": game._car_x() + 150.0, "w": 70.0, "h": 34.0}]
rock = game.rocks[0]
game.gas(True)
for _ in range(420):
    game.update(FRAME)
    if game.screen != "playing": break
check("a boulder is passable too, not a wall",
      game.screen == "playing" and game._car_x() > rock["x"] + 80.0)

# --- reaching the target wins + unlocks the next location ---
game.start_game()
game.wallet = 0
lv = game.LEVELS[game.level_index]
game.rear["x"] = game.START_X + lv["target"] * game.PIXELS_PER_METER + 10
game.front["x"] = game.rear["x"] + game.VEHICLES[game.vehicle_index]["wheelbase"]
game.update(FRAME)
check("reaching the target wins the level", game.screen == "won")
check("winning pays a bonus", game.wallet >= 50)
check("winning unlocks the next location", 1 in game.unlocked)

# --- crash ---
game.start_game()
game.rear["x"] = 300.0
game.rear["y"] = game.terrain(300.0) - game.VEHICLES[game.vehicle_index]["wheel_r"]
game.front["x"] = 300.0 - game.VEHICLES[game.vehicle_index]["wheelbase"]
game.front["y"] = game.rear["y"]
for w in (game.rear, game.front): w["vx"] = 0.0; w["vy"] = 0.0
game.update(FRAME)
check("flipping ends the run as a crash", game.screen == "over" and game.over_reason == "crash")

# --- out of fuel ---
game.start_game()
game.fuel = 0.001
game.gas(True)
game.update(FRAME)
check("running out of fuel ends the run", game.screen == "over" and game.over_reason == "fuel")

# --- every location generates a playable track ---
ok_tracks = True
for i in range(len(game.LEVELS)):
    game.unlocked = list(range(len(game.LEVELS)))
    game.level_index = i
    game.start_game()
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

print()
if fails:
    print("FAILURES:", fails); sys.exit(1)
print("All checks passed.")

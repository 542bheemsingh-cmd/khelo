"""
Headless harness for the hill-climb game.py (stubs out the browser `js`).
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
check("starts in ready state", game.state == "ready")
check("canvas scaled by DPR", CANVAS.width == 1800 and CANVAS.height == 1120)
check("car sits on the terrain at start",
      abs(game.rear["y"] - (game.terrain(game.rear["x"]) - game.WHEEL_R)) < 1.0)
check("draw() runs in ready state", (lambda: (CALLS.clear(), game.draw(), len(CALLS) > 30)[-1])())

# --- no throttle: the car must not drive itself forward ---
game.reset_game(); game.state = "playing"
x0 = game._car_x()
for _ in range(120): game.update(FRAME)
check("does not drive forward with no throttle", game._car_x() - x0 < 15.0)

# --- throttle: car drives forward and climbs ---
game.reset_game()
game.gas(True)
check("gas starts the game", game.state == "playing")
x_start = game._car_x()
min_y = 1e9
frames = 0
for _ in range(1800):                      # up to 30 s
    if game.state != "playing": break
    game.update(FRAME)
    frames += 1
    min_y = min(min_y, game._car_y())
    # wheels must not sink through the ground
    for w in (game.rear, game.front):
        assert w["y"] <= game.terrain(w["x"]) - game.WHEEL_R + 1.5, "wheel sank through ground"

check("car drives forward under gas", game._car_x() - x_start > 300)
check("distance meter climbed", game._meters() > 0)
check("car climbed a hill (its y rose well above start)",
      (game.terrain(x_start) - min_y) > 40)
check("fuel drained", game.fuel < game.FUEL_MAX)
check("run ended (out of fuel or crash)", game.state == "over")
print("   ended after %.1fs, reason=%s, distance=%dm" % (frames / 60.0, game.over_reason, game._meters()))
check("over_reason is set", game.over_reason in ("fuel", "crash"))

# --- best score recorded ---
check("best score recorded", game.best >= 1 and STORE.get("khelo_climb_best") is not None)

# --- crash detection: flip the car so the driver's head hits the ground ---
game.reset_game(); game.state = "playing"
game.rear["x"] = 300.0
game.rear["y"] = game.terrain(300.0) - game.WHEEL_R
game.front["x"] = 300.0 - game.WHEELBASE
game.front["y"] = game.rear["y"]
for w in (game.rear, game.front):
    w["vx"] = 0.0; w["vy"] = 0.0
hx, hy = game._head_point()
check("flipped car puts the head below ground", hy > game.terrain(hx))
game.update(FRAME)
check("head-on-ground crash ends the run", game.state == "over")
check("crash reason recorded", game.over_reason == "crash")

# --- restart ---
game.gas(True)
check("gas after game over restarts", game.state == "playing")
check("restart refills fuel", game.fuel == game.FUEL_MAX)

# --- slope sanity ---
check("slope() matches a numeric derivative of terrain()",
      abs(game.slope(500.0) - (game.terrain(500.5) - game.terrain(499.5))) < 0.02)

print()
if fails:
    print("FAILURES:", fails); sys.exit(1)
print("All checks passed.")

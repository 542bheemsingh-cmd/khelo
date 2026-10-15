"""
Headless harness for game.py.

game.py talks to the browser through Pyodide's `js` module. Here we inject a
fake `js` module that records canvas calls and backs localStorage with a dict,
so the real game logic can be driven and checked outside a browser.
"""
import sys
import types
import os

CALLS = []
STORE = {}


class FakeGradient:
    def addColorStop(self, *args):
        CALLS.append(("addColorStop", args))


class FakeCtx:
    def __getattr__(self, name):
        def method(*args, **kwargs):
            CALLS.append((name, args))
            if name == "createLinearGradient":
                return FakeGradient()
            return None
        return method


CTX = FakeCtx()


class FakeCanvas:
    width = 480
    height = 720

    def getContext(self, kind):
        CALLS.append(("getContext", kind))
        return CTX


CANVAS = FakeCanvas()


class FakeStorage:
    def getItem(self, key):
        return STORE.get(key)

    def setItem(self, key, value):
        STORE[key] = value


js = types.ModuleType("js")
js.devicePixelRatio = 3          # should be clamped to 2
js.document = types.SimpleNamespace(getElementById=lambda _id: CANVAS)
js.window = types.SimpleNamespace(localStorage=FakeStorage())
js.playSound = lambda name: CALLS.append(("sound", name))
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

failures = []


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        failures.append(label)


# --- 1. boot state --------------------------------------------------------
check("starts in ready state", game.state == "ready")
check("canvas scaled by clamped DPR (480*2=960)", CANVAS.width == 960 and CANVAS.height == 1440)
check("best starts at 0 with empty storage", game.best == 0)
check("clouds seeded", len(game.clouds) == 6)

# --- 2. draw() runs without error in ready state --------------------------
CALLS.clear()
game.draw()
check("draw() produced canvas calls", len(CALLS) > 20)
check("draw() drew the ready overlay text",
      any(c[0] == "fillText" and "KHELO FLY" in str(c[1]) for c in CALLS))

# --- 3. flap starts the game ---------------------------------------------
game.flap()
check("flap() moves to playing", game.state == "playing")
check("flap() gives upward velocity", game.bird_vel < 0)
check("flap played a sound", ("sound", "flap") in CALLS)

# --- 4. autopilot: keep the bird alive, expect pipes + score --------------
FRAME = 1.0 / 60.0
game.reset_game()
game.flap()

spawned_ever = False
max_score = 0
for _ in range(3000):                      # 50 simulated seconds
    if game.state != "playing":
        break
    ahead = [p for p in game.pipes if p["x"] + game.PIPE_W > game.BIRD_X]
    target = PLAY_H_CENTER = 0
    if ahead:
        nxt = min(ahead, key=lambda p: p["x"])
        target = nxt["gap_y"] + nxt["gap_h"] / 2.0
    else:
        target = (game.PLAY_H) / 2.0
    if game.bird_y > target - 6:
        game.flap()
    game.update(FRAME)
    if game.pipes:
        spawned_ever = True
    max_score = max(max_score, game.score)

check("pipes spawn during play", spawned_ever)
check("scoring works (score climbed)", max_score >= 3)
print("   autopilot reached score:", max_score, "final state:", game.state)

# --- 5. difficulty ramps with score --------------------------------------
game.score = 0
gap0, speed0 = game._difficulty_gap(), game._difficulty_speed()
game.score = 30
gap1, speed1 = game._difficulty_gap(), game._difficulty_speed()
check("gap shrinks as score rises", gap1 < gap0)
check("speed rises as score rises", speed1 > speed0)
check("gap never goes below the floor", game._difficulty_gap() >= game.MIN_GAP)
game.score = 999
check("gap clamps at MIN_GAP", abs(game._difficulty_gap() - game.MIN_GAP) < 1e-9)

# --- 6. collision ends the run and records a best score -------------------
game.best = 0                 # clear whatever the autopilot above recorded
STORE.clear()
game.reset_game()
game.state = "playing"
game.score = 7
game.bird_y = 300
game.pipes = [{"x": game.BIRD_X - 20, "gap_y": 0.0, "gap_h": 100.0, "scored": False}]
game.update(FRAME)
check("pipe collision ends the game", game.state == "over")
check("best score updated to 7", game.best == 7)
check("best score persisted to storage", STORE.get("khelo_best") == "7")
check("impact sound played", ("sound", "hit") in CALLS)

# --- 7. ground collision ends the run ------------------------------------
game.reset_game()
game.state = "playing"
game.bird_y = game.PLAY_H - game.BIRD_R + 1
game.pipes = []
game.update(FRAME)
check("ground collision ends the game", game.state == "over")

# --- 8. tap after game over restarts -------------------------------------
game.flap()
check("flap after game over restarts into playing", game.state == "playing")

# --- 9. culling ----------------------------------------------------------
game.reset_game()
game.state = "playing"
game.pipes = [{"x": -200.0, "gap_y": 100.0, "gap_h": 150.0, "scored": True}]
game.update(FRAME)
check("offscreen pipes are culled", len(game.pipes) == 0)

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
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("All checks passed.")

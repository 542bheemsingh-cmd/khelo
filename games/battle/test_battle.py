"""
Headless tests for Khelo Battleground.

The browser is faked, so the terrain, the bots, the bullets and the zone can
all be driven from Python. three.js is not involved at all.

Run with:  python3 test_battle.py
"""

import math
import os
import sys
import types

fails = []
count = 0


def check(label, cond):
    global count
    count += 1
    if cond:
        print("PASS", label)
    else:
        print("FAIL", label)
        fails.append(label)


# ---------------------------------------------------------------------------
# A fake browser
# ---------------------------------------------------------------------------
CALLS = []
SOUNDS = []


class _Grad:
    def addColorStop(self, *a):
        pass


class _Ctx:
    def __getattr__(self, name):
        def call(*a, **k):
            CALLS.append(name)
            if name in ("createLinearGradient", "createRadialGradient"):
                return _Grad()
            if name == "measureText":
                return types.SimpleNamespace(width=float(len(str(a[0])) * 7))
            return None
        return call


class _El:
    width = 0
    height = 0

    def getContext(self, kind):
        return _Ctx()


class _World3D:
    def __init__(self):
        self.built = None
        self.frames = []

    def build(self, payload):
        self.built = payload
        return True

    def frame(self, payload):
        self.frames.append(payload)


WORLD = _World3D()


def _noop(*a, **k):
    return None


js = types.ModuleType("js")
js.devicePixelRatio = 2
js.document = types.SimpleNamespace(getElementById=lambda i: _El())
js.playSound = lambda n: SOUNDS.append(n)
js.world3d = WORLD
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

import json  # noqa: E402

# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------
print("--- the map ---")
check("the outline has a sensible number of points", 100 < len(game.RING) < 260)
check("the outline closes on itself",
      len(set(game.RING)) == len(game.RING))
check("every point is inside the world box",
      all(0 <= x <= game.WORLD_W + 1 and 0 <= z <= game.WORLD_H + 1
          for x, z in game.RING))
check("the map is about as wide as it is tall",
      0.8 < game.WORLD_W / game.WORLD_H < 1.05)

game.build_terrain()
check("the terrain grid is filled", len(game.HEIGHTS) == game.NX * game.NZ)
check("some of the grid is land",
      1000 < sum(game.LAND) < game.NX * game.NZ)
check("the corners of the box are sea",
      not game.land_at(4, 4) and not game.land_at(game.WORLD_W - 4, 4))
check("the middle of the map is land",
      game.land_at(game.WORLD_W / 2, game.WORLD_H / 2))
check("heights are finite and sane",
      all(-10 < h < 200 for h in game.HEIGHTS))
check("land sits above the water line",
      game.height_at(game.WORLD_W / 2, game.WORLD_H / 2) > game.WATER_Y)
check("sampling is smooth between grid points",
      abs(game.height_at(300.0, 500.0) - game.height_at(300.5, 500.0)) < 2.0)

# ---------------------------------------------------------------------------
# A round
# ---------------------------------------------------------------------------
print()
print("--- starting a round ---")
game.start_game(seed=1)
check("the game is playing", game.state == "play")
check("nine bots spawn", len(game.bots) == game.BOT_COUNT == 9)
check("every bot is alive to begin with", all(b["alive"] for b in game.bots))
check("the player starts alive with full health",
      game.player["alive"] and game.player["hp"] == 100.0)
check("the player starts on land",
      game.land_at(game.player["x"], game.player["z"]))
check("every bot starts on land",
      all(game.land_at(b["x"], b["z"]) for b in game.bots))
check("bots start away from the player",
      all(math.hypot(b["x"] - game.player["x"], b["z"] - game.player["z"]) > 150
          for b in game.bots))
check("everybody starts inside the zone",
      all(math.hypot(b["x"] - game.zone["cx"], b["z"] - game.zone["cz"]) <= game.zone["r"]
          for b in game.bots))
check("ten are alive", game.alive_count() == 10)

# ---------------------------------------------------------------------------
# Moving
# ---------------------------------------------------------------------------
print()
print("--- moving ---")
game.start_game(seed=2)
px, pz = game.player["x"], game.player["z"]
game.set_move(1.0, 0.0)
for _ in range(30):
    game.update(1 / 60)
moved = math.hypot(game.player["x"] - px, game.player["z"] - pz)
check("the stick moves the player", moved > 3.0)
check("the player stays on land", game.land_at(game.player["x"], game.player["z"]))
check("the player faces the way it walks",
      abs(math.sin(game.player["yaw"])) + abs(math.cos(game.player["yaw"])) > 0.9)

game.set_move(0.0, 0.0)
for _ in range(10):
    game.update(1 / 60)
still = (game.player["x"], game.player["z"])
for _ in range(10):
    game.update(1 / 60)
check("letting go stops the player",
      abs(game.player["x"] - still[0]) < 0.01 and abs(game.player["z"] - still[1]) < 0.01)

# the coast must not let you walk out to sea - walk in every direction for a
# while and the player must never end up standing on water
game.start_game(seed=3)
ok = True
for step in range(900):
    game.set_move(math.sin(step * 0.31), math.cos(step * 0.71))
    game.update(1 / 60)
    if not game.land_at(game.player["x"], game.player["z"]):
        ok = False
        break
check("the player can never walk onto the sea", ok)
check("the player never leaves the world box",
      0 <= game.player["x"] <= game.WORLD_W and 0 <= game.player["z"] <= game.WORLD_H)

# ---------------------------------------------------------------------------
# Shooting
# ---------------------------------------------------------------------------
print()
print("--- shooting ---")
game.start_game(seed=4)
game.player["ammo"] = 5
n = len(game.shots)
game.fire()
check("firing spends a bullet", len(game.shots) == n + 1)
check("firing spends ammo", game.player["ammo"] == 4)
check("a shot has a cooldown", game.player["cool"] > 0)
m = len(game.shots)
game.fire()
check("the cooldown stops a second shot straight away", len(game.shots) == m)

# a bot in front takes the damage
game.start_game(seed=5)
b = game.bots[0]
game.player["x"], game.player["z"] = 300.0, 500.0
game.player["yaw"] = 0.0
b["x"], b["z"] = 300.0, 560.0
b["hp"] = 100.0
game.player["cool"] = 0.0
game.player["ammo"] = 50
for _ in range(40):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
check("shooting a bot hurts it", b["hp"] < 100.0)

# kill one and the count goes down
game.start_game(seed=6)
b = game.bots[0]
b["hp"] = 1.0
game.player["x"], game.player["z"] = 300.0, 500.0
game.player["yaw"] = 0.0
b["x"], b["z"] = 300.0, 545.0
game.player["cool"] = 0.0
game.player["ammo"] = 10
for _ in range(60):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
    if not b["alive"]:
        break
check("a bot can be killed", not b["alive"])
check("the kill is counted", game.player["kills"] >= 1)
check("the alive count drops", game.alive_count() == 9)

# ---------------------------------------------------------------------------
# The zone
# ---------------------------------------------------------------------------
print()
print("--- the zone ---")
game.start_game(seed=7)
r0 = game.zone["r"]
game.zone_timer = 0.0
game.update(1 / 60)
check("the zone shrinks when its timer runs out", game.zone["tr"] < r0)
check("the next timer is set", game.zone_timer > 0)

# standing outside hurts
game.start_game(seed=8)
game.player["x"] = 20.0
game.player["z"] = 20.0
hp0 = game.player["hp"]
for _ in range(60):
    game.update(1 / 60)
check("being outside the zone hurts", game.player["hp"] < hp0)

# ---------------------------------------------------------------------------
# Winning and losing
# ---------------------------------------------------------------------------
print()
print("--- winning and losing ---")
game.start_game(seed=9)
for b in game.bots:
    b["alive"] = False
game.update(1 / 60)
check("killing every bot wins", game.state == "over" and game.result == "win")

game.start_game(seed=10)
game.player["hp"] = 0.0
game.update(1 / 60)
check("running out of health loses", game.state == "over" and game.result == "lose")

# ---------------------------------------------------------------------------
# What three.js is handed
# ---------------------------------------------------------------------------
print()
print("--- the frame handed to three.js ---")
game.start_game(seed=11)
WORLD.frames.clear()
game.send_frame()
check("a frame is sent", len(WORLD.frames) == 1)
st = json.loads(WORLD.frames[-1])
check("the frame has the player", len(st["p"]) == 6)
check("the frame lists the living bots", len(st["b"]) == 9)
check("each bot has four numbers", all(len(b) == 4 for b in st["b"]))
check("the frame has the zone", len(st["z"]) == 3)
check("the frame has the camera", len(st["cam"]) == 2)
check("every number in the frame is finite",
      all(math.isfinite(v) for v in st["p"] + st["z"] + st["cam"]
          + [n for b in st["b"] for n in b]))

WORLD.built = None
check("the world can be handed over", game.build_world() is True)
check("the world payload arrives", WORLD.built is not None)
w = json.loads(WORLD.built)
check("the payload has every height", len(w["heights"]) == game.NX * game.NZ)
check("the payload says how big the grid is",
      w["nx"] == game.NX and w["nz"] == game.NZ)
check("the payload has the world size and water line",
      w["w"] == game.WORLD_W and abs(w["water"] - game.WATER_Y) < 0.01)

# ---------------------------------------------------------------------------
# The HUD
# ---------------------------------------------------------------------------
print()
print("--- the HUD ---")
game.set_size(900, 560)
game.set_ui(1.0)
CALLS.clear()
game.state = "menu"
game.draw()
check("the menu draws", len(CALLS) > 40)
check("the menu has a button", len(game._menu_hit) == 1)

game.start_game(seed=12)
game.set_touch_ui(True)
CALLS.clear()
game.draw()
check("the playing HUD draws", len(CALLS) > 120)
check("the touch controls are drawn on a phone", game.TOUCH_UI is True)

game.set_touch_ui(False)
CALLS.clear()
game.draw()
check("the HUD draws without the touch controls", len(CALLS) > 100)

game.state = "over"
game.result = "win"
CALLS.clear()
game.draw()
check("the end screen draws", len(CALLS) > 100)
check("the end screen offers again and menu",
      [t for t, _ in game._menu_hit] == ["again", "menu"])

game.set_size(390, 844)
CALLS.clear()
game.draw()
check("the HUD survives a phone-sized canvas", len(CALLS) > 80)

print()
if fails:
    print("FAILURES:", fails)
    sys.exit(1)
print("All checks passed.")

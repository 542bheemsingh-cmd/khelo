"""
Headless tests for Khelo Battleground.

The browser is faked, so the terrain, the bots, the bullets and the zone can
all be driven from Python. three.js is not involved at all.

Run with:  python3 test_battle.py
"""

import math
import os
import random
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
_STORE = {}
js.localStorage = types.SimpleNamespace(
    getItem=lambda k: _STORE.get(k),
    setItem=lambda k, v: _STORE.__setitem__(k, v))
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

import json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def open_spot(clear=80.0, seed=99):
    """Open ground with a clear run along +z, for a bot and for walking."""
    r = random.Random(seed)
    for _ in range(1500):
        x = r.uniform(240.0, game.WORLD_W - 240.0)
        z = r.uniform(240.0, game.WORLD_H - 320.0)
        # the whole approach has to be free, not just the two ends
        if any(game.blocked(x, z + k) for k in range(0, int(max(clear, 150.0)) + 1, 10)):
            continue
        if any(game.blocked(x + k, z) for k in (-30, 0, 30, 60)):
            continue
        return x, z
    return game.WORLD_W / 2, game.WORLD_H / 2


def begin(seed=None):
    """Start a round and get the soldier on the ground, past the plane drop."""
    game.start_game(seed=seed)
    game.jump()
    for _ in range(6000):
        game.update(1 / 60)
        if game.state == "play":
            break
    return game





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
begin(seed=1)
check("the game is playing", game.state == "play")
check("twelve bots spawn", len(game.bots) == game.BOT_COUNT == 12)
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
check("thirteen are alive", game.alive_count() == 13)

# ---------------------------------------------------------------------------
# Moving
# ---------------------------------------------------------------------------
print()
print("--- moving ---")
begin(seed=2)
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
for _ in range(60):
    game.update(1 / 60)
still = (game.player["x"], game.player["z"])
for _ in range(20):
    game.update(1 / 60)
check("letting go brings the player to rest",
      abs(game.player["x"] - still[0]) < 0.05 and abs(game.player["z"] - still[1]) < 0.05)
check("the player really has stopped", math.hypot(game.pvx, game.pvz) < 0.2)

# the coast must not let you walk out to sea - walk in every direction for a
# while and the player must never end up standing on water
begin(seed=3)
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
begin(seed=4)
game.mag = 5
n = len(game.shots)
game.fire()
check("firing spends a bullet", len(game.shots) == n + 1)
check("firing spends a round", game.mag == 4)
check("a shot has a cooldown", game.player["cool"] > 0)
m = len(game.shots)
game.fire()
check("the cooldown stops a second shot straight away", len(game.shots) == m)

# a bot in front takes the damage
begin(seed=5)
b = game.bots[0]
_ax, _az = open_spot(80.0, 5)
game.player["x"], game.player["z"] = _ax, _az
game.player["yaw"] = 0.0
game.cam_yaw = 0.0
b["x"], b["z"] = _ax, _az + 60.0
b["hp"] = 100.0
game.player["cool"] = 0.0
game.mag = 50
for _ in range(40):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
check("shooting a bot hurts it", b["hp"] < 100.0)

# kill one and the count goes down
begin(seed=6)
b = game.bots[0]
b["hp"] = 1.0
_ax, _az = open_spot(70.0, 6)
game.player["x"], game.player["z"] = _ax, _az
game.player["yaw"] = 0.0
game.cam_yaw = 0.0
b["x"], b["z"] = _ax, _az + 45.0
game.player["cool"] = 0.0
game.mag = 10
for _ in range(60):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
    if not b["alive"]:
        break
check("a bot can be killed", not b["alive"])
check("the kill is counted", game.player["kills"] >= 1)
check("the alive count drops", game.alive_count() == 12)

# ---------------------------------------------------------------------------
# Which way is which
# ---------------------------------------------------------------------------
print()
print("--- which way is which ---")

# with cam_yaw 0 the camera looks along +z, so the screen's right is -x
begin(seed=30)
game.cam_yaw = 0.0
game.player["yaw"] = 0.0
_dx, _dz = open_spot(90.0, 30)
game.player["x"], game.player["z"] = _dx, _dz
x0, z0 = game.player["x"], game.player["z"]
game.set_move(1.0, 0.0)                 # D
for _ in range(40):
    game.update(1 / 60)
check("D moves to the right of the screen", game.player["x"] < x0 - 2.0)
check("D does not sneak forwards", abs(game.player["z"] - z0) < 1.0)

begin(seed=31)
game.cam_yaw = 0.0
game.player["yaw"] = 0.0
_dx, _dz = open_spot(90.0, 30)
game.player["x"], game.player["z"] = _dx, _dz
x0, z0 = game.player["x"], game.player["z"]
game.set_move(-1.0, 0.0)                # A
for _ in range(40):
    game.update(1 / 60)
check("A moves to the left of the screen", game.player["x"] > x0 + 2.0)

begin(seed=32)
game.cam_yaw = 0.0
game.player["yaw"] = 0.0
_dx, _dz = open_spot(90.0, 31)
game.player["x"], game.player["z"] = _dx, _dz
z0 = game.player["z"]
game.set_move(0.0, 1.0)                 # W
for _ in range(40):
    game.update(1 / 60)
check("W walks forwards", game.player["z"] > z0 + 2.0)

# the soldier has weight: it ramps up to speed and eases back down
begin(seed=33)
game.set_move(1.0, 0.0)
game.update(1 / 60)
v1 = math.hypot(game.pvx, game.pvz)
for _ in range(30):
    game.update(1 / 60)
v2 = math.hypot(game.pvx, game.pvz)
check("the soldier speeds up instead of snapping", v1 < v2 * 0.7)
check("it reaches its top speed", abs(v2 - game.PLAYER_SPEED) < 1.5)
game.set_move(0.0, 0.0)
for _ in range(6):
    game.update(1 / 60)
v3 = math.hypot(game.pvx, game.pvz)
check("letting go slows it down", v3 < v2 * 0.7)

# ---------------------------------------------------------------------------
# Shooting feedback
# ---------------------------------------------------------------------------
print()
print("--- shooting feedback ---")
begin(seed=34)
game.cam_yaw = 0.0
_ax, _az = open_spot(70.0, 34)
game.player["x"], game.player["z"] = _ax, _az
b = game.bots[0]
b["x"], b["z"] = _ax + 4.0, _az + 48.0
b["hp"] = 100.0
game.player["cool"] = 0.0
game.mag = 40
for _ in range(80):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
    if b["hp"] < 100.0:
        break
check("a hit puts a marker on the crosshair", game.hitmark > 0)
check("a hit throws sparks", len(game.hits) > 0)

for _ in range(120):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
    if not b["alive"]:
        break
check("a downed bot leaves a body for a moment", b.get("dying", 0) > 0)
check("the kill lands in the feed",
      any("downed" in f["text"] for f in game.feed))

# ---------------------------------------------------------------------------
# The zone
# ---------------------------------------------------------------------------
print()
print("--- the zone ---")
begin(seed=7)
r0 = game.zone["r"]
game.zone_timer = 0.0
game.update(1 / 60)
check("the zone shrinks when its timer runs out", game.zone["tr"] < r0)
check("the next timer is set", game.zone_timer > 0)

# standing outside hurts - shrink the zone onto the middle first
begin(seed=8)
check("the first zone covers the whole map",
      game.zone["r"] >= math.hypot(game.WORLD_W / 2, game.WORLD_H / 2))
game.zone["r"] = game.zone["tr"] = 200.0
game.zone["cx"] = game.zone["tx"] = game.WORLD_W / 2
game.zone["cz"] = game.zone["tz"] = game.WORLD_H / 2
game.player["x"], game.player["z"] = 60.0, 60.0
hp0 = game.player["hp"]
for _ in range(60):
    game.update(1 / 60)
check("being outside the zone hurts", game.player["hp"] < hp0)

# ---------------------------------------------------------------------------
# Winning and losing
# ---------------------------------------------------------------------------
print()
print("--- winning and losing ---")
begin(seed=9)
for b in game.bots:
    b["alive"] = False
game.update(1 / 60)
check("killing every bot wins", game.state == "over" and game.result == "win")

begin(seed=10)
game.player["hp"] = 0.0
game.update(1 / 60)
check("running out of health loses", game.state == "over" and game.result == "lose")

# ---------------------------------------------------------------------------
# What three.js is handed
# ---------------------------------------------------------------------------
print()
print("--- the frame handed to three.js ---")
begin(seed=11)
WORLD.frames.clear()
game.send_frame()
check("a frame is sent", len(WORLD.frames) == 1)
st = json.loads(WORLD.frames[-1])
check("the frame has the player and its speed", len(st["p"]) == 7)
check("the frame lists the living bots", len(st["b"]) == 12)
check("each bot carries health, a dying timer, a grade and a flash",
      all(len(b) == 8 for b in st["b"]))
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
# Aiming and looking
# ---------------------------------------------------------------------------
print()
print("--- aiming and looking ---")
begin(seed=20)
game.cam_yaw = 0.0
for _ in range(40):
    game.update(1 / 60)
check("the soldier faces where you aim",
      abs(game.player["yaw"] - 0.0) < 0.02)

game.cam_yaw = 0.9
for _ in range(40):
    game.update(1 / 60)
check("turning the camera turns the soldier",
      abs(game.player["yaw"] - 0.9) < 0.02)

# a shot must follow the camera, not wherever the soldier last walked
begin(seed=21)
game.cam_yaw = 1.2
_ax, _az = open_spot(80.0, 21)
game.player["x"], game.player["z"] = _ax, _az
for b in game.bots:
    b["x"], b["z"] = _ax - 900.0, _az - 900.0   # all far outside the aim cone
game.player["cool"] = 0.0
game.mag = 20
game.shots = []
game.fire()
shot = game.shots[-1]
ang = math.atan2(shot["dx"], shot["dz"])
check("a shot follows the camera, not the last step",
      abs(ang - 1.2) < 0.03)

# the aim assist still lands hits on something in front of you
begin(seed=22)
game.cam_yaw = 0.0
_ax, _az = open_spot(70.0, 22)
game.player["x"], game.player["z"] = _ax, _az
b = game.bots[0]
b["x"], b["z"] = _ax + 6.0, _az + 50.0
b["hp"] = 100.0
game.player["cool"] = 0.0
game.mag = 40
for _ in range(80):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
    if b["hp"] < 100.0:
        break
check("something in front of the crosshair gets hit", b["hp"] < 100.0)

# dragging must swing the aim toward the side you dragged. the screen-right
# direction at yaw 0 is (-1, 0), so the aim has to gain -x to have gone right.

def _aim_after(drag_x, drag_y, seed):
    begin(seed=seed)
    game.cam_yaw = 0.0
    game.player["yaw"] = 0.0
    game.set_look(drag_x, drag_y)
    for _ in range(30):
        game.update(1 / 60)
    return (math.sin(game.cam_yaw), math.cos(game.cam_yaw))

right = (-1.0, 0.0)                       # screen-right at yaw 0
fwd = _aim_after(0.4, 0.0, 60)
check("dragging right swings the aim to the right of the screen",
      fwd[0] * right[0] + fwd[1] * right[1] > 0.05)

fwd = _aim_after(-0.4, 0.0, 61)
check("dragging left swings the aim to the left of the screen",
      fwd[0] * right[0] + fwd[1] * right[1] < -0.05)

# and it has to hold at other headings too, not just due north
for seed, start in ((62, 1.0), (63, 2.4), (64, -1.7)):
    begin(seed=seed)
    game.cam_yaw = start
    game.player["yaw"] = start
    before = (math.sin(start), math.cos(start))
    r0 = (-math.cos(start), math.sin(start))     # screen right at that heading
    game.set_look(0.35, 0.0)
    for _ in range(30):
        game.update(1 / 60)
    after = (math.sin(game.cam_yaw), math.cos(game.cam_yaw))
    check("a right drag turns right at heading %.1f" % start,
          after[0] * r0[0] + after[1] * r0[1] > 0.04)

p0 = game.cam_pitch
game.set_look(0.0, 0.4)
game.update(1 / 60)
check("dragging down looks down", game.cam_pitch > p0)

p1 = game.cam_pitch
game.set_look(0.0, -0.4)
game.update(1 / 60)
check("dragging up looks up", game.cam_pitch < p1)

# the pitch stays inside its limits however hard you drag
for _ in range(40):
    game.set_look(0.0, 1.0)
    game.update(1 / 60)
check("the camera never flips over the top", game.cam_pitch <= 0.96)
for _ in range(80):
    game.set_look(0.0, -1.0)
    game.update(1 / 60)
check("the camera never goes under the ground", game.cam_pitch >= 0.05)

# the on-screen stick remembers where the thumb is
game.set_stick(120, 400, True)
check("the stick knows where the thumb landed",
      game.STICK["on"] and game.STICK["x"] == 120 and game.STICK["y"] == 400)
game.set_stick(0, 0, False)
check("the stick can be let go", not game.STICK["on"])

# the fire button sits where the page looks for it
game.set_size(900, 560)
fx, fy, fr = game.fire_button()
check("the fire button is bottom-right",
      fx > game.W * 0.75 and fy > game.H * 0.75)
check("the fire button is big enough for a thumb", fr >= 56)

# ---------------------------------------------------------------------------
# The new kit: sprint, crouch, reload, weapons, crates, pause
# ---------------------------------------------------------------------------
print()
print("--- sprint, crouch and the rest ---")

def run(frames, setup=None):
    for _ in range(frames):
        if setup:
            setup()
        game.update(1 / 60)

# sprint covers more ground and burns stamina
begin(seed=40)
_dx, _dz = open_spot(90.0, 40)
game.player["x"], game.player["z"] = _dx, _dz
game.cam_yaw = 0.0
game.set_move(0.0, 1.0)
run(50)
walked = abs(game.player["z"] - _dz)
begin(seed=40)
_dx, _dz = open_spot(90.0, 41)
game.player["x"], game.player["z"] = _dx, _dz
game.cam_yaw = 0.0
game.set_move(0.0, 1.0)
game.set_sprint(True)
run(50)
ran = abs(game.player["z"] - _dz)
check("sprinting covers more ground", ran > walked * 1.25)
check("sprinting burns stamina", game.stamina < 100.0)
game.set_sprint(False)
run(120)
check("stamina comes back", game.stamina > 30.0)

# crouching is slower
begin(seed=41)
_dx, _dz = open_spot(90.0, 42)
game.player["x"], game.player["z"] = _dx, _dz
game.cam_yaw = 0.0
game.set_move(0.0, 1.0)
game.set_crouch(True)
run(50)
crept = abs(game.player["z"] - _dz)
check("crouching is slower than walking", crept < walked * 0.75)
check("crouching is remembered", game.crouching is True)
game.set_crouch(False)

# reloading refills the magazine
begin(seed=42)
game.mag = 3
game.set_reload()
check("reloading starts", game.reloading > 0)
run(140)
check("the magazine is full again", game.mag == game.WEAPONS["rifle"]["mag"])
check("reloading has finished", game.reloading == 0.0)

# an empty magazine reloads itself
begin(seed=43)
game.mag = 1
game.player["cool"] = 0.0
game.reloading = 0.0
game.fire()
check("the last round triggers a reload", game.reloading > 0)

# weapon swap
begin(seed=44)
check("you start with the rifle", game.weapon == "rifle")
game.set_swap()
check("swapping gives the shotgun", game.weapon == "shotgun")
check("the shotgun has its own magazine",
      game.mag == game.WEAPONS["shotgun"]["mag"])
game.set_swap()
check("swapping back gives the rifle", game.weapon == "rifle")

# the shotgun throws more pellets
begin(seed=45)
game.set_swap()
game.shots = []
game.player["cool"] = 0.0
game.reloading = 0.0
game.fire()
check("the shotgun fires a spread", len(game.shots) == 6)

# crates can be picked up
begin(seed=46)
game.pickups = [{"x": game.player["x"] + 2.0, "z": game.player["z"],
                 "kind": "health", "taken": False}]
game.player["hp"] = 40.0
game.update(1 / 60)
check("a medkit heals you", game.player["hp"] > 40.0)
check("the crate is used up", game.pickups[0]["taken"] is True)

begin(seed=47)
game.pickups = [{"x": game.player["x"] + 2.0, "z": game.player["z"],
                 "kind": "ammo", "taken": False}]
game.mag = 2
game.update(1 / 60)
check("an ammo crate refills the magazine", game.mag > 2)

# dying gives you a placement
begin(seed=48)
game.player["hp"] = 0.0
game.update(1 / 60)
check("dying records where you finished", game.placement >= 2)

# pausing freezes the world
begin(seed=49)
game.set_pause(True)
check("the game can be paused", game.paused is True)
px, pz = game.player["x"], game.player["z"]
game.set_move(1.0, 0.0)
run(30)
check("nothing moves while paused",
      abs(game.player["x"] - px) < 1e-9 and abs(game.player["z"] - pz) < 1e-9)
game.set_pause(False)
check("the game can be unpaused", game.paused is False)

# the new bits reach the renderer
begin(seed=50)
st = json.loads(game._frame_json())
check("the frame carries crates", "pk" in st)
check("the frame carries damage numbers", "dn" in st)
check("the frame carries screen shake", "sh" in st)
check("the frame carries the crouch state", "crouch" in st)

# ---------------------------------------------------------------------------
# Regressions: bugs that were found by the audit and fixed
# ---------------------------------------------------------------------------
print()
print("--- regressions ---")

# the first zone has to cover the map, or people spawn outside and bleed out
begin(seed=70)
check("the opening zone reaches every corner",
      game.zone["r"] >= math.hypot(game.WORLD_W / 2, game.WORLD_H / 2))

# swapping weapons must not be a free reload
begin(seed=71)
game.mag = 3
game.set_swap()
game.set_swap()
check("swapping weapons keeps what is left in the magazine", game.mag == 3)

# the pause key must be able to let you out
begin(seed=72)
game.set_pause(True)
check("pause stops the game", game.paused is True)
game.set_pause(True)
check("pausing again lets you back out", game.paused is False)

# the third button on the end screen needs a hit box
game.state = "over"
game.result = "win"
game.set_size(900, 560)
game.draw()
check("the arcade button can be tapped",
      "arcade" in [t for t, _ in game._menu_hit])

# placement has to be on screen, not just in a variable
_src = open(os.path.join(HERE, "game.py"), encoding="utf-8").read()
_over = _src[_src.index("def _draw_over"):]
_over = _over[:_over.index("def _draw_pause") if "def _draw_pause" in _over else len(_over)]
check("the end screen shows where you finished", "placement" in _over)

# a building has to stop a bullet, not just a person
begin(seed=73)
_ax, _az = open_spot(80.0, 73)
game.player["x"], game.player["z"] = _ax, _az
game.cam_yaw = 0.0
_b = game.bots[0]
_b["x"], _b["z"] = _ax, _az + 60.0
_b["hp"] = 100.0
game.BUILDINGS.append([_ax, _az + 30.0, 44.0, 14.0, 12.0, 0.0])
game._index_buildings()
game.player["cool"] = 0.0
game.reloading = 0.0
game.mag = 30
for _ in range(90):
    game.player["cool"] = 0.0
    game.fire()
    game.update(1 / 60)
check("a wall stops a bullet", _b["hp"] == 100.0)

# and a building has to stop a person
check("a wall stops the player", game.blocked(_ax, _az + 30.0) is True)
check("the wall does not block the whole map",
      game.blocked(_ax, _az) is False)

game.BUILDINGS.pop()
game._index_buildings()
check("removing the wall reopens the ground",
      game.blocked(_ax, _az + 30.0) is False)

# the renderer needs a slot for every crate the game makes
_html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
import re as _re
_m = _re.search(r"for \(let i = 0; i < (\d+); i\+\+\) \{\s*const h = new THREE\.Mesh\(crateGeo", _html)
check("the renderer has a slot for every crate",
      bool(_m) and int(_m.group(1)) >= len(game.pickups))

# a bot that died must not stay invisible next round
check("a dead bot's materials are made opaque again",
      "o.material.opacity = 1" in _html)

# and the crouch key must not drift out of step between rounds
check("the page clears its crouch flag between rounds",
      "crouchOn = false" in _html)

# the camera must not sit inside a building
check("the camera knows about buildings", "blockPos" in _html)

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
check("the menu draws", len(CALLS) >= 2)
check("the menu has no buttons to hunt for", len(game._menu_hit) == 0)

game.state = "menu"
game.tap(40.0, 40.0)
check("a tap anywhere drops you in", game.state == "plane")

begin(seed=12)
game.set_touch_ui(True)
CALLS.clear()
game.draw()
check("the playing HUD draws", len(CALLS) > 70)
check("the touch controls are drawn on a phone", game.TOUCH_UI is True)

game.set_touch_ui(False)
CALLS.clear()
game.draw()
check("the HUD draws without the touch controls", len(CALLS) > 60)

game.state = "over"
game.result = "win"
CALLS.clear()
game.draw()
check("the end screen draws", len(CALLS) > 100)
check("the end screen offers again, menu and the arcade",
      [t for t, _ in game._menu_hit] == ["again", "menu", "arcade"])

game.set_size(390, 844)
CALLS.clear()
game.draw()
check("the HUD survives a phone-sized canvas", len(CALLS) > 80)

# --- regression: the compass used to call south "N" ------------------------
print()
print("--- compass and minimap arrow agree ---")
for yaw_deg, want in ((0, 180), (90, 90), (180, 0), (270, 270)):
    game.cam_yaw = math.radians(yaw_deg)
    got = game.compass_bearing()
    check("yaw %d points to bearing %d (got %.0f)" % (yaw_deg, want, got),
          abs(((got - want + 180) % 360) - 180) < 0.5)

game.cam_yaw = math.pi
check("facing north reads as 0 degrees", abs(game.compass_bearing()) < 0.5)

# ---------------------------------------------------------------------------
# The drop: plane, jump, parachute, land
# ---------------------------------------------------------------------------
print()
print("--- the drop ---")
game.start_game(seed=90)
check("a round opens in the plane", game.state == "plane")
check("the plane starts outside the map",
      not (0 <= game.plane["x"] < game.WORLD_W and 0 <= game.plane["z"] < game.WORLD_H))

x0, z0 = game.plane["x"], game.plane["z"]
for _ in range(30):
    game.update(1 / 60)
check("the plane flies",
      math.hypot(game.plane["x"] - x0, game.plane["z"] - z0) > 40.0)

game.jump()
check("jumping starts the fall", game.state == "fall")
check("you start high up", game.player["y"] is not None and game.player["y"] > 250.0)
check("the canopy is shut at first", game.chute is False)

saw_chute = False
for _ in range(6000):
    game.update(1 / 60)
    if game.chute:
        saw_chute = True
    if game.state == "play":
        break
check("the parachute opens on the way down", saw_chute)
check("you land and the round begins", game.state == "play")
check("you land on dry ground",
      game.land_at(game.player["x"], game.player["z"]))
check("your feet are back on the ground", game.player["y"] is None)

# the flight is different every round
paths = set()
for sd in (91, 92, 93, 94):
    game.start_game(seed=sd)
    paths.add((round(game.plane["x"] / 50), round(game.plane["z"] / 50)))
check("every round flies a different line", len(paths) >= 3)

# --- the circle, and what the bots do about it ---------------------------
print()
print("--- the circle ---")
begin(seed=50)
game.zone["cx"] = game.zone["tx"] = game.WORLD_W * 0.5
game.zone["cz"] = game.zone["tz"] = game.WORLD_H * 0.5
game.zone["r"] = game.zone["tr"] = 120.0

outside = [b for b in game.bots
           if math.hypot(b["x"] - game.zone["cx"], b["z"] - game.zone["cz"]) > 120]
check("some bots are outside the circle", len(outside) > 0)
before = [(b["x"], b["z"], math.hypot(b["x"] - game.zone["cx"],
                                      b["z"] - game.zone["cz"])) for b in outside]
for _ in range(120):
    game.update(1 / 60)
closer = 0
for b, (bx, bz, bd) in zip(outside, before):
    nd = math.hypot(b["x"] - game.zone["cx"], b["z"] - game.zone["cz"])
    if nd < bd - 1.0:
        closer += 1
check("bots outside the circle run for it", closer >= max(1, len(outside) // 2))

# the new circle is always put on dry land
begin(seed=51)
wet = 0
for _ in range(10):
    game.zone_timer = 0.0
    game.update(1 / 60)
    if not game.land_at(game.zone["tx"], game.zone["tz"]):
        wet += 1
check("the next circle is always on land", wet == 0)

# the minimap shows where the circle is going
game.zone["tr"] = game.zone["r"] * 0.5
CALLS.clear()
game.set_size(900, 560)
game.draw()
check("the next circle is drawn on the map",
      any(c in ("setLineDash", "arc") for c in CALLS))

# --- gunfire shows up on the map -----------------------------------------
print()
print("--- gunfire on the map ---")
begin(seed=60)
game.pings[:] = []
game.zone["r"] = game.zone["tr"] = 9000.0        # keep the circle out of it
b = game.bots[0]
b["x"], b["z"] = game.player["x"] + 40.0, game.player["z"] + 40.0
b["cool"] = 0.0
b["hp"] = 100.0
fired = False
for _ in range(180):
    b["cool"] = 0.0
    game.update(1 / 60)
    if game.pings:
        fired = True
        break
check("a bot shooting leaves a mark on the map", fired)
check("the mark is where the bot is",
      math.hypot(game.pings[0]["x"] - b["x"], game.pings[0]["z"] - b["z"]) < 60.0)

# and the marks fade away again
for _ in range(200):
    game.update(1 / 60)
    b["cool"] = 99.0
check("the marks fade away", len(game.pings) == 0)

# --- the record carries over between rounds ------------------------------
print()
print("--- your record ---")
game.stats.update({"matches": 0, "wins": 0, "best_kills": 0, "best_place": 0})
_STORE.clear()

begin(seed=70)
game.player["kills"] = 6
game.placement = 1
game.result = "win"
game.record_result()
check("a win counts as a match", game.stats["matches"] == 1)
check("a win counts as a win", game.stats["wins"] == 1)
check("the kills are remembered", game.stats["best_kills"] == 6)
check("the best placing is remembered", game.stats["best_place"] == 1)

game.player["kills"] = 2
game.placement = 5
game.result = "lose"
game.record_result()
check("a second match is counted", game.stats["matches"] == 2)
check("a loss is not a win", game.stats["wins"] == 1)
check("a worse round does not lower the best kills", game.stats["best_kills"] == 6)
check("a worse round does not lower the best placing", game.stats["best_place"] == 1)

game.player["kills"] = 11
game.placement = 2
game.record_result()
check("a better kill count is kept", game.stats["best_kills"] == 11)
check("the best placing still stands", game.stats["best_place"] == 1)

# and it survives a reload
game.stats.update({"matches": 0, "wins": 0, "best_kills": 0, "best_place": 0})
game._load_stats()
check("the record comes back after a reload", game.stats["best_kills"] == 11)
check("so do the match and win counts",
      game.stats["matches"] == 3 and game.stats["wins"] == 1)

# --- the end-screen buttons sit where they are drawn ---------------------
print()
print("--- end screen buttons ---")
game.state = "over"
game.result = "win"
game.placement = 1
game.set_size(900, 560)
game.draw()
src = open(os.path.join(HERE, "game.py"), encoding="utf-8").read()
over = src[src.index("def _draw_over"):]
over = over[:over.index("def _draw_pause")] if "def _draw_pause" in over else over
import re as _re
drawn = [int(m) for m in _re.findall(r"_button\([^,]+, cy \+ ch - (\d+)", over)]
hits = [int(m) for m in _re.findall(r'"\w+", \(cx \+ [^,]+, cy \+ ch - (\d+)', over)]
check("every button is drawn and hit-tested at the same spot",
      sorted(drawn) == sorted(hits) and len(drawn) == 3)

# --- the line under the compass does not sit there forever ----------------
print()
print("--- the message line ---")
begin(seed=80)
game.message = "A fresh line of text."
game.update(1 / 60)
check("a new line starts its timer", game.message_t > 4.0)
for _ in range(180):
    game.update(1 / 60)
check("it is still there after three seconds", game.message_t > 0.0)
for _ in range(150):
    game.update(1 / 60)
check("and then it fades away", game.message_t == 0.0)

# a new line gets its own timer
game.message = "Something else happened."
game.update(1 / 60)
check("a new line starts the timer again", game.message_t > 4.0)

# the HUD is one panel, not two boxes stacked up
CALLS.clear()
game.state = "play"
game.set_size(900, 560)
game.draw()
check("the HUD still draws", len(CALLS) > 30)

print()
if fails:
    print("FAILURES:", fails)
    sys.exit(1)
print("All checks passed.")

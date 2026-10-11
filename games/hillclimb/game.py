"""
Khelo Climb - a 2D hill-climb driving game written in Python.

Runs in the browser through Pyodide, same as the rest of the Khelo arcade.
Everything here is the game: the physics, the levels, the vehicles, the coins,
fuel, obstacles, the in-game HUD and the menu screen.

The page calls:

    update(dt)          -> advance the simulation
    draw()              -> render a frame
    tap(x, y)           -> a click/tap on the canvas (menu buttons)
    gas(True/False)     -> throttle on / off
    brake(True/False)   -> brake / reverse on / off
    enter_key()         -> Enter / Space shortcut
    playing()           -> True while actually driving (lets the page hide pedals)
"""

import json
import math
import random

import js

# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------
W, H = 900, 560

canvas = js.document.getElementById("game")
DPR = 1.0
try:
    DPR = float(js.devicePixelRatio or 1.0)
except Exception:
    DPR = 1.0
DPR = min(max(DPR, 1.0), 2.0)
canvas.width = int(W * DPR)
canvas.height = int(H * DPR)
ctx = canvas.getContext("2d")
ctx.scale(DPR, DPR)

# ---------------------------------------------------------------------------
# Physics constants
# ---------------------------------------------------------------------------
GRAVITY_DEFAULT = 2000.0
MAX_REVERSE = 210.0
ANG_DAMP = 30.0
ROLL_DRAG = 0.5
SUSP_K = 900.0          # suspension stiffness (softer -> smoother landings)
SUSP_D = 62.0           # suspension damping (absorbs the impact)
MAX_PEN = 12.0          # a wheel never sinks deeper than this
AIR_TORQUE = 55.0       # gas/brake pitch the car while airborne
WHEELIE_TORQUE = 12.0   # gas lifts the nose on the ground
CAM_UP_MAX = 220.0      # how far the camera may pan up on a big jump
GROUND_FRICTION = 1.1   # light rolling grip, scaled by each level's surface
FIXED = 1.0 / 120.0
START_X = 130.0
PIXELS_PER_METER = 50.0
HEAD_OFF = 34.0
FUEL_MAX = 100.0
FUEL_RATE = 6.0
COIN_VALUE = 5

# ---------------------------------------------------------------------------
# Levels / locations
# ---------------------------------------------------------------------------
LEVELS = [
    {
        "name": "Sunset Hills",
        "target": 250,
        "base": 380.0,
        "gravity": 2000.0,
        "terrain": [(60.0, 0.0032, 0.0), (30.0, 0.0071, 1.7), (12.0, 0.0165, 0.5)],
        "obstacle_rate": 620.0,
        "obstacles": ["rock", "log"],
        "friction": 1.0,
        "theme": {
            "sky": ["#142a63", "#4a6bd0", "#f4a15e", "#ffd28a"],
            "sun": "#fff0bd", "sun_glow": "rgba(255, 236, 170, 0.45)",
            "sun_pos": (700, 300),
            "hills": ["#2b3f86", "#3a56a6"],
            "dirt": "#5c4022", "grass": "#3fa34d",
        },
    },
    {
        "name": "Desert Dunes",
        "target": 380,
        "base": 360.0,
        "gravity": 2000.0,
        "terrain": [(92.0, 0.0026, 0.5), (40.0, 0.0055, 2.0), (14.0, 0.0130, 1.0)],
        "obstacle_rate": 520.0,
        "obstacles": ["rock", "log", "cactus", "ramp"],
        "friction": 0.92,
        "theme": {
            "sky": ["#2a3f7a", "#7a6bb0", "#f0a868", "#ffd9a0"],
            "sun": "#fff2c4", "sun_glow": "rgba(255, 220, 150, 0.5)",
            "sun_pos": (220, 250),
            "hills": ["#8a6a3a", "#a9854a"],
            "dirt": "#c08a4a", "grass": "#e0b06a",
        },
    },
    {
        "name": "Frozen Peaks",
        "target": 480,
        "base": 400.0,
        "gravity": 2000.0,
        "terrain": [(112.0, 0.0030, 1.0), (55.0, 0.0062, 0.3), (20.0, 0.0140, 2.5)],
        "obstacle_rate": 460.0,
        "obstacles": ["rock", "boulder", "ice", "ramp"],
        "friction": 0.55,
        "theme": {
            "sky": ["#0e2a4a", "#3f7fb5", "#a9d6ee", "#e8f6ff"],
            "sun": "#ffffff", "sun_glow": "rgba(220, 245, 255, 0.45)",
            "sun_pos": (720, 120),
            "hills": ["#4a6a8a", "#6a8aa8"],
            "dirt": "#7f95a8", "grass": "#eaf4ff",
        },
    },
    {
        "name": "Volcano Run",
        "target": 600,
        "base": 380.0,
        "gravity": 2100.0,
        "terrain": [(132.0, 0.0034, 2.0), (70.0, 0.0070, 1.2), (26.0, 0.0170, 0.8)],
        "obstacle_rate": 400.0,
        "obstacles": ["rock", "boulder", "barrel", "cone", "ramp"],
        "friction": 0.95,
        "theme": {
            "sky": ["#2a0a12", "#6b1d1d", "#c0431f", "#ffa23a"],
            "sun": "#ffd08a", "sun_glow": "rgba(255, 140, 60, 0.5)",
            "sun_pos": (180, 320),
            "hills": ["#3a1a1a", "#54241c"],
            "dirt": "#3d2320", "grass": "#7a3020",
        },
    },
    {
        "name": "Moon Base",
        "target": 750,
        "base": 340.0,
        "gravity": 900.0,          # low gravity - big floaty jumps
        "terrain": [(70.0, 0.0028, 0.2), (35.0, 0.0060, 1.9), (15.0, 0.0150, 1.4)],
        "obstacle_rate": 700.0,
        "obstacles": ["rock", "boulder", "crater", "tyre", "ramp"],
        "friction": 0.80,
        "theme": {
            "sky": ["#05060f", "#101a3a", "#2a2f5a", "#4a4f80"],
            "sun": "#dfe6ff", "sun_glow": "rgba(200, 210, 255, 0.35)",
            "sun_pos": (760, 110),
            "hills": ["#2a2c40", "#3a3d55"],
            "dirt": "#5a5d70", "grass": "#8f93a8",
        },
    },
]

# ---------------------------------------------------------------------------
# Vehicles (unlocked by collecting coins)
# ---------------------------------------------------------------------------
VEHICLES = [
    {"name": "Rusty Jeep", "wheel_r": 17.0, "wheelbase": 64.0, "head": 34.0,
     "drive": 2600.0, "damp": 16.0, "max_speed": 430.0, "price": 0,
     "body": "#e63946", "trim": "#ff6b6b", "kind": "jeep"},
    {"name": "Dirt Bike", "wheel_r": 15.0, "wheelbase": 52.0, "head": 30.0,
     "drive": 3100.0, "damp": 11.0, "max_speed": 470.0, "price": 150,
     "body": "#2dd4bf", "trim": "#7ef0c0", "kind": "bike"},
    {"name": "Monster Truck", "wheel_r": 24.0, "wheelbase": 84.0, "head": 40.0,
     "drive": 2500.0, "damp": 28.0, "max_speed": 380.0, "price": 400,
     "body": "#a855f7", "trim": "#d8b4fe", "kind": "truck"},
    {"name": "Turbo Car", "wheel_r": 14.0, "wheelbase": 72.0, "head": 24.0,
     "drive": 3500.0, "damp": 9.0, "max_speed": 520.0, "price": 800,
     "body": "#f59e0b", "trim": "#fcd34d", "kind": "car"},
]

# ---------------------------------------------------------------------------
# Obstacle types. Each level draws from its own list, and each new level
# introduces a couple more. "shape" decides how the ground profile is built:
#   hill    - smooth rounded hump (rocks, boulders)
#   log     - low rounded top
#   wedge   - rises to the peak then drops away (a launch ramp)
#   plateau - steep-ish lead-in and a flat top (blocks, barrels, cones)
#   dip     - ground drops away (a crater)
# ---------------------------------------------------------------------------
OBSTACLES = {
    "rock":    {"label": "Rocks",         "shape": "hill",    "w": (30, 48),  "h": (12, 22), "style": "rock"},
    "log":     {"label": "Fallen Logs",   "shape": "log",     "w": (58, 88),  "h": (11, 17), "style": "log"},
    "cactus":  {"label": "Cacti",         "shape": "plateau", "w": (22, 34),  "h": (34, 50), "style": "cactus"},
    "ramp":    {"label": "Launch Ramps",  "shape": "wedge",   "w": (80, 124), "h": (32, 52), "style": "ramp"},
    "boulder": {"label": "Boulders",      "shape": "hill",    "w": (52, 82),  "h": (36, 58), "style": "boulder"},
    "ice":     {"label": "Ice Blocks",    "shape": "plateau", "w": (30, 46),  "h": (22, 36), "style": "ice"},
    "barrel":  {"label": "Oil Barrels",   "shape": "plateau", "w": (24, 34),  "h": (26, 40), "style": "barrel"},
    "cone":    {"label": "Traffic Cones", "shape": "peak",    "w": (16, 24),  "h": (16, 26), "style": "cone"},
    "tyre":    {"label": "Tyre Stacks",   "shape": "hill",    "w": (22, 32),  "h": (24, 36), "style": "tyre"},
    "crater":  {"label": "Craters",       "shape": "dip",     "w": (64, 104), "h": (14, 24), "style": "crater"},
}

SAVE_KEY = "khelo_climb_save"
# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
screen = "menu"          # menu | intro | playing | over | won
intro_seen = []          # levels whose new-obstacle intro has been shown
_intro_t = 0.0
_intro_new = []
level_index = 0
vehicle_index = 0
wallet = 0
owned = [0]
unlocked = [0]
best = {}                # level index -> best metres
run_coins = 0
run_best_flag = False
over_reason = ""

fuel = FUEL_MAX
gas_pressed = False
brake_pressed = False
_acc = 0.0
_cam = 0.0
_cam_y = 0.0
_flash = 0.0

rear = {"x": START_X, "y": 0.0, "vx": 0.0, "vy": 0.0, "contact": True, "spin": 0.0}
front = {"x": START_X + 64.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "contact": True, "spin": 0.0}

coins = []
fuels = []
rocks = []
_menu_hit = []           # (kind, index, x, y, w, h) rebuilt every menu draw


# ---------------------------------------------------------------------------
# Level helpers
# ---------------------------------------------------------------------------
def _level():
    return LEVELS[level_index]


def terrain(x):
    lv = _level()
    y = lv["base"]
    for amp, freq, phase in lv["terrain"]:
        y += amp * math.sin(x * freq + phase)
    return y


def slope(x):
    lv = _level()
    s = 0.0
    for amp, freq, phase in lv["terrain"]:
        s += amp * freq * math.cos(x * freq + phase)
    return s


def _vehicle():
    return VEHICLES[vehicle_index]


def _target_px():
    return _level()["target"] * PIXELS_PER_METER


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------
def _save():
    data = {
        "wallet": wallet, "owned": owned, "unlocked": unlocked,
        "best": best, "level": level_index, "vehicle": vehicle_index,
        "intro_seen": intro_seen,
    }
    try:
        js.window.localStorage.setItem(SAVE_KEY, json.dumps(data))
    except Exception:
        pass


def _load():
    global wallet, owned, unlocked, best, level_index, vehicle_index, intro_seen
    try:
        raw = js.window.localStorage.getItem(SAVE_KEY)
    except Exception:
        raw = None
    if not raw:
        return
    try:
        data = json.loads(raw)
        wallet = int(data.get("wallet", 0))
        owned = list(data.get("owned", [0])) or [0]
        unlocked = list(data.get("unlocked", [0])) or [0]
        intro_seen = list(data.get("intro_seen", []))
        best = {int(k): int(v) for k, v in (data.get("best") or {}).items()}
        level_index = min(int(data.get("level", 0)), len(LEVELS) - 1)
        vehicle_index = int(data.get("vehicle", 0))
        if vehicle_index not in owned:
            vehicle_index = owned[0]
    except Exception:
        pass


def _sound(name):
    try:
        js.playSound(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Car geometry
# ---------------------------------------------------------------------------
def _car_x():
    return (rear["x"] + front["x"]) / 2.0


def _car_y():
    return (rear["y"] + front["y"]) / 2.0


def _car_angle():
    return math.atan2(front["y"] - rear["y"], front["x"] - rear["x"])


def _meters():
    return max(0, int((_car_x() - START_X) / PIXELS_PER_METER))


def _head_point():
    a = _car_angle()
    v = _vehicle()
    ux, uy = math.sin(a), -math.cos(a)
    return _car_x() + ux * v["head"], _car_y() + uy * v["head"]


def _place_car():
    global _cam, _cam_y
    v = _vehicle()
    rear["x"] = START_X
    rear["y"] = terrain(START_X) - v["wheel_r"]
    front["x"] = START_X + v["wheelbase"]
    front["y"] = terrain(START_X + v["wheelbase"]) - v["wheel_r"]
    for w in (rear, front):
        w["vx"] = 0.0
        w["vy"] = 0.0
        w["contact"] = True
        w["spin"] = 0.0
    _cam = START_X - 260.0
    _cam_y = 0.0


# ---------------------------------------------------------------------------
# Track items (coins, fuel cans, obstacles) - deterministic per level
# ---------------------------------------------------------------------------
def _build_items():
    global coins, fuels, rocks
    coins, fuels, rocks = [], [], []
    rng = random.Random(1000 + level_index * 37)
    end = _target_px() + 900.0

    # coins: shallow arcs that sit inside a normal jump height, so every coin
    # is actually reachable - nothing parked above the roof of a jump
    x = 420.0
    while x < end:
        if rng.random() < 0.55:
            for k in range(rng.randint(3, 6)):
                cx = x + k * 46.0
                coins.append({"x": cx, "y": terrain(cx) - 34.0 - 18.0 * math.sin(k * 0.7),
                              "got": False})
            x += rng.randint(4, 6) * 46.0 + 260.0
        else:
            coins.append({"x": x, "y": terrain(x) - 32.0, "got": False})
            x += 150.0

    # fuel cans
    fx = 900.0
    while fx < end:
        fuels.append({"x": fx, "y": terrain(fx) - 26.0, "got": False})
        fx += rng.uniform(1300.0, 1900.0)

    # obstacles: the level picks from its own set, spaced so they never overlap
    ids = _level()["obstacles"]
    rate = _level()["obstacle_rate"]
    ox = 1150.0
    last_right = -1e9
    first = True
    while ox < end:
        oid = ids[0] if first else ids[rng.randrange(len(ids))]
        spec = OBSTACLES[oid]
        w = rng.uniform(*spec["w"])
        h = rng.uniform(*spec["h"])
        if ox - w < last_right + 70.0:
            ox = last_right + 70.0 + w
        rocks.append({"x": ox, "w": w, "h": h, "shape": spec["shape"],
                      "style": spec["style"], "id": oid})
        last_right = ox + w
        first = False
        ox += rate * rng.uniform(0.8, 1.5)


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------
def _solve_rod():
    v = _vehicle()
    dx = front["x"] - rear["x"]
    dy = front["y"] - rear["y"]
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return
    diff = (d - v["wheelbase"]) / d
    rear["x"] += dx * diff * 0.5
    rear["y"] += dy * diff * 0.5
    front["x"] -= dx * diff * 0.5
    front["y"] -= dy * diff * 0.5


def _bump_at(ob, x):
    """Height of an obstacle's profile at x (0 outside its footprint)."""
    dx = x - ob["x"]
    w = ob["w"]
    if not (-w < dx < w):
        return 0.0
    h = ob["h"]
    shape = ob["shape"]
    if shape == "wedge":
        # rises steadily across the ramp, then drops away -> a launch
        return h * (dx + w) / (2.0 * w)
    if shape == "plateau":
        lead = max(14.0, h * 1.1)          # a climbable lead-in, then a flat top
        if dx < -w + lead:
            return h * (dx + w) / lead
        return h
    if shape == "log":
        return h * (1.0 - (dx / w) ** 2)   # low, rounded top
    if shape == "peak":
        return h * (1.0 - abs(dx) / w)     # a triangular peak (cones)
    if shape == "dip":
        return -h * 0.5 * (1.0 + math.cos(math.pi * dx / w))
    return h * 0.5 * (1.0 + math.cos(math.pi * dx / w))


def _ground_y(x):
    """Ground height including obstacle profiles - bumps and craters."""
    h = terrain(x)
    for ob in rocks:
        dx = x - ob["x"]
        if -ob["w"] < dx < ob["w"]:
            surface = terrain(x) - _bump_at(ob, x)
            if ob["shape"] == "dip":
                if surface > h:
                    h = surface
            elif surface < h:
                h = surface
    return h


def _solve_ground(w, dt):
    r = _vehicle()["wheel_r"]
    floor = _ground_y(w["x"]) - r
    pen = w["y"] - floor
    if pen > 0:
        eps = 2.0
        s = (_ground_y(w["x"] + eps) - _ground_y(w["x"] - eps)) / (2.0 * eps)
        inv = 1.0 / math.hypot(1.0, s)
        nx, ny = s * inv, -inv
        vn = w["vx"] * nx + w["vy"] * ny
        # suspension: a spring pushes the wheel out, a damper eats the impact.
        # That is what makes landings smooth instead of a hard snap.
        force = SUSP_K * pen - SUSP_D * vn
        if force > 0.0:
            w["vx"] += nx * force * dt
            w["vy"] += ny * force * dt
        # a light touch of ground friction on the tangential motion
        # (lower on ice and the moon, so it slides more)
        tx, ty = -ny, nx
        vt = w["vx"] * tx + w["vy"] * ty
        grip = GROUND_FRICTION * _level()["friction"]
        w["vx"] -= tx * vt * min(1.0, grip * dt)
        w["vy"] -= ty * vt * min(1.0, grip * dt)
        if pen > MAX_PEN:                 # safety: never sink through the floor
            w["y"] = floor + MAX_PEN
        w["contact"] = True


def _substep(dt, throttle):
    v = _vehicle()
    dx = front["x"] - rear["x"]
    dy = front["y"] - rear["y"]
    dist = math.hypot(dx, dy) or 1.0
    ax, ay = dx / dist, dy / dist

    for w in (rear, front):
        w["vy"] += _level()["gravity"] * dt

    if throttle:
        for w in (rear, front):
            if not w["contact"]:
                continue
            spd = w["vx"] * ax + w["vy"] * ay
            if throttle > 0 and spd < v["max_speed"]:
                w["vx"] += ax * v["drive"] * dt
                w["vy"] += ay * v["drive"] * dt
            elif throttle < 0 and spd > -MAX_REVERSE:
                w["vx"] -= ax * v["drive"] * dt
                w["vy"] -= ay * v["drive"] * dt

    for w in (rear, front):
        w["x"] += w["vx"] * dt
        w["y"] += w["vy"] * dt
        w["spin"] += (w["vx"] * dt) / v["wheel_r"]

    rear["contact"] = False
    front["contact"] = False
    for _ in range(4):
        _solve_rod()
        _solve_ground(rear, dt)
        _solve_ground(front, dt)

    # keep the rod velocity-consistent
    dx = front["x"] - rear["x"]
    dy = front["y"] - rear["y"]
    dist = math.hypot(dx, dy) or 1.0
    ax, ay = dx / dist, dy / dist
    along = (front["vx"] - rear["vx"]) * ax + (front["vy"] - rear["vy"]) * ay
    rear["vx"] += ax * along * 0.5
    rear["vy"] += ay * along * 0.5
    front["vx"] -= ax * along * 0.5
    front["vy"] -= ay * along * 0.5

    # angular damping
    l2 = dx * dx + dy * dy or 1.0
    length = math.sqrt(l2)
    omega = (dx * (front["vy"] - rear["vy"]) - dy * (front["vx"] - rear["vx"])) / l2
    ux, uy = -dy / length, dx / length
    fd = v["damp"] * omega
    rear["vx"] += ux * fd * dt
    rear["vy"] += uy * fd * dt
    front["vx"] -= ux * fd * dt
    front["vy"] -= uy * fd * dt

    # pitch control: gas lifts the nose, brake drops it. On the ground this is a
    # wheelie; in the air it is air control - which is how you flatten a landing,
    # and also how you over-rotate into an accidental flip.
    if throttle:
        on_ground = rear["contact"] or front["contact"]
        fd_t = (WHEELIE_TORQUE if on_ground else AIR_TORQUE) * throttle
        rear["vx"] += ux * fd_t * dt
        rear["vy"] += uy * fd_t * dt
        front["vx"] -= ux * fd_t * dt
        front["vy"] -= uy * fd_t * dt

    for w in (rear, front):
        w["vx"] *= (1.0 - ROLL_DRAG * dt)
        speed = math.hypot(w["vx"], w["vy"])
        if speed > 1400.0:
            k = 1400.0 / speed
            w["vx"] *= k
            w["vy"] *= k


# ---------------------------------------------------------------------------
# Game flow
# ---------------------------------------------------------------------------
def reset_run():
    global fuel, run_coins, run_best_flag, over_reason, _acc, gas_pressed, brake_pressed, _flash
    fuel = FUEL_MAX
    run_coins = 0
    run_best_flag = False
    over_reason = ""
    _acc = 0.0
    _flash = 0.0
    gas_pressed = False
    brake_pressed = False
    _build_items()
    _place_car()


def _new_obstacles(i):
    """Obstacle types that appear in level i but not in the one before it."""
    ids = LEVELS[i]["obstacles"]
    if i == 0:
        return list(ids)
    prev = set(LEVELS[i - 1]["obstacles"])
    return [x for x in ids if x not in prev]


def _begin_play():
    global screen
    reset_run()
    screen = "playing"
    _sound("start")


def _end_intro():
    global screen
    if level_index not in intro_seen:
        intro_seen.append(level_index)
        _save()
    _begin_play()


def start_game():
    global screen, _intro_t, _intro_new
    news = _new_obstacles(level_index)
    if news and level_index not in intro_seen:
        _intro_new = news
        _intro_t = 0.0
        screen = "intro"
        _sound("click")
        return
    _begin_play()


def back_to_menu():
    global screen
    screen = "menu"


def playing():
    return screen == "playing"


def select_level(i):
    if 0 <= i < len(LEVELS) and i in unlocked:
        global level_index
        level_index = i
        _save()
        _sound("click")


def select_vehicle(i):
    global vehicle_index, wallet, owned
    if not (0 <= i < len(VEHICLES)):
        return
    if i in owned:
        vehicle_index = i
        _save()
        _sound("click")
        return
    price = VEHICLES[i]["price"]
    if wallet >= price:
        wallet -= price
        owned = owned + [i]
        vehicle_index = i
        _save()
        _sound("buy")
    else:
        _sound("deny")


def _finish(reason):
    global screen, over_reason, best
    if screen != "playing":
        return
    over_reason = reason
    m = _meters()
    if m > best.get(level_index, 0):
        best[level_index] = m
    _save()
    screen = "over"
    _sound("crash")


def _win():
    global screen, wallet, best
    m = _meters()
    if m > best.get(level_index, 0):
        best[level_index] = m
    bonus = 50 + level_index * 25
    wallet += bonus
    nxt = level_index + 1
    if nxt < len(LEVELS) and nxt not in unlocked:
        unlocked.append(nxt)
    _save()
    screen = "won"
    _sound("win")


def _check_crash():
    hx, hy = _head_point()
    if hy > terrain(hx) - 2.0:
        _finish("crash")


def _collect():
    global fuel, wallet, run_coins
    cx, cy = _car_x(), _car_y()
    for c in coins:
        if not c["got"] and math.hypot(c["x"] - cx, c["y"] - cy) < 46.0:
            c["got"] = True
            wallet += COIN_VALUE
            run_coins += 1
            _sound("coin")
    for f in fuels:
        if not f["got"] and math.hypot(f["x"] - cx, f["y"] - cy) < 52.0:
            f["got"] = True
            fuel = FUEL_MAX
            _sound("refuel")


def update(dt):
    global _acc, fuel, _cam, _cam_y, _flash, _intro_t
    dt = min(max(float(dt), 0.0), 0.05)

    if screen == "intro":
        _intro_t += dt
        return

    if screen != "playing":
        _flash = max(0.0, _flash - dt * 2.0)
        return

    throttle = 0
    if fuel > 0.0:
        if gas_pressed:
            throttle = 1
        elif brake_pressed:
            throttle = -1

    _acc += dt
    steps = 0
    while _acc >= FIXED and steps < 10:
        _substep(FIXED, throttle)
        _acc -= FIXED
        steps += 1
    if _acc > FIXED * 10:
        _acc = 0.0

    if gas_pressed and fuel > 0.0:
        fuel = max(0.0, fuel - FUEL_RATE * dt)
        if fuel <= 0.0:
            _finish("fuel")

    _collect()
    _check_crash()

    if screen == "playing" and _meters() >= _level()["target"]:
        _win()

    target_cam = _car_x() - 260.0
    _cam += (target_cam - _cam) * min(1.0, dt * 6.0)

    # pan up smoothly on big jumps so the car stays in frame
    target_cam_y = min(0.0, max(-CAM_UP_MAX, _car_y() - H * 0.56))
    _cam_y += (target_cam_y - _cam_y) * min(1.0, dt * 4.0)


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
def gas(down):
    global gas_pressed
    gas_pressed = bool(down)
    if down and screen == "intro":
        _end_intro()


def brake(down):
    global brake_pressed
    brake_pressed = bool(down)


def enter_key():
    if screen == "intro":
        _end_intro()
    elif screen == "menu":
        start_game()
    elif screen in ("over", "won"):
        back_to_menu()


def tap(x, y):
    """A canvas tap. In the menu it hits buttons; elsewhere it does nothing."""
    if screen == "intro":
        _end_intro()
    elif screen == "menu":
        for kind, index, bx, by, bw, bh in _menu_hit:
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if kind == "level":
                    select_level(index)
                elif kind == "vehicle":
                    select_vehicle(index)
                elif kind == "start":
                    start_game()
                return
    elif screen in ("over", "won"):
        back_to_menu()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _panel(x, y, w, h, fill="rgba(10, 22, 48, 0.92)", stroke="#ffb703", r=18):
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()
    ctx.fillStyle = fill
    ctx.fill()
    if stroke:
        ctx.lineWidth = 2.5
        ctx.strokeStyle = stroke
        ctx.stroke()


def _button(x, y, w, h, label, active, locked, accent):
    ctx.beginPath()
    r = 12
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()
    if locked:
        ctx.fillStyle = "rgba(20, 26, 44, 0.7)"
        ctx.strokeStyle = "rgba(150, 165, 200, 0.28)"
    elif active:
        ctx.fillStyle = accent
        ctx.strokeStyle = "#ffffff"
    else:
        ctx.fillStyle = "rgba(24, 34, 62, 0.9)"
        ctx.strokeStyle = "rgba(150, 180, 240, 0.3)"
    ctx.fill()
    ctx.lineWidth = active and not locked and 3 or 2
    ctx.stroke()
    ctx.textAlign = "left"
    ctx.fillStyle = "#ffffff" if (active or not locked) else "#8794b3"
    ctx.font = "700 16px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(label, x + 14, y + 23)
    return (x, y, w, h)


# ---------------------------------------------------------------------------
# Drawing: world
# ---------------------------------------------------------------------------
def _draw_sky(theme):
    grad = ctx.createLinearGradient(0, 0, 0, H)
    stops = theme["sky"]
    for i, col in enumerate(stops):
        grad.addColorStop(i / (len(stops) - 1), col)
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, W, H)
    sx, sy = theme["sun_pos"]
    ctx.fillStyle = theme["sun_glow"]
    ctx.beginPath()
    ctx.arc(sx, sy, 58, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = theme["sun"]
    ctx.beginPath()
    ctx.arc(sx, sy, 34, 0, math.pi * 2)
    ctx.fill()


def _draw_parallax(theme):
    layers = ((0.25, theme["hills"][0], 300.0, 46.0),
              (0.45, theme["hills"][1], 330.0, 34.0))
    for depth, color, base, amp in layers:
        ctx.beginPath()
        ctx.moveTo(0, H)
        sx = 0.0
        while sx <= W:
            wx = _cam * depth + sx
            y = base + amp * math.sin(wx * 0.004) + (amp * 0.45) * math.sin(wx * 0.011 + 1.0)
            ctx.lineTo(sx, y)
            sx += 16.0
        ctx.lineTo(W, H)
        ctx.closePath()
        ctx.fillStyle = color
        ctx.fill()


def _draw_terrain(theme):
    ctx.beginPath()
    ctx.moveTo(0, H)
    x = _cam
    while x <= _cam + W + 12:
        ctx.lineTo(x - _cam, terrain(x))
        x += 10
    ctx.lineTo(W, H)
    ctx.closePath()
    ctx.fillStyle = theme["dirt"]
    ctx.fill()

    ctx.beginPath()
    x = _cam
    ctx.moveTo(x - _cam, terrain(x))
    while x <= _cam + W + 12:
        ctx.lineTo(x - _cam, terrain(x))
        x += 10
    ctx.lineWidth = 15
    ctx.lineJoin = "round"
    ctx.lineCap = "round"
    ctx.strokeStyle = theme["grass"]
    ctx.stroke()


def _visible(x):
    return _cam - 80 <= x <= _cam + W + 80


def _draw_items():
    # coins
    for c in coins:
        if c["got"] or not _visible(c["x"]):
            continue
        sx = c["x"] - _cam
        ctx.fillStyle = "#ffd23f"
        ctx.beginPath()
        ctx.arc(sx, c["y"], 11, 0, math.pi * 2)
        ctx.fill()
        ctx.fillStyle = "#c99a10"
        ctx.beginPath()
        ctx.arc(sx, c["y"], 6, 0, math.pi * 2)
        ctx.fill()
        ctx.fillStyle = "#ffe9a3"
        ctx.font = "800 12px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
        ctx.textAlign = "center"
        ctx.fillText("$", sx, c["y"] + 4)

    # fuel cans
    for f in fuels:
        if f["got"] or not _visible(f["x"]):
            continue
        sx = f["x"] - _cam
        ctx.fillStyle = "#d64545"
        ctx.fillRect(sx - 11, f["y"] - 14, 22, 28)
        ctx.fillStyle = "#ffffff"
        ctx.fillRect(sx - 11, f["y"] - 4, 22, 8)
        ctx.fillStyle = "#8f2b2b"
        ctx.fillRect(sx - 4, f["y"] - 20, 8, 7)
        ctx.fillStyle = "#ffffff"
        ctx.font = "800 11px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
        ctx.textAlign = "center"
        ctx.fillText("F", sx, f["y"] + 3)

    _draw_obstacles()


def _profile_path(ob):
    """The obstacle's silhouette, following the exact profile the physics uses."""
    w = ob["w"]
    ctx.beginPath()
    ctx.moveTo(ob["x"] - w - _cam, terrain(ob["x"]) + 10)
    steps = 18
    for k in range(steps + 1):
        dx = -w + (2.0 * w) * k / steps
        px = ob["x"] + dx
        ctx.lineTo(px - _cam, terrain(px) - _bump_at(ob, px))
    ctx.lineTo(ob["x"] + w - _cam, terrain(ob["x"]) + 10)
    ctx.closePath()


def _draw_obstacles():
    for ob in rocks:
        if not _visible(ob["x"]):
            continue
        style = ob["style"]
        sx = ob["x"] - _cam
        base = terrain(ob["x"])
        w = ob["w"]
        h = ob["h"]

        if style == "crater":
            _profile_path(ob)
            ctx.fillStyle = "#2b1d12"
            ctx.fill()
            ctx.lineWidth = 3
            ctx.strokeStyle = "rgba(255, 255, 255, 0.10)"
            ctx.stroke()

        elif style in ("rock", "boulder"):
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "#8b939f" if style == "rock" else "#79828f"
            ctx.fill()
            ctx.clip()
            ctx.fillStyle = "rgba(255, 255, 255, 0.18)"
            ctx.beginPath()
            ctx.moveTo(sx - w, base - h * 0.10)
            ctx.lineTo(sx - w * 0.15, base - h)
            ctx.lineTo(sx + w * 0.35, base - h * 0.28)
            ctx.closePath()
            ctx.fill()
            ctx.fillStyle = "rgba(0, 0, 0, 0.22)"
            ctx.beginPath()
            ctx.moveTo(sx - w * 0.20, base)
            ctx.lineTo(sx + w * 0.50, base - h * 0.85)
            ctx.lineTo(sx + w, base - h * 0.10)
            ctx.closePath()
            ctx.fill()
            ctx.fillStyle = "rgba(0, 0, 0, 0.13)"
            ctx.beginPath()
            ctx.arc(sx + w * 0.45, base - h * 0.22, h * 0.28, 0, math.pi * 2)
            ctx.fill()
            ctx.restore()
            _profile_path(ob)
            ctx.lineWidth = 3
            ctx.strokeStyle = "rgba(236, 243, 253, 0.5)"
            ctx.stroke()

        elif style == "log":
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "#7a4f28"
            ctx.fill()
            ctx.clip()
            ctx.strokeStyle = "rgba(0, 0, 0, 0.25)"
            ctx.lineWidth = 3
            for k in range(-3, 4):
                bx = sx + k * w * 0.26
                ctx.beginPath()
                ctx.moveTo(bx, base - h * 1.5)
                ctx.lineTo(bx, base + 12)
                ctx.stroke()
            ctx.restore()
            ctx.fillStyle = "#a9793f"
            ctx.beginPath()
            ctx.ellipse(sx - w + 5, base - h * 0.5, 7, h * 0.5, 0, 0, math.pi * 2)
            ctx.fill()
            ctx.strokeStyle = "rgba(0, 0, 0, 0.35)"
            ctx.lineWidth = 2
            ctx.beginPath()
            ctx.ellipse(sx - w + 5, base - h * 0.5, 3.5, h * 0.26, 0, 0, math.pi * 2)
            ctx.stroke()

        elif style == "ramp":
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "#8a6a3a"
            ctx.fill()
            ctx.clip()
            ctx.strokeStyle = "rgba(0, 0, 0, 0.30)"
            ctx.lineWidth = 2
            for k in range(9):
                px = sx - w + (2.0 * w) * k / 8.0
                top = terrain(px + _cam) - _bump_at(ob, px + _cam)
                ctx.beginPath()
                ctx.moveTo(px, top)
                ctx.lineTo(px, base + 12)
                ctx.stroke()
            ctx.restore()
            ctx.beginPath()
            for k in range(19):
                dx = -w + (2.0 * w) * k / 18.0
                px = ob["x"] + dx
                py = terrain(px) - _bump_at(ob, px)
                if k == 0:
                    ctx.moveTo(px - _cam, py)
                else:
                    ctx.lineTo(px - _cam, py)
            ctx.lineWidth = 5
            ctx.strokeStyle = "#c99a5a"
            ctx.stroke()
            ctx.fillStyle = "#5c4326"
            ctx.fillRect(sx + w - 12, base - h * 0.85, 9, h * 0.85)

        elif style == "cactus":
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "#2f8f4a"
            ctx.fill()
            ctx.clip()
            ctx.strokeStyle = "rgba(0, 0, 0, 0.20)"
            ctx.lineWidth = 2
            for k in (-1, 0, 1):
                ctx.beginPath()
                ctx.moveTo(sx + k * w * 0.38, base - h * 1.4)
                ctx.lineTo(sx + k * w * 0.38, base + 10)
                ctx.stroke()
            ctx.fillStyle = "rgba(255, 255, 255, 0.16)"
            ctx.fillRect(sx - w * 0.62, base - h * 0.85, w * 0.22, h * 0.85)
            ctx.restore()
            ctx.fillStyle = "#2f8f4a"
            ctx.fillRect(sx - w - 7, base - h * 0.62, 7, h * 0.34)
            ctx.fillRect(sx - w - 7, base - h * 0.70, w * 0.30, 7)
            ctx.fillRect(sx + w, base - h * 0.52, 7, h * 0.26)
            ctx.fillRect(sx + w * 0.72, base - h * 0.60, w * 0.30, 7)

        elif style == "ice":
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "rgba(176, 226, 246, 0.92)"
            ctx.fill()
            ctx.clip()
            ctx.fillStyle = "rgba(255, 255, 255, 0.45)"
            ctx.beginPath()
            ctx.moveTo(sx - w, base)
            ctx.lineTo(sx - w * 0.1, base - h)
            ctx.lineTo(sx + w * 0.35, base - h * 0.55)
            ctx.lineTo(sx + w, base)
            ctx.closePath()
            ctx.fill()
            ctx.fillStyle = "rgba(120, 190, 220, 0.5)"
            ctx.beginPath()
            ctx.moveTo(sx + w * 0.1, base)
            ctx.lineTo(sx + w * 0.5, base - h * 0.9)
            ctx.lineTo(sx + w, base)
            ctx.closePath()
            ctx.fill()
            ctx.restore()
            _profile_path(ob)
            ctx.lineWidth = 3
            ctx.strokeStyle = "rgba(255, 255, 255, 0.85)"
            ctx.stroke()

        elif style == "barrel":
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "#b23a2e"
            ctx.fill()
            ctx.clip()
            ctx.fillStyle = "rgba(255, 255, 255, 0.16)"
            ctx.fillRect(sx - w, base - h * 0.74, 2 * w, h * 0.13)
            ctx.fillRect(sx - w, base - h * 0.32, 2 * w, h * 0.13)
            ctx.fillStyle = "rgba(0, 0, 0, 0.20)"
            ctx.fillRect(sx + w * 0.28, base - h * 1.2, w * 0.30, h * 1.4)
            ctx.restore()
            _profile_path(ob)
            ctx.lineWidth = 2
            ctx.strokeStyle = "rgba(255, 220, 210, 0.5)"
            ctx.stroke()
            ctx.fillStyle = "#d4534a"
            ctx.beginPath()
            ctx.ellipse(sx, base - h, w * 0.72, 5, 0, 0, math.pi * 2)
            ctx.fill()

        elif style == "cone":
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "#f06a1e"
            ctx.fill()
            ctx.clip()
            ctx.fillStyle = "#ffffff"
            ctx.fillRect(sx - w, base - h * 0.52, 2 * w, h * 0.20)
            ctx.restore()
            _profile_path(ob)
            ctx.lineWidth = 2.5
            ctx.strokeStyle = "rgba(255, 255, 255, 0.55)"
            ctx.stroke()
            ctx.fillStyle = "#2b2f3a"
            ctx.fillRect(sx - w * 1.25, base - 5, w * 2.5, 7)

        elif style == "tyre":
            ctx.save()
            _profile_path(ob)
            ctx.fillStyle = "#1f2430"
            ctx.fill()
            ctx.clip()
            ctx.fillStyle = "#3a4150"
            ctx.beginPath()
            ctx.arc(sx, base - h * 0.72, h * 0.30, 0, math.pi * 2)
            ctx.fill()
            ctx.fillStyle = "#4a5261"
            ctx.beginPath()
            ctx.arc(sx, base - h * 0.30, h * 0.30, 0, math.pi * 2)
            ctx.fill()
            ctx.restore()
            _profile_path(ob)
            ctx.lineWidth = 2.5
            ctx.strokeStyle = "rgba(190, 200, 215, 0.45)"
            ctx.stroke()

        else:
            _profile_path(ob)
            ctx.fillStyle = "#6b7280"
            ctx.fill()


def _draw_wheel(w, kind):
    v = _vehicle()
    r = v["wheel_r"]
    sx = w["x"] - _cam
    sy = w["y"]
    ctx.save()
    ctx.translate(sx, sy)
    ctx.rotate(w["spin"])

    # tyre
    ctx.fillStyle = "#14171f"
    ctx.beginPath()
    ctx.arc(0, 0, r, 0, math.pi * 2)
    ctx.fill()
    # tread blocks
    ctx.strokeStyle = "rgba(125, 136, 156, 0.55)"
    ctx.lineWidth = max(2.0, r * 0.15)
    for i in range(8):
        ang = i * math.pi / 4
        ctx.beginPath()
        ctx.moveTo(math.cos(ang) * r * 0.80, math.sin(ang) * r * 0.80)
        ctx.lineTo(math.cos(ang) * r * 0.99, math.sin(ang) * r * 0.99)
        ctx.stroke()
    # rim
    ctx.fillStyle = "#b9c2d0"
    ctx.beginPath()
    ctx.arc(0, 0, r * 0.54, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#8d97a8"
    ctx.beginPath()
    ctx.arc(0, 0, r * 0.45, 0, math.pi * 2)
    ctx.fill()
    # spokes
    ctx.strokeStyle = "#eef2f9"
    ctx.lineWidth = max(1.6, r * 0.11)
    for i in range(5):
        ang = i * math.pi * 2 / 5
        ctx.beginPath()
        ctx.moveTo(0, 0)
        ctx.lineTo(math.cos(ang) * r * 0.43, math.sin(ang) * r * 0.43)
        ctx.stroke()
    # hub
    ctx.fillStyle = "#5b6472"
    ctx.beginPath()
    ctx.arc(0, 0, r * 0.17, 0, math.pi * 2)
    ctx.fill()
    ctx.restore()


def _driver(head_y, suit, x0=2.0):
    """A simple seated driver whose head sits on the crash point."""
    ctx.fillStyle = suit
    ctx.beginPath()
    ctx.moveTo(x0 - 8, head_y + 8)
    ctx.lineTo(x0 + 6, head_y + 8)
    ctx.lineTo(x0 + 8, head_y + 22)
    ctx.lineTo(x0 - 10, head_y + 22)
    ctx.closePath()
    ctx.fill()
    ctx.fillStyle = "#f2c14e"
    ctx.beginPath()
    ctx.arc(x0, head_y, 7, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#2b2d42"
    ctx.beginPath()
    ctx.arc(x0, head_y, 7, math.pi * 1.05, math.pi * 2.0)
    ctx.fill()


def _draw_car():
    v = _vehicle()
    cx = _car_x() - _cam
    cy = _car_y()
    a = _car_angle()
    kind = v["kind"]
    body = v["body"]
    trim = v["trim"]
    hy = -v["head"] + 4

    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(a)

    if kind == "bike":
        ctx.strokeStyle = "#2b2f3a"
        ctx.lineWidth = 5
        ctx.beginPath(); ctx.moveTo(-24, 4); ctx.lineTo(-6, -4); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(-2, -6); ctx.lineTo(18, -3); ctx.stroke()
        ctx.fillStyle = "#3c4250"
        ctx.fillRect(-13, -7, 17, 13)
        ctx.fillStyle = body
        ctx.beginPath()
        ctx.moveTo(-9, -8); ctx.lineTo(3, -15); ctx.lineTo(14, -12); ctx.lineTo(16, -6); ctx.lineTo(-7, -4)
        ctx.closePath(); ctx.fill()
        ctx.fillStyle = "#1f2430"
        ctx.beginPath()
        ctx.moveTo(-27, -7); ctx.lineTo(-9, -11); ctx.lineTo(-7, -4); ctx.lineTo(-27, 1)
        ctx.closePath(); ctx.fill()
        ctx.strokeStyle = "#c9ced8"
        ctx.lineWidth = 4
        ctx.beginPath(); ctx.moveTo(16, -9); ctx.lineTo(24, 6); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(11, -17); ctx.lineTo(25, -15); ctx.stroke()
        ctx.strokeStyle = "#8d97a8"
        ctx.beginPath(); ctx.moveTo(-14, 3); ctx.lineTo(-31, 1); ctx.stroke()
        _driver(hy, "#2b2d42")

    elif kind == "truck":
        ctx.fillStyle = body
        ctx.beginPath()
        ctx.moveTo(-44, 6); ctx.lineTo(-44, -20); ctx.lineTo(12, -20)
        ctx.lineTo(18, -46); ctx.lineTo(40, -46); ctx.lineTo(46, -16); ctx.lineTo(46, 6)
        ctx.closePath(); ctx.fill()
        ctx.fillStyle = "#2b3350"
        ctx.beginPath()
        ctx.moveTo(20, -43); ctx.lineTo(38, -43); ctx.lineTo(42, -24); ctx.lineTo(20, -24)
        ctx.closePath(); ctx.fill()
        ctx.fillStyle = trim
        ctx.fillRect(-42, -20, 34, 7)
        ctx.fillStyle = "#3c4250"
        ctx.fillRect(-42, -10, 24, 12)
        ctx.strokeStyle = "#c9ced8"
        ctx.lineWidth = 4
        ctx.beginPath(); ctx.moveTo(34, -46); ctx.lineTo(34, -62); ctx.stroke()
        ctx.fillStyle = "#ffe9a3"
        ctx.fillRect(42, -18, 5, 9)
        _driver(hy, "#2b2d42", 28.0)

    elif kind == "car":
        ctx.fillStyle = body
        ctx.beginPath()
        ctx.moveTo(-40, 6); ctx.lineTo(-40, -8); ctx.lineTo(-26, -12)
        ctx.lineTo(22, -12); ctx.lineTo(36, -4); ctx.lineTo(40, 6)
        ctx.closePath(); ctx.fill()
        ctx.beginPath()
        ctx.moveTo(-20, -12); ctx.lineTo(-10, -34); ctx.lineTo(12, -34); ctx.lineTo(22, -12)
        ctx.closePath(); ctx.fill()
        ctx.fillStyle = "#22304d"
        ctx.beginPath()
        ctx.moveTo(-17, -14); ctx.lineTo(-8, -32); ctx.lineTo(10, -32); ctx.lineTo(19, -14)
        ctx.closePath(); ctx.fill()
        ctx.fillStyle = body
        ctx.fillRect(-50, -31, 19, 5)
        ctx.fillRect(-42, -31, 5, 19)
        ctx.fillStyle = trim
        ctx.fillRect(-36, -7, 70, 4)
        ctx.fillStyle = "#ffe9a3"
        ctx.fillRect(31, -10, 7, 6)
        ctx.fillStyle = "#2b2f3a"
        ctx.fillRect(-42, 6, 84, 4)
        _driver(hy, "#1f2430", -4.0)

    else:  # jeep
        ctx.fillStyle = body
        ctx.beginPath()
        ctx.moveTo(-36, 6); ctx.lineTo(-36, -12); ctx.lineTo(-22, -14)
        ctx.lineTo(-14, -30); ctx.lineTo(16, -30); ctx.lineTo(24, -12)
        ctx.lineTo(38, -8); ctx.lineTo(38, 6)
        ctx.closePath(); ctx.fill()
        ctx.fillStyle = "#22304d"
        ctx.beginPath()
        ctx.moveTo(-12, -28); ctx.lineTo(14, -28); ctx.lineTo(20, -14); ctx.lineTo(-13, -14)
        ctx.closePath(); ctx.fill()
        ctx.fillStyle = trim
        ctx.fillRect(-36, -12, 74, 5)
        ctx.strokeStyle = "#c9ced8"
        ctx.lineWidth = 4
        ctx.beginPath(); ctx.moveTo(-14, -30); ctx.lineTo(18, -30); ctx.stroke()
        ctx.fillStyle = "#ffe9a3"
        ctx.fillRect(33, -6, 5, 7)
        ctx.fillStyle = "#3c4250"
        ctx.fillRect(28, -4, 11, 10)
        ctx.fillStyle = "#1f2430"
        ctx.fillRect(-40, 4, 78, 5)
        _driver(hy, "#2b2d42")

    ctx.restore()

    _draw_wheel(rear, kind)
    _draw_wheel(front, kind)


# ---------------------------------------------------------------------------
# Drawing: HUD + screens
# ---------------------------------------------------------------------------
def _draw_speedo():
    spd = math.hypot(rear["vx"], rear["vy"])
    kmh = spd * 0.36
    frac = min(1.0, kmh / 190.0)
    cx0, cy0, r = 96.0, H - 34.0, 46.0

    ctx.beginPath()
    ctx.arc(cx0, cy0, r + 12, math.pi, math.pi * 2)
    ctx.closePath()
    ctx.fillStyle = "rgba(6, 14, 32, 0.62)"
    ctx.fill()

    ctx.beginPath()
    ctx.arc(cx0, cy0, r, math.pi, math.pi * 2)
    ctx.lineWidth = 9
    ctx.strokeStyle = "rgba(255, 255, 255, 0.14)"
    ctx.stroke()

    ctx.beginPath()
    ctx.arc(cx0, cy0, r, math.pi, math.pi + math.pi * frac)
    ctx.strokeStyle = "#7ef0c0" if frac < 0.72 else "#ff8f5c"
    ctx.stroke()

    ctx.strokeStyle = "rgba(200, 215, 240, 0.45)"
    ctx.lineWidth = 2
    for i in range(9):
        ang = math.pi + math.pi * i / 8.0
        ctx.beginPath()
        ctx.moveTo(cx0 + math.cos(ang) * (r - 10), cy0 + math.sin(ang) * (r - 10))
        ctx.lineTo(cx0 + math.cos(ang) * (r - 2), cy0 + math.sin(ang) * (r - 2))
        ctx.stroke()

    ang = math.pi + math.pi * frac
    ctx.beginPath()
    ctx.moveTo(cx0, cy0)
    ctx.lineTo(cx0 + math.cos(ang) * (r - 13), cy0 + math.sin(ang) * (r - 13))
    ctx.lineWidth = 3
    ctx.strokeStyle = "#ff5c5c"
    ctx.stroke()
    ctx.fillStyle = "#eaf2ff"
    ctx.beginPath()
    ctx.arc(cx0, cy0, 4, 0, math.pi * 2)
    ctx.fill()

    ctx.textAlign = "left"
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 24px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(str(int(kmh)), cx0 + r + 14, cy0 - 2)
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 12px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("km/h", cx0 + r + 14, cy0 + 14)


def _draw_hud():
    lv = _level()
    # distance / progress
    ctx.fillStyle = "rgba(6, 14, 32, 0.6)"
    ctx.fillRect(18, 18, 300, 84)
    ctx.textAlign = "left"
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 12px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(lv["name"].upper(), 32, 40)
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 26px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(str(_meters()) + " / " + str(lv["target"]) + " m", 32, 70)

    prog = min(1.0, _meters() / float(lv["target"]))
    ctx.fillStyle = "rgba(255,255,255,0.16)"
    ctx.fillRect(32, 80, 272, 10)
    ctx.fillStyle = "#7ef0c0"
    ctx.fillRect(32, 80, 272 * prog, 10)

    # coins + wallet
    ctx.textAlign = "right"
    ctx.fillStyle = "#ffd23f"
    ctx.font = "800 20px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("$ " + str(run_coins), W - 200, 44)
    ctx.fillStyle = "#cfe0ff"
    ctx.font = "600 14px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("wallet " + str(wallet), W - 200, 66)
    ctx.fillStyle = "#cfe0ff"
    ctx.fillText("best " + str(best.get(level_index, 0)) + " m", W - 200, 86)

    # fuel
    ctx.fillStyle = "rgba(6, 14, 32, 0.6)"
    ctx.fillRect(W - 186, 18, 168, 46)
    ctx.textAlign = "left"
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 12px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("FUEL", W - 172, 40)
    ctx.fillStyle = "rgba(255,255,255,0.16)"
    ctx.fillRect(W - 172, 46, 140, 10)
    ratio = max(0.0, fuel / FUEL_MAX)
    ctx.fillStyle = "#ffd23f" if ratio > 0.25 else "#ff5c5c"
    ctx.fillRect(W - 172, 46, 140 * ratio, 10)

    _draw_speedo()

    # menu button
    _button(W - 186, H - 62, 168, 44, "Menu  (Esc)", False, False, "#ffb703")


def _draw_ready():
    lv = _level()
    v = _vehicle()
    _panel(W / 2 - 250, 150, 500, 210)
    ctx.textAlign = "center"
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 38px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(lv["name"], W / 2, 208)
    ctx.fillStyle = "#ffe9a3"
    ctx.font = "600 18px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Drive " + str(lv["target"]) + " m in the " + v["name"], W / 2, 246)
    ctx.fillStyle = "#cfe0ff"
    ctx.fillText("Right / D = gas    Left / A = brake", W / 2, 284)
    ctx.fillStyle = "#7ef0c0"
    ctx.fillText("Collect $ coins and grab fuel cans to keep going", W / 2, 318)
    ctx.fillStyle = "#ffd23f"
    ctx.fillText("Hold the gas to start", W / 2, 348)


def _draw_over():
    ctx.fillStyle = "rgba(4, 10, 24, 0.55)"
    ctx.fillRect(0, 0, W, H)
    _panel(W / 2 - 230, 150, 460, 230)
    ctx.textAlign = "center"
    ctx.fillStyle = "#ff8fa3"
    ctx.font = "800 34px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    titles = {"crash": "CRASHED!", "fuel": "OUT OF FUEL!", "spike": "OUCH! SPIKES!"}
    ctx.fillText(titles.get(over_reason, "GAME OVER"), W / 2, 210)
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 50px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(str(_meters()) + " m", W / 2, 274)
    ctx.fillStyle = "#ffd23f"
    ctx.font = "600 18px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Coins this run: " + str(run_coins) + "   ·   Wallet: " + str(wallet), W / 2, 312)
    ctx.fillStyle = "#cfe0ff"
    ctx.fillText("Best: " + str(best.get(level_index, 0)) + " m", W / 2, 340)
    ctx.fillStyle = "#7ef0c0"
    ctx.fillText("Tap / Enter to continue", W / 2, 366)


def _draw_won():
    ctx.fillStyle = "rgba(4, 10, 24, 0.55)"
    ctx.fillRect(0, 0, W, H)
    _panel(W / 2 - 230, 140, 460, 250, stroke="#7ef0c0")
    ctx.textAlign = "center"
    ctx.fillStyle = "#7ef0c0"
    ctx.font = "800 38px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("LEVEL COMPLETE!", W / 2, 200)
    ctx.fillStyle = "#ffffff"
    ctx.font = "700 22px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(_level()["name"], W / 2, 240)
    ctx.fillStyle = "#ffd23f"
    ctx.font = "800 30px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("+" + str(50 + level_index * 25) + " bonus coins", W / 2, 288)
    ctx.fillStyle = "#cfe0ff"
    ctx.font = "600 17px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Wallet: " + str(wallet), W / 2, 322)
    if level_index + 1 < len(LEVELS):
        ctx.fillStyle = "#7ef0c0"
        ctx.fillText("New location unlocked: " + LEVELS[level_index + 1]["name"], W / 2, 352)
    ctx.fillStyle = "#ffffff"
    ctx.fillText("Tap / Enter to continue", W / 2, 380)


def _demo_car(x, base):
    ctx.fillStyle = _vehicle()["body"]
    ctx.beginPath()
    ctx.moveTo(x - 22, base - 8)
    ctx.lineTo(x - 15, base - 21)
    ctx.lineTo(x + 8, base - 23)
    ctx.lineTo(x + 22, base - 8)
    ctx.closePath()
    ctx.fill()
    ctx.fillStyle = "#22304d"
    ctx.beginPath()
    ctx.moveTo(x - 11, base - 21)
    ctx.lineTo(x + 6, base - 21)
    ctx.lineTo(x + 11, base - 11)
    ctx.lineTo(x - 13, base - 11)
    ctx.closePath()
    ctx.fill()
    for wx in (x - 12, x + 12):
        ctx.fillStyle = "#14171f"
        ctx.beginPath()
        ctx.arc(wx, base - 7, 7.5, 0, math.pi * 2)
        ctx.fill()
        ctx.fillStyle = "#8d97a8"
        ctx.beginPath()
        ctx.arc(wx, base - 7, 3, 0, math.pi * 2)
        ctx.fill()


def _demo_icon(style, cx, base, w, h):
    if style in ("rock", "boulder"):
        ctx.fillStyle = "#8b939f" if style == "rock" else "#79828f"
        ctx.beginPath()
        ctx.moveTo(cx - w, base)
        ctx.quadraticCurveTo(cx - w * 0.55, base - h * 1.3, cx, base - h)
        ctx.quadraticCurveTo(cx + w * 0.6, base - h * 1.2, cx + w, base)
        ctx.closePath()
        ctx.fill()
        ctx.fillStyle = "rgba(255, 255, 255, 0.20)"
        ctx.beginPath()
        ctx.moveTo(cx - w * 0.6, base - h * 0.12)
        ctx.lineTo(cx - w * 0.15, base - h * 0.92)
        ctx.lineTo(cx + w * 0.25, base - h * 0.35)
        ctx.closePath()
        ctx.fill()
    elif style == "log":
        ctx.fillStyle = "#7a4f28"
        ctx.fillRect(cx - w, base - h, 2 * w, h)
        ctx.beginPath()
        ctx.arc(cx - w, base - h * 0.5, h * 0.5, 0, math.pi * 2)
        ctx.fill()
        ctx.fillStyle = "#a9793f"
        ctx.beginPath()
        ctx.arc(cx - w, base - h * 0.5, h * 0.32, 0, math.pi * 2)
        ctx.fill()
    elif style == "ramp":
        ctx.fillStyle = "#8a6a3a"
        ctx.beginPath()
        ctx.moveTo(cx - w, base)
        ctx.lineTo(cx + w, base - h)
        ctx.lineTo(cx + w, base)
        ctx.closePath()
        ctx.fill()
        ctx.strokeStyle = "rgba(0, 0, 0, 0.3)"
        ctx.lineWidth = 2
        for k in range(1, 5):
            px = cx - w + (2 * w) * k / 5.0
            py = base - h * (k / 5.0)
            ctx.beginPath()
            ctx.moveTo(px, py)
            ctx.lineTo(px, base)
            ctx.stroke()
    elif style == "cactus":
        ctx.fillStyle = "#2f8f4a"
        ctx.fillRect(cx - w * 0.45, base - h, w * 0.9, h)
        ctx.fillRect(cx - w * 1.2, base - h * 0.7, w * 0.5, h * 0.3)
        ctx.fillRect(cx + w * 0.7, base - h * 0.55, w * 0.5, h * 0.25)
    elif style == "ice":
        ctx.fillStyle = "rgba(176, 226, 246, 0.92)"
        ctx.fillRect(cx - w * 0.8, base - h, w * 1.6, h)
        ctx.fillStyle = "rgba(255, 255, 255, 0.5)"
        ctx.beginPath()
        ctx.moveTo(cx - w * 0.8, base)
        ctx.lineTo(cx, base - h)
        ctx.lineTo(cx + w * 0.3, base)
        ctx.closePath()
        ctx.fill()
    elif style == "barrel":
        ctx.fillStyle = "#b23a2e"
        ctx.fillRect(cx - w * 0.7, base - h, w * 1.4, h)
        ctx.fillStyle = "rgba(255, 255, 255, 0.2)"
        ctx.fillRect(cx - w * 0.7, base - h * 0.75, w * 1.4, h * 0.12)
        ctx.fillRect(cx - w * 0.7, base - h * 0.35, w * 1.4, h * 0.12)
    elif style == "cone":
        ctx.fillStyle = "#f06a1e"
        ctx.beginPath()
        ctx.moveTo(cx, base - h)
        ctx.lineTo(cx + w * 0.7, base)
        ctx.lineTo(cx - w * 0.7, base)
        ctx.closePath()
        ctx.fill()
        ctx.fillStyle = "#ffffff"
        ctx.fillRect(cx - w * 0.42, base - h * 0.6, w * 0.84, h * 0.18)
    elif style == "tyre":
        for cy in (base - h * 0.72, base - h * 0.26):
            ctx.fillStyle = "#1f2430"
            ctx.beginPath()
            ctx.arc(cx, cy, h * 0.28, 0, math.pi * 2)
            ctx.fill()
            ctx.fillStyle = "#4a5261"
            ctx.beginPath()
            ctx.arc(cx, cy, h * 0.12, 0, math.pi * 2)
            ctx.fill()
    elif style == "crater":
        ctx.fillStyle = "#2b1d12"
        ctx.beginPath()
        ctx.ellipse(cx, base + h * 0.15, w * 0.8, h * 0.5, 0, 0, math.pi * 2)
        ctx.fill()


def _draw_intro():
    theme = _level()["theme"]
    _draw_sky(theme)
    ctx.fillStyle = "rgba(5, 10, 24, 0.80)"
    ctx.fillRect(0, 0, W, H)

    ctx.textAlign = "center"
    ctx.fillStyle = "#7ef0c0"
    ctx.font = "700 14px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("LEVEL " + str(level_index + 1) + "  ·  " + _level()["name"].upper(), W / 2.0, 54)
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 34px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("New obstacles ahead", W / 2.0, 96)
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "600 14px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Watch how they behave before you drive", W / 2.0, 122)

    n = max(1, len(_intro_new))
    for i, oid in enumerate(_intro_new):
        spec = OBSTACLES[oid]
        x0 = W * (i + 0.5) / n
        base = 320.0
        ctx.strokeStyle = "rgba(150, 180, 230, 0.30)"
        ctx.lineWidth = 3
        ctx.beginPath()
        ctx.moveTo(x0 - 130, base)
        ctx.lineTo(x0 + 130, base)
        ctx.stroke()

        t = (_intro_t + i * 0.55) % 2.6
        prog = min(1.0, t / 1.6)
        carx = x0 - 100 + prog * 118
        _demo_icon(spec["style"], x0 + 52, base, 30.0, 26.0)
        _demo_car(carx, base)
        if prog >= 1.0 and t < 1.9:
            ctx.strokeStyle = "rgba(255, 220, 120, 0.9)"
            ctx.lineWidth = 3
            for a in range(6):
                ang = a * math.pi / 3
                ctx.beginPath()
                ctx.moveTo(x0 + 34, base - 26)
                ctx.lineTo(x0 + 34 + math.cos(ang) * 18, base - 26 + math.sin(ang) * 18)
                ctx.stroke()

        ctx.fillStyle = "#ffffff"
        ctx.font = "700 16px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
        ctx.fillText(spec["label"], x0, base + 46)

    _button(W / 2.0 - 150, H - 74, 300, 52, "Press gas / tap to start", True, False, "#7ef0c0")


def _draw_menu():
    global _menu_hit
    theme = _level()["theme"]
    _draw_sky(theme)
    _draw_parallax(theme)

    ctx.fillStyle = "rgba(5, 10, 24, 0.72)"
    ctx.fillRect(0, 0, W, H)

    _menu_hit = []
    ctx.textAlign = "center"
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 40px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("KHELO CLIMB", W / 2, 68)
    ctx.fillStyle = "#cfe0ff"
    ctx.font = "600 15px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Pick a location and a vehicle, then hit start", W / 2, 94)

    # wallet
    ctx.textAlign = "right"
    ctx.fillStyle = "#ffd23f"
    ctx.font = "800 20px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("$ " + str(wallet), W - 40, 52)

    # columns
    ctx.textAlign = "left"
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 13px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("LOCATIONS", 60, 140)
    ctx.fillText("VEHICLES", 480, 140)

    for i, lv in enumerate(LEVELS):
        y = 152 + i * 62
        locked = i not in unlocked
        label = lv["name"] + ("  (locked)" if locked else "  ·  " + str(lv["target"]) + " m")
        _button(60, y, 360, 52, label, i == level_index and not locked, locked, "#4aa8ff")
        if not locked:
            _menu_hit.append(("level", i, 60, y, 360, 52))

    for i, v in enumerate(VEHICLES):
        y = 152 + i * 62
        if i in owned:
            label = v["name"]
            locked = False
        else:
            label = v["name"] + "  ·  $" + str(v["price"])
            locked = wallet < v["price"]
        _button(480, y, 360, 52, label, i == vehicle_index, locked, v["body"])
        _menu_hit.append(("vehicle", i, 480, y, 360, 52))

    _button(W / 2 - 110, 490, 220, 52, "START", True, False, "#7ef0c0")
    _menu_hit.append(("start", 0, W / 2 - 110, 490, 220, 52))


def draw():
    if screen == "menu":
        _draw_menu()
        return
    if screen == "intro":
        _draw_intro()
        return

    theme = _level()["theme"]
    _draw_sky(theme)
    ctx.save()
    ctx.translate(0, -_cam_y)
    _draw_parallax(theme)
    _draw_terrain(theme)
    _draw_items()
    _draw_car()
    ctx.restore()
    _draw_hud()

    if screen == "playing" and _meters() < 4 and not gas_pressed:
        _draw_ready()
    elif screen == "over":
        _draw_over()
    elif screen == "won":
        _draw_won()


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
_load()
if vehicle_index not in owned:
    vehicle_index = owned[0]
if level_index not in unlocked:
    level_index = unlocked[0]
reset_run()
screen = "menu"

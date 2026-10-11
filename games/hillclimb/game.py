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

SAVE_KEY = "khelo_climb_save"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
screen = "menu"          # menu | playing | over | won
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
    }
    try:
        js.window.localStorage.setItem(SAVE_KEY, json.dumps(data))
    except Exception:
        pass


def _load():
    global wallet, owned, unlocked, best, level_index, vehicle_index
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
    global _cam
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


# ---------------------------------------------------------------------------
# Track items (coins, fuel cans, obstacles) - deterministic per level
# ---------------------------------------------------------------------------
def _build_items():
    global coins, fuels, rocks
    coins, fuels, rocks = [], [], []
    rng = random.Random(1000 + level_index * 37)
    end = _target_px() + 900.0

    # coins: little arcs floating above the ground
    x = 420.0
    while x < end:
        if rng.random() < 0.55:
            for k in range(rng.randint(3, 6)):
                cx = x + k * 46.0
                coins.append({"x": cx, "y": terrain(cx) - 60.0 - 34.0 * math.sin(k * 0.7),
                              "got": False})
            x += rng.randint(4, 6) * 46.0 + 260.0
        else:
            coins.append({"x": x, "y": terrain(x) - 42.0, "got": False})
            x += 150.0

    # fuel cans
    fx = 900.0
    while fx < end:
        fuels.append({"x": fx, "y": terrain(fx) - 26.0, "got": False})
        fx += rng.uniform(1300.0, 1900.0)

    # obstacles are smooth bumps in the ground. small rocks are just a nudge;
    # boulders are tall enough to launch (and flip) you if you hit them fast.
    rate = _level()["obstacle_rate"]
    ox = 1150.0
    while ox < end:
        if rng.random() < 0.80:
            rocks.append({"x": ox, "w": rng.uniform(30.0, 50.0), "h": rng.uniform(12.0, 20.0)})
        else:
            rocks.append({"x": ox, "w": rng.uniform(34.0, 54.0), "h": rng.uniform(34.0, 56.0)})
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


def _bump_at(rock, x):
    """Smooth cosine hill: 0 at the edges, rock['h'] at the peak."""
    dx = x - rock["x"]
    w = rock["w"]
    if -w < dx < w:
        return rock["h"] * 0.5 * (1.0 + math.cos(math.pi * dx / w))
    return 0.0


def _ground_y(x):
    """Ground height including obstacle bumps - smooth hills, never walls."""
    h = terrain(x)
    for rock in rocks:
        dx = x - rock["x"]
        if -rock["w"] < dx < rock["w"]:
            surface = terrain(x) - _bump_at(rock, x)
            if surface < h:
                h = surface
    return h


def _solve_ground(w):
    r = _vehicle()["wheel_r"]
    floor = _ground_y(w["x"]) - r
    if w["y"] > floor:
        w["y"] = floor
        eps = 2.0
        s = (_ground_y(w["x"] + eps) - _ground_y(w["x"] - eps)) / (2.0 * eps)
        inv = 1.0 / math.hypot(1.0, s)
        nx, ny = s * inv, -inv
        vn = w["vx"] * nx + w["vy"] * ny
        if vn < 0:
            w["vx"] -= nx * vn
            w["vy"] -= ny * vn
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
        _solve_ground(rear)
        _solve_ground(front)

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


def start_game():
    global screen
    reset_run()
    screen = "playing"
    _sound("start")


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
    global _acc, fuel, _cam, _flash
    dt = min(max(float(dt), 0.0), 0.05)

    if screen != "playing":
        _flash = max(0.0, _flash - dt * 2.0)
        # ease the camera so the menu background isn't jarring
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


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
def gas(down):
    global gas_pressed
    gas_pressed = bool(down)
    if down and screen == "playing" and fuel <= 0.0:
        pass


def brake(down):
    global brake_pressed
    brake_pressed = bool(down)


def enter_key():
    if screen == "menu":
        start_game()
    elif screen in ("over", "won"):
        back_to_menu()


def tap(x, y):
    """A canvas tap. In the menu it hits buttons; elsewhere it does nothing."""
    if screen == "menu":
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

    # obstacles: draw the same smooth hill the physics rides over
    for rock in rocks:
        if not _visible(rock["x"]):
            continue
        w = rock["w"]
        steps = 14
        ctx.beginPath()
        ctx.moveTo(rock["x"] - w - _cam, terrain(rock["x"]) + 8)
        for k in range(steps + 1):
            dx = -w + (2.0 * w) * k / steps
            px = rock["x"] + dx
            ctx.lineTo(px - _cam, terrain(px) - _bump_at(rock, px))
        ctx.lineTo(rock["x"] + w - _cam, terrain(rock["x"]) + 8)
        ctx.closePath()
        ctx.fillStyle = "#5b6270" if rock["h"] < 24 else "#4a505d"
        ctx.fill()
        ctx.lineWidth = 3
        ctx.strokeStyle = "rgba(200, 212, 228, 0.45)"
        ctx.stroke()


def _draw_wheel(w, kind):
    v = _vehicle()
    r = v["wheel_r"]
    sx = w["x"] - _cam
    sy = w["y"]
    ctx.save()
    ctx.translate(sx, sy)
    ctx.rotate(w["spin"])
    ctx.fillStyle = "#1c2233"
    ctx.beginPath()
    ctx.arc(0, 0, r, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#7b8798"
    ctx.beginPath()
    ctx.arc(0, 0, r * 0.45, 0, math.pi * 2)
    ctx.fill()
    ctx.strokeStyle = "#cfd6e2"
    ctx.lineWidth = 2
    for i in range(4):
        ang = i * math.pi / 2
        ctx.beginPath()
        ctx.moveTo(0, 0)
        ctx.lineTo(math.cos(ang) * r * 0.85, math.sin(ang) * r * 0.85)
        ctx.stroke()
    ctx.restore()


def _draw_car():
    v = _vehicle()
    cx = _car_x() - _cam
    cy = _car_y()
    a = _car_angle()
    kind = v["kind"]

    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(a)

    if kind == "bike":
        ctx.fillStyle = v["body"]
        ctx.beginPath()
        ctx.moveTo(-22, 2)
        ctx.lineTo(-6, -12)
        ctx.lineTo(16, -8)
        ctx.lineTo(24, 2)
        ctx.lineTo(24, 8)
        ctx.lineTo(-22, 8)
        ctx.closePath()
        ctx.fill()
    elif kind == "truck":
        ctx.fillStyle = v["body"]
        ctx.fillRect(-40, -18, 80, 26)
        ctx.fillStyle = v["trim"]
        ctx.fillRect(-36, -26, 34, 12)
    elif kind == "car":
        ctx.fillStyle = v["body"]
        ctx.beginPath()
        ctx.moveTo(-36, 2)
        ctx.lineTo(-24, -14)
        ctx.lineTo(12, -18)
        ctx.lineTo(30, -6)
        ctx.lineTo(36, 2)
        ctx.lineTo(36, 8)
        ctx.lineTo(-36, 8)
        ctx.closePath()
        ctx.fill()
        ctx.fillStyle = v["trim"]
        ctx.fillRect(-24, -14, 40, 5)
    else:  # jeep
        ctx.fillStyle = v["body"]
        ctx.beginPath()
        ctx.moveTo(-34, 2)
        ctx.lineTo(-30, -12)
        ctx.lineTo(6, -16)
        ctx.lineTo(24, -8)
        ctx.lineTo(34, 2)
        ctx.lineTo(34, 8)
        ctx.lineTo(-34, 8)
        ctx.closePath()
        ctx.fill()
        ctx.fillStyle = v["trim"]
        ctx.fillRect(-30, -12, 34, 6)

    # cabin
    ctx.fillStyle = "rgba(20, 26, 44, 0.85)"
    ctx.beginPath()
    ctx.moveTo(-12, -14)
    ctx.lineTo(-4, -26)
    ctx.lineTo(14, -26)
    ctx.lineTo(20, -10)
    ctx.closePath()
    ctx.fill()

    # driver
    ctx.fillStyle = "#f2c14e"
    ctx.beginPath()
    ctx.arc(2, -30, 7, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#2b2d42"
    ctx.beginPath()
    ctx.arc(2, -30, 7, math.pi, math.pi * 2)
    ctx.fill()

    ctx.restore()

    _draw_wheel(rear, kind)
    _draw_wheel(front, kind)


# ---------------------------------------------------------------------------
# Drawing: HUD + screens
# ---------------------------------------------------------------------------
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

    theme = _level()["theme"]
    _draw_sky(theme)
    _draw_parallax(theme)
    _draw_terrain(theme)
    _draw_items()
    _draw_car()
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

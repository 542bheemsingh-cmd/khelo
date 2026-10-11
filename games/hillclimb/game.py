"""
Khelo Climb - a 2D hill-climb driving game written in Python.

Like the fly game, all the logic lives here and runs in the browser through
Pyodide. The car is two wheels joined by a rigid rod; gravity pulls them down,
the terrain pushes them up, and holding the gas drives them along the ground
surface so the car climbs hills and flips over when you get it wrong.

The page calls:

    update(dt)        -> advance the simulation
    draw()            -> render a frame
    gas(True/False)   -> throttle on / off
    brake(True/False) -> brake / reverse on / off
    restart()         -> start a fresh run
"""

import math

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
# Tunables
# ---------------------------------------------------------------------------
GRAVITY = 2000.0        # px / s^2
MAX_SPEED = 430.0       # px / s forward
MAX_REVERSE = 210.0     # px / s backward
DRIVE_ACC = 2600.0      # engine acceleration (applied to both wheels)
ANG_DAMP = 30.0         # damps chassis spin so it wheelies but doesn't loop
ROLL_DRAG = 0.5         # gentle rolling resistance (per second)
WHEEL_R = 17.0
WHEELBASE = 64.0
HEAD_OFF = 34.0         # driver's head height above the chassis
FUEL_MAX = 100.0
FUEL_RATE = 6.5         # fuel units burned per second on the gas
FIXED = 1.0 / 120.0     # physics substep
START_X = 130.0
PIXELS_PER_METER = 50.0

# ---------------------------------------------------------------------------
# Terrain (a fixed sum of sines -> an endless, deterministic landscape)
# ---------------------------------------------------------------------------
def terrain(x):
    return (360.0
            + 70.0 * math.sin(x * 0.0032)
            + 42.0 * math.sin(x * 0.0071 + 1.7)
            + 20.0 * math.sin(x * 0.0165 + 0.5)
            + 9.0 * math.sin(x * 0.0330 + 2.2))


def slope(x):
    return (70.0 * 0.0032 * math.cos(x * 0.0032)
            + 42.0 * 0.0071 * math.cos(x * 0.0071 + 1.7)
            + 20.0 * 0.0165 * math.cos(x * 0.0165 + 0.5)
            + 9.0 * 0.0330 * math.cos(x * 0.0330 + 2.2))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
state = "ready"         # ready | playing | over
over_reason = ""
fuel = FUEL_MAX
best = 0
gas_pressed = False
brake_pressed = False
_acc = 0.0
_cam = 0.0

rear = {"x": START_X, "y": 0.0, "vx": 0.0, "vy": 0.0, "contact": True, "spin": 0.0}
front = {"x": START_X + WHEELBASE, "y": 0.0, "vx": 0.0, "vy": 0.0, "contact": True, "spin": 0.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sound(name):
    try:
        js.playSound(name)
    except Exception:
        pass


def _load_best():
    try:
        value = js.window.localStorage.getItem("khelo_climb_best")
        return int(value) if value else 0
    except Exception:
        return 0


def _save_best(value):
    try:
        js.window.localStorage.setItem("khelo_climb_best", str(int(value)))
    except Exception:
        pass


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
    ux, uy = math.sin(a), -math.cos(a)
    return _car_x() + ux * HEAD_OFF, _car_y() + uy * HEAD_OFF


def _place_car():
    global _cam
    rear["x"] = START_X
    rear["y"] = terrain(START_X) - WHEEL_R
    front["x"] = START_X + WHEELBASE
    front["y"] = terrain(START_X + WHEELBASE) - WHEEL_R
    for w in (rear, front):
        w["vx"] = 0.0
        w["vy"] = 0.0
        w["contact"] = True
        w["spin"] = 0.0
    _cam = START_X - 260.0


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------
def _solve_rod():
    dx = front["x"] - rear["x"]
    dy = front["y"] - rear["y"]
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return
    diff = (d - WHEELBASE) / d
    rear["x"] += dx * diff * 0.5
    rear["y"] += dy * diff * 0.5
    front["x"] -= dx * diff * 0.5
    front["y"] -= dy * diff * 0.5


def _solve_ground(w):
    floor = terrain(w["x"]) - WHEEL_R
    if w["y"] > floor:
        w["y"] = floor
        s = slope(w["x"])
        inv = 1.0 / math.hypot(1.0, s)
        nx, ny = s * inv, -inv          # outward normal, pointing "up"
        vn = w["vx"] * nx + w["vy"] * ny
        if vn < 0:                       # moving into the ground
            w["vx"] -= nx * vn
            w["vy"] -= ny * vn
        w["contact"] = True


def _substep(dt, throttle):
    dx = front["x"] - rear["x"]
    dy = front["y"] - rear["y"]
    dist = math.hypot(dx, dy) or 1.0
    ax, ay = dx / dist, dy / dist          # chassis forward axis

    for w in (rear, front):
        w["vy"] += GRAVITY * dt

    # drive both wheels along the chassis axis. The two forces are collinear
    # with the rod, so they thrust without creating a spin couple, and the
    # body settles onto the slope -> the car climbs.
    if throttle:
        for w in (rear, front):
            if not w["contact"]:
                continue
            spd = w["vx"] * ax + w["vy"] * ay
            if throttle > 0 and spd < MAX_SPEED:
                w["vx"] += ax * DRIVE_ACC * dt
                w["vy"] += ay * DRIVE_ACC * dt
            elif throttle < 0 and spd > -MAX_REVERSE:
                w["vx"] -= ax * DRIVE_ACC * dt
                w["vy"] -= ay * DRIVE_ACC * dt

    for w in (rear, front):
        w["x"] += w["vx"] * dt
        w["y"] += w["vy"] * dt
        w["spin"] += (w["vx"] * dt) / WHEEL_R

    rear["contact"] = False
    front["contact"] = False
    for _ in range(4):
        _solve_rod()
        _solve_ground(rear)
        _solve_ground(front)

    # keep the rod velocity-consistent, otherwise the position solver injects
    # energy and the car spins up on its own
    dx = front["x"] - rear["x"]
    dy = front["y"] - rear["y"]
    dist = math.hypot(dx, dy) or 1.0
    ax, ay = dx / dist, dy / dist
    dvx = front["vx"] - rear["vx"]
    dvy = front["vy"] - rear["vy"]
    along = dvx * ax + dvy * ay
    rear["vx"] += ax * along * 0.5
    rear["vy"] += ay * along * 0.5
    front["vx"] -= ax * along * 0.5
    front["vy"] -= ay * along * 0.5

    # angular damping: oppose any spin of the chassis so the car can't loop
    dx = front["x"] - rear["x"]
    dy = front["y"] - rear["y"]
    l2 = dx * dx + dy * dy or 1.0
    length = math.sqrt(l2)
    dvx = front["vx"] - rear["vx"]
    dvy = front["vy"] - rear["vy"]
    omega = (dx * dvy - dy * dvx) / l2
    ux, uy = -dy / length, dx / length
    fd = ANG_DAMP * omega
    rear["vx"] += ux * fd * dt
    rear["vy"] += uy * fd * dt
    front["vx"] -= ux * fd * dt
    front["vy"] -= uy * fd * dt

    # gentle rolling drag
    for w in (rear, front):
        w["vx"] *= (1.0 - ROLL_DRAG * dt)

    for w in (rear, front):              # safety clamp
        speed = math.hypot(w["vx"], w["vy"])
        if speed > 1200.0:
            k = 1200.0 / speed
            w["vx"] *= k
            w["vy"] *= k


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def reset_game():
    global state, over_reason, fuel, _acc, gas_pressed, brake_pressed
    state = "ready"
    over_reason = ""
    fuel = FUEL_MAX
    _acc = 0.0
    gas_pressed = False
    brake_pressed = False
    _place_car()


def restart():
    reset_game()
    state_start()


def state_start():
    global state
    if state == "ready":
        state = "playing"
        _sound("start")


def gas(down):
    global gas_pressed, state
    gas_pressed = bool(down)
    if down:
        if state == "over":
            reset_game()
            state = "playing"
            _sound("start")
        elif state == "ready":
            state = "playing"
            _sound("start")


def brake(down):
    global brake_pressed, state
    brake_pressed = bool(down)
    if down and state == "ready":
        state = "playing"
        _sound("start")


def _finish(reason):
    global state, over_reason, best
    if state == "over":
        return
    state = "over"
    over_reason = reason
    m = _meters()
    if m > best:
        best = m
        _save_best(best)
    _sound("crash")


def _check_crash():
    hx, hy = _head_point()
    if hy > terrain(hx) - 2.0:
        _finish("crash")


def update(dt):
    global _acc, fuel, _cam
    dt = min(max(float(dt), 0.0), 0.05)

    throttle = 0
    if state == "playing" and fuel > 0.0:
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

    if state == "playing":
        if gas_pressed and fuel > 0.0:
            fuel = max(0.0, fuel - FUEL_RATE * dt)
            if fuel <= 0.0:
                _finish("fuel")
        _check_crash()

    # camera eases toward the car
    target_cam = _car_x() - 260.0
    _cam += (target_cam - _cam) * min(1.0, dt * 6.0)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------
def _draw_sky():
    grad = ctx.createLinearGradient(0, 0, 0, H)
    grad.addColorStop(0.0, "#142a63")
    grad.addColorStop(0.45, "#4a6bd0")
    grad.addColorStop(0.78, "#f4a15e")
    grad.addColorStop(1.0, "#ffd28a")
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, W, H)

    # sun low on the horizon
    ctx.fillStyle = "rgba(255, 236, 170, 0.45)"
    ctx.beginPath()
    ctx.arc(700, 300, 62, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#fff0bd"
    ctx.beginPath()
    ctx.arc(700, 300, 38, 0, math.pi * 2)
    ctx.fill()


def _draw_parallax():
    layers = ((0.25, "#2b3f86", 300.0, 46.0),
              (0.45, "#3a56a6", 330.0, 34.0))
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


def _draw_terrain():
    # dirt body
    ctx.beginPath()
    ctx.moveTo(0, H)
    x = _cam
    while x <= _cam + W + 12:
        ctx.lineTo(x - _cam, terrain(x))
        x += 10
    ctx.lineTo(W, H)
    ctx.closePath()
    ctx.fillStyle = "#5c4022"
    ctx.fill()

    # grass band along the surface
    ctx.beginPath()
    x = _cam
    ctx.moveTo(x - _cam, terrain(x))
    while x <= _cam + W + 12:
        ctx.lineTo(x - _cam, terrain(x))
        x += 10
    ctx.lineWidth = 15
    ctx.lineJoin = "round"
    ctx.lineCap = "round"
    ctx.strokeStyle = "#3fa34d"
    ctx.stroke()


def _draw_wheel(w):
    sx = w["x"] - _cam
    sy = w["y"]
    ctx.save()
    ctx.translate(sx, sy)
    ctx.rotate(w["spin"])
    ctx.fillStyle = "#1c2233"
    ctx.beginPath()
    ctx.arc(0, 0, WHEEL_R, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#7b8798"
    ctx.beginPath()
    ctx.arc(0, 0, WHEEL_R * 0.45, 0, math.pi * 2)
    ctx.fill()
    ctx.strokeStyle = "#cfd6e2"
    ctx.lineWidth = 2
    for i in range(4):
        ang = i * math.pi / 2
        ctx.beginPath()
        ctx.moveTo(0, 0)
        ctx.lineTo(math.cos(ang) * WHEEL_R * 0.85, math.sin(ang) * WHEEL_R * 0.85)
        ctx.stroke()
    ctx.restore()


def _draw_car():
    cx = _car_x() - _cam
    cy = _car_y()
    a = _car_angle()

    # chassis
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(a)

    ctx.fillStyle = "#e63946"
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
    ctx.fillStyle = "#ff6b6b"
    ctx.fillRect(-30, -12, 34, 6)

    # cabin
    ctx.fillStyle = "#c1121f"
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
    ctx.arc(2, -30, 7, 0, math.pi * 2)   # head
    ctx.fill()
    ctx.fillStyle = "#2b2d42"
    ctx.beginPath()
    ctx.arc(2, -30, 7, math.pi, math.pi * 2)
    ctx.fill()

    ctx.restore()

    _draw_wheel(rear)
    _draw_wheel(front)


def _draw_hud():
    ctx.textAlign = "left"
    ctx.fillStyle = "rgba(6, 14, 32, 0.55)"
    ctx.fillRect(18, 18, 250, 74)
    ctx.fillStyle = "#eaf2ff"
    ctx.font = "700 15px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("DISTANCE", 32, 42)
    ctx.font = "800 30px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(str(_meters()) + " m", 32, 76)

    # fuel bar
    ctx.fillStyle = "rgba(6, 14, 32, 0.55)"
    ctx.fillRect(W - 268, 18, 250, 46)
    ctx.fillStyle = "#9fb3d9"
    ctx.font = "700 13px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("FUEL", W - 254, 40)
    ctx.fillStyle = "rgba(255,255,255,0.16)"
    ctx.fillRect(W - 254, 46, 222, 10)
    ratio = max(0.0, fuel / FUEL_MAX)
    ctx.fillStyle = "#ffd23f" if ratio > 0.25 else "#ff5c5c"
    ctx.fillRect(W - 254, 46, 222 * ratio, 10)

    # best
    ctx.textAlign = "right"
    ctx.fillStyle = "#cfe0ff"
    ctx.font = "600 14px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Best: " + str(best) + " m", W - 18, 92)


def _panel(x, y, w, h):
    ctx.beginPath()
    r = 20
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()
    ctx.fillStyle = "rgba(10, 22, 48, 0.92)"
    ctx.fill()
    ctx.lineWidth = 3
    ctx.strokeStyle = "#ffb703"
    ctx.stroke()


def _draw_ready():
    _panel(W / 2 - 220, 150, 440, 200)
    ctx.textAlign = "center"
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 40px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("KHELO CLIMB", W / 2, 210)
    ctx.fillStyle = "#ffe9a3"
    ctx.font = "600 18px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Hold the gas to climb. Don't land on your head.", W / 2, 250)
    ctx.fillStyle = "#cfe0ff"
    ctx.fillText("Right / D = gas    Left / A = brake", W / 2, 288)
    ctx.fillText("Best: " + str(best) + " m", W / 2, 320)


def _draw_over():
    ctx.fillStyle = "rgba(4, 10, 24, 0.5)"
    ctx.fillRect(0, 0, W, H)
    _panel(W / 2 - 210, 160, 420, 210)
    ctx.textAlign = "center"
    ctx.fillStyle = "#ff8fa3"
    ctx.font = "800 34px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    title = "CRASHED!" if over_reason == "crash" else "OUT OF FUEL!"
    ctx.fillText(title, W / 2, 220)
    ctx.fillStyle = "#ffffff"
    ctx.font = "800 54px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(str(_meters()) + " m", W / 2, 288)
    ctx.fillStyle = "#cfe0ff"
    ctx.font = "600 18px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Best: " + str(best) + " m", W / 2, 320)
    ctx.fillStyle = "#ffd23f"
    ctx.fillText("Press the gas to try again", W / 2, 352)


def draw():
    _draw_sky()
    _draw_parallax()
    _draw_terrain()
    _draw_car()
    _draw_hud()

    if state == "ready":
        _draw_ready()
    elif state == "over":
        _draw_over()


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
best = _load_best()
_place_car()

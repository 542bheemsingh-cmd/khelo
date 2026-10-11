"""
Khelo Fly - a Flappy-Bird-style 2D game written in Python.

The whole game (physics, spawning, collision, scoring, difficulty, drawing)
lives in this Python file. It runs in the browser through Pyodide, which lets
Python talk to the HTML5 canvas and the Web Audio API through its `js` bridge.

The page loads this file, then drives the loop from JavaScript:

    update(dt)   -> advance the simulation by dt seconds
    draw()       -> render the current frame
    flap()       -> called on tap / click / Space

Nothing here needs a server: the same file runs on GitHub Pages.
"""

import math
import random

import js

# ---------------------------------------------------------------------------
# Canvas + layout
# ---------------------------------------------------------------------------
W, H = 480, 720            # logical resolution (CSS scales it to the screen)
GROUND_H = 96
PLAY_H = H - GROUND_H      # the bird plays in the area above the ground

canvas = js.document.getElementById("game")

# Render at the device pixel ratio so the game stays crisp on retina screens,
# then scale the context so all the code below can keep thinking in 480x720.
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
# Tunables - tweak these to change how the game feels
# ---------------------------------------------------------------------------
GRAVITY = 1700.0           # px / s^2, pulls the bird down
FLAP_VELOCITY = -455.0     # px / s, the instant upward kick on a flap
MAX_FALL = 640.0           # terminal velocity, keeps fast drops readable
BIRD_X = 132               # bird's fixed horizontal position
BIRD_R = 15                # bird collision radius

PIPE_W = 72                # pipe width
BASE_GAP = 200.0           # starting vertical gap between pipe pairs
MIN_GAP = 132.0            # the gap never gets tighter than this
BASE_SPEED = 165.0         # starting scroll speed (px / s)
SPAWN_INTERVAL = 1.5       # seconds between pipe pairs

GROUND_PERIOD = 48.0       # width of one ground stripe tile

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
state = "ready"            # ready | playing | over
bird_y = PLAY_H / 2.0
bird_vel = 0.0
bird_angle = 0.0           # how far the bird is tilted, for feel
wing_phase = 0.0           # drives the wing-flap animation

pipes = []                 # each: {"x", "gap_y", "gap_h", "scored"}
spawn_timer = 0.0
score = 0
best = 0
elapsed = 0.0
ground_offset = 0.0
flash = 0.0                # white flash on impact, fades out
clouds = []


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _sound(name):
    """Play a Web Audio blip; never let audio break the game."""
    try:
        js.playSound(name)
    except Exception:
        pass


def _load_best():
    try:
        value = js.window.localStorage.getItem("khelo_best")
        return int(value) if value else 0
    except Exception:
        return 0


def _save_best(value):
    try:
        js.window.localStorage.setItem("khelo_best", str(int(value)))
    except Exception:
        pass


def _difficulty_gap():
    """Gap shrinks as the score climbs, down to a floor."""
    return max(MIN_GAP, BASE_GAP - score * 4.5)


def _difficulty_speed():
    """Pipes scroll faster the longer you survive."""
    return BASE_SPEED + score * 5.0


def _circle_hits_rect(cx, cy, r, rx, ry, rw, rh):
    """True if a circle overlaps an axis-aligned rectangle."""
    nearest_x = min(max(cx, rx), rx + rw)
    nearest_y = min(max(cy, ry), ry + rh)
    dx = cx - nearest_x
    dy = cy - nearest_y
    return dx * dx + dy * dy <= r * r


def _spawn_pipe():
    gap = _difficulty_gap()
    margin = 70.0
    top = random.uniform(margin, PLAY_H - gap - margin)
    pipes.append({"x": float(W), "gap_y": top, "gap_h": gap, "scored": False})


def _init_clouds():
    global clouds
    clouds = [
        {
            "x": random.uniform(0, W),
            "y": random.uniform(40, 260),
            "scale": random.uniform(0.6, 1.4),
            "speed": random.uniform(8.0, 22.0),
        }
        for _ in range(6)
    ]


# ---------------------------------------------------------------------------
# Public API (called from JavaScript)
# ---------------------------------------------------------------------------
def reset_game():
    global state, bird_y, bird_vel, bird_angle, pipes, spawn_timer
    global score, elapsed, flash
    state = "ready"
    bird_y = PLAY_H / 2.0
    bird_vel = 0.0
    bird_angle = 0.0
    pipes = []
    spawn_timer = 0.5
    score = 0
    elapsed = 0.0
    flash = 0.0


def flap(*_args):
    """Start the run, or flap if already flying. Tap on game-over restarts."""
    global state, bird_vel, wing_phase
    if state == "over":
        reset_game()
    if state == "ready":
        state = "playing"
    if state == "playing":
        bird_vel = FLAP_VELOCITY
        wing_phase = 0.0
        _sound("flap")


def update(dt):
    """Advance the simulation by dt seconds."""
    global bird_y, bird_vel, bird_angle, spawn_timer, score, elapsed
    global wing_phase, ground_offset, flash, state

    dt = min(max(float(dt), 0.0), 0.033)   # clamp big gaps (tab switches)
    elapsed += dt
    flash = max(0.0, flash - dt * 3.0)

    speed = _difficulty_speed() if state == "playing" else BASE_SPEED
    ground_offset = (ground_offset + speed * dt) % GROUND_PERIOD

    for cloud in clouds:
        cloud["x"] -= cloud["speed"] * dt
        if cloud["x"] < -90:
            cloud["x"] = W + 40
            cloud["y"] = random.uniform(40, 260)

    # --- not started yet: the bird bobs in place ---
    if state == "ready":
        bird_y = PLAY_H / 2.0 + math.sin(elapsed * 3.2) * 9.0
        bird_angle = 0.0
        wing_phase += dt * 9.0
        return

    # --- game over: let the bird drop to the ground, then rest ---
    if state != "playing":
        if bird_y < PLAY_H - BIRD_R:
            bird_vel = min(bird_vel + GRAVITY * dt, MAX_FALL)
            bird_y = min(PLAY_H - BIRD_R, bird_y + bird_vel * dt)
        bird_angle = min(bird_angle + dt * 4.0, 1.4)
        return

    # --- playing ---
    wing_phase += dt * (18.0 if bird_vel < 0 else 6.0)

    bird_vel = min(bird_vel + GRAVITY * dt, MAX_FALL)
    bird_y += bird_vel * dt

    # tilt toward the direction of travel, smoothed
    target_angle = max(-0.5, min(1.2, bird_vel / 700.0))
    bird_angle += (target_angle - bird_angle) * min(1.0, dt * 10.0)

    if bird_y < BIRD_R:
        bird_y = BIRD_R
        bird_vel = 0.0

    # spawn
    spawn_timer -= dt
    if spawn_timer <= 0:
        _spawn_pipe()
        spawn_timer = SPAWN_INTERVAL

    # move + cull
    for pipe in pipes:
        pipe["x"] -= speed * dt
    pipes[:] = [p for p in pipes if p["x"] + PIPE_W > -10]

    # score when a pipe is fully cleared
    for pipe in pipes:
        if not pipe["scored"] and pipe["x"] + PIPE_W < BIRD_X - BIRD_R:
            pipe["scored"] = True
            score += 1
            _sound("score")

    # collisions
    alive = True
    for pipe in pipes:
        top_h = pipe["gap_y"]
        bottom_y = pipe["gap_y"] + pipe["gap_h"]
        if _circle_hits_rect(BIRD_X, bird_y, BIRD_R, pipe["x"], 0.0, PIPE_W, top_h):
            alive = False
        if _circle_hits_rect(
            BIRD_X, bird_y, BIRD_R, pipe["x"], bottom_y, PIPE_W, PLAY_H - bottom_y
        ):
            alive = False

    if bird_y + BIRD_R >= PLAY_H:
        bird_y = PLAY_H - BIRD_R
        alive = False

    if not alive:
        _game_over()


def _game_over():
    global state, best, flash
    state = "over"
    flash = 1.0
    if score > best:
        best = score
        _save_best(best)
    _sound("hit")


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------
def _draw_sky():
    grad = ctx.createLinearGradient(0, 0, 0, PLAY_H)
    grad.addColorStop(0.0, "#123a9e")
    grad.addColorStop(0.5, "#2f7ff0")
    grad.addColorStop(1.0, "#9ad7ff")
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, W, PLAY_H)

    # sun with a soft glow
    ctx.fillStyle = "rgba(255, 236, 150, 0.35)"
    ctx.beginPath()
    ctx.arc(W - 92, 96, 54, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#ffe9a3"
    ctx.beginPath()
    ctx.arc(W - 92, 96, 34, 0, math.pi * 2)
    ctx.fill()


def _draw_clouds():
    ctx.fillStyle = "rgba(255, 255, 255, 0.82)"
    for cloud in clouds:
        x, y, s = cloud["x"], cloud["y"], cloud["scale"]
        for dx, dy, r in ((-26, 0, 22), (0, -8, 30), (28, 0, 22), (0, 8, 24)):
            ctx.beginPath()
            ctx.arc(x + dx * s, y + dy * s, r * s, 0, math.pi * 2)
            ctx.fill()


def _pipe_body(x, y, w, h, cap_at_bottom):
    if h <= 0:
        return
    ctx.fillStyle = "#3fae4a"
    ctx.fillRect(x, y, w, h)
    ctx.fillStyle = "#6ad672"                     # light edge
    ctx.fillRect(x + 5, y, 11, h)
    ctx.fillStyle = "#2c8a37"                     # dark edge
    ctx.fillRect(x + w - 12, y, 12, h)

    cap_h = 26
    if cap_at_bottom:
        cap_y = y + h - cap_h
    else:
        cap_y = y
    ctx.fillStyle = "#3fae4a"
    ctx.fillRect(x - 6, cap_y, w + 12, cap_h)
    ctx.fillStyle = "#6ad672"
    ctx.fillRect(x - 6, cap_y, w + 12, 7)
    ctx.fillStyle = "#2c8a37"
    ctx.fillRect(x - 6, cap_y + cap_h - 7, w + 12, 7)


def _draw_pipes():
    for pipe in pipes:
        x = pipe["x"]
        gy = pipe["gap_y"]
        bottom_y = gy + pipe["gap_h"]
        _pipe_body(x, 0.0, PIPE_W, gy, True)
        _pipe_body(x, bottom_y, PIPE_W, PLAY_H - bottom_y, False)


def _draw_ground():
    # grass strip
    ctx.fillStyle = "#57c96b"
    ctx.fillRect(0, PLAY_H, W, 20)
    ctx.fillStyle = "#3ea34f"
    x = -ground_offset
    while x < W:
        ctx.fillRect(x, PLAY_H, GROUND_PERIOD / 2.0, 20)
        x += GROUND_PERIOD
    # dirt
    ctx.fillStyle = "#cf9450"
    ctx.fillRect(0, PLAY_H + 20, W, GROUND_H - 20)
    ctx.fillStyle = "#b5793a"
    x = -ground_offset * 0.6
    while x < W:
        ctx.fillRect(x, PLAY_H + 34, 30, 12)
        x += 60


def _draw_bird():
    ctx.save()
    ctx.translate(BIRD_X, bird_y)
    ctx.rotate(bird_angle)

    # body
    ctx.fillStyle = "#ffd23f"
    ctx.beginPath()
    ctx.ellipse(0, 0, BIRD_R + 4, BIRD_R + 1, 0, 0, math.pi * 2)
    ctx.fill()

    # belly
    ctx.fillStyle = "#fff2bd"
    ctx.beginPath()
    ctx.ellipse(-1, 5, BIRD_R - 3, BIRD_R - 5, 0, 0, math.pi * 2)
    ctx.fill()

    # wing (flaps while rising, glides while falling)
    lift = math.sin(wing_phase) * 5.0
    ctx.fillStyle = "#ffb703"
    ctx.beginPath()
    ctx.ellipse(-4, 2 + lift, 9, 6, -0.3, 0, math.pi * 2)
    ctx.fill()

    # eye
    ctx.fillStyle = "#ffffff"
    ctx.beginPath()
    ctx.arc(7, -6, 6, 0, math.pi * 2)
    ctx.fill()
    ctx.fillStyle = "#111827"
    ctx.beginPath()
    ctx.arc(9, -6, 2.6, 0, math.pi * 2)
    ctx.fill()

    # beak
    ctx.fillStyle = "#ff7b00"
    ctx.beginPath()
    ctx.moveTo(BIRD_R + 1, -2)
    ctx.lineTo(BIRD_R + 15, 3)
    ctx.lineTo(BIRD_R + 1, 8)
    ctx.closePath()
    ctx.fill()

    ctx.restore()


def _draw_score():
    if state not in ("playing", "over"):
        return
    ctx.textAlign = "center"
    ctx.font = "800 54px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.lineWidth = 7
    ctx.strokeStyle = "rgba(8, 20, 45, 0.55)"
    ctx.strokeText(str(score), W / 2.0, 100)
    ctx.fillStyle = "#ffffff"
    ctx.fillText(str(score), W / 2.0, 100)


def _draw_ready():
    ctx.textAlign = "center"

    ctx.font = "800 46px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.lineWidth = 7
    ctx.strokeStyle = "rgba(8, 20, 45, 0.55)"
    ctx.strokeText("KHELO FLY", W / 2.0, 214)
    ctx.fillStyle = "#ffffff"
    ctx.fillText("KHELO FLY", W / 2.0, 214)

    ctx.font = "600 20px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillStyle = "#eaf6ff"
    ctx.fillText("Tap, click or press Space to flap", W / 2.0, 262)

    ctx.fillStyle = "#ffe9a3"
    ctx.fillText("Best score: " + str(best), W / 2.0, 300)


def _round_rect(x, y, w, h, r):
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()


def _draw_over():
    ctx.fillStyle = "rgba(4, 12, 30, 0.55)"
    ctx.fillRect(0, 0, W, PLAY_H)

    _round_rect(W / 2.0 - 150, 188, 300, 254, 22)
    ctx.fillStyle = "rgba(12, 26, 56, 0.94)"
    ctx.fill()
    ctx.lineWidth = 3
    ctx.strokeStyle = "#63d06e"
    ctx.stroke()

    ctx.textAlign = "center"
    ctx.fillStyle = "#9fe6ff"
    ctx.font = "700 22px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("GAME OVER", W / 2.0, 238)

    ctx.fillStyle = "#ffffff"
    ctx.font = "800 64px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText(str(score), W / 2.0, 316)

    ctx.fillStyle = "#cfe9ff"
    ctx.font = "600 20px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Best: " + str(best), W / 2.0, 354)

    ctx.fillStyle = "#ffd23f"
    ctx.font = "700 20px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    ctx.fillText("Tap to play again", W / 2.0, 402)


def draw():
    """Render one frame."""
    _draw_sky()
    _draw_clouds()
    _draw_pipes()
    _draw_ground()
    _draw_bird()
    _draw_score()

    if state == "ready":
        _draw_ready()
    elif state == "over":
        _draw_over()

    if flash > 0:
        ctx.fillStyle = "rgba(255, 255, 255, " + str(round(flash * 0.5, 3)) + ")"
        ctx.fillRect(0, 0, W, H)


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
best = _load_best()
_init_clouds()
reset_game()

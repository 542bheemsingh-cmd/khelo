"""
Khelo Battleground - a third-person 3D battle royale on a map shaped like India.

The game logic is all Python. three.js only draws what Python tells it to.

You drop onto the map with nine bots. The blue zone closes in. Last one
standing wins.

The page calls:
    set_size(w, h)        -> the HUD canvas was resized (CSS pixels)
    set_move(x, z)        -> the movement stick, -1..1 each
    set_look(dx, dy)      -> a look drag, in radians
    set_fire(on)          -> the fire button went down / up
    tap(x, y)             -> a click on the canvas
    update(dt)            -> advance the game
    draw()                -> redraw the HUD
    start_game()          -> begin a round
"""

import json
import math
import random

import js

# ---------------------------------------------------------------------------
# The map: the mainland outline, taken from DataMeet's open India boundary
# data (india-composite.geojson, CC0), simplified to 189 points and scaled so
# the map is 1000 units tall. North is up (-z).
# ---------------------------------------------------------------------------
# the outline below is authored in a 912.5 x 1000 box; the world is scaled up
# from it so there is room for towns, roads and bridges
_SRC_W, _SRC_H = 912.5, 1000.0
WORLD_W = 1825.0
WORLD_H = 2000.0

_RING_RAW = [
    (291.9, 53.5), (348.8, 36.1), (371.1, 55.6), (382.2, 53.8),
    (371.7, 80.4), (354, 89.1), (350.7, 104.7), (334.6, 105.7),
    (340.9, 117.3), (336.3, 126.2), (350.9, 132.8), (355.2, 150.5),
    (337.1, 162.2), (330, 149.8), (319.2, 155.5), (331.2, 174.1),
    (331.2, 197.6), (341.2, 192.7), (351.5, 207.6), (401.5, 234.4),
    (380.8, 251.6), (371.7, 283.5), (428.2, 316.9), (453.9, 321.5),
    (454.8, 329.1), (472.9, 335.1), (499, 328.6), (532.1, 354.8),
    (545.1, 350.9), (552.1, 361.4), (619.4, 368.5), (622.8, 314.8),
    (639.1, 307.9), (646.9, 316.9), (642.4, 341.6), (654.6, 353.1),
    (745.8, 351.8), (747.9, 336.6), (733.2, 329.8), (732.9, 320.2),
    (758.3, 319.1), (765.2, 306.7), (826.1, 267.2), (845.9, 275.1),
    (870.7, 264.2), (888.7, 286.6), (881.7, 294.5), (891.2, 290.8),
    (912.5, 311.5), (896.8, 325.6), (904.5, 343.3), (891, 333.6),
    (876.1, 336.9), (842.4, 359.7), (843.5, 378.5), (826.3, 401.9),
    (828.8, 417.8), (811.4, 455.3), (785.6, 447.3), (787.3, 480),
    (779.2, 483.1), (781.6, 510), (772.4, 521.2), (765.9, 513.8),
    (762.9, 519.9), (752.8, 459.8), (742.7, 459.3), (732.2, 486.8),
    (717.8, 463.5), (724.5, 446.4), (741, 445.4), (749.2, 435.6),
    (757.4, 414.5), (676.6, 405.4), (671.6, 372.8), (668.4, 382.1),
    (661.5, 380.7), (653.1, 367.3), (640, 371.9), (631.6, 359.4),
    (635.5, 368.6), (622.5, 387.4), (650.6, 406.4), (633, 408.3),
    (619.4, 427), (642.1, 440.4), (636.6, 462.2), (644.2, 467.4),
    (641.6, 475.8), (650.3, 477.2), (645.5, 484.3), (653.5, 531.7),
    (641.7, 530.3), (639.1, 516.5), (626.9, 534.3), (619.8, 511.4),
    (625.1, 515.5), (613, 529.6), (585.2, 542), (583.8, 561.4),
    (590.1, 563.3), (568.3, 589.8), (526.7, 609.2), (498.3, 646.6),
    (441.4, 690.5), (441.3, 707), (408.9, 716.2), (398.6, 736.3),
    (390.5, 730.1), (377.6, 737.6), (370.8, 758.3), (380.2, 820.1),
    (361.8, 875.8), (365.6, 922.8), (347.3, 924.5), (335, 951.2),
    (344, 958.3), (315.2, 967.4), (309.1, 989.6), (292.8, 1000),
    (261.5, 971.5), (240.4, 894.7), (219.5, 864.3), (198.1, 787),
    (165, 724.5), (146.3, 633.3), (152.9, 622), (150.3, 616.2),
    (144.7, 626.4), (147.3, 604.6), (140, 593.9), (148.6, 562),
    (138.2, 543.4), (148.5, 530.3), (136.3, 530.8), (142.9, 520.1),
    (135.4, 520), (148, 510), (129.7, 508.5), (123, 546.8), (82.8, 564.3),
    (61.9, 551.8), (23.8, 508.5), (62.5, 500.4), (71.1, 485.6),
    (63.9, 482.7), (48.1, 493.7), (32, 490.3), (7.9, 467), (19.9, 454.3),
    (0, 463.3), (5.8, 451), (18.1, 451.1), (19.9, 439.2), (57.9, 444.2),
    (92, 436.2), (77.7, 391.3), (60.2, 383.1), (62.5, 362), (41.8, 355.3),
    (44.2, 340.2), (68.7, 311.5), (84.3, 322.1), (116.4, 313.3),
    (131.7, 285.4), (149.1, 276.5), (163.2, 244.8), (181.1, 236),
    (179.9, 226), (203.7, 205.8), (197.9, 203.8), (201, 177.6), (224.8, 166),
    (203.3, 156.8), (204, 144.8), (193.6, 147.3), (170.6, 136.1),
    (163.2, 91.7), (186.1, 66.1), (174.2, 62.6), (175.3, 52.1), (163.4, 52),
    (156.3, 40.5), (137.3, 40.8), (136.7, 27.7), (152.7, 11.6),
    (177.4, 10.9), (171.7, 3.9), (217.8, 0)
]

_SX = WORLD_W / _SRC_W
_SZ = WORLD_H / _SRC_H
RING = [(x * _SX, z * _SZ) for x, z in _RING_RAW]

# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------
NX, NZ = 160, 176
CELL_X = WORLD_W / NX
CELL_Z = WORLD_H / NZ

HEIGHTS = []
LAND = []
_READY = False

WATER_Y = -2.2


def _hash2(i, j, seed):
    h = (i * 374761393 + j * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _vnoise(x, y, seed):
    i, j = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - i, y - j
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = _hash2(i, j, seed)
    b = _hash2(i + 1, j, seed)
    c = _hash2(i, j + 1, seed)
    d = _hash2(i + 1, j + 1, seed)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _fbm(x, y, seed, octaves=3):
    v, amp, f = 0.0, 1.0, 1.0
    for o in range(octaves):
        v += _vnoise(x * f, y * f, seed + o * 17) * amp
        amp *= 0.5
        f *= 2.0
    return v


def _scan_mask(seed=0):
    """Fill the land mask a row at a time - far cheaper than testing every point."""
    mask = [[0] * NX for _ in range(NZ)]
    n = len(RING)
    for j in range(NZ):
        z = (j + 0.5) * CELL_Z
        xs = []
        for i in range(n):
            x1, z1 = RING[i]
            x2, z2 = RING[(i + 1) % n]
            if (z1 <= z < z2) or (z2 <= z < z1):
                t = (z - z1) / (z2 - z1)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            i0 = max(0, int(xs[k] / CELL_X))
            i1 = min(NX - 1, int(xs[k + 1] / CELL_X))
            for i in range(i0, i1 + 1):
                mask[j][i] = 1
    return mask


def _blur(mask, passes=3):
    """A cheap way to know how far inland a cell is."""
    cur = [row[:] for row in mask]
    for _ in range(passes):
        nxt = [row[:] for row in cur]
        for j in range(NZ):
            for i in range(NX):
                s, c = 0, 0
                for dj in (-1, 0, 1):
                    for di in (-1, 0, 1):
                        jj, ii = j + dj, i + di
                        if 0 <= jj < NZ and 0 <= ii < NX:
                            s += cur[jj][ii]
                            c += 1
                nxt[j][i] = s / float(c)
        cur = nxt
    return cur


def build_terrain(seed=7):
    """Work out the height of every grid point, once, at start-up."""
    global HEIGHTS, LAND, _READY
    mask = _scan_mask(seed)
    soft = _blur(mask, 3)
    heights = [0.0] * (NX * NZ)
    for j in range(NZ):
        for i in range(NX):
            ramp = min(1.0, max(0.0, (soft[j][i] - 0.45) / 0.5))
            if not mask[j][i]:
                heights[j * NX + i] = WATER_Y - 1.0
                continue
            wx = (i + 0.5) * CELL_X
            wz = (j + 0.5) * CELL_Z
            h = _fbm(wx / 150.0, wz / 150.0, seed)
            ridge = _fbm(wx / 420.0, wz / 420.0, seed + 91, 2)
            hill = 4.0 + h * 24.0 + max(0.0, ridge - 0.45) * 52.0
            heights[j * NX + i] = WATER_Y + hill * ramp
    HEIGHTS = heights
    LAND = [bool(v) for row in mask for v in row]
    _READY = True
    build_towns()
    _index_buildings()


# towns, roads and the buildings inside them
TOWNS = []          # [{"x": .., "z": .., "r": ..}]
BUILDINGS = []      # [[x, z, w, d, h, rot]]
ROADS = []          # [[(x, z), ...], ...]


def _flat_spot(margin, lo, hi, sep, tries=900):
    """A reasonably flat piece of land, away from the ones we already have."""
    best, bestd = None, -1.0
    for _ in range(tries):
        x = _rng.uniform(margin, WORLD_W - margin)
        z = _rng.uniform(margin, WORLD_H - margin)
        if not land_at(x, z):
            continue
        h = height_at(x, z)
        if h < lo or h > hi:
            continue
        # flatness: compare with a few neighbours
        spread = max(abs(height_at(x + 18, z) - h), abs(height_at(x - 18, z) - h),
                     abs(height_at(x, z + 18) - h), abs(height_at(x, z - 18) - h))
        if spread > 7.0:
            continue
        if TOWNS:
            d = min(math.hypot(x - t["x"], z - t["z"]) for t in TOWNS)
            if d < sep:
                continue
            if d > bestd:
                best, bestd = (x, z), d
        else:
            return x, z
    return best if best else (WORLD_W / 2, WORLD_H / 2)


def build_towns(seed=11):
    """Ten towns, each a little grid of blocks with a few gaps."""
    TOWNS[:] = []
    BUILDINGS[:] = []
    ROADS[:] = []
    r = random.Random(seed)
    for _ in range(10):
        x, z = _flat_spot(150.0, WATER_Y + 6.0, 30.0, 340.0)
        TOWNS.append({"x": x, "z": z, "r": 0.0})

    for t in TOWNS:
        n = r.randint(8, 16)
        span = 120.0
        placed = []
        for _ in range(n * 4):
            if len(placed) >= n:
                break
            bx = t["x"] + r.uniform(-span, span)
            bz = t["z"] + r.uniform(-span, span)
            if not land_at(bx, bz):
                continue
            if height_at(bx, bz) < WATER_Y + 3.0:
                continue
            w = r.uniform(9.0, 17.0)
            d = r.uniform(9.0, 17.0)
            if any(math.hypot(bx - p[0], bz - p[1]) < (w + p[2]) * 0.62 for p in placed):
                continue
            hh = r.uniform(7.0, 13.0)
            if r.random() < 0.18:
                hh = r.uniform(17.0, 24.0)      # the odd tower
            placed.append((bx, bz, w, d, hh))
            BUILDINGS.append([bx, bz, w, d, hh, 0.0])
            t["r"] = max(t["r"], math.hypot(bx - t["x"], bz - t["z"]) + 20.0)

    # roads: link each town to its nearest neighbour, plus a couple of extras
    links = []
    for i, a in enumerate(TOWNS):
        best, bd = None, 1e9
        for j, b in enumerate(TOWNS):
            if i == j:
                continue
            d = math.hypot(a["x"] - b["x"], a["z"] - b["z"])
            if d < bd:
                best, bd = j, d
        if best is not None:
            pair = (min(i, best), max(i, best))
            if pair not in links:
                links.append(pair)
    for _ in range(3):
        i = r.randrange(len(TOWNS))
        j = r.randrange(len(TOWNS))
        if i != j:
            pair = (min(i, j), max(i, j))
            if pair not in links:
                links.append(pair)

    for i, j in links:
        ROADS.append(_road_path(TOWNS[i], TOWNS[j], r))


def _road_path(a, b, r, steps=16):
    pts = []
    dx, dz = b["x"] - a["x"], b["z"] - a["z"]
    length = math.hypot(dx, dz) or 1.0
    bend = r.uniform(-0.09, 0.09) * length
    for k in range(steps + 1):
        t = k / steps
        x = a["x"] + dx * t
        z = a["z"] + dz * t
        off = math.sin(t * math.pi) * bend
        x += -dz / length * off
        z += dx / length * off
        pts.append((round(x, 1), round(z, 1)))
    return pts


_BGRID = {}
BGRID_CELL = 200.0


def _index_buildings():
    """Bucket the buildings so a movement check only looks nearby."""
    _BGRID.clear()
    for i, b in enumerate(BUILDINGS):
        gx = int(b[0] / BGRID_CELL)
        gz = int(b[1] / BGRID_CELL)
        _BGRID.setdefault((gx, gz), []).append(i)


def blocked(x, z):
    """Land you can stand on: dry ground with no building on it."""
    if not land_at(x, z):
        return True
    gx = int(x / BGRID_CELL)
    gz = int(z / BGRID_CELL)
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for i in _BGRID.get((gx + dx, gz + dz), ()):
                b = BUILDINGS[i]
                if (abs(x - b[0]) < b[2] * 0.5 + 1.6
                        and abs(z - b[1]) < b[3] * 0.5 + 1.6):
                    return True
    return False


def height_at(x, z):
    """The ground height at a world point, smoothed between grid points."""
    if not _READY:
        return 0.0
    gx = x / CELL_X - 0.5
    gz = z / CELL_Z - 0.5
    i = int(math.floor(gx))
    j = int(math.floor(gz))
    fx = gx - i
    fz = gz - j
    i = max(0, min(NX - 2, i))
    j = max(0, min(NZ - 2, j))
    fx = max(0.0, min(1.0, fx))
    fz = max(0.0, min(1.0, fz))
    h00 = HEIGHTS[j * NX + i]
    h10 = HEIGHTS[j * NX + i + 1]
    h01 = HEIGHTS[(j + 1) * NX + i]
    h11 = HEIGHTS[(j + 1) * NX + i + 1]
    return (h00 * (1 - fx) + h10 * fx) * (1 - fz) + (h01 * (1 - fx) + h11 * fx) * fz


def land_at(x, z):
    if not _READY:
        return False
    if x < 0 or z < 0 or x >= WORLD_W or z >= WORLD_H:
        return False
    i = min(NX - 1, int(x / CELL_X))
    j = min(NZ - 1, int(z / CELL_Z))
    return LAND[j * NX + i]


def _random_land(margin=40.0, tries=600, lo=None, hi=None):
    """A random point on dry land. Give lo/hi to keep off beaches and peaks."""
    for _ in range(tries):
        x = _rng.uniform(margin, WORLD_W - margin)
        z = _rng.uniform(margin, WORLD_H - margin)
        if not land_at(x, z):
            continue
        if lo is not None:
            h = height_at(x, z)
            if h < lo or h > hi:
                continue
        if BUILDINGS and blocked(x, z):
            continue
        return x, z
    return WORLD_W / 2, WORLD_H / 2


# ---------------------------------------------------------------------------
# HUD canvas
# ---------------------------------------------------------------------------
W, H = 900, 560
DPR = 1.0
try:
    DPR = min(max(float(js.devicePixelRatio or 1.0), 1.0), 2.0)
except Exception:
    DPR = 1.0

hud = js.document.getElementById("hud")
hctx = hud.getContext("2d")

UI = 1.0
MIN_TOUCH = 0.0


def set_ui(scale):
    global UI, MIN_TOUCH
    try:
        s = float(scale)
    except Exception:
        return
    if s <= 0:
        return
    UI = max(1.0, min(1.35, 1.0 / s))
    MIN_TOUCH = min(66.0, 48.0 / s)


def _fs(px, cap=1.35):
    return int(round(px * min(UI, cap)))


FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"


def set_size(w, h):
    """The page tells us the HUD canvas size in CSS pixels."""
    global W, H
    W = max(240, int(w))
    H = max(240, int(h))
    hud.width = int(W * DPR)
    hud.height = int(H * DPR)
    hctx.setTransform(DPR, 0, 0, DPR, 0, 0)
    set_ui(min(W / 900.0, H / 560.0))


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
WEAPONS = {
    "rifle":   {"name": "RIFLE",   "mag": 30, "dmg": 17.0, "cool": 0.16,
                "pellets": 1, "spread": 0.012, "reload": 1.5},
    "shotgun": {"name": "SHOTGUN", "mag": 6,  "dmg": 9.0,  "cool": 0.80,
                "pellets": 6, "spread": 0.075, "reload": 2.2},
}

# ---- 8. bots come in three grades -----------------------------------------
TIERS = [
    {"cool": (1.3, 2.1), "spread": 0.11, "range": 230.0, "strafe": 0.15},  # green
    {"cool": (0.9, 1.5), "spread": 0.06, "range": 300.0, "strafe": 0.45},  # veteran
    {"cool": (0.6, 1.0), "spread": 0.03, "range": 360.0, "strafe": 0.80},  # elite
]

BOT_COUNT = 12
PLAYER_SPEED = 15.0
BOT_SPEED = 9.5
FIRE_COOL = 0.16
BULLET_SPEED = 210.0
BULLET_LIFE = 1.1
PLAYER_DAMAGE = 17.0
BOT_DAMAGE = 9.0

state = "menu"          # menu | play | over
result = ""             # win | lose
player = {}
bots = []
shots = []
zone = {}
message = ""
elapsed = 0.0
zone_timer = 0.0
zone_phase = 0
_menu_hit = []

TOUCH_UI = False
STICK = {"x": 0.0, "y": 0.0, "on": False}
move_x = 0.0
move_z = 0.0
pvx = 0.0                 # the soldier has weight: it speeds up and slows down
pvz = 0.0
hitmark = 0.0             # a little cross on the crosshair when a shot lands
stamina = 100.0           # 1. sprinting burns it, standing still refills it
crouching = False
sprinting = False
weapon = "rifle"
mag = 30
reloading = 0.0
pickups = []              # health and ammo crates lying about
dmg_numbers = []          # the numbers that float off a bot you hit
shake = 0.0               # screen shake, handed to the renderer
hurt_dir = 0.0            # which way the last hit came from, for the arc
placement = 0
paused = False
hits = []                 # where bullets struck, for the sparks
feed = []                 # the kill feed
look_dx = 0.0
look_dy = 0.0
firing = False
cam_yaw = 0.0
cam_pitch = 0.34

_rng = random.Random()


def _notify_playing(on):
    """Tell the page whether a round is on, so it can lock or free the mouse."""
    try:
        js.set_playing(bool(on))
    except Exception:
        pass


def _sound(name):
    try:
        js.playSound(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
def set_stick(cx, cy, on):
    """Where the thumb is resting, so the stick can be drawn there."""
    STICK["x"] = float(cx)
    STICK["y"] = float(cy)
    STICK["on"] = bool(on)


def set_touch_ui(on):
    global TOUCH_UI
    TOUCH_UI = bool(on)


def set_move(x, z):
    global move_x, move_z
    move_x = max(-1.0, min(1.0, float(x)))
    move_z = max(-1.0, min(1.0, float(z)))


def set_look(dx, dy):
    global look_dx, look_dy
    look_dx += float(dx)
    look_dy += float(dy)


def set_sprint(on):
    global sprinting
    sprinting = bool(on)


def set_crouch(on):
    global crouching
    crouching = bool(on)


def set_swap():
    """Change weapon - 6. weapon swap."""
    global weapon, mag, reloading
    if state != "play" or reloading > 0:
        return
    weapon = "shotgun" if weapon == "rifle" else "rifle"
    mag = WEAPONS[weapon]["mag"]
    reloading = 0.0
    _sound("tap")


def set_reload():
    """4. reload, by hand or by itself when the magazine runs dry."""
    global reloading
    if state != "play" or reloading > 0:
        return
    if mag >= WEAPONS[weapon]["mag"]:
        return
    reloading = WEAPONS[weapon]["reload"]
    _sound("reload")


def set_pause(on):
    global paused
    if state != "play":
        paused = False
        return
    paused = bool(on)
    _notify_playing(not paused)


def set_fire(on):
    global firing
    firing = bool(on)


def _in(rect, x, y):
    rx, ry, rw, rh = rect
    if MIN_TOUCH > rw:
        rx -= (MIN_TOUCH - rw) / 2.0
        rw = MIN_TOUCH
    if MIN_TOUCH > rh:
        ry -= (MIN_TOUCH - rh) / 2.0
        rh = MIN_TOUCH
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def press_primary():
    """Space or Enter on a menu: take the obvious action."""
    if state == "menu":
        _sound("start")
        start_game()
    elif state == "over":
        _sound("tap")
        start_game()


PAUSE_RECT = (16, 12, 58, 44)


def tap(x, y):
    global state, paused
    if state == "play":
        if paused:
            for tag, r in _menu_hit:
                if _in(r, x, y):
                    _sound("tap")
                    if tag == "resume":
                        set_pause(False)
                    else:
                        set_pause(False)
                        state = "menu"
                        _notify_playing(False)
                    return
            return
        if _in(PAUSE_RECT, x, y):
            _sound("tap")
            set_pause(True)
            return
        for tag, label, active, r in touch_buttons():
            if _in(r, x, y):
                _sound("tap")
                if tag == "sprint":
                    set_sprint(not sprinting)
                elif tag == "crouch":
                    set_crouch(not crouching)
                elif tag == "reload":
                    set_reload()
                elif tag == "swap":
                    set_swap()
                return
    if state == "menu":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("start")
                start_game()
                return
        return
    if state == "over":
        for tag, r in _menu_hit:
            if _in(r, x, y):
                _sound("tap")
                if tag == "again":
                    start_game()
                else:
                    state = "menu"
                    _notify_playing(False)
                return
        return


# ---------------------------------------------------------------------------
# Starting a round
# ---------------------------------------------------------------------------
def start_game(seed=None):
    global state, player, bots, shots, zone, message, elapsed, result
    global zone_timer, zone_phase, cam_yaw, cam_pitch, move_x, move_z, firing
    global pvx, pvz, hitmark, hits, feed

    if not _READY:
        build_terrain()

    _rng.seed(seed if seed is not None else _rng.randrange(1 << 30))

    px, pz = _random_land(120.0, lo=WATER_Y + 5.0, hi=26.0)
    player = {"x": px, "z": pz, "yaw": 0.0, "hp": 100.0, "alive": True,
              "cool": 0.0, "kills": 0, "ammo": 120, "hurt": 0.0}

    bots = []
    for k in range(BOT_COUNT):
        for _ in range(200):
            bx, bz = _random_land(80.0, lo=WATER_Y + 5.0, hi=28.0)
            if math.hypot(bx - px, bz - pz) > 220:
                break
        bots.append({"x": bx, "z": bz, "yaw": _rng.uniform(0, 6.283),
                     "hp": 100.0, "alive": True, "cool": _rng.uniform(0.4, 1.6),
                     "wander": 0.0, "wx": 0.0, "wz": 0.0, "dying": 0.0,
                     "tier": min(2, int(_rng.random() * 3)),
                     "flash": 0.0, "strafe": 1.0 if _rng.random() < 0.5 else -1.0})

    # 7. health and ammo crates, scattered over the land
    pickups[:] = []
    for _ in range(26):
        gx, gz = _random_land(70.0, lo=WATER_Y + 4.0, hi=26.0)
        pickups.append({"x": gx, "z": gz,
                        "kind": "health" if _rng.random() < 0.45 else "ammo",
                        "taken": False})

    shots = []
    zone = {"cx": WORLD_W / 2, "cz": WORLD_H / 2, "r": 1250.0,
            "tx": WORLD_W / 2, "tz": WORLD_H / 2, "tr": 1250.0}
    zone_timer = 26.0
    zone_phase = 0
    elapsed = 0.0
    result = ""
    message = "Land, loot and survive. The zone closes in %d seconds." % int(zone_timer)
    state = "play"
    _notify_playing(True)
    cam_yaw = 0.0
    cam_pitch = 0.34
    move_x = move_z = 0.0
    pvx = pvz = 0.0
    global stamina, crouching, sprinting, weapon, mag, reloading, shake
    global dmg_numbers, hurt_dir, placement, paused
    stamina = 100.0
    crouching = sprinting = paused = False
    weapon = "rifle"
    mag = WEAPONS["rifle"]["mag"]
    reloading = 0.0
    shake = 0.0
    dmg_numbers[:] = []
    hurt_dir = 0.0
    placement = 0
    hitmark = 0.0
    hits[:] = []
    feed[:] = []
    firing = False
    _sound("start")


# ---------------------------------------------------------------------------
# Shooting
# ---------------------------------------------------------------------------
def _spawn_shot(x, z, yaw, owner, dmg=PLAYER_DAMAGE):
    shots.append({"x": x, "z": z,
                  "dx": math.sin(yaw) * BULLET_SPEED,
                  "dz": math.cos(yaw) * BULLET_SPEED,
                  "life": BULLET_LIFE, "owner": owner, "dmg": dmg})


def _nearest_target(x, z, yaw, max_dist=180.0, cone=0.34):
    """A little aim assist, so the game is playable with a thumb."""
    best, bestd = None, max_dist
    for b in bots:
        if not b["alive"]:
            continue
        dx, dz = b["x"] - x, b["z"] - z
        d = math.hypot(dx, dz)
        if d > bestd or d < 1e-6:
            continue
        ang = math.atan2(dx, dz)
        diff = (ang - yaw + math.pi) % 6.283185 - math.pi
        if abs(diff) <= cone:
            best, bestd = b, d
    return best


def fire():
    global mag, shake
    if state != "play" or paused or not player.get("alive"):
        return
    if reloading > 0 or player["cool"] > 0:
        return
    w = WEAPONS[weapon]
    if mag <= 0:
        set_reload()
        return

    player["cool"] = w["cool"]
    mag -= 1
    shake = max(shake, 0.45 if weapon == "shotgun" else 0.16)

    base = cam_yaw
    t = _nearest_target(player["x"], player["z"], base)
    if t is not None:
        base = math.atan2(t["x"] - player["x"], t["z"] - player["z"])
    for _ in range(w["pellets"]):
        _spawn_shot(player["x"], player["z"],
                    base + _rng.uniform(-w["spread"], w["spread"]),
                    "p", w["dmg"])
    try:
        js.world3d.flash()
    except Exception:
        pass
    _sound("shot")
    if mag <= 0:
        set_reload()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def update(dt):
    global elapsed, zone_timer, zone_phase, message, state, result
    global cam_yaw, cam_pitch, look_dx, look_dy
    global hitmark, pvx, pvz, stamina, mag, reloading, shake
    global dmg_numbers, hurt_dir, placement

    dt = min(max(float(dt), 0.0), 0.06)
    if state != "play" or paused:
        look_dx = look_dy = 0.0
        return

    elapsed += dt

    if hitmark > 0:
        hitmark = max(0.0, hitmark - dt)
    for h in hits:
        h["life"] -= dt
    hits[:] = [h for h in hits if h["life"] > 0]
    for f in feed:
        f["life"] -= dt
    feed[:] = [f for f in feed if f["life"] > 0]
    for b in bots:
        if not b["alive"] and b.get("dying", 0) > 0:
            b["dying"] = max(0.0, b["dying"] - dt)

    # growing yaw swings the aim to the LEFT of the screen (screen-right is
    # rotate(forward, -90) = (-cos y, sin y)), so a right drag must lower it
    cam_yaw -= look_dx
    cam_pitch = max(0.06, min(0.95, cam_pitch + look_dy))
    look_dx = look_dy = 0.0

    # --- the player ---
    p = player
    p["cool"] = max(0.0, p["cool"] - dt)
    p["hurt"] = max(0.0, p["hurt"] - dt)

    if p["alive"]:
        # turn toward the aim instead of snapping to it
        diff = (cam_yaw - p["yaw"] + math.pi) % 6.283185 - math.pi
        p["yaw"] += diff * min(1.0, dt * 15.0)
        # 1. sprinting burns stamina, 3. crouching is slow and low
        if crouching:
            spd = PLAYER_SPEED * 0.52
        elif sprinting and stamina > 1.0:
            spd = PLAYER_SPEED * 1.55
        else:
            spd = PLAYER_SPEED
        if sprinting and not crouching and stamina > 0.5:
            stamina = max(0.0, stamina - 30.0 * dt)
        else:
            stamina = min(100.0, stamina + 20.0 * dt)

        mx, mz = move_x, move_z
        magd = math.hypot(mx, mz)
        if magd > 1.0:
            mx, mz = mx / magd, mz / magd
        if magd > 0.08:
            # move relative to where the camera is looking
            s, c = math.sin(cam_yaw), math.cos(cam_yaw)
            # screen-right is rotate(forward, -90), so D must go to (-c, +s)
            wx = -mx * c + mz * s
            wz = mx * s + mz * c
            tvx, tvz = wx * spd, wz * spd
        else:
            tvx = tvz = 0.0
        # ease toward the wanted speed, so starts and stops are not instant
        k = min(1.0, dt * (11.0 if (tvx or tvz) else 16.0))
        pvx += (tvx - pvx) * k
        pvz += (tvz - pvz) * k
        if abs(pvx) > 0.01 or abs(pvz) > 0.01:
            nx = p["x"] + pvx * dt
            nz = p["z"] + pvz * dt
            if not blocked(nx, p["z"]):
                p["x"] = max(2.0, min(WORLD_W - 2.0, nx))
            else:
                pvx = 0.0
            if not blocked(p["x"], nz):
                p["z"] = max(2.0, min(WORLD_H - 2.0, nz))
            else:
                pvz = 0.0
        if firing:
            fire()

    # 4. reloading
    if reloading > 0:
        reloading = max(0.0, reloading - dt)
        if reloading <= 0.0:
            mag = WEAPONS[weapon]["mag"]

    # 7. crates you can walk over
    for pk in pickups:
        if pk["taken"]:
            continue
        if math.hypot(pk["x"] - p["x"], pk["z"] - p["z"]) < 7.0:
            pk["taken"] = True
            if pk["kind"] == "health":
                p["hp"] = min(100.0, p["hp"] + 35.0)
                message = "Picked up a medkit"
            else:
                mag = WEAPONS[weapon]["mag"]
                reloading = 0.0
                message = "Picked up ammo"
            _sound("home")

    # --- the bots ---
    for b in bots:
        if not b["alive"]:
            continue
        b["cool"] = max(0.0, b["cool"] - dt)
        b["flash"] = max(0.0, b.get("flash", 0.0) - dt)
        tier = TIERS[b.get("tier", 0)]
        dx, dz = p["x"] - b["x"], p["z"] - b["z"]
        d = math.hypot(dx, dz) or 1e-6
        if p["alive"] and d < tier["range"]:
            b["yaw"] = math.atan2(dx, dz)
            step = BOT_SPEED * dt
            if d > 46.0:
                ax, az = dx / d, dz / d
            else:
                ax, az = -dx / d * 0.6, -dz / d * 0.6
            if d < 115.0:
                # 9. sidestep instead of standing still in the open
                ax += -dz / d * b["strafe"] * tier["strafe"]
                az += dx / d * b["strafe"] * tier["strafe"]
            am = math.hypot(ax, az) or 1.0
            nx = b["x"] + ax / am * step
            nz = b["z"] + az / am * step
            if not blocked(nx, b["z"]):
                b["x"] = max(2.0, min(WORLD_W - 2.0, nx))
            if not blocked(b["x"], nz):
                b["z"] = max(2.0, min(WORLD_H - 2.0, nz))
            if d < 150.0 and b["cool"] <= 0:
                b["cool"] = _rng.uniform(*tier["cool"])
                _spawn_shot(b["x"], b["z"],
                            b["yaw"] + _rng.uniform(-tier["spread"], tier["spread"]),
                            "b", BOT_DAMAGE)
        else:
            # nobody in sight: drift about
            b["wander"] -= dt
            if b["wander"] <= 0:
                b["wander"] = _rng.uniform(1.5, 3.5)
                a = _rng.uniform(0, 6.283)
                b["wx"], b["wz"] = math.sin(a), math.cos(a)
            nx = b["x"] + b["wx"] * BOT_SPEED * 0.5 * dt
            nz = b["z"] + b["wz"] * BOT_SPEED * 0.5 * dt
            if not blocked(nx, nz):
                b["x"], b["z"] = nx, nz
            else:
                b["wander"] = 0.0

    # --- bullets ---
    keep = []
    for s in shots:
        s["life"] -= dt
        if s["life"] <= 0:
            continue
        s["x"] += s["dx"] * dt
        s["z"] += s["dz"] * dt
        if not land_at(s["x"], s["z"]):
            continue
        hit = False
        if s["owner"] == "p":
            for b in bots:
                if b["alive"] and math.hypot(b["x"] - s["x"], b["z"] - s["z"]) < 6.0:
                    b["hp"] -= s["dmg"]
                    b["flash"] = 0.16
                    dmg_numbers.append({"x": s["x"], "z": s["z"],
                                        "text": "%d" % int(s["dmg"]), "life": 0.75})
                    hit = True
                    hits.append({"x": s["x"], "z": s["z"], "life": 0.45})
                    hitmark = 0.30
                    if b["hp"] <= 0:
                        b["alive"] = False
                        b["dying"] = 1.1
                        p["kills"] += 1
                        feed.insert(0, {"text": "You downed a bot", "life": 3.5})
                        _sound("hit")
                    break
        else:
            if p["alive"] and math.hypot(p["x"] - s["x"], p["z"] - s["z"]) < 6.0:
                hits.append({"x": s["x"], "z": s["z"], "life": 0.45})
                p["hp"] -= s["dmg"]
                p["hurt"] = 0.5
                hurt_dir = math.atan2(s["x"] - p["x"], s["z"] - p["z"])
                shake = max(shake, 0.35)
                hit = True
                _sound("hurt")
        if not hit:
            keep.append(s)
    shots[:] = keep

    # --- the zone ---
    zone_timer -= dt
    if zone_timer <= 0:
        zone_phase += 1
        zone_timer = max(14.0, 26.0 - zone_phase * 1.2)
        zone["cx"], zone["cz"], zone["r"] = zone["tx"], zone["tz"], zone["tr"]
        nr = max(70.0, zone["r"] * 0.74)
        a = _rng.uniform(0, 6.283)
        off = max(0.0, zone["r"] - nr) * 0.55
        zone["tx"] = max(60.0, min(WORLD_W - 60.0, zone["cx"] + math.cos(a) * off))
        zone["tz"] = max(60.0, min(WORLD_H - 60.0, zone["cz"] + math.sin(a) * off))
        zone["tr"] = nr
        message = "The zone is closing."
        _sound("zone")

    # ease the drawn circle toward its target
    zone["r"] += (zone["tr"] - zone["r"]) * min(1.0, dt * 0.8)
    zone["cx"] += (zone["tx"] - zone["cx"]) * min(1.0, dt * 0.8)
    zone["cz"] += (zone["tz"] - zone["cz"]) * min(1.0, dt * 0.8)

    zone_dmg = 5.0 + zone_phase * 3.0
    if p["alive"] and math.hypot(p["x"] - zone["cx"], p["z"] - zone["cz"]) > zone["r"]:
        p["hp"] -= zone_dmg * dt
        p["hurt"] = 0.2
    for b in bots:
        if b["alive"] and math.hypot(b["x"] - zone["cx"], b["z"] - zone["cz"]) > zone["r"]:
            b["hp"] -= zone_dmg * dt
            if b["hp"] <= 0:
                b["alive"] = False
                b["dying"] = 1.1
                feed.insert(0, {"text": "The zone took a bot", "life": 3.5})

    # --- who won ---
    shake = max(0.0, shake - dt * 2.5)
    for dn in dmg_numbers:
        dn["life"] -= dt
    dmg_numbers[:] = [dn for dn in dmg_numbers if dn["life"] > 0]

    if p["hp"] <= 0 and p["alive"]:
        p["alive"] = False
        p["hp"] = 0.0
        placement = alive_count() + 1
        state = "over"
        result = "lose"
        _notify_playing(False)
        _sound("lose")
    elif not any(b["alive"] for b in bots):
        state = "over"
        result = "win"
        placement = 1
        _notify_playing(False)
        _sound("win")


def alive_count():
    return (1 if player.get("alive") else 0) + sum(1 for b in bots if b["alive"])


# ---------------------------------------------------------------------------
# Handing the frame to three.js
# ---------------------------------------------------------------------------
def _frame_json():
    p = player
    b = []
    for q in bots:
        if q["alive"] or q.get("dying", 0) > 0:
            b.append([round(q["x"], 2), round(height_at(q["x"], q["z"]), 2),
                      round(q["z"], 2), round(q["yaw"], 3),
                      max(0.0, round(q["hp"], 0)),
                      0 if q["alive"] else round(q.get("dying", 0), 2),
                      int(q.get("tier", 0)), round(q.get("flash", 0.0), 2)])
    s = []
    for t in shots:
        s.append([round(t["x"], 2), round(height_at(t["x"], t["z"]) + 1.6, 2),
                  round(t["z"], 2), round(t["dx"], 1), round(t["dz"], 1)])
    h = [[round(e["x"], 2), round(height_at(e["x"], e["z"]) + 1.4, 2), round(e["z"], 2),
          round(e["life"], 2)] for e in hits]
    return json.dumps({
        "p": [round(p["x"], 2), round(height_at(p["x"], p["z"]), 2),
              round(p["z"], 2), round(p["yaw"], 3),
              1 if p["alive"] else 0, round(p["hp"], 1),
              round(math.hypot(pvx, pvz), 2)],
        "b": b,
        "s": s,
        "h": h,
        "pk": [[round(e["x"], 2), round(height_at(e["x"], e["z"]) + 1.2, 2),
                round(e["z"], 2), 1 if e["kind"] == "health" else 0]
               for e in pickups if not e["taken"]],
        "dn": [[round(e["x"], 2), round(height_at(e["x"], e["z"]) + 5.0, 2),
                round(e["z"], 2), e["text"]] for e in dmg_numbers],
        "z": [round(zone["cx"], 2), round(zone["cz"], 2), round(zone["r"], 2)],
        "cam": [round(cam_yaw, 3), round(cam_pitch, 3)],
        "sh": round(shake, 3),
        "wp": 0 if weapon == "rifle" else 1,
        "crouch": 1 if crouching else 0,
    })


def send_frame():
    try:
        js.world3d.frame(_frame_json())
    except Exception:
        pass


def build_world():
    """Give three.js the terrain once, when the page is ready."""
    if not _READY:
        build_terrain()
    payload = json.dumps({
        "nx": NX, "nz": NZ, "w": WORLD_W, "h": WORLD_H, "water": WATER_Y,
        "heights": [round(h, 2) for h in HEIGHTS],
        "buildings": [[round(b[0], 1), round(b[1], 1), round(b[2], 1),
                       round(b[3], 1), round(b[4], 1)] for b in BUILDINGS],
        "roads": [[[p[0], p[1]] for p in r] for r in ROADS],
    })
    try:
        js.world3d.build(payload)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HUD
# ---------------------------------------------------------------------------
def _panel(x, y, w, h, fill="rgba(12, 20, 40, 0.86)",
           stroke="rgba(150, 180, 240, 0.22)", r=12):
    c = hctx
    c.beginPath()
    c.moveTo(x + r, y)
    c.arcTo(x + w, y, x + w, y + h, r)
    c.arcTo(x + w, y + h, x, y + h, r)
    c.arcTo(x, y + h, x, y, r)
    c.arcTo(x, y, x + w, y, r)
    c.closePath()
    c.fillStyle = fill
    c.fill()
    if stroke:
        c.lineWidth = 2
        c.strokeStyle = stroke
        c.stroke()


def _button(x, y, w, h, label, active=False, accent="#7ef0c0", size=17):
    _panel(x, y, w, h, accent if active else "rgba(24, 34, 62, 0.94)",
           "#ffffff" if active else "rgba(150, 180, 240, 0.30)", 12)
    hctx.textAlign = "center"
    hctx.textBaseline = "middle"
    hctx.fillStyle = "#06101f" if active else "#eaf2ff"
    hctx.font = "800 %dpx %s" % (_fs(size), FONT)
    hctx.fillText(label, x + w / 2, y + h / 2)
    hctx.textBaseline = "alphabetic"


def _wrap(text, x, y, maxw, size=15, color="#9fb3d9"):
    c = hctx
    c.font = "600 %dpx %s" % (_fs(size), FONT)
    c.fillStyle = color
    c.textAlign = "center"
    words, line = text.split(" "), ""
    for wd in words:
        trial = (line + " " + wd).strip()
        if c.measureText(trial).width > maxw and line:
            c.fillText(line, x, y)
            y += size * 1.5
            line = wd
        else:
            line = trial
    if line:
        c.fillText(line, x, y)
    return y


FIRE_R = 64.0
FIRE_X = 0.0
FIRE_Y = 0.0


def touch_buttons():
    """The small action buttons that sit along the bottom on a phone."""
    if not TOUCH_UI:
        return []
    labels = [("sprint", "RUN", sprinting), ("crouch", "DUCK", crouching),
              ("reload", "RELOAD", reloading > 0), ("swap", "SWAP", False)]
    bw, bh, gap = 62, 40, 8
    total = len(labels) * bw + (len(labels) - 1) * gap
    x = W / 2 - total / 2
    y = H - 58
    out = []
    for tag, label, active in labels:
        out.append((tag, label, active, (x, y, bw, bh)))
        x += bw + gap
    return out


def fire_button():
    """The fire button's centre and radius, in HUD pixels."""
    return (W - 104.0, H - 104.0, FIRE_R)


def minimap_size():
    return min(190.0, W * 0.30, H * 0.34)


def _minimap():
    size = minimap_size()
    mx, my = W - size - 16, 16
    _panel(mx - 5, my - 5, size + 10, size + 10, "rgba(8, 14, 30, 0.86)",
           "rgba(150,180,240,0.26)", 10)
    sx = size / WORLD_W
    sz = size / WORLD_H
    c = hctx

    # the land
    c.beginPath()
    for i, (x, z) in enumerate(RING):
        px, py = mx + x * sx, my + z * sz
        c.moveTo(px, py) if i == 0 else c.lineTo(px, py)
    c.closePath()
    c.fillStyle = "rgba(56, 96, 72, 0.94)"
    c.fill()
    c.lineWidth = 1.2
    c.strokeStyle = "rgba(160, 220, 190, 0.62)"
    c.stroke()

    # the roads
    c.strokeStyle = "rgba(230, 218, 184, 0.5)"
    c.lineWidth = 1.3
    for road in ROADS:
        c.beginPath()
        for i, (x, z) in enumerate(road):
            px, py = mx + x * sx, my + z * sz
            c.moveTo(px, py) if i == 0 else c.lineTo(px, py)
        c.stroke()

    # the towns
    for t in TOWNS:
        c.beginPath()
        c.arc(mx + t["x"] * sx, my + t["z"] * sz, 3.4, 0, 6.2832)
        c.fillStyle = "rgba(255, 210, 63, 0.92)"
        c.fill()

    # crates you have not taken
    for pk in pickups:
        if pk["taken"]:
            continue
        c.beginPath()
        c.arc(mx + pk["x"] * sx, my + pk["z"] * sz, 1.7, 0, 6.2832)
        c.fillStyle = "#7ef0c0" if pk["kind"] == "health" else "#ffd23f"
        c.fill()

    # the zone
    c.beginPath()
    c.arc(mx + zone["cx"] * sx, my + zone["cz"] * sz,
          zone["r"] * (sx + sz) * 0.5, 0, 6.2832)
    c.lineWidth = 2
    c.strokeStyle = "rgba(90, 170, 255, 0.95)"
    c.stroke()

    # the bots
    for b in bots:
        if b["alive"]:
            c.beginPath()
            c.arc(mx + b["x"] * sx, my + b["z"] * sz, 2.8, 0, 6.2832)
            c.fillStyle = "#ff5c7a"
            c.fill()

    # us, with a little tick showing which way we face
    px, py = mx + player["x"] * sx, my + player["z"] * sz
    c.beginPath()
    c.moveTo(px, py)
    c.lineTo(px + math.sin(player["yaw"]) * 26 * sx,
             py + math.cos(player["yaw"]) * 26 * sz)
    c.strokeStyle = "#7ef0c0"
    c.lineWidth = 1.6
    c.stroke()
    c.beginPath()
    c.arc(px, py, 3.6, 0, 6.2832)
    c.fillStyle = "#7ef0c0"
    c.fill()

    # north
    c.textAlign = "center"
    c.fillStyle = "rgba(255,255,255,0.75)"
    c.font = "800 %dpx %s" % (_fs(9), FONT)
    c.fillText("N", mx + size / 2, my + 10)


def draw():
    global FIRE_X, FIRE_Y
    FIRE_X, FIRE_Y, _r = fire_button()
    c = hctx
    c.clearRect(0, 0, W, H)

    if state == "menu":
        _draw_menu()
        return
    if state == "play":
        _draw_play_hud()
    if state == "over":
        _draw_play_hud()
        _draw_over()


def _draw_menu():
    global _menu_hit
    _menu_hit = []
    c = hctx
    c.fillStyle = "rgba(4, 10, 24, 0.72)"
    c.fillRect(0, 0, W, H)

    c.textAlign = "center"
    c.fillStyle = "#ffffff"
    c.font = "800 %dpx %s" % (_fs(40), FONT)
    c.fillText("KHELO", W / 2, H / 2 - 96)
    c.fillStyle = "#ffb703"
    c.fillText("BATTLEGROUND", W / 2, H / 2 - 56)

    _wrap("Drop onto the map with nine bots. The blue zone closes in.",
          W / 2, H / 2 - 20, min(560, W - 80), 15)
    _wrap("Last one standing wins. Move, aim, fire.", W / 2, H / 2 + 6,
          min(560, W - 80), 14, "#8fa3c9")

    bw, bh = 220, 54
    _button(W / 2 - bw / 2, H / 2 + 40, bw, bh, "DROP IN", True, "#ffb703", size=19)
    _menu_hit.append(("play", (W / 2 - bw / 2, H / 2 + 40, bw, bh)))

    _wrap("Laptop: WASD to move \u00b7 click once to grab the mouse, then move it to look",
          W / 2, H / 2 + 126, min(640, W - 50), 12, "#7f93bb")
    _wrap("Click or Space to fire \u00b7 Esc lets the mouse go",
          W / 2, H / 2 + 148, min(640, W - 50), 12, "#7f93bb")
    _wrap("Phone: a stick appears under your left thumb \u00b7 drag the right side to look \u00b7 FIRE",
          W / 2, H / 2 + 174, min(640, W - 50), 12, "#7f93bb")


def _draw_play_hud():
    c = hctx
    p = player

    # the pause button
    _panel(PAUSE_RECT[0], PAUSE_RECT[1], PAUSE_RECT[2], PAUSE_RECT[3],
           "rgba(8, 14, 30, 0.8)", "rgba(150,180,240,0.22)", 12)
    c.textAlign = "center"
    c.textBaseline = "middle"
    c.fillStyle = "#eaf2ff"
    c.font = "800 %dpx %s" % (_fs(15), FONT)
    c.fillText("\u23f8", PAUSE_RECT[0] + PAUSE_RECT[2] / 2,
               PAUSE_RECT[1] + PAUSE_RECT[3] / 2 + 1)
    c.textBaseline = "alphabetic"

    # ---- 23. compass -------------------------------------------------------
    cw_, chh = 240, 18
    cx0 = W / 2 - cw_ / 2
    _panel(cx0, 8, cw_, chh, "rgba(8, 14, 30, 0.72)", "rgba(150,180,240,0.18)", 6)
    heading = (math.degrees(cam_yaw) % 360.0 + 360.0) % 360.0
    for deg, label in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        d = ((deg - heading + 180) % 360) - 180
        if abs(d) > 68:
            continue
        px = W / 2 + d * (cw_ / 150.0)
        c.textAlign = "center"
        c.fillStyle = "#eaf2ff" if label in ("N", "E", "S", "W") else "#8fa3c9"
        c.font = "800 %dpx %s" % (_fs(10), FONT)
        c.fillText(label, px, 22)
    c.textAlign = "center"
    c.fillStyle = "#7ef0c0"
    c.font = "800 %dpx %s" % (_fs(9), FONT)
    c.fillText("%03d" % int(heading), W / 2, 34)

    # ---- 29. alive count and placement ------------------------------------
    _panel(W / 2 - 78, 38, 156, 44, "rgba(8, 14, 30, 0.8)", "rgba(150,180,240,0.2)", 10)
    c.textAlign = "center"
    c.fillStyle = "#eaf2ff"
    c.font = "800 %dpx %s" % (_fs(19), FONT)
    c.fillText("%d ALIVE" % alive_count(), W / 2, 61)
    c.fillStyle = "#5aaaff"
    c.font = "700 %dpx %s" % (_fs(10), FONT)
    c.fillText("ZONE %ds" % max(0, int(zone_timer)), W / 2, 75)

    if message:
        _wrap(message, W / 2, 98, min(520, W - 60), 12, "#cfe0ff")

    # ---- 24 25. health, stamina, weapon and magazine ----------------------
    bx = 18
    by = (H - 200) if TOUCH_UI else (H - 96)
    bw = min(260, W * 0.42)

    _panel(bx - 6, by - 8, bw + 12, 34, "rgba(8, 14, 30, 0.8)", "rgba(150,180,240,0.2)", 9)
    frac = max(0.0, min(1.0, p["hp"] / 100.0))
    c.fillStyle = "rgba(60, 74, 108, 0.7)"
    c.fillRect(bx, by, bw, 18)
    col = "#22c55e" if frac > 0.55 else ("#fbbf24" if frac > 0.25 else "#ff3b5c")
    c.fillStyle = col
    c.fillRect(bx, by, bw * frac, 18)
    c.textAlign = "left"
    c.fillStyle = "#eaf2ff"
    c.font = "800 %dpx %s" % (_fs(12), FONT)
    c.fillText("%d HP" % max(0, int(p["hp"])), bx + 8, by + 14)

    # stamina, right under the health
    sy = by + 24
    c.fillStyle = "rgba(60, 74, 108, 0.55)"
    c.fillRect(bx, sy, bw, 6)
    c.fillStyle = "#5aaaff" if stamina > 20 else "#ff8a3d"
    c.fillRect(bx, sy, bw * (stamina / 100.0), 6)

    # the weapon and its magazine
    w = WEAPONS[weapon]
    ty = sy + 22
    _panel(bx - 6, ty - 15, bw + 12, 34, "rgba(8, 14, 30, 0.72)",
           "rgba(150,180,240,0.16)", 8)
    c.textAlign = "left"
    c.fillStyle = "#ffd23f"
    c.font = "800 %dpx %s" % (_fs(12), FONT)
    c.fillText(w["name"], bx, ty)
    c.fillStyle = "#eaf2ff"
    c.font = "800 %dpx %s" % (_fs(15), FONT)
    c.fillText("%d / %d" % (max(0, mag), w["mag"]), bx + 78, ty)
    c.fillStyle = "#9fb3d9"
    c.font = "700 %dpx %s" % (_fs(11), FONT)
    c.fillText("KILLS %d" % p["kills"], bx + 168, ty)

    if reloading > 0:
        rw = bw * (1.0 - reloading / w["reload"])
        c.fillStyle = "rgba(255, 210, 63, 0.28)"
        c.fillRect(bx, ty + 8, bw, 5)
        c.fillStyle = "#ffd23f"
        c.fillRect(bx, ty + 8, rw, 5)
        c.fillStyle = "#ffd23f"
        c.font = "800 %dpx %s" % (_fs(10), FONT)
        c.fillText("RELOADING", bx, ty + 26)
    elif mag <= 0:
        c.fillStyle = "#ff5c7a"
        c.font = "800 %dpx %s" % (_fs(10), FONT)
        c.fillText("PRESS R", bx, ty + 26)

    # ---- 26. the arc that says where the hurt came from -------------------
    if p["hurt"] > 0.05:
        rel = (hurt_dir - cam_yaw + math.pi) % 6.283185 - math.pi
        a = math.degrees(rel)
        cxx, cyy = W / 2, H / 2
        c.beginPath()
        c.arc(cxx, cyy, 92, math.radians(a - 90 - 22), math.radians(a - 90 + 22))
        c.lineWidth = 7
        c.strokeStyle = "rgba(255, 60, 90, %.2f)" % min(1.0, p["hurt"] * 2)
        c.stroke()

    _minimap()

    # the kill feed, under the minimap
    fy = minimap_size() + 40
    for i, f in enumerate(feed[:4]):
        a = min(1.0, f["life"] / 1.2)
        c.textAlign = "right"
        c.fillStyle = "rgba(255, 255, 255, %.2f)" % a
        c.font = "700 %dpx %s" % (_fs(12), FONT)
        c.fillText(f["text"], W - 16, fy + i * 17)

    # the crosshair sits where the bullets go
    cxx, cyy = W / 2, H / 2
    spread = 8 if crouching else (14 if sprinting else 10)
    c.strokeStyle = "rgba(255, 255, 255, 0.80)"
    c.lineWidth = 2
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        c.beginPath()
        c.moveTo(cxx + dx * spread, cyy + dy * spread)
        c.lineTo(cxx + dx * (spread + 7), cyy + dy * (spread + 7))
        c.stroke()
    c.beginPath()
    c.arc(cxx, cyy, 2.2, 0, 6.2832)
    c.fillStyle = "rgba(255, 255, 255, 0.9)"
    c.fill()

    if hitmark > 0:
        a = min(1.0, hitmark / 0.3)
        c.strokeStyle = "rgba(255, 92, 122, %.2f)" % a
        c.lineWidth = 3
        for sx_, sy_ in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            c.beginPath()
            c.moveTo(cxx + sx_ * 9, cyy + sy_ * 9)
            c.lineTo(cxx + sx_ * 17, cyy + sy_ * 17)
            c.stroke()

    if TOUCH_UI:
        # the movement stick, drawn wherever the thumb is resting
        if STICK["on"]:
            sx, sy2 = STICK["x"], STICK["y"]
            base_a, knob_a = 0.40, 0.82
        else:
            sx, sy2 = 108, H - 108
            base_a, knob_a = 0.18, 0.30
        c.beginPath()
        c.arc(sx, sy2, 66, 0, 6.2832)
        c.fillStyle = "rgba(12, 20, 40, %.2f)" % base_a
        c.fill()
        c.lineWidth = 2
        c.strokeStyle = "rgba(150, 180, 240, 0.42)"
        c.stroke()
        c.beginPath()
        c.arc(sx + move_x * 46, sy2 - move_z * 46, 28, 0, 6.2832)
        c.fillStyle = "rgba(126, 240, 192, %.2f)" % knob_a
        c.fill()

        # the little action buttons along the bottom
        for tag, label, active, r in touch_buttons():
            _panel(r[0], r[1], r[2], r[3],
                   "rgba(126, 240, 192, 0.85)" if active else "rgba(20, 30, 56, 0.85)",
                   "rgba(150,180,240,0.35)", 10)
            c.textAlign = "center"
            c.textBaseline = "middle"
            c.fillStyle = "#06101f" if active else "#cfe0ff"
            c.font = "800 %dpx %s" % (_fs(11), FONT)
            c.fillText(label, r[0] + r[2] / 2, r[1] + r[3] / 2 + 1)
            c.textBaseline = "alphabetic"

        # the fire button
        fx, fy2 = FIRE_X, FIRE_Y
        c.beginPath()
        c.arc(fx, fy2, FIRE_R, 0, 6.2832)
        c.fillStyle = "rgba(255, 92, 122, 0.86)" if firing else "rgba(255, 92, 122, 0.62)"
        c.fill()
        c.lineWidth = 3
        c.strokeStyle = "rgba(255, 255, 255, 0.60)"
        c.stroke()
        c.textAlign = "center"
        c.textBaseline = "middle"
        c.fillStyle = "#ffffff"
        c.font = "800 %dpx %s" % (_fs(15), FONT)
        c.fillText("FIRE", fx, fy2 + 1)
        c.textBaseline = "alphabetic"

    if p["hurt"] > 0:
        c.fillStyle = "rgba(255, 40, 70, %.2f)" % (0.30 * p["hurt"] / 0.5)
        c.fillRect(0, 0, W, H)

    if paused:
        _draw_pause()


def _draw_pause():
    global _menu_hit
    _menu_hit = []
    c = hctx
    c.fillStyle = "rgba(4, 10, 24, 0.78)"
    c.fillRect(0, 0, W, H)
    pw, ph = min(380, W - 40), 220
    px, py = (W - pw) / 2, (H - ph) / 2
    _panel(px, py, pw, ph, "rgba(12, 20, 42, 0.97)", "#ffb703", 18)
    c.textAlign = "center"
    c.fillStyle = "#ffb703"
    c.font = "800 %dpx %s" % (_fs(26), FONT)
    c.fillText("PAUSED", W / 2, py + 52)
    _button(px + 30, py + 84, pw - 60, 50, "Resume", True, "#7ef0c0")
    _button(px + 30, py + 146, pw - 60, 44, "Quit to menu", False, size=15)
    _menu_hit = [("resume", (px + 30, py + 84, pw - 60, 50)),
                 ("quit", (px + 30, py + 146, pw - 60, 44))]


def _draw_over():
    global _menu_hit
    _menu_hit = []
    c = hctx
    c.fillStyle = "rgba(4, 10, 24, 0.80)"
    c.fillRect(0, 0, W, H)

    cw, ch = min(460, W - 40), 280
    cx, cy = (W - cw) / 2, (H - ch) / 2
    _panel(cx, cy, cw, ch, "rgba(12, 20, 42, 0.97)",
           "#22c55e" if result == "win" else "#ff5c7a", 20)

    c.textAlign = "center"
    c.fillStyle = "#22c55e" if result == "win" else "#ff5c7a"
    c.font = "800 %dpx %s" % (_fs(30), FONT)
    c.fillText("WINNER WINNER" if result == "win" else "YOU ARE DOWN", W / 2, cy + 60)

    c.fillStyle = "#eaf2ff"
    c.font = "700 %dpx %s" % (_fs(15), FONT)
    c.fillText("%d kills  \u00b7  survived %ds" % (player["kills"], int(elapsed)),
               W / 2, cy + 96)

    bw = min(200, (cw - 60) / 2)
    _button(cx + 20, cy + ch - 130, bw, 52, "Drop again", True,
            "#22c55e" if result == "win" else "#ffb703")
    _button(cx + cw - bw - 20, cy + ch - 130, bw, 52, "Menu", False)
    _button(cx + 20, cy + ch - 66, cw - 40, 44, "Back to the arcade", False, size=15)
    _menu_hit = [("again", (cx + 20, cy + ch - 130, bw, 52)),
                 ("menu", (cx + cw - bw - 20, cy + ch - 130, bw, 52))]

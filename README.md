# 🎮 Khelo

A little browser **arcade of games written in Python** — no installs, no server.
Each game is plain Python running client-side through
[Pyodide](https://pyodide.org) (Python compiled to WebAssembly), served as
static files, so the whole thing hosts on GitHub Pages.

**▶ Play: <https://542bheemsingh-cmd.github.io/khelo/>**

---

## The games

| Game | What it is | Controls |
|---|---|---|
| 🐦 **[Khelo Fly](https://542bheemsingh-cmd.github.io/khelo/games/fly/)** | Flappy-Bird-style flyer — tap to flap, dodge the pipes, best score saved | `Space` / `↑` / `W` / tap / click |
| 🚙 **[Khelo Climb](https://542bheemsingh-cmd.github.io/khelo/games/hillclimb/)** | Hill-climb driving — hold the gas to climb, don't land on your head | `→` / `D` = gas, `←` / `A` = brake, or on-screen pedals |

The dashboard at the root lists them all and links into each game.

## How it works

```
index.html (dashboard)
   └── games/<name>/
         ├── game.py       ← ALL the game logic, in Python
         ├── index.html    ← loads Pyodide, runs game.py, drives the loop
         └── style.css
```

Each game's `game.py` owns the whole simulation and talks to the HTML5 canvas
and the Web Audio API through Pyodide's `js` bridge. The page's JavaScript only
does two things: run the `requestAnimationFrame` loop and forward input.

```
update(dt)  →  advance the simulation
draw()      →  render one frame
```

## Repository layout

```
khelo/
├── index.html                 # the dashboard (lists every game)
├── style.css
├── games/
│   ├── fly/
│   │   ├── game.py            # Khelo Fly
│   │   ├── index.html
│   │   ├── style.css
│   │   └── test_game.py       # headless logic tests
│   └── hillclimb/
│       ├── game.py            # Khelo Climb
│       ├── index.html
│       ├── style.css
│       └── test_climb.py
├── README.md
└── LICENSE
```

## Run it locally

The pages load `game.py` with `fetch`, so they must be served over HTTP
(opening the HTML files directly won't work):

```bash
python3 -m http.server 5173
# then open http://localhost:5173
```

The first load downloads the Python runtime (~10 MB) once; the browser caches
it after that.

## Run the tests

Each game ships a headless harness that stubs out the browser and drives the
real `game.py` — no browser needed:

```bash
python3 games/fly/test_game.py
python3 games/hillclimb/test_climb.py
```

## Add a new game

1. Create `games/<name>/` with `game.py`, `index.html`, `style.css`.
   Start from an existing game — copy a folder and edit.
2. In `game.py`, define `update(dt)` and `draw()`, and expose any input
   functions you need (e.g. `flap()`, `gas(down)`).
3. Copy a `card` block in the root `index.html` and point it at the new folder.

## Deploy to GitHub Pages

Settings → Pages → Source: **Deploy from a branch**, branch **`main`**,
folder **`/ (root)`**. The dashboard goes live at
`https://<user>.github.io/khelo/`.

## Tweaking

The feel of each game is in the "Tunables" block at the top of its `game.py` —
gravity, speeds, gaps, spawn rates, fuel, and the difficulty curve.

## License

MIT — see [LICENSE](LICENSE).

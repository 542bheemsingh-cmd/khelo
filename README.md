# 🐦 Khelo Fly

A Flappy-Bird-style 2D game **written in Python** that plays in the browser — no
server, no build step. The game logic (physics, pipes, collision, scoring,
difficulty, rendering) all lives in [`game.py`](game.py), which runs in the
browser through [Pyodide](https://pyodide.org) (Python compiled to WebAssembly).

**[▶ Play it live](https://542bheemsingh-cmd.github.io/khelo/)**

---

## How it works

```
index.html ──loads──> Pyodide (WebAssembly) ──runs──> game.py
     │                                                   │
     └── drives the loop ────────────────────────────────┘
             update(dt)  →  advance the simulation
             draw()      →  render one frame to the canvas
             flap()      →  called on tap / click / Space
```

`game.py` owns the whole game and talks to the HTML5 canvas and the Web Audio
API through Pyodide's `js` bridge. JavaScript only does two things: drive the
`requestAnimationFrame` loop and forward input. Because everything is static
files, it hosts perfectly on GitHub Pages.

## Features

- 🐦 Flappy-Bird-style endless flyer — gravity, flap, pipes, gaps
- 🐍 **Game logic in Python**, running client-side via Pyodide
- 🏆 High score saved in the browser (`localStorage`)
- 🔊 Sound effects generated with the Web Audio API (no audio files needed)
- 📱 Mouse, keyboard **and** touch controls
- 📈 Increasing difficulty — gaps tighten and pipes speed up as you score
- 🎨 Crisp rendering at the device pixel ratio, responsive to any screen
- 🧪 Headless test harness (`test_game.py`) — no browser needed to verify logic

## Controls

| Action | Input |
|---|---|
| Flap / start | `Space`, `↑`, `W`, click, or tap |
| Restart | Tap / press again after game over |
| Mute | Speaker button, top-right |

## Run it locally

Because the page loads `game.py` with `fetch`, it must be served over HTTP
(opening `index.html` by double-clicking won't work).

```bash
# from the project folder
python3 -m http.server 5173
```

Then open <http://localhost:5173>.

The first load downloads the Python runtime (~10 MB) once; after that it's
cached by the browser.

## Run the logic tests

`test_game.py` stubs out the browser and drives the real `game.py` headlessly:

```bash
python3 test_game.py
```

## Deploy to GitHub Pages

1. Push this repo to GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, set **Source: Deploy from a branch**,
   branch **`main`**, folder **`/ (root)`**.
4. Save. The game goes live at `https://<user>.github.io/khelo/`.

## Tweaking the game

All the feel is in the "Tunables" block at the top of `game.py` — gravity, flap
strength, pipe width, gap size, scroll speed, spawn interval, and the
difficulty curve (`_difficulty_gap` / `_difficulty_speed`).

## License

MIT — see [LICENSE](LICENSE).

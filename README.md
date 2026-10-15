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
| 🚙 **[Khelo Climb](https://542bheemsingh-cmd.github.io/khelo/games/hillclimb/)** | Hill-climb driving — 5 locations, 4 vehicles, coins, fuel and obstacles | `→` / `D` = gas, `←` / `A` = brake, or on-screen pedals |
| 🧩 **[Khelo Puzzles](https://542bheemsingh-cmd.github.io/khelo/games/puzzle/)** | 10 logic puzzles of increasing difficulty, one new kind per level, each with a hint | click / tap, type for the word puzzles |
| 🎲 **[Khelo Ludo](https://542bheemsingh-cmd.github.io/khelo/games/ludo/)** | The classic board game — 2, 3 or 4 players, or 2 against 2 | tap the dice, then tap a token |

The dashboard at the root lists them all and links into each game.

## Playing on a phone

Every game is built for touch as well as a keyboard:

- **Full-screen button** in the top bar of each game — one tap fills the screen
  (and asks for landscape on the wide games where the browser allows it).
- **The canvas always keeps its exact shape.** It is fitted to whatever space is
  left and letterboxed rather than stretched or cropped, so taps land where you
  meant them to.
- **On-screen keyboard** for the two puzzle levels that need typing (Riddle and
  Number Sequence) — no physical keyboard required.
- **Rotate hint** on the landscape games (Climb, Puzzles) when you're holding the
  phone upright; Fly is portrait and needs no turning.
- **Tap-friendly controls** — gas/brake pedals in Climb, tap-to-flap in Fly, and a
  canvas-tap Menu button so you are never stuck without an `Esc` key.

## Khelo Ludo

The classic race home, with the full board and the full rules.

- **Two modes.** *Single-Single* — everyone for themselves, and you choose **2, 3
  or 4 players** on the next screen. *Team-Team* — always 4 players, **Red +
  Yellow against Green + Blue**.
- **Real Ludo rules.** Roll a 6 to bring a token out of your yard. Land on an
  opponent and it goes back to their yard. The four coloured start squares and
  the four star squares are safe. A 6, a capture or getting a token home all earn
  you another roll.
- **Animated.** The dice tumbles before it settles, tokens hop square by square
  along the ring, captured tokens spark, and a confetti burst celebrates the win.
- **Playable solo on one screen** — every player takes their turn on the same
  device, so it works as a pass-and-play game on a phone.

## Khelo Puzzles levels

**20 levels**, a different kind of puzzle each time, unlocked one at a time and
saved in your browser. Every level carries a **GOAL** line on screen saying
exactly what you are being asked to do, and a **Hint** button that floats its
advice in a card right above the button.

| # | Puzzle | What you do |
|---|---|---|
| 1 | Lights Out (3×3) | Switch every light off |
| 2 | Memory Match | Find the matching pairs |
| 3 | Number Sequence | Work out the next term |
| 4 | Riddle | Answer a classic riddle |
| 5 | Sliding Puzzle (3×3) | Order the tiles |
| 6 | Tower of Hanoi (3 discs) | Move the stack, big never on small |
| 7 | Crack the Code | **Deduce** a 3-digit code from the clues |
| 8 | Mini Sudoku (4×4) | Fill every row, column and box with 1-4 |
| 9 | Nonogram (5×5) | Reveal the hidden picture from the clues |
| 10 | N-Queens (6×6) | Place 6 queens with no two attacking |
| 11 | Futoshiki (4×4) | Latin square with < and > between neighbours |
| 12 | Lights Out + (4×4) | The bigger board |
| 13 | Memory Match + | Five pairs, ten tiles |
| 14 | Sliding Puzzle + (4×4) | The 15-puzzle |
| 15 | Tower of Hanoi + (4 discs) | 15 moves minimum |
| 16 | Logic Grid (3×3) | Deduce who owns which pet from the clues |
| 17 | Nonogram + (6×6) | A bigger hidden picture |
| 18 | N-Queens + (7×7) | Seven queens |
| 19 | Futoshiki + (5×5) | Five symbols per line |
| 20 | Logic Grid + (4×4) | Four of each |

### Every puzzle is solvable by logic

Nothing here needs guessing:

- **Crack the Code** (level 7) replaced the old guess-the-code game. All the
  clues are on screen from the start, and there is exactly one code that fits
  every clue - you deduce it. The tests verify each generated puzzle is
  uniquely deducible.
- **Futoshiki** is generated so that its solution is provably the *only* one
  satisfying the signs.
- **Logic Grid** puzzles are hand-written and checked to have exactly one
  arrangement consistent with their clues.
- Lights Out, the sliding puzzle and the crack-the-code puzzles are all
  generated *from* a valid solution, so they can never be unsolvable.

### Stuck? The solution shows itself

Every level watches for wrong tries. Make **10** of them and the solution opens by
itself: the solved board on the left (with the answer marked where it matters,
like the tiles to press in Lights Out), and a plain-language explanation on the
right of **what the answer was and how to get there**.

A wrong try means a move that genuinely sets you back, not just a slow one:

| Level | What counts as a wrong try |
|---|---|
| Lights Out | a press that leaves more lights on than before |
| Memory Match | flipping two tiles that do not match |
| Number Sequence / Riddle | a wrong answer you submit |
| Sliding Puzzle | sliding a tile further from its home square |
| Tower of Hanoi | trying to drop a bigger disc on a smaller one |
| Code Breaker | a guess that is not the code |
| Mini Sudoku | placing a digit that is not the answer for that cell |
| Nonogram | filling a cell that should stay empty (or the reverse) |
| N-Queens | trying to place a queen on an attacked square |

The HUD shows a `wrong tries n / 10` counter once you have any. **Keep trying**
dismisses the solution and gives you a fresh count; **Back to levels** returns to
the menu. Solving a level the normal way still unlocks the next one — seeing the
solution does not.

## Khelo Climb features

- 🗺️ **5 locations** — Sunset Hills, Desert Dunes, Frozen Peaks, Volcano Run and
  low-gravity Moon Base, each with its own terrain, scenery and target distance.
- 🚗 **4 vehicles** — Rusty Jeep, Dirt Bike, Monster Truck and Turbo Car, with
  different power, grip and stability. Unlock them with coins.
- 💰 **Coins** — collect them along the track (and for finishing a level) to
  build a wallet, saved in your browser.
- ⛽ **Fuel + refill cans** — the tank drains while you're on the gas; grab the
  red cans to keep going.
- 🕹️ **Air control** — while airborne, gas lifts the nose and brake drops it.
  Flatten out before you land, or over-rotate and flip.
- 🪨 **Obstacles that change as you progress** — every location has its own set
  of 2–5 obstacle types (rocks, fallen logs, cacti, launch ramps, boulders, ice
  blocks, oil barrels, traffic cones, tyre stacks and spike strips). New types
  are introduced as you unlock new locations, and each new one gets a short
  demo before the level starts.
- ⚠️ **Spike strips end runs** — the lethal obstacle: crawl over them slowly,
  or launch off a ramp and clear them. Hit one at speed and it's game over.
- 🛞 **Different surfaces** — each location has its own grip, so Frozen Peaks is
  slippery while Sunset Hills bites.
- 📊 **In-game HUD** — location, distance to target with a progress bar, coins,
  wallet, best distance, fuel and a speedometer.
- 🏁 **Level progression** — reach the target to unlock the next location.
- 🖥️ **In-game menu** — pick a location and vehicle and buy new vehicles, all
  drawn in Python on the canvas.

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

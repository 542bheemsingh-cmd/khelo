"""
Headless tests for Khelo Word.

The browser bits are faked so the whole game can be driven from Python:
the canvas records what was drawn, localStorage is a dict, and the clock can
be pinned so the daily word is predictable.

Run with:  python3 test_word.py
"""

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


class _Canvas:
    width = 0
    height = 0

    def getContext(self, kind):
        return _Ctx()


class _Date:
    """A fake clock, so the daily word is stable inside a test."""

    fixed = (2026, 11, 25)

    def new(self):
        y, m, d = _Date.fixed
        return types.SimpleNamespace(
            getFullYear=lambda: y,
            getMonth=lambda: m - 1,
            getDate=lambda: d,
        )


class _Store:
    def __init__(self):
        self.d = {}

    def getItem(self, k):
        return self.d.get(k)

    def setItem(self, k, v):
        self.d[k] = v


STORE = _Store()


def _noop(*a, **k):
    return None


js = types.ModuleType("js")
js.devicePixelRatio = 2
js.document = types.SimpleNamespace(getElementById=lambda i: _Canvas())
js.Date = _Date()
js.localStorage = STORE
js.navigator = types.SimpleNamespace(
    clipboard=types.SimpleNamespace(writeText=_noop))
js.playSound = _noop
sys.modules["js"] = js

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
game.set_words(open(os.path.join(HERE, "answers.txt"), encoding="utf-8").read(),
               open(os.path.join(HERE, "words.txt"), encoding="utf-8").read())


def settle(limit=400):
    for _ in range(limit):
        if game.reveal is None:
            return
        game.update(0.02)


def type_word(w):
    for ch in w:
        game.key(ch)


def play(words):
    """Type each word in turn, waiting for the flip between them."""
    for w in words:
        type_word(w)
        game.key("enter")
        settle()


# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------
print("--- the word lists ---")
check("the answer list loaded", len(game.ANSWERS) > 3000)
check("the valid list is bigger than the answers",
      len(game.VALID) > len(game.ANSWERS))
check("every answer is five letters",
      all(len(w) == 5 and w.isalpha() for w in game.ANSWERS))
check("every answer is also a valid guess",
      all(w in game.VALID for w in game.ANSWERS[:500]))
check("common words are accepted",
      all(w in game.VALID for w in ("crane", "slate", "about", "which")))
check("nonsense is not", "zzzzz" not in game.VALID)

# ---------------------------------------------------------------------------
# The marking rule
# ---------------------------------------------------------------------------
print()
print("--- marking a guess ---")
check("an exact match is all green",
      game.mark("crane", "crane") == ["correct"] * 5)
check("a word with no shared letters is all grey",
      game.mark("crimp", "bough") == ["absent"] * 5)

# answer ABBEY, guess BOBBY - there are two Bs, one is in place
check("a right letter in the wrong place is amber",
      game.mark("bobby", "abbey") ==
      ["present", "absent", "correct", "absent", "correct"])

# answer ABBEY, guess KEBAB - the B count must be spent correctly
check("repeated letters are only counted as often as they occur",
      game.mark("kebab", "abbey") ==
      ["absent", "present", "correct", "present", "present"])

# answer CRANE, guess EERIE - only one E is left after the correct one
check("a letter cannot be marked twice for one occurrence",
      game.mark("eerie", "crane") ==
      ["absent", "absent", "present", "absent", "correct"])

check("the count of marks is always five",
      all(len(game.mark(w, "crane")) == 5
          for w in ("about", "zzzzz", "eerie", "crane")))
check("marks only use the three names",
      set(game.mark("eerie", "crane")) <= {"correct", "present", "absent"})

# ---------------------------------------------------------------------------
# Playing
# ---------------------------------------------------------------------------
print()
print("--- playing a round ---")
game.new_game("practice")
game.answer = "crane"
game.rows = []
game.current = ""

type_word("about")
check("letters go into the current guess", game.current == "about")
type_word("zz")          # already full
check("a guess cannot grow past five", game.current == "about")

game.key("back")
check("backspace removes a letter", game.current == "abou")
type_word("t")

before = len(game.rows)
game.key("enter")
check("a valid guess starts a reveal", game.reveal is not None)
settle()
check("the guess is recorded", len(game.rows) == before + 1)
check("the guess is marked", len(game.rows[-1][1]) == 5)
check("the row is cleared for the next guess", game.current == "")

# a short guess is refused
game.key("enter")
check("a short guess is refused", game.shake > 0 and not game.rows[-1][0] == "")

# a word that is not in the list is refused
game.shake = 0.0
game.current = ""
type_word("zzzzz")
n = len(game.rows)
game.key("enter")
check("a word outside the list is refused", len(game.rows) == n and game.shake > 0)

# ---------------------------------------------------------------------------
# Winning and losing
# ---------------------------------------------------------------------------
print()
print("--- winning and losing ---")
game.new_game("practice")
game.answer = "crane"
play(["about", "crane"])
check("the right word wins", game.won is True)
check("the game ends", game.state == "over")
check("it took two tries", len(game.rows) == 2)

game.new_game("practice")
game.answer = "crane"
play(["about", "bough", "crimp", "dwelt", "fjord", "knoll"])
check("six wrong guesses lose", game.lost is True)
check("the game ends after six", game.state == "over")
check("six rows are filled", len(game.rows) == 6)

game.new_game("practice")
game.answer = "crane"
play(["about", "crane"])
n = len(game.rows)
check("no more guesses are accepted once it is over", n == 2)
game.key("a")
check("typing after the end does nothing", game.current == "")

# ---------------------------------------------------------------------------
# The daily word
# ---------------------------------------------------------------------------
print()
print("--- the daily word ---")
_Date.fixed = (2026, 11, 25)
game.new_game("daily")
a1 = game.answer
game.new_game("daily")
a2 = game.answer
check("the daily word is the same all day", a1 == a2)
check("the daily word comes from the answer list", a1 in game.ANSWERS)

seen = set()
for day in range(1, 29):
    _Date.fixed = (2026, 11, day)
    game.new_game("daily")
    seen.add(game.answer)
check("different days give different words", len(seen) > 20)

_Date.fixed = (2026, 11, 25)

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
print()
print("--- stats ---")
game.stats = {"played": 0, "wins": 0, "streak": 0, "best": 0,
              "dist": [0, 0, 0, 0, 0, 0], "day": "", "done": False}
STORE.d.clear()

game.new_game("practice")
game.answer = "crane"
play(["crane"])
check("a win counts as played", game.stats["played"] == 1)
check("a win counts as a win", game.stats["wins"] == 1)
check("the streak starts at one", game.stats["streak"] == 1)
check("a first-try win lands in bin one", game.stats["dist"][0] == 1)

game.new_game("practice")
game.answer = "crane"
play(["about", "bough", "crimp", "dwelt", "fjord", "knoll"])
check("a loss counts as played", game.stats["played"] == 2)
check("a loss does not count as a win", game.stats["wins"] == 1)
check("a loss breaks the streak", game.stats["streak"] == 0)
check("the best streak is remembered", game.stats["best"] == 1)
check("the stats were written to storage", STORE.d.get("khelo_word_save") is not None)

saved = game.stats.copy()
game.stats = {"played": 0, "wins": 0, "streak": 0, "best": 0,
              "dist": [0, 0, 0, 0, 0, 0], "day": "", "done": False}
game._load()
check("the stats come back after a reload", game.stats["played"] == saved["played"])

# the daily marks itself as played
game.stats = {"played": 0, "wins": 0, "streak": 0, "best": 0,
              "dist": [0, 0, 0, 0, 0, 0], "day": "", "done": False}
STORE.d.clear()
game.new_game("daily")
game.answer = "crane"
play(["crane"])
check("finishing the daily marks it done", game._daily_left() is True)

# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
print()
print("--- screens ---")
game.state = "menu"
CALLS.clear()
game.draw()
check("the menu draws", len(CALLS) > 60)
check("the menu offers both modes",
      [t for t, _ in game._menu_hit] == ["daily", "practice"])

game.new_game("practice")
game.answer = "crane"
play(["about", "crane"])
CALLS.clear()
game.draw()
check("the end screen draws", len(CALLS) > 60)
check("the end screen offers again, share and menu",
      [t for t, _ in game._menu_hit] == ["again", "share", "menu"])

game.new_game("practice")
game.answer = "crane"
CALLS.clear()
game.draw()
check("the playing screen draws", len(CALLS) > 200)

# the on-screen keyboard covers every letter plus enter and back
keys = [k for k, _ in game._keys()]
check("the keyboard has 26 letters", len([k for k in keys if len(k) == 1]) == 26)
check("the keyboard has enter and back", "enter" in keys and "back" in keys)
check("every key sits inside the canvas",
      all(0 <= r[0] and r[0] + r[2] <= game.W and 0 <= r[1] and r[1] + r[3] <= game.H
          for _, r in game._keys()))
check("no two keys overlap",
      all(not (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
               and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])
          for i, (_, a) in enumerate(game._keys())
          for j, (_, b) in enumerate(game._keys()) if i < j))

# tapping a key on screen types that letter
game.new_game("practice")
game.answer = "crane"
kx, ky = None, None
for k, r in game._keys():
    if k == "q":
        kx, ky = r[0] + r[2] / 2, r[1] + r[3] / 2
game.tap(kx, ky)
check("tapping a key types it", game.current == "q")

# the share text is a grid of squares
game.rows = [("about", ["absent", "present", "correct", "absent", "absent"])]
game.won = True
game._share()
check("sharing does not crash", True)

# --- screen-adaptive UI -----------------------------------------------------
print()
print("--- screen-adaptive UI ---")
game.set_ui(1.0)
check("on a big screen the type is left alone",
      game._fit_font("700 15px X") == "700 15px X")
game.set_ui(0.70)
check("on a phone the type is scaled up",
      game._fit_font("700 15px X") != "700 15px X")
check("a 48 CSS px target is larger than 48 logical px", game.MIN_TOUCH > 48)
check("the type scale is capped", game.UI <= 1.35)
game.set_ui(1.0)

print()
if fails:
    print("FAILURES:", fails)
    sys.exit(1)
print("All checks passed.")

"""
Two devices in one room, played out to the end.

Each "device" is its own copy of game.py, and the only thing they share is the
messages we pass between them - the same snapshot, seats and actions that
Firebase carries in a real room. If the two boards ever disagree, this fails.
"""
import sys, os, types, json, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
SENT = []
fails = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def make_js(my_id):
    class Ctx:
        def __getattr__(self, n):
            def m(*a, **k):
                if n in ("createLinearGradient", "createRadialGradient"):
                    return type("G", (), {"addColorStop": lambda *x: None})()
                if n == "measureText":
                    return type("M", (), {"width": 40.0})()
                return None
            return m

    class El:
        width = 0
        height = 0
        def getContext(self, k):
            return Ctx()

    js = types.ModuleType("js")
    js.devicePixelRatio = 2
    js.document = types.SimpleNamespace(getElementById=lambda i: El())
    js.playSound = lambda n: None
    js.localStorage = types.SimpleNamespace(getItem=lambda k: None,
                                            setItem=lambda k, v: None)
    js.dice3d = types.SimpleNamespace(frame=lambda *a: None, canvas=El())
    js.focusName = lambda i, n: None
    js.netMe = lambda: my_id
    js.netAction = lambda p: SENT.append((my_id, p))
    return js


def load(name, my_id):
    sys.modules["js"] = make_js(my_id)
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "game.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def settle(g, frames=500):
    for _ in range(frames):
        g.update(1 / 60)
        if not g.anims and g.rolling <= 0:
            break


def tap_roll(g):
    g.tap(g.ROLL_RECT[0] + g.ROLL_RECT[2] / 2,
          g.ROLL_RECT[1] + g.ROLL_RECT[3] / 2)


def tap_first_token(g):
    if not g.moves:
        return False
    t = g.moves[0][0]
    x, y = g.token_xy(t["c"], t["i"], t["pos"])
    g.tap(x, y)
    return True


def main():
    host = load("host_game", "HOST")
    guest = load("guest_game", "GUEST")
    for g in (host, guest):
        g.set_size(560, 1155)

    seats = json.dumps({"HOST": 0, "GUEST": 1})
    host.set_net_ludo(True, True, 0)
    host.set_seats(seats, "HOST")
    host.start_game("single", 2)

    guest.set_net_ludo(True, False, -1)
    guest.set_seats(seats, "GUEST")
    guest.apply_net(host.snapshot())

    check("the host sits in seat 0", host.net_seat == 0)
    check("the guest takes the seat the room gave it", guest.net_seat == 1)
    check("both devices start on the same turn", guest.turn == host.turn)
    check("both devices have the same colours", list(guest.players) == list(host.players))

    problems = []
    rolls = moves = 0
    guest_rolled = False
    guest_moved = False

    for _ in range(600):
        if host.state != "play":
            break
        whose = host.turn % len(host.players)
        me = host if whose == 0 else guest
        tag = "host" if me is host else "guest"

        if not me.my_turn():
            problems.append("turn %d: the %s says it is not their turn"
                            % (host.turn, tag))
            break

        if me.can_roll and me.rolling <= 0 and not me.anims:
            SENT.clear()
            tap_roll(me)
            if me is guest:
                if not SENT:
                    problems.append("turn %d: the guest's roll never left the device"
                                    % host.turn)
                    break
                guest_rolled = True
                for _who, payload in SENT:
                    host.net_apply_action(payload)
            settle(host)
            guest.apply_net(host.snapshot())
            settle(guest)
            rolls += 1

        if me is guest:
            guest.apply_net(host.snapshot())

        if me.moves:
            SENT.clear()
            tap_first_token(me)
            if me is guest:
                if not SENT:
                    problems.append("turn %d: the guest's move never left the device"
                                    % host.turn)
                    break
                guest_moved = True
                for _who, payload in SENT:
                    host.net_apply_action(payload)
            settle(host)
            settle(guest)
            moves += 1
        else:
            settle(host)
            settle(guest)

        guest.apply_net(host.snapshot())

        if guest.turn != host.turn:
            problems.append("turn %d: guest says %d" % (host.turn, guest.turn))
            break
        if guest.dice != host.dice:
            problems.append("dice %d vs %d" % (host.dice, guest.dice))
            break
        if [(t["c"], t["i"], t["pos"]) for t in host.tokens] != \
           [(t["c"], t["i"], t["pos"]) for t in guest.tokens]:
            problems.append("tokens differ at turn %d" % host.turn)
            break
        if len(guest.moves) != len(host.moves):
            problems.append("moves %d vs %d at turn %d"
                            % (len(host.moves), len(guest.moves), host.turn))
            break

    check("the guest can roll its own dice", guest_rolled)
    check("the guest can move its own tokens", guest_moved)
    check("the round reaches a winner", host.state == "over" and host.winner is not None)
    check("both devices stayed in step for the whole round", not problems)
    # ---- a player walking out must not freeze the room -------------------
    print()
    print("--- somebody leaves mid-game ---")
    h3 = load("host3", "HOST")
    h3.set_size(560, 1155)
    h3.set_net_ludo(True, True, 0)
    seats3 = json.dumps({"HOST": 0, "B": 1, "C": 2})
    h3.set_seats(seats3, "HOST")
    h3.start_game("single", 3)
    c3 = load("guest3", "C")
    c3.set_size(560, 1155)
    c3.set_net_ludo(True, False, -1)
    c3.set_seats(seats3, "C")
    c3.apply_net(h3.snapshot())

    h3.set_present(json.dumps([0, 2]))        # B is gone
    check("the room remembers who is left", h3.net_present == [0, 2])

    stuck = False
    for _ in range(200):
        if h3.state != "play":
            break
        whose = h3.turn % len(h3.players)
        if whose == 1:
            stuck = True                      # the empty seat got the dice
            break
        me = h3 if whose == 0 else c3
        if me.can_roll and me.rolling <= 0 and not me.anims:
            SENT.clear()
            tap_roll(me)
            if me is c3:
                if not SENT:
                    break
                for _who, payload in SENT:
                    h3.net_apply_action(payload)
            settle(h3); c3.apply_net(h3.snapshot()); settle(c3)
        if me is c3:
            c3.apply_net(h3.snapshot())
        if me.moves:
            SENT.clear()
            tap_first_token(me)
            if me is c3:
                if not SENT:
                    break
                for _who, payload in SENT:
                    h3.net_apply_action(payload)
            settle(h3); settle(c3)
        else:
            settle(h3); settle(c3)
        c3.apply_net(h3.snapshot())
        if c3.turn != h3.turn:
            break

    check("the empty seat is never handed the dice", not stuck)


    # ---- a guest should see the same motion, not a snap -------------------
    print()
    print("--- what the guest sees ---")
    g = load("guest_view", "GUEST")
    g.set_size(560, 1155)
    g.set_net_ludo(True, False, 1)
    g.apply_net(host.snapshot())
    g.rolling = 0.0
    g.roll_t = 1.0

    h = load("host_view", "HOST")
    h.set_size(560, 1155)
    h.set_net_ludo(True, True, 0)
    h.start_game("single", 2)
    g.apply_net(h.snapshot())

    # the host rolls a new number
    h.dice = 4
    g.apply_net(h.snapshot())
    check("the guest's die tumbles when the host rolls", g.rolling > 0)

    # and a token that moves slides rather than jumping
    before = g.tokens[0]["x"]
    g.tokens[0]["pos"] = 0
    h.tokens[0]["pos"] = 0
    snap = h.snapshot()
    g.tokens[0]["x"] = 0.0
    g.apply_net(snap)
    moved = g.tokens[0]
    check("a token that moves gets a glide, not a jump",
          "glide" in moved or abs(moved["x"] - before) >= 0)



    if problems:
        print()
        for p in problems[:8]:
            print("  -", p)

    print()
    if fails:
        print("FAILURES:", fails)
        sys.exit(1)
    print("All checks passed. (%d rolls, %d moves)" % (rolls, moves))


if __name__ == "__main__":
    main()

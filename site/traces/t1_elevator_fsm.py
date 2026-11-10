"""Lift controller: three calls, the model stepped one clock at a time (travel and door times shrunk as in the bench)."""

FC, DC = 4, 3
CALLS = {1: 0b1000, 3: 0b0010, 14: 0b0001}   # clock -> floors called (switch edges)
N = 37
STATES = ["idle", "moving", "door open"]


def trace(m):
    md = m.Model(FC, DC)
    for at, mask in CALLS.items():
        md.call(at, mask)
    x, fl, dr, pe, stt, mv, cap = [], [], [], [], [], [], []
    seen = 0
    for t in range(N):
        md.run_to(t + 1)
        x.append(t)
        fl.append(md.read(m.FLOOR)); dr.append(md.read(m.DIR)); pe.append(md.read(m.PENDING))
        stt.append(STATES[md.read(m.STATE)]); mv.append(md.read(m.MOVES))
        new = [e for e in md.events[seen:]]
        seen = len(md.events)
        words = []
        if t in CALLS:
            fls = [str(k) for k in range(4) if CALLS[t] >> k & 1]
            words.append("call for floor " + ", ".join(fls))
        for (_, kind, f) in new:
            words.append({"depart": f"leaves floor {f}", "arrive": f"reaches floor {f}", "open": f"door opens at floor {f}",
                          "close": f"door closes at floor {f}"}[kind])
        if not words:
            st = md.read(m.STATE)
            words.append(f"moving {'down' if md.read(m.DIR) else 'up'} from floor {md.read(m.FLOOR)}" if st == m.MOVING
                         else f"{STATES[st]} at floor {md.read(m.FLOOR)}")
        cap.append(f"Clock {t}: " + "; ".join(words) + f". Outstanding calls {md.read(m.PENDING):04b}, floors travelled {md.read(m.MOVES)}.")
    return {
        "stimulus": f"Travel time {FC} clocks a floor and door time {DC} clocks (shrunk, as the bench does). Calls: "
                    + "; ".join(f"floor {k} at clock {at}" for at, mk in CALLS.items() for k in range(4) if mk >> k & 1) + ".",
        "unit": "clock", "x": x,
        "signals": [
            {"name": "FLOOR", "kind": "bus", "radix": "dec", "v": fl},
            {"name": "STATE", "kind": "text", "v": stt},
            {"name": "DIR (1 = down)", "kind": "bit", "v": dr},
            {"name": "PENDING", "kind": "bus", "radix": "bin", "width": 4, "v": pe},
            {"name": "MOVES", "kind": "bus", "radix": "dec", "v": mv},
        ],
        "captions": cap,
        "hero": {"floors": 4, "floor_cycles": FC},
    }

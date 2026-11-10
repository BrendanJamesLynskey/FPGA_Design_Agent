"""ADSR envelope: one note, the key held for GATE_ON ticks then released, the model run tick by tick."""

GATE_ON, GATE_OFF = 14, 8
ATK, DEC, SUS, REL = 12000, 8000, 30000, 14000
NAMES = ["idle", "attack", "decay", "sustain", "release"]


def trace(m):
    sc = [[1, ATK, DEC, SUS, REL]] * GATE_ON + [[0, ATK, DEC, SUS, REL]] * GATE_OFF
    out = m.run(sc)
    x, g, lv, st, cap = [], [], [], [], []
    prev = 0
    for t, ((gate, *_), (level, state)) in enumerate(zip(sc, out)):
        x.append(t); g.append(gate); lv.append(int(level)); st.append(NAMES[state])
        note = ""
        if t and state != out[t - 1][1]:
            note = f" The state changes to {NAMES[state]}."
        cap.append(f"Tick {t}: gate {'high' if gate else 'low'}, level {level} ({level * 100 // 65535}% of full scale), state {NAMES[state]}.{note}")
    return {
        "stimulus": f"One note: the gate is high for {GATE_ON} ticks and then low for {GATE_OFF}. Attack step {ATK}, decay step {DEC}, sustain level {SUS}, release step {REL}.",
        "unit": "tick", "x": x,
        "signals": [
            {"name": "gate", "kind": "bit", "v": g},
            {"name": "level", "kind": "wave", "lo": 0, "hi": 65535, "v": lv},
            {"name": "state", "kind": "text", "v": st},
        ],
        "captions": cap,
    }

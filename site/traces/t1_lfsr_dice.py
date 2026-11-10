"""LFSR dice: presses roll the model, a burst of silent steps and a reseed show the state moving without rolls."""

BURST = 10
ACTIONS = ["P"] * 6 + [("burst", BURST), "P", "P", ("seed", 0xACE1), "P", "P", "P", ("seed", 0)]
SEED = 0xACE1
BURST = 10


def trace(m):
    md = m.Model()
    x, st, rl, hi, rs, cap = [0], [md.read(m.STATE)], [md.read(m.ROLL)], [md.read(m.HISTORY)], [md.read(m.ROLLS)], []
    cap.append(f"Start: the LFSR state is {st[0]:04X} (the reset value) and nothing has been rolled.")
    for i, a in enumerate(ACTIONS, 1):
        before = md.read(m.STATE)
        if a == "P":
            md.press()
            s = f"Press {i}: the LFSR steps from {before:04X} to {md.read(m.STATE):04X}, which rolls a {md.read(m.ROLL)}. Rolls so far {md.read(m.ROLLS)}."
        elif a[0] == "burst":
            md.write(m.STEP, a[1])
            s = f"Event {i}: a burst of {a[1]} steps with no rolls moves the state from {before:04X} to {md.read(m.STATE):04X}."
        else:
            md.write(m.SEED, a[1])
            s = f"Event {i}: the seed {a[1]:04X} is loaded, so the state becomes {md.read(m.STATE):04X}" + (" (zero is replaced, so it never sticks at zero)." if a[1] == 0 else ".")
        x.append(i); st.append(md.read(m.STATE)); rl.append(md.read(m.ROLL)); hi.append(md.read(m.HISTORY)); rs.append(md.read(m.ROLLS))
        cap.append(s)
    return {
        "stimulus": f"From the reset state, press the button six times, run a silent burst of {BURST} steps, press twice, reload the seed {SEED:04X}, "
                    "press three times, then load a seed of zero.",
        "unit": "event", "x": x,
        "signals": [
            {"name": "STATE", "kind": "bus", "radix": "hex", "width": 16, "v": st},
            {"name": "ROLL", "kind": "bus", "radix": "dec", "v": rl},
            {"name": "HISTORY", "kind": "bus", "radix": "hex", "width": 16, "v": hi},
            {"name": "ROLLS", "kind": "bus", "radix": "dec", "v": rs},
        ],
        "captions": cap,
    }

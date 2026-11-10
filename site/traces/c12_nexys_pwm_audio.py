"""PWM audio stage: the model's script of gain writes and held samples, plus a few extra samples at the final gain."""

EXTRA = [0, -1, 100, -20000]


def trace(m):
    steps = list(m.steps()) + [{"reset": False, "write": None, "sample": v} for v in EXTRA]
    exp = m.expected(steps)
    x, smp, wr, so, low, cap = [], [], [], [], [], []
    for i, (s, e) in enumerate(zip(steps, exp)):
        x.append(i); smp.append(s["sample"])
        w = "reset" if s["reset"] else ("write " + str(s["write"]) if s["write"] is not None else "none")
        wr.append(w); so.append(int(e["sample_out"])); low.append(int(e["low_per_period"]))
        what = {"reset": "Reset (gain back to the default). ", "none": ""}.get(w, f"Gain {w}. ")
        cap.append(f"Step {i}: {what}Sample {s['sample']} gives sample_out {e['sample_out']} and the pin is pulled low for {e['low_per_period']} of 1024 clocks.")
    return {
        "stimulus": f"The model's script of resets, gain writes (up to {max(s['write'] or 0 for s in steps)}, against a limit of {m.GAIN_MAX}) and held samples, followed by {len(EXTRA)} more samples at the last gain.",
        "unit": "step", "x": x,
        "signals": [
            {"name": "sample", "kind": "wave", "lo": -32768, "hi": 32767, "v": smp},
            {"name": "gain action", "kind": "text", "v": wr},
            {"name": "sample_out", "kind": "wave", "lo": -4096, "hi": 4096, "v": so},
            {"name": "clocks low per period", "kind": "bus", "radix": "dec", "width": 11, "v": low},
        ],
        "captions": cap,
    }

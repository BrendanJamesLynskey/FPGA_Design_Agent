"""Pattern sequencer: five programmed entries played in loop mode; a step is one entry (tick shrunk as the bench does)."""

TICK = 4
ENTRIES = [(0x000F, 3), (0x00F0, 2), (0x0F00, 4), (0xF000, 1), (0xAAAA, 5)]   # (pattern, duration in ticks)
N = 16


def trace(m):
    md = m.Model(TICK)
    for i, (p, d) in enumerate(ENTRIES):
        md.write(m.ENTRY0 + i, p | d << 16)
    md.write(m.LENGTH, len(ENTRIES))
    md.write(m.CTRL, 1)          # run, loop mode (ONESHOT = 0)
    shown = md.show(N)
    x, idx, led, clk, lp, cap = [], [], [], [], [], []
    start = 0
    for i, (pat, n) in enumerate(shown):
        x.append(i)
        idx.append(i % md.length); lp.append(i // md.length)
        led.append(pat); clk.append(n)
        cap.append(f"Entry {i % md.length} (pass {i // md.length}): the LEDs show {pat:016b} for {n} clocks, from clock {start} to {start + n - 1}."
                   + (" The last entry is done, so playback goes round again." if i % md.length == md.length - 1 else ""))
        start += n
    return {
        "stimulus": f"{len(ENTRIES)} entries are written (patterns and durations in ticks), length {len(ENTRIES)}, loop mode, then playback is started. "
                    f"One tick is {TICK} clocks (shrunk). No pause and no changes while it runs. The first {N} entries shown are listed.",
        "unit": "entry", "x": x,
        "signals": [
            {"name": "INDEX", "kind": "bus", "radix": "dec", "v": idx},
            {"name": "LED[15:0]", "kind": "bus", "radix": "bin", "width": 16, "v": led},
            {"name": "clocks shown", "kind": "wave", "v": clk, "lo": 0},
            {"name": "LOOPS", "kind": "bus", "radix": "dec", "v": lp},
        ],
        "captions": cap,
    }

"""Gray-code stepper: the model stepped up across the wrap, then down across it again."""

START = 1019
UP, DOWN = 8, 12


def trace(m):
    md = m.Model()
    md.write(m.BIN, START)
    x, gr, bn, ch, cap = [0], [md.read(m.GRAY)], [md.read(m.BIN)], [0], []
    cap.append(f"Step 0: the count is set to {bn[0]}, so the LEDs show Gray code {gr[0]:010b}.")
    for i in range(1, UP + DOWN + 1):
        md.dir = 0 if i <= UP else 1
        prev = md.read(m.GRAY)
        md.step()
        g = md.read(m.GRAY)
        x.append(i); gr.append(g); bn.append(md.read(m.BIN)); ch.append(bin(prev ^ g).count("1"))
        cap.append(f"Step {i}: {'up' if md.dir == 0 else 'down'} to count {bn[-1]}, Gray {g:010b}; {ch[-1]} LED changed.")
    return {
        "stimulus": f"The count is set to {START}, then stepped up {UP} times (past the top of the range) and down {DOWN} times (past the bottom of the range again).",
        "unit": "step", "x": x,
        "signals": [
            {"name": "BIN", "kind": "bus", "radix": "dec", "v": bn},
            {"name": "GRAY", "kind": "bus", "radix": "bin", "width": 10, "v": gr},
            {"name": "LEDs changed", "kind": "bus", "radix": "dec", "v": ch},
        ],
        "captions": cap,
    }

"""Byte FIFO: fill it to the brim, overflow it, drain it, underflow it, clearing the sticky flags between."""

AF = 4
N = 16


def trace(m):
    md = m.Model()
    ops = [("af", AF)] + [("push", 0xA0 + k) for k in range(N + 1)] + [("head", 0)] + [("pop", 0)] * 4 + [("clr", 0x100)] \
        + [("pop", 0)] * (N - 4) + [("pop", 0), ("clr", 0x200)]
    x, lv, hd, out, em, fu, af, ov, un, cap = [], [], [], [], [], [], [], [], [], []
    for i, (op, a) in enumerate(ops):
        got = None
        lvl0 = md.read(m.LEVEL)
        if op == "af":
            md.write(m.AF_THRESH, a); s = f"Almost-full threshold set to {md.read(m.AF_THRESH)}."
        elif op == "push":
            md.write(m.PUSH, a)
            s = f"Push {a:02X}: " + (f"stored, level {lvl0} to {md.read(m.LEVEL)}." if md.read(m.LEVEL) != lvl0 else f"the FIFO is full, so the byte is lost and the overflow flag is set.")
        elif op == "head":
            got = md.read(m.HEAD); s = f"Read HEAD: {got:02X}, the oldest byte, which stays in the FIFO."
        elif op == "pop":
            got = md.pop()
            s = f"Pop: returns {got:02X}, level {lvl0} to {md.read(m.LEVEL)}." if lvl0 else f"Pop of an empty FIFO returns {got:02X} and sets the underflow flag."
        else:
            md.write(m.FLAGS, a); s = f"Write FLAGS with {a:03X}: the {'overflow' if a == 0x100 else 'underflow'} flag is cleared."
        f = md.read(m.FLAGS)
        x.append(i); lv.append(md.read(m.LEVEL)); hd.append(md.read(m.HEAD)); out.append(got if got is not None else 0)
        em.append(f & 1); fu.append(f >> 1 & 1); af.append(f >> 2 & 1); ov.append(f >> 8 & 1); un.append(f >> 9 & 1)
        if op == "push" and fu[-1] and lvl0 == 15:
            s += " The FIFO is now full."
        if op == "pop" and em[-1] and lvl0:
            s += " The FIFO is now empty."
        cap.append(f"Op {i}: {s}" + (f" Almost-full flag is {af[-1]}." if op in ("push", "pop") and af[-1] != (af[-2] if len(af) > 1 else 0) else ""))
    return {
        "stimulus": f"The almost-full threshold is set to {AF}. Then {N + 1} bytes are pushed (one more than fits), one is peeked, four are popped, the overflow flag is cleared, "
                    f"the rest are popped, one extra pop hits the empty FIFO and the underflow flag is cleared.",
        "unit": "operation", "x": x,
        "signals": [
            {"name": "LEVEL", "kind": "bus", "radix": "dec", "v": lv},
            {"name": "HEAD", "kind": "bus", "radix": "hex", "width": 8, "v": hd},
            {"name": "data read", "kind": "bus", "radix": "hex", "width": 8, "v": out},
            {"name": "EMPTY", "kind": "bit", "v": em},
            {"name": "FULL", "kind": "bit", "v": fu},
            {"name": "ALMOST_FULL", "kind": "bit", "v": af},
            {"name": "OVERFLOW", "kind": "bit", "v": ov},
            {"name": "UNDERFLOW", "kind": "bit", "v": un},
        ],
        "captions": cap,
    }

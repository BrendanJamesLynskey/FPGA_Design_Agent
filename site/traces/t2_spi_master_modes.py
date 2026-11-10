"""SPI master: two 8-bit frames shown edge by edge, in mode 0 (slave answering) and in mode 3 with LSB first (loopback)."""

DIVV = 5
TX = 0xA5
SLAVE = 0x3C                 # what the slave on JB3 sends in the first frame
N = 8


def trace(m):
    md = m.Model()
    md.write(m.DIV, DIVV)
    x, cs, sclk, mosi, miso, rx, busy, cap = [], [], [], [], [], [], [], []
    g = 0
    frames = [(0, SLAVE), (m.CPOL | m.CPHA | m.LSB | m.LOOP, None)]
    for fi, (ctrl, slave) in enumerate(frames):
        md.write(m.CTRL, ctrl)
        cpol, cpha = ctrl & m.CPOL, bool(ctrl & m.CPHA)
        mode = cpol * 2 + int(cpha)
        started = md.write(m.TXDATA, TX)
        assert started
        out = m.tx_bits(TX, md.ctrl)
        sl = m.tx_bits(slave, md.ctrl) if slave is not None else None      # slave's bits in the order they go out
        mo_bits = out
        mi_bits = out if md.ctrl & m.LOOP else sl
        order = "LSB first" if ctrl & m.LSB else "MSB first"
        rx_before = md.read(m.RXDATA)
        for k in range(2 * N + 1):
            idx = min(k // 2, N - 1) if not cpha else (None if k == 0 else (k - 1) // 2)
            lvl = cpol ^ (k & 1)
            x.append(g); g += 1
            cs.append(0); sclk.append(lvl); busy.append(1); rx.append(rx_before)
            mosi.append(mo_bits[idx] if idx is not None else 0)
            miso.append(mi_bits[idx] if idx is not None else 0)
            if k == 0:
                s = f"Frame {fi + 1} (mode {mode}, {order}{', MISO wired to MOSI' if md.ctrl & m.LOOP else ''}): chip select goes low, SCLK idles {'high' if cpol else 'low'}."
                s += " The first bit is already on MOSI." if not cpha else " MOSI waits for the first clock edge."
            else:
                lead = k % 2 == 1
                samp = lead != cpha            # sampling edge: leading for phase 0, trailing for phase 1
                s = f"Edge {k} ({'leading' if lead else 'trailing'}): SCLK goes {'high' if lvl else 'low'}."
                if samp:
                    j = (k - 1) // 2 if lead else k // 2 - 1
                    s += f" Both sides sample bit {j + 1} of {N}: MOSI {mo_bits[j]}, MISO {mi_bits[j]}."
                else:
                    if k == 1 and cpha:
                        s += " MOSI now shows the first bit."
                    elif k < 2 * N:
                        s += " The data lines move on to the next bit."
            cap.append(f"Step {g - 1}: {s}")
        out = md.finish(sl)
        x.append(g); g += 1
        cs.append(1); sclk.append(cpol); busy.append(0); mosi.append(0); miso.append(0); rx.append(md.read(m.RXDATA))
        cap.append(f"Step {g - 1}: One SCLK half period later the frame ends: busy falls, done is set, chip select goes high and RXDATA reads {md.read(m.RXDATA):#04x}.")
    return {
        "stimulus": f"Divisor {DIVV}, so SCLK edges are {DIVV} clocks apart. Frame 1 sends {TX:#04x} in mode 0 (idle low, sample on the leading edge) to a slave that answers {SLAVE:#04x}. "
                    f"Frame 2 sends {TX:#04x} in mode 3 (idle high, sample on the trailing edge), least significant bit first, with MISO looped back from MOSI. "
                    "The bit order and RXDATA come from the model; the SCLK edges are drawn from the spec's mode rules, which the model does not clock. "
                    "MOSI and MISO are shown as 0 when no bit is being driven.",
        "unit": "SCLK edge", "x": x,
        "signals": [
            {"name": "JB1 CS_N", "kind": "bit", "v": cs},
            {"name": "JB4 SCLK", "kind": "bit", "v": sclk},
            {"name": "JB2 MOSI", "kind": "bit", "v": mosi},
            {"name": "JB3 MISO", "kind": "bit", "v": miso},
            {"name": "BUSY", "kind": "bit", "v": busy},
            {"name": "RXDATA", "kind": "bus", "radix": "hex", "width": 16, "v": rx},
        ],
        "captions": cap,
    }

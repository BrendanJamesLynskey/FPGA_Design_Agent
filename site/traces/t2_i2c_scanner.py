"""I2C scanner: the model runs a whole scan over a bus with two devices; the trace shows one probe per step for a window of addresses."""

PRESENT = {0x1D, 0x4B}
WINDOWS = [(0x08, 0x0A), (0x1A, 0x20), (0x48, 0x4D)]        # (first, last) address ranges shown; the probes between are left out


def trace(m):
    md = m.Model()
    log = md.scan(PRESENT)
    probes = [e for e in log if e[0] == "A"]            # ("A", address, 0, acked), one per probe
    cnt, rows = 0, []
    lowest = 0xFF
    for _, a, rw, ack in probes:
        if ack:
            cnt += 1
            if lowest == 0xFF:
                lowest = a
        rows.append((a, int(ack), cnt, lowest))
    assert (cnt, lowest) == (md.read(m.COUNT), md.read(m.LOWEST))
    rows = [r for r in rows if any(lo <= r[0] <= hi for lo, hi in WINDOWS)]
    x = [r[0] for r in rows]
    cap = []
    for a, ack, c, lo in rows:
        cap.append(f"Probe {a:#04x}: START, address byte {a << 1:#04x} (write), then STOP; "
                   + (f"the ACK bit is low, so a device answers. Devices found so far {c}, lowest {lo:#04x}." if ack else "no answer (ACK bit left high)."))
    return {
        "stimulus": f"A scan is started over a bus where the devices at {', '.join(f'{a:#04x}' for a in sorted(PRESENT))} answer. "
                    "Only the probes of " + ", ".join(f"{lo:#04x} to {hi:#04x}" for lo, hi in WINDOWS) + " are shown (the rest of the scan runs the same way); every probe is a write address and a STOP, never a data byte.",
        "unit": "probe", "x": x,
        "signals": [
            {"name": "address", "kind": "bus", "radix": "hex", "width": 7, "v": [r[0] for r in rows]},
            {"name": "ACK", "kind": "bit", "v": [r[1] for r in rows]},
            {"name": "COUNT", "kind": "bus", "radix": "dec", "v": [r[2] for r in rows]},
            {"name": "LOWEST", "kind": "bus", "radix": "hex", "width": 8, "v": [r[3] for r in rows]},
        ],
        "captions": cap,
    }

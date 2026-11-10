"""Byte-command I2C master: a script of START / WRITE / READ / STOP commands against the sensor and one other slave."""

Q = 250
TEMP_Q7 = 0x0D87
# (op, data, read_nack)
SCRIPT = [("S", 0, 0), ("W", 0x4B << 1, 0), ("W", 0x0B, 0), ("S", 0, 0), ("W", 0x4B << 1 | 1, 0), ("R", 0, 1), ("P", 0, 0),
          ("S", 0, 0), ("W", 0x1D << 1 | 1, 0), ("R", 0, 1), ("P", 0, 0),
          ("S", 0, 0), ("W", 0x50 << 1, 0), ("P", 0, 0)]
OPS = {"S": 1, "W": 2, "R": 3, "P": 4}
NAMES = {"S": "START", "W": "WRITE", "R": "READ", "P": "STOP"}


def trace(m):
    from benchmark.lib.i2c_devices import Adt7420, FixedDevice
    md = m.Model([Adt7420(TEMP_Q7), FixedDevice(0x1D)], Q)
    x, op, dat, own, nk, rx, cap = [], [], [], [], [], [], []
    for i, (o, d, rn) in enumerate(SCRIPT):
        n0 = len(md.log)
        was_owned = md.owned
        md.command(m.cmd_word(OPS[o], d, rn))
        new = md.log[n0:]
        st = md.read(m.STATUS)
        x.append(i)
        label = "Sr" if o == "S" and was_owned else NAMES[o]
        op.append(label if label != "Sr" else "repeated START")
        dat.append(d if o == "W" else (md.read(m.RXDATA) if o == "R" else 0))
        own.append(st >> 2 & 1); nk.append(st >> 1 & 1); rx.append(md.read(m.RXDATA))
        e = new[0] if new else None
        if o == "S":
            s = "a repeated START (the master already holds the bus, so no STOP in between)" if was_owned else "START on a free bus"
        elif o == "W" and e and e[0] == "A":
            s = f"the address byte {d:#04x} (device {e[1]:#04x}, {'read' if e[2] else 'write'}): " + ("acknowledged" if e[3] else "not acknowledged")
        elif o == "W" and e:
            s = f"data byte {d:#04x}: " + ("acknowledged" if e[2] else "not acknowledged")
        elif o == "W":
            s = f"byte {d:#04x} with nobody listening: not acknowledged"
        elif o == "R":
            s = f"reads byte {md.read(m.RXDATA):#04x} and answers " + ("NACK, the last byte" if rn else "ACK, more to come")
        else:
            s = "STOP, the bus is free again"
        cap.append(f"Command {i}: {NAMES[o]} - {s}.")
    return {
        "stimulus": f"A script of {len(SCRIPT)} commands: read the sensor's ID register (pointer write, repeated START, one read), read one byte from a second device at 0x1D, "
                    "then address a device that is not there.",
        "unit": "command", "x": x,
        "signals": [
            {"name": "command", "kind": "text", "v": op},
            {"name": "data", "kind": "bus", "radix": "hex", "width": 8, "v": dat},
            {"name": "OWNED", "kind": "bit", "v": own},
            {"name": "NACK", "kind": "bit", "v": nk},
            {"name": "RXDATA", "kind": "bus", "radix": "hex", "width": 8, "v": rx},
        ],
        "captions": cap,
    }

"""ADT7420 alarm: the model's configure sequence and three readings, one bus event per step."""

CODES = [0x0C80, 0x2100, 0x0A00]       # raw 16-bit readings the sensor returns (1/128 C a step)
POINTERS = {0x00: "temperature", 0x03: "CONFIG", 0x04: "T_HIGH", 0x06: "T_LOW"}


def trace(m):
    md = m.Model()
    cfg = md.configure()
    seq = [("cfg", e) for e in cfg]
    for c in CODES:
        md.alarm = False
        # keep a copy of the registers as they are before the reading, and after it
        before = (md.temp, md.max, md.min, md.samples)
        log = md.reading(c)
        after = (md.temp, md.max, md.min, md.samples)
        md.alarm = m.s16(c) > m.s16(md.thigh)          # the sensor holds TMP_INT low while it reads above T_HIGH
        seq += [("rd", e, before, after, md.alarm, c) for e in log]
    x, ev, by, te, mx, mn, sa, al, cap = [], [], [], [], [], [], [], [], []
    cur = (0, 0, 0, 0)
    alarm = 0
    ptr = None
    wcount = 0
    for i, item in enumerate(seq):
        kind, e = item[0], item[1]
        if kind == "rd":
            cur = item[2] if e[0] != "P" else item[3]
            alarm = int(item[4]) if e[0] == "P" else alarm
        k = e[0]
        byte = 0
        if k == "S":
            name, s = "START", "START on the bus."
            wcount = 0
        elif k == "Sr":
            name, s = "repeated START", "Repeated START, with no STOP, so the sensor keeps its register pointer."
        elif k == "A":
            byte = e[1] << 1 | e[2]
            name = "address " + ("R" if e[2] else "W")
            s = f"Address byte {byte:#04x} ({'read from' if e[2] else 'write to'} {e[1]:#04x}): " + ("acknowledged." if e[3] else "not acknowledged.")
            wcount = 0
        elif k == "W":
            byte = e[1]
            if wcount == 0:
                ptr = byte
                name, s = "pointer", f"Write {byte:#04x}: selects the {POINTERS.get(byte, 'register')} register."
            else:
                name, s = "data", f"Write {byte:#04x}: data for the {POINTERS.get(ptr, 'register')} register."
            wcount += 1
        elif k == "R":
            byte = e[1]
            name, s = "data read", f"Read {byte:#04x}, answered with " + ("ACK, one more byte to come." if e[2] else "NACK, the last byte.")
        else:
            name, s = "STOP", "STOP." + (f" The reading is stored: TEMP {item[3][0]:04X}, highest {item[3][1]:04X}, lowest {item[3][2]:04X}, readings so far {item[3][3]}, alarm {'on' if item[4] else 'off'}." if kind == "rd" else "")
        x.append(i); ev.append(name); by.append(byte)
        te.append(cur[0]); mx.append(cur[1]); mn.append(cur[2]); sa.append(cur[3]); al.append(alarm)
        cap.append(f"Event {i}: {s}")
    return {
        "stimulus": "The configure command writes three register blocks (CONFIG, T_HIGH, T_LOW) to the sensor, then the model takes "
                    f"{len(CODES)} readings that the sensor returns as " + ", ".join(f"{c:#06x}" for c in CODES) + ". The sensor's INT pin is part of the stimulus: it is held active while a reading is above T_HIGH (comparator mode), and ALARM follows it.",
        "unit": "bus event", "x": x,
        "signals": [
            {"name": "bus", "kind": "text", "v": ev},
            {"name": "byte", "kind": "bus", "radix": "hex", "width": 8, "v": by},
            {"name": "TEMP", "kind": "bus", "radix": "hex", "width": 16, "v": te},
            {"name": "MAX", "kind": "bus", "radix": "hex", "width": 16, "v": mx},
            {"name": "MIN", "kind": "bus", "radix": "hex", "width": 16, "v": mn},
            {"name": "SAMPLES", "kind": "bus", "radix": "dec", "v": sa},
            {"name": "ALARM", "kind": "bit", "v": al},
        ],
        "captions": cap,
    }

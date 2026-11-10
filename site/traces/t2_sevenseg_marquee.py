"""Seven-segment marquee: the model's scroll position stepped left, then right; the window text is the characters the raw bytes stand for."""

# character -> raw segment byte (bit 0 = a ... bit 6 = g, bit 7 = point): the message the user would write
FONT = {"F": 0x71, "P": 0x73, "G": 0x3D, "A": 0x77, "-": 0x40, "7": 0x07, "S": 0x6D, "E": 0x79}
MESSAGE = "FPGA-7SEG-"
LEFT, RIGHT = 12, 8


def trace(m):
    md = m.Model()
    for i, ch in enumerate(MESSAGE):
        md.write(m.MSG0 + i, FONT[ch])
    md.write(m.LENGTH, len(MESSAGE))
    back = {v: k for k, v in FONT.items()}
    x, pos, win, lft, rgt, dr, cap = [], [], [], [], [], [], []

    def snap(i, note):
        x.append(i); pos.append(md.read(m.POS))
        win.append("".join(back[md.digit_byte(k)] for k in range(7, -1, -1)))
        lft.append(md.digit_byte(7)); rgt.append(md.digit_byte(0)); dr.append(md.read(m.CTRL) >> 1 & 1)
        cap.append(f"Step {i}: {note} Position {pos[-1]}; the eight digits show {win[-1]}.")

    snap(0, "Scrolling starts from the beginning of the message.")
    md.write(m.CTRL, m.SCROLL)
    for i in range(1, LEFT + 1):
        md.step()
        snap(i, "The text moves one character left." + (" The message wraps round to its start." if md.read(m.POS) == 0 else ""))
    md.write(m.CTRL, m.SCROLL | m.DIR)
    for i in range(LEFT + 1, LEFT + RIGHT + 1):
        md.step()
        snap(i, ("The direction is reversed, so the text moves right." if i == LEFT + 1 else "The text moves one character right.")
             + (" The message wraps round to its end." if md.read(m.POS) == len(MESSAGE) - 1 and i > LEFT else ""))
    return {
        "stimulus": f"The message {MESSAGE} ({len(MESSAGE)} characters, each written as a raw segment byte) is scrolled {LEFT} steps left and then {RIGHT} steps right. "
                    "The window text below is those bytes shown as the letters they draw.",
        "unit": "scroll step", "x": x,
        "signals": [
            {"name": "window (left to right)", "kind": "text", "v": win},
            {"name": "POS", "kind": "bus", "radix": "dec", "v": pos},
            {"name": "leftmost digit", "kind": "bus", "radix": "hex", "width": 8, "v": lft},
            {"name": "rightmost digit", "kind": "bus", "radix": "hex", "width": 8, "v": rgt},
            {"name": "DIR", "kind": "bit", "v": dr},
        ],
        "captions": cap,
    }

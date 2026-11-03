"""Golden model of p_morse_beacon, written from spec.yaml alone."""

from __future__ import annotations

CHAR, CTRL, STATUS = 0, 1, 2
DESIGN_ID = 0x4D4F5253
CODE = {"A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....", "I": "..",
        "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
        "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--", "Z": "--..",
        "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....",
        "7": "--...", "8": "---..", "9": "----."}


def key_units(text: str) -> list[tuple[int, int]]:
    """The keying as [(level, units)] for one transmission of text: no leading or trailing off period."""
    out: list[tuple[int, int]] = []
    gap = 0
    for ch in text:
        if ch == " ":
            gap = 7 if out else 0
            continue
        if out:
            out.append((0, gap if gap == 7 else 3))
        gap = 0
        for i, m in enumerate(CODE[ch]):
            if i:
                out.append((0, 1))
            out.append((1, 1 if m == "." else 3))
    return out


class Model:
    def __init__(self) -> None:
        self.text = ""
        self.dropped = 0
        self.busy = False

    def write(self, off: int, v: int) -> None:
        if off == CHAR:
            ch = chr(v & 0xFF).upper() if chr(v & 0xFF).isalnum() and (v & 0xFF) < 128 else chr(v & 0xFF)
            if ch in CODE or ch == " ":
                if self.busy or len(self.text) >= 16:
                    self.dropped = min(255, self.dropped + 1)
                else:
                    self.text += ch
        elif off == CTRL and not self.busy:
            if v & 2:
                self.text = ""
            if v & 1 and self.text:
                self.busy = True

    def finish(self) -> None:
        self.busy = False

    def read(self, off: int) -> int:
        if off == CHAR:
            return len(self.text)
        if off == STATUS:
            return int(self.busy) | len(self.text) << 8 | self.dropped << 16
        return 0

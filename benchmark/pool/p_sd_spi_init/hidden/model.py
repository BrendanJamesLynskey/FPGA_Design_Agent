"""Golden model of p_sd_spi_init, written from spec.yaml alone: what the registers and the command list must be for a given card."""

from __future__ import annotations

STATE, CARDTYPE, OCR, TRIES, ERRCODE = range(5)
DESIGN_ID = 0x5344494E
ACMD41_V2_ARG = 0x40000000


def expect(card: dict, max_tries: int) -> dict:
    """card: present, v2, sdhc, tries_needed, cmd0_r1 (default 0x01). Returns state, type, ocr, tries, err and the command list [(index, argument)]."""
    cmds: list[tuple[int, int]] = [(0, 0)]
    if not card.get("present", True) or card.get("cmd0_r1", 0x01) != 0x01:
        return {"state": 6, "type": 0, "ocr": 0, "tries": 0, "err": 1, "cmds": cmds}
    cmds.append((8, 0x1AA))
    v2 = card.get("v2", True)
    arg = ACMD41_V2_ARG if v2 else 0
    ready, k = False, 0
    for k in range(1, max_tries + 1):
        cmds += [(55, 0), (41, arg)]
        if k >= card.get("tries_needed", 1):
            ready = True
            break
    if not ready:
        return {"state": 6, "type": 0, "ocr": 0, "tries": max_tries, "err": 3, "cmds": cmds}
    if not v2:
        return {"state": 5, "type": 1, "ocr": 0, "tries": k, "err": 0, "cmds": cmds}
    cmds.append((58, 0))
    return {"state": 5, "type": 3 if card.get("sdhc", True) else 2, "ocr": ocr_word(card), "tries": k, "err": 0, "cmds": cmds}


def ocr_word(card: dict) -> int:
    return 0x80FF8000 | (0x40000000 if card.get("sdhc", True) else 0)


def leds(e: dict) -> int:
    return e["state"] | e["type"] << 4 | int(e["state"] == 5) << 8 | int(e["state"] == 6) << 9


class Model:
    def __init__(self, max_tries: int) -> None:
        self.max_tries = max_tries
        self.e: dict | None = None

    def run(self, card: dict) -> dict:
        self.e = expect(card, self.max_tries)
        return self.e

    def read(self, off: int) -> int:
        e = self.e or {"state": 0, "type": 0, "ocr": 0, "tries": 0, "err": 0}
        return {STATE: e["state"], CARDTYPE: e["type"], OCR: e["ocr"], TRIES: e["tries"], ERRCODE: e["err"]}.get(off, 0)

"""The register map is generated from regmap.py and checked against the RTL decode (house rule: document wherever a user could be unsure)."""

from __future__ import annotations

import re
from pathlib import Path

from designs.b96_kr260_10g import regmap

DESIGN = Path(__file__).parent.parent
CORE = (DESIGN / "rtl" / "b96_core.sv").read_text()


def test_register_map_is_current() -> None:
    assert (DESIGN / "docs" / "register_map.md").read_text() == regmap.render(), "run: python3 designs/b96_kr260_10g/regmap.py --write"


def test_every_address_is_decoded_and_nothing_else() -> None:
    mapped = {a for a, *_ in regmap.REGS} | {a for a, *_ in regmap.RANGES}
    in_rtl = {int(m, 16) for m in re.findall(r"12'h([0-9A-Fa-f]{3})", CORE)}
    assert in_rtl == mapped, f"RTL decodes {sorted(map(hex, in_rtl - mapped))} unlisted; map lists {sorted(map(hex, mapped - in_rtl))} unimplemented"


def test_vector_widths_agree() -> None:
    assert f"NRXW = {len(regmap.RXV)}" in CORE and f"NTXW = {len(regmap.TXV)}" in CORE
    tx = (DESIGN / "rtl" / "tx_path.sv").read_text()
    assert f"NTXW = {len(regmap.TXV)}" in tx
    assert max(int(m) for m in re.findall(r"tw\[(\d+)\] =", tx)) == len(regmap.TXV) - 1
    rx = (DESIGN / "rtl" / "rx_path.sv").read_text()
    assert max(int(m) for m in re.findall(r"rw\[(\d+)\] =", rx)) == len(regmap.RXV) - 1


def test_stated_rules() -> None:
    doc = (DESIGN / "docs" / "register_map.md").read_text()
    for must in ("Unmapped addresses", "Reserved bits", "Reads have no side effects", "Write-only registers read as 0", "snapshot"):
        assert must in doc, must

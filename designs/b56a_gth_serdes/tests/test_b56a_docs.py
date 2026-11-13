"""The register-map document is generated and checked against the RTL (house rule: document wherever a user could be unsure)."""

from __future__ import annotations

import re
from pathlib import Path

from designs.b56a_gth_serdes import regmap

DESIGN = Path(__file__).parent.parent
CORE = (DESIGN / "rtl" / "gth_serdes_core.sv").read_text()


def test_register_map_is_current() -> None:
    assert (DESIGN / "docs" / "register_map.md").read_text() == regmap.render(), "run: python3 designs/b56a_gth_serdes/regmap.py --write"


def test_every_address_is_decoded_and_nothing_else() -> None:
    mapped = {a for a, *_ in regmap.REGS}
    in_rtl = {int(m, 16) for m in re.findall(r"12'h([0-9A-Fa-f]{3})", CORE)}
    assert in_rtl == mapped, f"RTL decodes {sorted(map(hex, in_rtl - mapped))} unlisted; map lists {sorted(map(hex, mapped - in_rtl))} unimplemented"


def test_reset_values_agree_with_the_bench() -> None:
    ctrl = [r for r in regmap.REGS if r[1] == "CTRL"][0]
    bench = (DESIGN / "sim" / "tb_gth_loopback.sv").read_text()
    assert ctrl[3].lower().replace("0x", "") in bench.lower().replace("0x", "").replace("32'h", "").replace("_", "")


def test_unmapped_and_reserved_rules_are_stated() -> None:
    doc = (DESIGN / "docs" / "register_map.md").read_text()
    for must in ("Unmapped addresses", "Reserved bits", "Reads have no side effects", "Write-only registers read as 0", "snapshot", "W1C"):
        assert must in doc, must

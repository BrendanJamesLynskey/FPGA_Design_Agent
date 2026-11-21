"""The ML register map is generated from regmap_ml.py and checked against the RTL decode and the stage's status vector."""
from __future__ import annotations

import re
from pathlib import Path

from designs.b96_kr260_10g.rm_gp_ml import regmap_ml as rm

D = Path(__file__).resolve().parents[1]
CORE = (D / "rtl" / "b96_core.sv").read_text()
BASE = (D.parent / "rtl" / "b96_core.sv").read_text()


def test_map_is_current() -> None:
    assert (D / "docs" / "ml_registers.md").read_text() == rm.render(), "run: python3 designs/b96_kr260_10g/rm_gp_ml/regmap_ml.py --write"


def test_every_new_address_is_decoded_and_nothing_else_changed() -> None:
    new = {int(m, 16) for m in re.findall(r"12'h([0-9A-Fa-f]{3})", CORE)} - {int(m, 16) for m in re.findall(r"12'h([0-9A-Fa-f]{3})", BASE)}
    mapped = {a for a, *_ in rm.REGS} | {a for a, *_ in rm.RANGES}
    assert new == mapped, (sorted(map(hex, new)), sorted(map(hex, mapped)))


def test_status_words_agree() -> None:
    stage = (D / "rtl" / "ml_stage.sv").read_text()
    pkg = (D / "rtl" / "ml_pkg.sv").read_text()
    assert f"NMLW = {len(rm.MLV)};" in pkg
    assert max(int(m) for m in re.findall(r"mw\[(\d+)\] =", stage)) == len(rm.MLV) - 1
    assert rm.RANGES[0][1] == len(rm.MLV)


def test_features_bit_8_and_reset_values() -> None:
    assert re.search(r"12'h008: rd = \{23'd0, 1'b1, 2'd0,", CORE), "FEATURES bit 8 must read 1 in this build"
    assert "ml_veto <= 1'b0; ml_inst <= 16'd1;" in CORE
    assert "rd = 32'h0113_0001" in CORE


def test_the_base_core_differs_only_where_marked() -> None:
    """Every line of the variant core that is not in the base core is a 113 line (or part of one), so the rule path stays the base design's."""
    base = {ln.strip() for ln in BASE.splitlines()}
    extra = [ln for ln in CORE.splitlines() if ln.strip() and ln.strip() not in base]
    unmarked = [ln for ln in extra if "113" not in ln and not any(k in ln for k in ("ml_", "ML_", "mlc_tx", "g_noml", "rm_gp_ml"))]
    assert not unmarked, unmarked[:5]

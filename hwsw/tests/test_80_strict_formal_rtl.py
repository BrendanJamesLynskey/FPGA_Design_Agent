"""Brief 80: SymbiYosys properties for the strict profile's rejections (hwsw/tests/regmap_formal.py: ``conformance``). The
harness holds an oracle written from the map's registers and settings; the block must answer as it says (SLVERR for an
unaligned address, an unmapped one, a strobe pattern covering part of a multi-byte field and a 1 in a reserved bit; OKAY
otherwise), change no software-writable output on a rejected write, and return 0 for an unaligned or unmapped read.
Bounded proof (depth 14 here, 20 in the committed run), the cover task (each rejection is reachable, so the proof is not
vacuous), and the same seeded strict-RTL faults the cocotb bench finds (hwsw/tests/test_64a_regmap_rtl.py STRICT_MUTANTS):
each must make the proof fail."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hwsw import regmap
from hwsw.tests import regmap_formal

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "hwsw" / "examples" / "demo_accel.yaml"
STRICT = ROOT / "hwsw" / "examples" / "profiles" / "spec_strict.yaml"
OUT = ROOT / "build" / "80" / "formal"
DEPTH = 14


def _strict_map() -> Path:
    """The demo map without its own `unmapped:` line, so the strict profile's setting (SLVERR for an unmapped address) applies:
    the same way the profile cost was measured (results/73_profiles/README.md)."""
    OUT.mkdir(parents=True, exist_ok=True)
    y = OUT / "demo_accel.yaml"
    y.write_text("".join(ln for ln in DEMO.read_text().splitlines(True) if not ln.startswith("unmapped:")))
    return y
pytestmark = pytest.mark.skipif(not shutil.which("sby"), reason="needs sby, yosys and z3 on PATH")


def test_strict_oracle_holds() -> None:
    assert regmap_formal.run(_strict_map(), OUT / "strict_bmc", "bmc", DEPTH, spec=STRICT) == "PASS"


def test_every_strict_rejection_is_reachable() -> None:
    assert regmap_formal.run(_strict_map(), OUT / "strict_cover", "cover", DEPTH, spec=STRICT) == "PASS"


def test_oracle_text_is_generated_from_the_settings() -> None:
    m = regmap.load(_strict_map(), STRICT)
    t = regmap_formal.conformance(m)
    for key in ("cover (w_unal);", "cover (!w_unal && w_hole);", "cover (!w_unal && w_part);", "cover (!w_unal && w_rsv && !w_part);"):
        assert key in t, key
    house = regmap_formal.conformance(regmap.load(_strict_map()))          # the house profile rejects none of these
    assert "cover (w_unal);" not in house and "cover (!w_unal && w_part);" not in house


FAULTS = [
    ("unaligned_write_accepted", "if (aw_lo != 2'b00) begin", "if (1'b0) begin"),
    ("unaligned_write_answers_okay", "wr_rej = 1'b1;\n            end else begin", "wr_rej = 1'b0;\n            end else begin"),
    ("unaligned_read_answers_okay", "s_axil_rresp <= rd_unal ? RESP_SLVERR : rd_hit ? RESP_OKAY : RESP_UNMAPPED_RD;",
     "s_axil_rresp <= rd_hit ? RESP_OKAY : RESP_UNMAPPED_RD;"),
    ("unaligned_read_returns_data", "s_axil_rdata <= rd_unal ? 32'h0 : rd_value;", "s_axil_rdata <= rd_value;"),
    ("partial_write_accepted", "wr_rej = ((w_strb & 4'b1100) != 4'b0000 && (w_strb & 4'b1100) != 4'b1100)",
     "wr_rej = (1'b0 && (w_strb & 4'b1100) != 4'b1100)"),
    ("rejected_write_still_applies", "wr_ctrl = !wr_rej;", "wr_ctrl = 1'b1;"),
    ("rejected_write_answers_okay", "!wr_hit ? RESP_UNMAPPED_WR : wr_rej ? RESP_SLVERR : RESP_OKAY;",
     "!wr_hit ? RESP_UNMAPPED_WR : RESP_OKAY;"),
    ("reserved_write_accepted", "32'hf000fe8e) != 32'h0)", "32'h00000000) != 32'h0)"),
    ("reserved_check_ignores_strobe", "(w_data & w_bits & 32'hf000fe8e)", "(w_data & 32'hf000fe8e)"),
]


@pytest.mark.parametrize("fid,old,new", FAULTS, ids=[f[0] for f in FAULTS])
def test_seeded_strict_fault_is_found(fid: str, old: str, new: str) -> None:
    good = regmap.emit_sv(regmap.load(_strict_map(), STRICT))
    assert good.count(old) == 1, old
    assert regmap_formal.run(_strict_map(), OUT / f"fault_{fid}", "bmc", DEPTH, sv_text=good.replace(old, new), spec=STRICT) == "FAIL"

"""ml_feat_pre against the 87 ml_feat in lockstep (tb/tb_feat_pre.sv), including messages that never reach their price
field, and the same bench on a mutant that commits state at the instrument field, which must fail."""
from __future__ import annotations

import subprocess
from pathlib import Path

D = Path(__file__).resolve().parents[1]
B87 = D.parent / "b87_ml_trading" / "rtl" / "ml_feat.sv"


def run(pre: Path, tmp: Path) -> str:
    subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "sim"), str(D / "tb" / "tb_feat_pre.sv"), str(pre), str(B87)], check=True,
                   capture_output=True)
    return subprocess.run(["vvp", "-n", str(tmp / "sim"), "+N=20000"], check=True, capture_output=True, text=True).stdout


def test_lockstep_with_the_87_unit(tmp_path) -> None:
    out = run(D / "rtl" / "ml_feat_pre.sv", tmp_path)
    assert "mismatches 0" in out and "partial 0" not in out, out


def test_a_mutant_that_commits_early_fails(tmp_path) -> None:
    src = (D / "rtl" / "ml_feat_pre.sv").read_text()
    assert "if (msg_px_v && pre_ok) begin" in src
    m = tmp_path / "mut.sv"
    m.write_text(src.replace("if (msg_px_v && pre_ok) begin", "if ((msg_px_v || inst_v) && pre_ok) begin"))
    out = run(m, tmp_path)
    assert "mismatches 0" not in out, out

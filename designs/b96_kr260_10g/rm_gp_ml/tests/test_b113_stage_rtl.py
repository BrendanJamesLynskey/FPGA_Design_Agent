"""Brief 113: rtl/ml_stage.sv (with gbt_comb) against the Python twin, in Icarus (tb/tb_ml_stage.sv), and mutants that must fail.

The twin's events (one observation per frame the rule path accepts, then the frame's end, good or bad) are replayed at realistic spacing; for every observation the feature vector, class and
agreement the fabric shows must equal the twin's, and the stage's counters must equal the twin's counts. Mutants of the stage (the state moves on a bad frame, the book is updated by a
TRADE with the wrong size, the veto counter counts in shadow mode) must be caught."""
from __future__ import annotations

import random
import subprocess
from pathlib import Path

import pytest

from designs.b58a_trigger.model import benchfeed as bf
from designs.b96_kr260_10g.rm_gp_ml.model import stream
from designs.b96_kr260_10g.rm_gp_ml.model.twin import Twin

D = Path(__file__).resolve().parents[1]
B87 = D.parent.parent / "b87_ml_trading" / "rtl" / "gen" / "gbt_comb.sv"
INST = stream.INST


def events(seed: int, veto: bool):
    """(stimulus lines, per-observation expectation, twin counts) for a mixed stream of good and bad frames and two instruments."""
    rng = random.Random(seed)
    msgs = stream.orderflow_msgs(250, seed) + stream.stress_msgs(120, seed + 1)
    tw = Twin(inst=INST, thr=stream.THR, veto_mode=veto)
    lines, exp = [], []
    for m in msgs:
        r = rng.random()
        good = r >= 0.08
        if 0.08 <= r < 0.2:
            m = bf.Msg(m.type, m.side, stream.OTHER_INST, m.price, m.size)
        o = tw.frame(m, good)
        arm = int(o.dec) if False else 1                 # a decision is wanted for every message the rule would act on; the stage counts it only for a tracked hit
        lines.append(f"1 {m.inst} {m.type} {m.side} {m.price} {m.size} {int(o.hit and o.trk)}")
        exp.append(o)
        lines.append(f"0 {rng.randint(3, 6)} 0 0 0 0 0")
        lines.append(f"2 {int(good)} 0 0 0 0 0")
        lines.append(f"0 {rng.randint(5, 30)} 0 0 0 0 0")
        del arm
    return lines, exp, tw.n


def run(tmp: Path, lines: list[str], src: Path | None = None, veto: bool = True) -> dict:
    (tmp / "stim.txt").write_text("\n".join(lines) + "\n")
    stage = src or (D / "rtl" / "ml_stage.sv")
    top = (D / "tb" / "tb_ml_stage.sv").read_text().replace("logic        en_veto = 1;", f"logic        en_veto = {int(veto)};")
    (tmp / "tb.sv").write_text(top)
    subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "sim"), str(D / "rtl" / "ml_pkg.sv"), str(B87), str(stage), str(tmp / "tb.sv")], check=True, capture_output=True, cwd=tmp)
    out = subprocess.run(["vvp", "-n", str(tmp / "sim")], check=True, capture_output=True, text=True, cwd=tmp).stdout
    res = {"obs": [], "mlv": {}}
    for ln in out.splitlines():
        t = ln.split()
        if t and t[0] == "OBS":
            res["obs"].append((int(t[1], 16), int(t[2]), t[3] == "1", t[4] == "1"))
        elif t and t[0] == "MLV":
            res["mlv"][int(t[1])] = int(t[2])
    return res


def check(res: dict, exp: list, n: dict, veto: bool) -> list[str]:
    bad = []
    if len(res["obs"]) != len(exp):
        return [f"{len(res['obs'])} observations, expected {len(exp)}"]
    for i, ((feat, cls, agree, ok), e) in enumerate(zip(res["obs"], exp)):
        if (feat, cls) != (e.feat, e.cls) or not ok or agree != (e.cls == 2):
            bad.append(f"obs {i}: got feat {feat:x} cls {cls} agree {agree} ok {ok}; want feat {e.feat:x} cls {e.cls}")
    want = {0: n["obs"], 1: n["cls"][0], 2: n["cls"][1], 3: n["cls"][2], 4: n["dec"], 5: n["veto"] if veto else 0, 6: 0 if veto else n["would"], 7: 0, 8: n["apply"], 9: n["drop"], 10: 0}
    for k, v in want.items():
        if res["mlv"].get(k) != v:
            bad.append(f"counter {k}: got {res['mlv'].get(k)}, want {v}")
    return bad


@pytest.mark.parametrize("veto", [True, False])
def test_stage_matches_the_twin(tmp_path, veto) -> None:
    lines, exp, n = events(4242, veto)
    res = run(tmp_path, lines, veto=veto)
    assert not check(res, exp, n, veto)


def late_case() -> list[str]:
    m = bf.Msg(bf.ADD, bf.BID, INST, 10000, 200)
    return [f"1 {INST} {m.type} {m.side} {m.price} {m.size} 0", "0 3 0 0 0 0 0", "2 1 0 0 0 0 0", "0 1 0 0 0 0 0",
            f"1 {INST} {m.type} {m.side} {m.price} {m.size} 1", "0 3 0 0 0 0 0", "2 1 0 0 0 0 0", "0 20 0 0 0 0 0"]


def late_ok(res: dict) -> bool:
    return res["obs"][1][3] is False and res["obs"][1][2] is False and res["mlv"][7] >= 1


def test_decision_inside_the_settling_window_is_counted_late(tmp_path) -> None:
    """An observation 2 clocks after a good frame's end sees a class that has not settled: n_late counts it and `agree` is 0 (the veto fails closed)."""
    res = run(tmp_path, late_case())
    assert late_ok(res), res["mlv"]


MUTANTS = {
    "state moves on a bad frame": ("assign apply = end_v && end_good && pv;", "assign apply = end_v && pv;"),
    "TRADE ignores the size": ("csz = (csz > psz) ? csz - psz : 32'd0;", "csz = csz;"),
    "shadow mode counts a veto": ("if (en_veto) n_veto <= n_veto + 32'd1; else n_would <= n_would + 32'd1;", "n_veto <= n_veto + 32'd1;"),
    "the class is not re-settled after an apply": ("settle <= 3'd3;\n            end\n            if (clr) begin", "end\n            if (clr) begin"),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_a_mutant_is_caught(tmp_path, name) -> None:
    old, new = MUTANTS[name]
    src = (D / "rtl" / "ml_stage.sv").read_text()
    assert old in src, name
    mut = tmp_path / "ml_stage_mut.sv"
    mut.write_text(src.replace(old, new, 1))
    if name.startswith("the class is not re-settled"):
        assert not late_ok(run(tmp_path, late_case(), src=mut)), f"mutant not caught: {name}"
        return
    veto = name != "shadow mode counts a veto"
    lines, exp, n = events(4242, veto)
    res = run(tmp_path, lines, src=mut, veto=veto)
    bad = check(res, exp, n, veto)
    if name == "shadow mode counts a veto":
        res2 = run(tmp_path, events(4242, False)[0], src=mut, veto=False)
        bad = check(res2, events(4242, False)[1], events(4242, False)[2], False)
    assert bad, f"mutant not caught: {name}"

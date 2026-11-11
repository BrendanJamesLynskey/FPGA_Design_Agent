"""Brief 24: the FSM coverage check (flow/fsm_coverage.py) and its V2 hook (flow/verif_gates.py --fsm-coverage): the parts that
need no simulator. The runs against real designs are in test_24_fsm_rtl.py."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from flow import fsm_coverage as fc
from flow import verif_gates

SV = """
module m;
  typedef enum logic [2:0] {S_IDLE, S_A, S_B = 5, S_C, S_D} st_t;   // 0 1 5 6 7
endmodule
"""


def make_design(tmp: Path, transitions, waive=None, reset="S_IDLE") -> Path:
    (tmp / "rtl").mkdir(parents=True)
    (tmp / "verif").mkdir()
    (tmp / "rtl" / "m.sv").write_text(SV)
    (tmp / "verif" / "fsm.yaml").write_text(yaml.safe_dump({"fsms": [{
        "name": "m", "signal": "tb.m.st", "file": "rtl/m.sv", "enum": "st_t", "reset_state": reset,
        "transitions": transitions, "waive": waive or []}]}))
    return tmp


def trace(tmp: Path, values: list[int], name="run.fsmtrace") -> Path:
    p = tmp / name
    p.write_text("".join(f"{i} {v} tb.m.st\n" for i, v in enumerate(values)))
    return p


FULL = [["S_IDLE", "S_A"], ["S_A", "S_B"], ["S_B", "S_C"], ["S_C", "S_D"], ["S_D", "S_IDLE"]]


def test_enum_values_follow_the_rtl() -> None:
    assert fc.parse_enum(SV, "st_t") == {"S_IDLE": 0, "S_A": 1, "S_B": 5, "S_C": 6, "S_D": 7}


def test_full_coverage_passes(tmp_path: Path) -> None:
    d = make_design(tmp_path / "d", FULL)
    rep = fc.evaluate(d, [trace(tmp_path, [0, 1, 5, 6, 7, 0])])
    assert rep["pass"] and rep["fsms"][0]["states_hit"] == 5 and rep["fsms"][0]["transitions_hit"] == 5


def test_a_state_never_visited_fails_and_is_named(tmp_path: Path) -> None:
    d = make_design(tmp_path / "d", FULL)
    rep = fc.evaluate(d, [trace(tmp_path, [0, 1, 5, 6])])
    f = rep["fsms"][0]
    assert not rep["pass"] and f["states_missed"] == ["S_D"]
    assert f["transitions_missed"] == ["S_C->S_D", "S_D->S_IDLE"]


def test_a_transition_missed_although_every_state_was_seen(tmp_path: Path) -> None:
    d = make_design(tmp_path / "d", FULL + [["S_B", "S_IDLE"]])
    rep = fc.evaluate(d, [trace(tmp_path, [0, 1, 5, 6, 7, 0])])
    f = rep["fsms"][0]
    assert f["states_missed"] == [] and f["transitions_missed"] == ["S_B->S_IDLE"] and not rep["pass"]


def test_a_transition_not_in_the_table_fails_but_a_reset_does_not(tmp_path: Path) -> None:
    d = make_design(tmp_path / "d", FULL)
    ok = fc.evaluate(d, [trace(tmp_path, [0, 1, 5, 0, 1, 5, 6, 7, 0])])       # S_B -> S_IDLE: a reset (reset_state)
    assert ok["pass"]
    bad = fc.evaluate(d, [trace(tmp_path, [0, 1, 5, 6, 7, 0, 1, 6, 7, 0, 1, 5, 6, 7, 0], "b.fsmtrace")])   # S_A -> S_C is not legal
    assert bad["fsms"][0]["unexpected_transitions"] == ["S_A->S_C"] and not bad["pass"]


def test_waivers_need_a_reason(tmp_path: Path) -> None:
    w = [{"item": "S_D", "reason": "needs a fault the model cannot inject"}, {"item": "S_C->S_D", "reason": "same"},
         {"item": "S_D->S_IDLE", "reason": "same"}]
    d = make_design(tmp_path / "d", FULL, waive=w)
    assert fc.evaluate(d, [trace(tmp_path, [0, 1, 5, 6])])["pass"]
    d2 = make_design(tmp_path / "e", FULL, waive=[{"item": "S_D", "reason": ""}])
    rep = fc.evaluate(d2, [trace(tmp_path, [0, 1, 5, 6, 7, 0], "c.fsmtrace")])
    assert rep["fsms"][0]["waivers_without_reason"] == ["S_D"] and not rep["pass"]


def test_several_runs_are_united_but_no_transition_crosses_two_files(tmp_path: Path) -> None:
    d = make_design(tmp_path / "d", FULL)
    a, b = trace(tmp_path, [0, 1, 5], "a.fsmtrace"), trace(tmp_path, [6, 7, 0], "b.fsmtrace")
    rep = fc.evaluate(d, [a, b])
    assert "S_B->S_C" in rep["fsms"][0]["transitions_missed"] and not rep["pass"]       # B then C straddles the files
    assert fc.evaluate(d, [a, trace(tmp_path, [5, 6, 7, 0], "c.fsmtrace")])["pass"]


def test_x_values_are_ignored_and_values_outside_the_enum_reported(tmp_path: Path) -> None:
    d = make_design(tmp_path / "d", FULL)
    p = tmp_path / "x.fsmtrace"
    p.write_text("0 x tb.m.st\n1 0 tb.m.st\n2 1 tb.m.st\n3 5 tb.m.st\n4 6 tb.m.st\n5 7 tb.m.st\n6 0 tb.m.st\n")
    assert fc.evaluate(d, [p])["pass"]
    q = trace(tmp_path, [0, 1, 5, 6, 7, 0, 3], "y.fsmtrace")
    assert fc.evaluate(d, [q])["fsms"][0]["values_outside_enum"] == [3]


def test_vcd_reader_gives_the_same_sequence(tmp_path: Path) -> None:
    vcd = tmp_path / "w.vcd"
    vcd.write_text("$scope module tb $end\n$scope module m $end\n$var reg 3 ! st [2:0] $end\n$upscope $end\n$upscope $end\n"
                   "$enddefinitions $end\n#0\nb000 !\n#10\nb001 !\n#20\nb101 !\n#30\nb110 !\n#40\nb111 !\n#50\nb000 !\n")
    d = make_design(tmp_path / "d", FULL)
    assert fc.evaluate(d, [vcd])["pass"]


def test_trace_module_names_every_register() -> None:
    d = Path(__file__).resolve().parents[2] / "designs" / "b2_qspi_jedec"
    src = fc.trace_module(d, Path("/tmp/x.fsmtrace"))
    assert "tb_qspi.u_regs.u_rdid.st" in src and "$fopen" in src


def test_vivado_log_table_is_parsed() -> None:
    log = Path(__file__).parent / "fixtures" / "fsm_discipline" / "golden" / "sep_base.log"
    got = fc.parse_vivado_log(log)
    (reg,) = got.values()
    assert reg["encoding"] == "sequential" and reg["states"][0] == "IDLE" and len(reg["states"]) == 11


def test_the_v2_check_reads_the_evidence(tmp_path: Path) -> None:
    good = {"fsms": [{"name": "m", "states_hit": 5, "n_states": 5, "transitions_hit": 5, "transitions_listed": 5, "pass": True,
                      "states_missed": [], "transitions_missed": [], "unexpected_transitions": [], "waivers_without_reason": []}]}
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(good))
    assert verif_gates.fsm_cov_check(p)["pass"]
    bad = json.loads(json.dumps(good))
    bad["fsms"][0].update({"pass": False}, states_hit=4, states_missed=["S_D"], transitions_missed=["S_C->S_D"])
    q = tmp_path / "bad.json"
    q.write_text(json.dumps(bad))
    c = verif_gates.fsm_cov_check(q)
    assert not c["pass"] and "S_D never visited" in c["why"] and "S_C->S_D never taken" in c["why"]
    assert not verif_gates.fsm_cov_check(tmp_path / "missing.json")["pass"]

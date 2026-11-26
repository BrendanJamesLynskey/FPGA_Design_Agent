"""Brief 213: first-failing-check digest, failure ledger, fresh-stimulus regrade. No model is called; the simulator (Icarus) runs the small fixture designs
in agent/tests/data/b213_counter (good, bad = a corner case the design's own bench misses, bad_always = a bug the bench catches)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agent.graph import feedback as fb
from agent.graph import repair
from flow import divergence, lockstep, model_record, regrade

DATA = Path(__file__).parent / "data" / "b213_counter"
needs_sim = pytest.mark.skipif(shutil.which("iverilog") is None, reason="Icarus not installed")


def run_local(argv, env, timeout):
    p = subprocess.run(argv, env={**os.environ, **env}, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


@pytest.fixture
def make(tmp_path, monkeypatch):
    monkeypatch.setenv("FDA_SIM_BUILD_ROOT", str(tmp_path / "simroot"))
    monkeypatch.delenv("FDA_MODEL_RECORD", raising=False)

    def _make(variant: str, record: bool = True) -> Path:
        d = tmp_path / variant
        shutil.copytree(DATA / variant, d, ignore=shutil.ignore_patterns("__pycache__"))
        (d / "build" / "verif").mkdir(parents=True)
        if record:      # the simulate tool's recording of the design's own bench (the R3 arm sets this variable)
            env = {**os.environ, "FDA_MODEL_RECORD": str(divergence.record_path(d)), "SIM": "icarus", "FDA_SIM_BUILD_ROOT": str(tmp_path / "simroot")}
            subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(d / "tests" / "test_rg_counter_rtl.py")],
                           env=env, capture_output=True, text=True, timeout=120)
        return d
    return _make


# --- recording --------------------------------------------------------------------------------------------------------------------------------

@needs_sim
def test_the_bench_calls_are_recorded(make):
    d = make("good")
    rec = [json.loads(x) for x in divergence.record_path(d).read_text().splitlines()]
    assert rec[0]["op"] == "new"
    steps = [r for r in rec if r["op"] == "step"]
    assert len(steps) >= 20 and steps[0]["in"] == {"en": 0, "load": 0, "d": 0} and set(steps[0]["out"]) == {"q", "wrap"}
    st = regrade.recording_stats(divergence.record_path(d))
    assert st["steps_with_inputs"] == len(steps) and regrade.applicable(st)[0]


def test_register_api_benches_are_not_applicable():
    st = {"segments": 1, "steps": 5000, "steps_with_inputs": 0, "register_calls": 900, "truncated": 0}
    ok, why = regrade.applicable(st)
    assert not ok and "read_reg/write_reg" in why
    assert not regrade.applicable({"segments": 0, "steps": 0, "steps_with_inputs": 0, "register_calls": 0, "truncated": 0})[0]


# --- item 1: the first failing check ---------------------------------------------------------------------------------------------------------

@needs_sim
def test_digest_on_a_known_bad_rtl(make):
    d = make("bad_always", record=False)
    snap = divergence.diagnose(d, run_local)
    assert snap and snap["test"] == "directed" and "q: rtl" in snap["message"]
    assert snap["site"]["file"] == "bench_rg_counter.py" and "assert" in snap["site"]["source"]
    txt = divergence.snapshot_digest(snap, sorted((d / "rtl").glob("*.sv")))
    assert "[first failing check]" in txt and "bench_rg_counter.py" in txt
    assert "q: RTL" in txt and "| model" in txt                           # the named signal, RTL values over the cycles and the model's value
    assert "drivers of q" in txt and "rg_counter.sv" in txt and "q + 8'h02" in txt     # the driver cone reaches the wrong statement
    assert "not a netlist" in txt and "unconfirmed" in txt                # says which walk, and that the model is not assumed right
    assert len(txt) < divergence.DIGEST_LIMIT + 800


def test_the_digest_replaces_the_raw_log_tail():
    ev = {"lint": {"ok": True}, "contract": {"ok": True}, "verif": {"reached": "V2"}, "verif_level": "V2",
          "simulate": {"ok": False, "text": "RAW LOG TAIL " * 50, "first_failure": {"test": "t", "message": ["AssertionError: q"], "where": None, "cause": [], "log_errors": [], "frames": []}}}
    owners, _ = repair.stage2_owners(ev)
    assert "RAW LOG TAIL" in owners["rtl"][0]
    ev["simulate"]["first_check"] = {"text": "[first failing check] DIGEST"}
    owners, _ = repair.stage2_owners(ev)
    assert "DIGEST" in owners["rtl"][0] and "RAW LOG TAIL" not in owners["rtl"][0]


def test_driver_cone_reads_inline_guards_and_case_labels(tmp_path):
    f = tmp_path / "m.sv"
    f.write_text("module m(input logic clk, input logic [3:0] a, output logic [7:0] y);\n  always_ff @(posedge clk) begin\n"
                 "    if (a == 4'h1) y <= 8'h11;\n    else begin\n      case (a)\n        4'h2: y <= 8'h22;\n        default: y <= 8'h00;\n      endcase\n    end\n"
                 "  end\nendmodule\n")
    cone = divergence.driver_cone([f], "y", values=(2,))
    assert cone[0]["text"].startswith("4'h2: y <= 8'h22") and "selected by" in cone[0]["note"]
    assert any("a" in c["reads"] for c in cone)


# --- item 2: the failure ledger --------------------------------------------------------------------------------------------------------------

def test_ledger_grows_and_shows_earlier_visits():
    ev = {"simulate": {"ok": False, "first_failure": {"test": "t", "message": ["AssertionError: q"]}}}
    led: list = []
    owners = {"rtl": ["x"]}
    for visit, (sig, changed) in enumerate([("rtl:sim:t:AssertionError: q", []), ("rtl:sim:t:AssertionError: q", ["rtl/a.sv"]), ("rtl:standards", ["rtl/a.sv", "rtl/b.sv"])], start=1):
        led.append(fb.ledger_entry(visit, sig, owners, ev, ["fail"], changed, {"site": {"file": "b.py", "line": 7}, "message": "q: rtl 1 model 2"} if visit < 3 else None))
        txt = fb.ledger_text(led)
        assert (txt == "") == (visit == 1)                                  # nothing before a second visit
        assert txt.count("- visit") == visit - 1                           # the newest failure is the visit's own reason, not repeated
        assert len(txt) < 5 * fb.ENTRY_CHARS + 200
    assert "first attempt" in txt and "changed rtl/a.sv" in txt and "(the same failure as now)" not in txt.split("visit 2")[1]
    assert "first failing check b.py:7" in txt
    led.append(fb.ledger_entry(4, "rtl:standards", owners, ev, ["fail"], ["rtl/b.sv"]))
    assert "visit 3" in fb.ledger_text(led) and "(the same failure as now)" in fb.ledger_text(led).split("visit 3")[1]
    wl = fb.with_ledger({"rtl": ["own reason"], "tests": ["t"]}, led)
    assert wl["rtl"][0] == "own reason" and "earlier visits" in wl["rtl"][1] and "earlier visits" in wl["tests"][1]
    assert fb.with_ledger({"rtl": ["r"]}, led[:1]) == {"rtl": ["r"]}


def test_fingerprint_names_the_files_a_repair_changed(tmp_path):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "a.sv").write_text("a")
    (tmp_path / "model.py").write_text("m")
    f1 = fb.fingerprint(tmp_path)
    (tmp_path / "rtl" / "a.sv").write_text("b")
    (tmp_path / "rtl" / "b.sv").write_text("n")
    assert fb.changed_files(f1, fb.fingerprint(tmp_path)) == ["rtl/a.sv", "rtl/b.sv"] and fb.changed_files(None, f1) == []


def test_stop_detail_carries_the_ledger():
    led = [{"visit": 1, "gates": ["design standards"], "roles": ["rtl"], "finding": "f", "sig": "rtl:standards", "changed_before": []}]
    why, detail = repair.stop_diagnosis(2, 4, {"sig": "rtl:standards", "repeat": 0, "owners": {"rtl": ["x"]}, "ledger": led})
    assert detail["ledger"] == led


# --- item 3: the fresh-stimulus regrade ------------------------------------------------------------------------------------------------------

@needs_sim
def test_regrade_passes_a_good_design_and_catches_the_seeded_corner_case(make):
    good, bad = make("good"), make("bad")
    # the seeded corner case (load and enable together with d = 0xF0) is invisible to the design's own bench ...
    for d in (good, bad):
        assert regrade.recording_stats(divergence.record_path(d))["steps"] >= 20
    rg_good = regrade.run_regrade(good, run_local, seed=5, fresh_cycles=2500, rtl_files=sorted((good / "rtl").glob("*.sv")))
    assert rg_good["status"] == "pass" and rg_good["seed"] == 5 and rg_good["calibration"]["agreed"] and rg_good["fresh"]["resets"] >= 3
    # ... and the regrade finds it, with the first-divergence digest
    rg_bad = regrade.run_regrade(bad, run_local, seed=5, fresh_cycles=2500, rtl_files=sorted((bad / "rtl").glob("*.sv")))
    assert rg_bad["status"] == "fail" and rg_bad["calibration"]["agreed"]
    assert "d=0xf0" in rg_bad["digest"] and "load=1" in rg_bad["digest"] and "en=1" in rg_bad["digest"]
    assert "q: model (expected) 0xF0" in rg_bad["digest"] and "8'hF0" in rg_bad["digest"]
    assert rg_bad["divergence"]["signals"][0]["signal"] == "q"
    # the same seed gives the same result
    assert regrade.run_regrade(bad, run_local, seed=5, fresh_cycles=2500)["divergence"] == rg_bad["divergence"]


@needs_sim
def test_regrade_reports_when_the_model_is_not_aligned_with_the_rtl(make):
    d = make("good")
    (d / "rtl" / "rg_counter.sv").write_text((d / "rtl" / "rg_counter.sv").read_text().replace("q <= d;", "q <= d + 8'h01;"))   # the bench would fail: record a passing run first
    rec = divergence.record_path(d)
    rg = regrade.run_regrade(d, run_local, seed=1, fresh_cycles=500)
    assert rg["status"] == "not_calibrated" and "cycle aligned" in rg["why"] and "calibration divergence" in rg["digest"]
    assert not regrade.blocks(rg, "V3") and rec.is_file()


def test_blocking_policy_and_statuses():
    assert not regrade.blocks({"status": "pass"}, "V3") and not regrade.blocks(None, "V2")
    old = dict(regrade.BLOCKS)
    try:
        regrade.BLOCKS["V3"] = True
        assert regrade.blocks({"status": "fail"}, "V3") and not regrade.blocks({"status": "fail"}, "V2")
        assert not regrade.blocks({"status": "not_calibrated"}, "V3") and not regrade.blocks({"status": "error"}, "V3")
    finally:
        regrade.BLOCKS.clear(); regrade.BLOCKS.update(old)


def test_regrade_failure_is_routed_to_the_rtl_role():
    ev = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True}, "verif": {"reached": "V2"}, "verif_level": "V2",
          "regrade": {"status": "fail", "blocking": True, "digest": "[fresh-stimulus regrade: first divergence] q differs"}}
    owners, sig = repair.stage2_owners(ev)
    assert "q differs" in owners["rtl"][0] and "rtl:regrade" in sig
    ev["regrade"]["blocking"] = False
    assert "regrade" not in repair.stage2_owners(ev)[1]


def test_the_model_wrapper_records_register_calls(tmp_path, monkeypatch):
    out = tmp_path / "rec.jsonl"
    monkeypatch.setenv("FDA_MODEL_RECORD", str(out))
    monkeypatch.setattr(model_record, "_state", {"lines": 0, "full": False, "seq": 0, "started": False, "design": None, "names": []})

    class M:
        def __init__(self, W=8): self.r = {}
        def reset(self): pass
        def step(self, inputs=None): return {"y": 1}
        def read_reg(self, a): return self.r.get(a, 0)
        def write_reg(self, a, v): self.r[a] = v
    mod = type(sys)("model")
    mod.Model = M
    model_record.wrap(mod)
    m = mod.Model(W=4)
    m.write_reg(2, 9); m.read_reg(2); m.step({"a": 1}); m.reset()
    ops = [json.loads(x) for x in out.read_text().splitlines()]
    assert [o["op"] for o in ops] == ["new", "wr", "rd", "step", "reset"] and ops[0]["params"] == {"W": 4} and ops[2]["val"] == 9
    assert lockstep.harvest_pool(lockstep.read_record(out)) == {"a": [1]}

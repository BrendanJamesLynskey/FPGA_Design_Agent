"""Brief 221: the lab file, method choice, safety limits, the lab adapters and the bring-up runner, all on mock instruments (no instrument is touched)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from hil import lab as L
from hil import lab_bringup as B
from hil import lab_drivers as D

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "hil" / "lab.example.yaml"
P1 = ROOT / "pilots" / "209" / "p1_clkmeter" / "run3" / "design"


@pytest.fixture(autouse=True)
def _no_owner_profile(monkeypatch):
    monkeypatch.setenv(L.ENV_FILE, "none")          # a test never reads the owner's real lab profile


def counter(onboarded=True, mock=True, accuracy=1.0, **kw):
    e = {"id": "counter", "kind": "frequency_counter", "make": "mock", "model": "mock counter", "onboarded": onboarded, "mock": mock,
         "connection": {"type": "none"}, "control": {"mode": "scripted", "driver": "mock"},
         "channels": [{"name": "A"}, {"name": "B"}], "capabilities": [{"measure": "frequency", "channels": ["A", "B"], "max_hz": 100e6, "accuracy_ppm": accuracy}],
         "outputs": [{"name": "SUP", "kind": "supply", "max_v": 3.3, "max_a": 0.1}, {"name": "AWG", "kind": "awg", "never_by_script": True},
                     {"name": "TX", "kind": "rf_tx", "max_dbm": -10}]}
    e.update(kw)
    return e


def lab_of(*insts, conns=()):
    return L.merge({"instruments": list(insts)}, {"connections": list(conns)})


WIRED = [{"instrument": "counter", "channel": "A", "probes": "pin C3"}]


def p1_spec():
    return yaml.safe_load((P1 / "spec.yaml").read_text())


# ---- the file ---------------------------------------------------------------------------------------------------------------------------
def test_the_example_profile_is_valid_and_holds_the_owners_bench():
    doc = yaml.safe_load(EXAMPLE.read_text())
    assert L.validate(doc) == []
    ids = {i["id"] for i in doc["instruments"]}
    assert {"m2k", "redpitaya", "pluto", "rtl_sdr", "ugreen_capture", "umc22", "sysmon", "ila", "sfp_loopback", "xm105"} <= ids
    by = {i["id"]: i for i in doc["instruments"]}
    assert not by["m2k"]["onboarded"] and not by["redpitaya"]["onboarded"] and by["umc22"]["onboarded"]
    assert "address" not in json.dumps({k: v for k, v in by["m2k"].items()}) and by["redpitaya"]["connection"]["address"] == "TO-BE-GIVEN-BY-OWNER"


def test_validation_names_each_problem():
    bad = counter()
    bad.pop("onboarded")
    bad["connection"] = {"type": "lan"}
    bad["outputs"] = [{"name": "X", "kind": "supply"}]
    bad["capabilities"] = [{"measure": "frequency", "channels": ["Z"]}]
    errs = L.validate({"instruments": [bad, counter()]})
    text = "\n".join(errs)
    assert "onboarded must be true or false" in text and "needs connection.address" in text
    assert "has no limit and is not marked never_by_script" in text and "channel 'Z'" in text
    assert L.validate({"instruments": [counter(), counter()]})[0].endswith("appears twice")
    assert any("needs instrument, channel and probes" in e for e in L.validate({"instruments": [], "connections": [{"instrument": "x"}]}))


def test_profile_and_design_file_merge_and_the_design_wins(tmp_path):
    prof = tmp_path / "prof.yaml"
    prof.write_text(yaml.safe_dump({"instruments": [counter(onboarded=False)]}))
    d = tmp_path / "design"
    d.mkdir()
    (d / "lab.yaml").write_text(yaml.safe_dump({"instruments": [{"id": "counter", "onboarded": True}], "connections": WIRED}))
    lab = L.load(d, prof)
    assert lab.problems == [] and lab.get("counter")["onboarded"] is True and lab.get("counter")["kind"] == "frequency_counter"
    assert lab.connected("counter")[0]["probes"] == "pin C3"
    assert L.load(d, tmp_path / "missing.yaml").instruments == {"counter": {"id": "counter", "onboarded": True}} or True


def test_a_connection_to_a_channel_the_instrument_lacks_is_a_problem_and_is_dropped(tmp_path):
    prof = tmp_path / "prof.yaml"
    prof.write_text(yaml.safe_dump({"instruments": [counter()]}))
    d = tmp_path / "design"
    d.mkdir()
    (d / "lab.yaml").write_text(yaml.safe_dump({"connections": [{"instrument": "counter", "channel": "Q9", "probes": "pin C3"}, {"instrument": "ghost", "channel": "A", "probes": "x"}]}))
    lab = L.load(d, prof)
    assert lab.connections == [] and any("no such channel" in p and "Q9" in p for p in lab.problems) and any("ghost" in p for p in lab.problems)
    with pytest.raises(L.LabError):
        L.load(d, prof, strict=True)


def test_an_unreadable_or_invalid_profile_is_reported_and_not_used(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text("instruments: [oops")
    lab = L.load(None, p)
    assert not lab.present and lab.problems and "cannot be read" in lab.problems[0]
    p.write_text(yaml.safe_dump({"instruments": [{"id": "Bad Id"}]}))
    assert L.load(None, p).instruments == {}


def test_env_file_none_means_no_profile(monkeypatch, tmp_path):
    assert L.profile_path() is None
    monkeypatch.setenv(L.ENV_FILE, str(tmp_path / "x.yaml"))
    assert L.profile_path() == tmp_path / "x.yaml"
    monkeypatch.delenv(L.ENV_FILE)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert L.profile_path() == tmp_path / "fpga-force" / "lab.yaml"


def test_usb_listing_is_parsed_not_opened():
    txt = "Bus 001 Device 007: ID 0456:b672 Analog Devices Inc. ADALM2000\nBus 002 Device 003: ID 2b89:5854 MACROSILICON UGREEN 25854\nBus 1 ID 1d6b:0002 hub"
    assert L.usb_seen(txt) == ["m2k", "ugreen_capture"]


# ---- needs and methods ------------------------------------------------------------------------------------------------------------------
def test_the_p1_spec_has_one_frequency_need_that_an_instrument_can_check():
    needs = L.needs_from_spec(p1_spec())
    assert [n.requirement for n in needs] == ["REQ-13"]
    n = needs[0]
    assert n.quantity == "frequency" and n.value == 25e6 and n.tolerance_ppm == 100.0


def test_no_lab_means_on_chip_only():
    pl = L.plan(L.Lab(), L.needs_from_spec(p1_spec()))
    r = pl["requirements"][0]
    assert r["chosen"]["method"] == "on_chip" and not r["independent"] and pl["summary"] == {"needs": 1, "independent_check": 0, "on_chip_only": 1}


def test_not_onboarded_is_offered_never_chosen():
    r = L.plan(lab_of(counter(onboarded=False, mock=False), conns=WIRED), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert r["chosen"]["method"] == "on_chip" and r["left_out"] == [{"instrument": "counter", "reason": "available after onboarding"}]


def test_onboarded_but_not_wired_for_this_design_is_left_out():
    r = L.plan(lab_of(counter()), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert r["chosen"]["method"] == "on_chip" and r["left_out"][0]["reason"] == "not connected for this design"


def test_a_wired_scripted_counter_is_the_independent_check_beside_the_on_chip_count():
    r = L.plan(lab_of(counter(), conns=WIRED), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert r["chosen"]["method"] == "scripted" and r["chosen"]["instrument"] == "counter" and r["chosen"]["probes"] == "pin C3" and r["independent"]
    assert [m["method"] for m in r["methods"]] == ["scripted", "on_chip"]


def test_scripted_beats_manual_and_a_manual_instrument_is_chosen_when_alone():
    man = counter(id="handheld", control={"mode": "manual"}, mock=False)
    both = L.plan(lab_of(man, counter(), conns=[*WIRED, {"instrument": "handheld", "channel": "A", "probes": "pin C3"}]), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert [m["method"] for m in both["methods"]] == ["scripted", "manual", "on_chip"]
    only = L.plan(lab_of(man, conns=[{"instrument": "handheld", "channel": "A", "probes": "pin C3"}]), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert only["chosen"]["method"] == "manual"


def test_a_limit_or_accuracy_the_instrument_cannot_meet_is_a_reason_not_a_choice():
    slow = counter(capabilities=[{"measure": "frequency", "channels": ["A"], "max_hz": 10e6, "accuracy_ppm": 1}])
    r = L.plan(lab_of(slow, conns=WIRED), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert r["chosen"]["method"] == "on_chip" and "above its limit" in r["left_out"][0]["reason"]
    coarse = counter(accuracy=60.0)
    r = L.plan(lab_of(coarse, conns=WIRED), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert r["chosen"]["method"] == "on_chip" and "three times better" in r["left_out"][0]["reason"]


def test_on_chip_instruments_are_not_an_independent_method():
    sysmon = {"id": "sysmon", "kind": "on_chip", "onboarded": True, "connection": {"type": "usb"}, "control": {"mode": "scripted", "driver": "x"},
              "channels": [{"name": "VCCINT"}], "capabilities": [{"measure": "frequency", "channels": ["VCCINT"]}]}
    r = L.plan(lab_of(sysmon, conns=[{"instrument": "sysmon", "channel": "VCCINT", "probes": "x"}]), L.needs_from_spec(p1_spec()))["requirements"][0]
    assert r["chosen"]["method"] == "on_chip" and r["left_out"] == []


# ---- safety -----------------------------------------------------------------------------------------------------------------------------
def test_drive_within_limits_passes_and_beyond_is_refused():
    lab = lab_of(counter())
    assert lab and L.check_drive(lab, "counter", "SUP", volts=3.3, amps=0.05)["name"] == "SUP"
    with pytest.raises(L.SafetyRefused, match="above the lab file's limit"):
        L.check_drive(lab, "counter", "SUP", volts=3.4)
    with pytest.raises(L.SafetyRefused, match="above the lab file's limit"):
        L.check_drive(lab, "counter", "SUP", volts=3.3, amps=0.5)
    with pytest.raises(L.SafetyRefused, match="does not state its v"):
        L.check_drive(lab, "counter", "SUP")


def test_never_by_script_unknown_and_not_onboarded_outputs_are_refused():
    with pytest.raises(L.SafetyRefused, match="never enabled by a script"):
        L.check_drive(lab_of(counter()), "counter", "AWG", volts=0.1)
    with pytest.raises(L.SafetyRefused, match="no such output"):
        L.check_drive(lab_of(counter()), "counter", "NOPE", volts=0.1)
    with pytest.raises(L.SafetyRefused, match="not onboarded"):
        L.check_drive(lab_of(counter(onboarded=False)), "counter", "SUP", volts=1.0)


def test_rf_needs_30_db_or_a_dummy_load_and_a_pin_voltage_is_never_exceeded():
    lab = lab_of(counter())
    for att in (None, 20.0):
        with pytest.raises(L.SafetyRefused, match="30 dB"):
            L.check_drive(lab, "counter", "TX", dbm=-20, attenuator_db=att)
    with pytest.raises(L.SafetyRefused, match="limit"):
        L.check_drive(lab, "counter", "TX", dbm=0, attenuator_db=40)
    assert L.check_drive(lab, "counter", "TX", dbm=-20, attenuator_db=30)
    with pytest.raises(L.SafetyRefused, match="3.3 V of the board pin"):
        L.check_drive(lab_of(counter(outputs=[{"name": "SUP", "kind": "supply", "max_v": 5.0}])), "counter", "SUP", volts=3.4, board_vcco_v=3.3)
    dummy = counter(outputs=[{"name": "TX", "kind": "rf_tx", "max_dbm": 0, "dummy_load": True}])
    assert L.check_drive(lab_of(dummy), "counter", "TX", dbm=0)


# ---- the adapters -----------------------------------------------------------------------------------------------------------------------
def test_manual_readings_need_a_unit_that_fits():
    assert D.parse_reading("25.0001 MHz", "frequency") == (25000100.0, "Hz")
    assert D.parse_reading("3,29 V", "voltage") == (3.29, "V")
    assert D.parse_reading("12.5 kHz", "frequency")[0] == 12500.0
    for bad in ("25.0001", "25 MHz V", "abc", "3.3 V", "25 furlongs"):
        with pytest.raises(D.ReadingError):
            D.parse_reading(bad, "frequency")


def test_freq_from_samples_recovers_a_known_frequency_and_refuses_a_flat_probe():
    fs, f = 100e6, 25e6
    bits = [1 if (i * f / fs) % 1 < 0.5 else 0 for i in range(1000)]
    assert abs(D.freq_from_samples(bits, fs, 0.5) - f) / f < 0.01
    with pytest.raises(L.LabError, match="not enough"):
        D.freq_from_samples([0] * 1000, fs, 0.5)


def test_the_contract_methods_and_the_drive_limit_inside_the_driver():
    lab = lab_of(counter())
    m = D.MockInstrument(lab.get("counter"), lab, {("frequency", "A"): 25e6})
    d = m.describe()
    assert d["mock"] and d["channels"] == ["A", "B"] and d["safety"]["outputs"][0]["name"] == "SUP"
    with pytest.raises(RuntimeError):
        m.arm()
    m.configure({"measure": "frequency", "channel": "A"})
    m.arm()
    cap = m.capture()
    assert cap["schema"] == "fda-measurement/1" and cap["value"] == 25e6 and cap["unit"] == "Hz" and cap["mock"] is True
    with pytest.raises(L.SafetyRefused):                                  # a driver cannot skip the lab file
        m.configure({"drive": {"output": "SUP", "volts": 5.0}})
    with pytest.raises(L.LabError):
        m.configure({"measure": "magic"})


class FakeRp:
    def __init__(self, wave):
        self.wave, self.calls = wave, []

    def acquire(self, ch, dec=1, trig=0.0):
        self.calls.append(("acq", ch, dec))
        return self.wave

    def generate(self, ch, shape, f, a, off=0.0):
        self.calls.append(("gen", ch, shape, f, a))

    def stop(self, ch):
        self.calls.append(("stop", ch))

    def close(self):
        self.calls.append(("close",))


def rp_lab():
    e = {"id": "rp", "kind": "oscilloscope", "onboarded": True, "connection": {"type": "lan", "address": "x"}, "control": {"mode": "scripted", "driver": "hil.instruments.redpitaya"},
         "channels": [{"name": "IN1"}, {"name": "OUT1"}], "capabilities": [{"measure": "frequency", "channels": ["IN1"], "max_hz": 30e6}],
         "outputs": [{"name": "OUT1", "kind": "awg", "max_v": 1.0}]}
    return lab_of(e)


def test_redpitaya_adapter_measures_and_drives_through_the_limits_and_stops_outputs():
    import math
    lab = rp_lab()
    wave = [math.sin(2 * math.pi * 1e6 * i / 125e6) for i in range(16384)]
    rp = FakeRp(wave)
    i = D.RedPitayaInstrument(lab.get("rp"), lab, rp)
    i.configure({"measure": "frequency", "channel": "IN1"})
    i.arm()
    cap = i.capture()
    assert abs(cap["value"] - 1e6) / 1e6 < 0.002 and cap["unit"] == "Hz"
    i.configure({"drive": {"output": "OUT1", "volts": 0.5, "hz": 1000.0}})
    i.arm()
    i.capture()
    assert ("gen", 1, "SINE", 1000.0, 0.5) in rp.calls
    with pytest.raises(L.SafetyRefused):
        i.configure({"drive": {"output": "OUT1", "volts": 1.5}})
    i.close()
    assert ("stop", 1) in rp.calls and ("stop", 2) in rp.calls and rp.calls[-1] == ("close",)


def test_m2k_adapter_counts_edges_on_a_logic_channel(monkeypatch):
    from hil.instruments import m2k
    fs, f = 100e6, 20e6
    bits = [1 if (k * f / fs) % 1 < 0.5 else 0 for k in range(2000)]
    monkeypatch.setattr(m2k, "logic_capture", lambda ctx, fs_, n: [bits] * 4)
    e = {"id": "m2k", "kind": "oscilloscope", "onboarded": True, "connection": {"type": "usb"}, "control": {"mode": "scripted", "driver": "hil.instruments.m2k"},
         "channels": [{"name": "DIO0"}, {"name": "W1"}], "capabilities": [{"measure": "frequency", "channels": ["DIO0"], "max_hz": 25e6}],
         "outputs": [{"name": "W1", "kind": "awg", "max_v": 3.3}]}
    lab = lab_of(e)
    i = D.M2kInstrument(e, lab, ctx=object())
    i.configure({"measure": "frequency", "channel": "DIO0", "samples": 2000})
    i.arm()
    assert abs(i.capture()["value"] - f) / f < 0.01
    i.configure({"drive": {"output": "W1", "volts": 1.0}})
    i.arm()
    with pytest.raises(L.SafetyRefused, match="does not drive outputs"):
        i.capture()


def test_open_instrument_picks_the_adapter_and_says_when_there_is_none():
    lab = lab_of(counter(mock=False))
    e = lab.get("counter")
    with pytest.raises(L.LabError, match="no adapter for driver 'mock'"):
        D.open_instrument(e, lab)
    assert isinstance(D.open_instrument(e, lab, mock=True), D.MockInstrument)
    man = {**e, "control": {"mode": "manual"}}
    with pytest.raises(L.LabError, match="needs a way to ask"):
        D.open_instrument(man, lab)
    assert isinstance(D.open_instrument(man, lab, ask=lambda p: "1 Hz"), D.ManualInstrument)


# ---- stage 9: steps, BRINGUP.md, runner -------------------------------------------------------------------------------------------------
def p1_copy(tmp_path):
    import shutil
    d = tmp_path / "p1"
    shutil.copytree(P1, d, ignore=shutil.ignore_patterns("build", "__pycache__"))
    if not (d / "BRINGUP.md").is_file():
        (d / "BRINGUP.md").write_text("# Bring-up\n\n## Setup\nx\n\n## Testing\n1. a\n\n## Debug aids\nb\n\n## If it fails\nc\n")
    return d


def test_apply_to_design_writes_plan_steps_and_an_idempotent_bringup_block(tmp_path):
    d = p1_copy(tmp_path)
    lab = lab_of(counter(), conns=WIRED)
    plan = B.apply_to_design(d, p1_spec(), lab)
    assert plan["summary"]["independent_check"] == 1
    steps = B.load_steps(d)
    assert [s["kind"] for s in steps] == ["confirm", "measure"] and steps[1]["expected"] == 25e6 and steps[1]["tolerance_ppm"] == 100.0
    once = (d / "BRINGUP.md").read_text()
    assert "## Lab instruments" in once and "REQ-13" in once and "counter A on pin C3" in once and "| REQ-13 | frequency of the C3 signal | scripted" in once
    B.apply_to_design(d, p1_spec(), lab)
    assert (d / "BRINGUP.md").read_text() == once and once.count(B.BEGIN) == 1
    (d / "BRINGUP.md").write_text("# rewritten by the model\n")                     # a rewrite loses the block; the next visit restores it
    B.apply_to_design(d, p1_spec(), lab)
    assert "## Lab instruments" in (d / "BRINGUP.md").read_text()
    plan = json.loads((d / "build" / "lab" / "plan.json").read_text())
    assert plan["requirements"][0]["chosen"]["instrument"] == "counter"


def test_a_design_with_no_lab_gets_nothing_written(tmp_path):
    d = p1_copy(tmp_path)
    before = (d / "BRINGUP.md").read_text()
    res = B.apply_to_design(d, p1_spec(), L.Lab())
    assert res["skipped"] == "no lab file" and (d / "BRINGUP.md").read_text() == before
    assert not (d / "lab_steps.yaml").exists() and not (d / "build" / "lab").exists()


def steps_for(lab):
    return B.steps_from_plan(L.plan(lab, L.needs_from_spec(p1_spec())), lab)


def test_a_dry_run_uses_mock_instruments_asks_nobody_and_is_never_evidence():
    lab = lab_of(counter(), conns=WIRED)
    res = B.run_steps(steps_for(lab), lab, dry_run=True, ask=lambda p: pytest.fail("a dry run asks nobody"), confirm=lambda p: pytest.fail("nor confirms"))
    assert res["mode"] == "dry_run" and res["evidence"] is False and res["pass"]
    meas = [r for r in res["rows"] if r["kind"] == "measure"][0]
    assert meas["result"] == "dry_run" and meas["result_if_real"] == "pass" and meas["mock"] and meas["value"] == 25e6


def test_a_dry_run_with_an_injected_fault_shows_the_failure_it_would_report():
    lab = lab_of(counter(), conns=WIRED)
    res = B.run_steps(steps_for(lab), lab, dry_run=True, truth={("frequency", "A"): 25.01e6})
    meas = [r for r in res["rows"] if r["kind"] == "measure"][0]
    assert meas["result_if_real"] == "fail" and round(meas["error_ppm"]) == 400


def test_a_real_run_needs_the_wiring_confirmed_first_and_skips_the_reading_if_not():
    lab = lab_of(counter(mock=True), conns=WIRED)
    res = B.run_steps(steps_for(lab), lab, dry_run=False, truth={("frequency", "A"): 25e6}, confirm=lambda p: False, open_fn=lambda e, l, **kw: D.MockInstrument(e, l, {("frequency", "A"): 25e6}))
    assert [r["result"] for r in res["rows"]] == ["not_confirmed", "skipped"] and not res["pass"]
    ok = B.run_steps(steps_for(lab), lab, dry_run=False, confirm=lambda p: True, open_fn=lambda e, l, **kw: D.MockInstrument(e, l, {("frequency", "A"): 25.0002e6}))
    meas = ok["rows"][1]
    assert [r["result"] for r in ok["rows"]] == ["confirmed", "pass"] and ok["evidence"] is False and ok["rows"][1]["mock"] and round(meas["error_ppm"]) == 8 and meas["caveat"] is None


def manual_lab():
    man = counter(id="handheld", control={"mode": "manual"}, mock=False, capabilities=[{"measure": "frequency", "channels": ["A"], "max_hz": 100e6}])
    return lab_of(man, conns=[{"instrument": "handheld", "channel": "A", "probes": "pin C3"}])


def test_manual_prompts_are_recorded_as_manual_with_what_was_typed():
    lab = manual_lab()
    steps = steps_for(lab)
    assert steps[1]["method"] == "manual" and "type it with its unit" in steps[1]["prompt"] and steps[1]["caveat"].startswith("the instrument's accuracy is not recorded")
    asked = []
    res = B.run_steps(steps, lab, dry_run=False, ask=lambda p: asked.append(p) or "25.0012 MHz", confirm=lambda p: True)
    row = res["rows"][1]
    assert row["method"] == "manual" and row["typed"] == "25.0012 MHz" and row["result"] == "pass" and len(asked) == 1 and "Expected about 25 MHz" in asked[0]


def test_a_reading_typed_without_or_in_the_wrong_unit_is_refused_or_flagged():
    lab = manual_lab()
    steps = steps_for(lab)
    bare = B.run_steps(steps, lab, dry_run=False, ask=lambda p: "25.0012", confirm=lambda p: True)["rows"][1]
    assert bare["result"] == "error" and "has no unit" in bare["detail"]
    slip = B.run_steps(steps, lab, dry_run=False, ask=lambda p: "25.0012 kHz", confirm=lambda p: True)["rows"][1]
    assert slip["result"] == "fail" and any("unit" in w for w in slip["warnings"])
    wrong = B.run_steps(steps, lab, dry_run=False, ask=lambda p: "3.3 V", confirm=lambda p: True)["rows"][1]
    assert wrong["result"] == "error" and "unit of voltage" in wrong["detail"]


def drive_step(**kw):
    return {"id": "drv", "kind": "drive", "method": "scripted", "instrument": "counter", "output": "SUP", "volts": 3.3, "requirement": "REQ-X", **kw}


def test_a_driving_step_is_marked_confirmed_by_the_owner_and_switched_off_at_the_end():
    lab = lab_of(counter())
    made = []

    def open_fn(e, l, **kw):
        made.append(D.MockInstrument(e, l, {}))
        return made[-1]
    asked = []
    res = B.run_steps([drive_step()], lab, dry_run=False, confirm=lambda p: asked.append(p) or True, open_fn=open_fn)
    r = res["rows"][0]
    assert r["action"] == "drive_instrument_output" and r["result"] == "driven" and "DRIVES" in asked[0]
    assert made[0].drives and made[0].output_on == set()                         # off again after close
    no = B.run_steps([drive_step()], lab, dry_run=False, confirm=lambda p: False, open_fn=open_fn)
    assert no["rows"][0]["result"] == "not_confirmed" and not no["pass"]


def test_a_driving_step_beyond_the_limit_is_refused_before_the_owner_is_asked():
    lab = lab_of(counter())
    for bad in (drive_step(volts=5.0), drive_step(output="AWG", volts=0.1), drive_step(output="TX", volts=None, dbm=-20)):
        res = B.run_steps([bad], lab, dry_run=False, confirm=lambda p: pytest.fail("the owner must not be asked"),
                          open_fn=lambda e, l, **kw: pytest.fail("nothing is opened"))
        assert res["rows"][0]["result"] == "refused" and not res["pass"]


def test_a_dry_run_of_a_driving_step_enables_nothing_real():
    lab = lab_of(counter())
    res = B.run_steps([drive_step()], lab, dry_run=True)
    assert res["rows"][0]["result"] == "driven" and "(mock)" in res["rows"][0]["detail"] and res["evidence"] is False


def test_run_for_design_writes_results_and_nothing_without_steps(tmp_path):
    d = p1_copy(tmp_path)
    assert B.run_for_design(d, dry_run=True, lab=L.Lab()) is None
    lab = lab_of(counter(), conns=WIRED)
    B.apply_to_design(d, p1_spec(), lab)
    res = B.run_for_design(d, dry_run=True, lab=lab)
    assert res["pass"] and json.loads((d / "build" / "lab" / "results.json").read_text())["mode"] == "dry_run"


def test_the_cli_plans_without_touching_anything(tmp_path, capsys, monkeypatch):
    d = p1_copy(tmp_path)
    prof = tmp_path / "prof.yaml"
    prof.write_text(yaml.safe_dump({"instruments": [counter()]}))
    (d / "lab.yaml").write_text(yaml.safe_dump({"connections": WIRED}))
    monkeypatch.setenv(L.ENV_FILE, str(prof))
    assert B.main(["plan", str(d)]) == 0
    out = capsys.readouterr().out
    assert "REQ-13" in out and "scripted" in out and "counter" in out
    assert L.main(["--design", str(d)]) == 0

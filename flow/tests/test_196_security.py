"""Brief 196: the production_secure request and check (flow/security.py), tested on synthetic builds and on the records of the real ones.
No Vivado here: the dump files are written by hand in the format flow/security.tcl writes, and results/b196 holds the real ones."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import security as S  # noqa: E402


# ---- the request ---------------------------------------------------------------------------------------------------------------------------

def test_no_request_is_no_security():
    r = S.resolve({}, env={})
    assert r["source"] == "none" and not any(r["switches"].values())


def test_build_yaml_request_defaults_every_subswitch_on():
    r = S.resolve({"security": {"production_secure": True}}, env={})
    assert r["source"] == "build.yaml" and all(r["switches"].values())
    r = S.resolve({"security": {"production_secure": True, "strip_debug": False}}, env={})
    assert r["switches"]["strip_debug"] is False and r["switches"]["encrypt"] is True
    assert not any(S.resolve({"security": {"production_secure": False}}, env={})["switches"].values())


def test_a_misspelt_key_is_refused_not_ignored():
    with pytest.raises(S.SecurityError, match="unknown security keys"):
        S.resolve({"security": {"production_secure": True, "encrpyt": True}}, env={})
    with pytest.raises(S.SecurityError, match="waiver"):
        S.resolve({"security": {"production_secure": True, "waive": [{"rule": "bscan", "reason": "needed"}]}}, env={})


def test_the_pin_beats_build_yaml_and_the_disagreement_is_recorded():
    pin = json.dumps({"production_secure": True})
    r = S.resolve({"security": {"production_secure": False}}, env={S.ENV: pin})
    assert r["source"] == "pin" and r["switches"]["encrypt"] is True and r["policy_conflict"]
    off = json.dumps({"production_secure": False})
    r = S.resolve({"security": {"production_secure": True}}, env={S.ENV: off})
    assert not any(r["switches"].values()) and r["policy_conflict"]                       # the model cannot turn it on against the user
    assert S.resolve({"security": {"production_secure": True}}, env={S.ENV: json.dumps({"production_secure": True})})["policy_conflict"] == []


def test_prepare_writes_the_request_into_inputs_tcl_only_when_there_is_one(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "flow"))
    import prepare
    cfg = {"part": "xck26-sfvc784-2LV-c"}
    monkeypatch.delenv(S.ENV, raising=False)
    assert prepare.security_tcl(cfg, cfg["part"], tmp_path) == []                             # an ordinary build is unchanged
    monkeypatch.setenv(S.ENV, json.dumps({"production_secure": False}))
    assert prepare.security_tcl(cfg, cfg["part"], tmp_path) == []                             # the pin says off and nothing disagrees
    monkeypatch.setenv(S.ENV, json.dumps({"production_secure": True}))
    lines = prepare.security_tcl(cfg, cfg["part"], tmp_path)
    assert lines[0] == "set security_on 1" and "BITSTREAM.READBACK.SECURITY" in lines[1]
    assert json.loads((tmp_path / "security_request.json").read_text())["switches"]["strip_debug"] is True
    with pytest.raises(SystemExit, match="measured on UltraScale"):
        prepare.security_tcl({"part": "xc7a100tcsg324-1"}, "xc7a100tcsg324-1", tmp_path)


# ---- the SYSMON thresholds ----------------------------------------------------------------------------------------------------------------

def test_the_codes_round_trip_inside_the_limits():
    lim = S.limits_of("kr260")
    init = S.sysmon_init(lim)
    assert S.code_to_temp(init["INIT_50"] >> 6) >= lim["tj_alarm_c"] and S.code_to_temp((init["INIT_50"] >> 6) - 1) < lim["tj_alarm_c"]
    for up, lo, key in (("INIT_51", "INIT_55", "vccint_v"), ("INIT_52", "INIT_56", "vccaux_v"), ("INIT_58", "INIT_5C", "vccbram_v")):
        vmin, vmax = lim[key]
        assert S.code_to_volt(init[up] >> 6) >= vmax and S.code_to_volt((init[up] >> 6) - 1) < vmax      # upper rounded up, never below the limit
        assert S.code_to_volt(init[lo] >> 6) <= vmin and S.code_to_volt((init[lo] >> 6) + 1) > vmin      # lower rounded down
    assert all(0 <= v <= 0xFFFF for v in init.values()) and (init["INIT_41"] >> 12) == 0b0010           # continuous sequence: alarms are live
    assert "INIT_53" not in init                                                                          # no user OT limit (it would enable the auto shutdown)


def test_the_generated_package_is_in_the_design():
    f = ROOT / "designs" / "b196_secure_demo" / "rtl" / "b196_sysmon_pkg.sv"
    assert f.read_text() == S.sysmon_header("kr260")


# ---- the check on synthetic dumps -----------------------------------------------------------------------------------------------------------

def _dump(init, ot_loads=1, extra=""):
    lines = ["PART xck26-sfvc784-2LV-c",
             "PROP BITSTREAM.READBACK.SECURITY LEVEL1", "PROP BITSTREAM.GENERAL.JTAG_SYSMON DISABLE", "PROP BITSTREAM.GENERAL.DISABLE_JTAG YES",
             "DEBUG_CORES 0", "DEBUG_CELL_COUNT 0", "BSCAN_COUNT 0", "MARK_DEBUG_NETS 0", "PORT IN clk_25", "PORT OUT led[0]",
             "SYSMON_CELL u_guard/u_sysmon"]
    lines += [f"SYSMON_ATTR {k} 16'h{v:04X}" for k, v in init.items()]
    for pn in ("OT", "ALM[0]", "ALM[1]", "ALM[2]", "ALM[3]", "ALM[4]", "ALM[5]", "ALM[6]"):
        n = ot_loads if pn == "OT" else 1
        lines.append(f"SYSMON_PIN {pn} {n} reg u_guard/u_shutdown/shutdown_reg qloads 7 :: LUT6:u_guard/u_shutdown/x/I0" if n else f"SYSMON_PIN {pn} 0 reg none :: ")
    return "\n".join(lines) + "\n" + extra


def _build(tmp, dump, props, conflict=(), bit=True, request=None):
    (tmp / "prepare.json").write_text(json.dumps({"top": "b196_top", "board": "kr260"}))
    req = {"source": "pin", "request": request or {"production_secure": True, "encrypt": True, "authenticate": True, "readback_off": True,
                                                    "strip_debug": True, "sysmon_shutdown": True, "waive": []},
           "switches": {k: True for k in S.SUBSWITCHES}, "policy_conflict": list(conflict), "properties": [list(p) for p in props], "part": "xck26-sfvc784-2LV-c"}
    (tmp / "security_request.json").write_text(json.dumps(req))
    (tmp / "security_apply.txt").write_text("".join(f"APPLY ok {p} {v}\n" for p, v in props))
    (tmp / "security_design.txt").write_text(dump)
    (tmp / "vivado.log").write_text("Command: write_bitstream -force -verbose x.bit\n")
    if bit:
        (tmp / "b196_top.bit").write_bytes(b"\x00\x09" + b"x" * 40)


PROPS = [("BITSTREAM.READBACK.SECURITY", "LEVEL1"), ("BITSTREAM.GENERAL.JTAG_SYSMON", "DISABLE"), ("BITSTREAM.GENERAL.DISABLE_JTAG", "YES")]


def test_a_clean_build_meets_the_profile(tmp_path):
    _build(tmp_path, _dump(S.sysmon_init(S.limits_of("kr260"))), PROPS)
    r = S.evaluate(tmp_path)
    assert r["gates"]["security_profile_met"] is True and all(r["gates"].values()), r["findings"]


def test_a_debug_core_a_bscan_and_a_debug_port_each_fail_strip_debug(tmp_path):
    init = S.sysmon_init(S.limits_of("kr260"))
    for extra, rule in (("DEBUG_CORES 1 u_ila_0\nDEBUG_CELL_COUNT 40\nDEBUG_CELL ila u_ila_0\n", "debug_core"),
                        ("BSCAN_COUNT 1\nBSCAN_CELL BSCANE2 u_jtag/bs\n", "bscan"), ("MARK_DEBUG_NETS 2\n", "mark_debug"),
                        ("PORT IN jtag_tck\n", "debug_port")):
        d = _dump(init).replace("DEBUG_CORES 0\n", "").replace("DEBUG_CELL_COUNT 0\n", "").replace("BSCAN_COUNT 0\n", "").replace("MARK_DEBUG_NETS 0\n", "")
        _build(tmp_path, d + extra, PROPS)
        r = S.evaluate(tmp_path)
        assert r["gates"]["security_strip_debug"] is False and r["gates"]["security_profile_met"] is False
        assert any(f["rule"] == rule for f in r["findings"]), (rule, r["findings"])


def test_a_waiver_needs_a_reason_and_names_the_rule(tmp_path):
    init = S.sysmon_init(S.limits_of("kr260"))
    req = S.normalise({"production_secure": True, "waive": [{"rule": "bscan", "reason": "the register bus is the product's control path"}]}, "t")
    _build(tmp_path, _dump(init).replace("BSCAN_COUNT 0", "BSCAN_COUNT 1\nBSCAN_CELL BSCANE2 u/b"), PROPS, request=req)
    assert S.evaluate(tmp_path)["gates"]["security_strip_debug"] is True


def test_a_file_of_a_debug_build_fails_even_when_the_dump_is_clean(tmp_path):
    _build(tmp_path, _dump(S.sysmon_init(S.limits_of("kr260"))), PROPS)
    (tmp_path / "b196_top.ltx").write_text("probes")
    assert S.evaluate(tmp_path)["gates"]["security_strip_debug"] is False


def test_sysmon_thresholds_and_wiring_are_checked(tmp_path):
    init = S.sysmon_init(S.limits_of("kr260"))
    bad = dict(init, INIT_50=init["INIT_50"] + 64)                        # one code too high
    _build(tmp_path, _dump(bad), PROPS)
    r = S.evaluate(tmp_path)
    assert r["gates"]["security_sysmon_shutdown"] is False and any("INIT_50" in f["what"] for f in r["findings"])
    _build(tmp_path, _dump(init, ot_loads=0), PROPS)
    r = S.evaluate(tmp_path)
    assert r["gates"]["security_sysmon_shutdown"] is False and any("OT drives nothing" in f["what"] for f in r["findings"])
    _build(tmp_path, _dump(init).replace("qloads 7", "qloads 0"), PROPS)
    assert any("drives nothing" in f["what"] for f in S.evaluate(tmp_path)["findings"])
    _build(tmp_path, _dump(init).replace("SYSMON_CELL u_guard/u_sysmon", "SYSMON_CELL_X").replace("SYSMON_ATTR", "X").replace("SYSMON_PIN", "Y"), PROPS)
    assert "no SYSMONE4 cell" in " ".join(f["what"] for f in S.evaluate(tmp_path)["findings"])


def test_a_setting_vivado_refused_or_never_read_back_fails(tmp_path):
    init = S.sysmon_init(S.limits_of("kr260"))
    _build(tmp_path, _dump(init), PROPS)
    (tmp_path / "security_apply.txt").write_text("APPLY ERROR BITSTREAM.READBACK.SECURITY LEVEL1 :: no such property\n")
    r = S.evaluate(tmp_path)
    assert r["gates"]["security_settings_applied"] is False and r["gates"]["security_profile_met"] is False
    _build(tmp_path, _dump(init).replace("PROP BITSTREAM.READBACK.SECURITY LEVEL1", "PROP BITSTREAM.READBACK.SECURITY NONE"), PROPS)
    assert S.evaluate(tmp_path)["gates"]["security_readback_off"] is False            # the request is not the evidence: the read-back is


def test_encryption_and_authentication_are_handed_to_the_owner_on_a_zynq_mpsoc(tmp_path):
    _build(tmp_path, _dump(S.sysmon_init(S.limits_of("kr260"))), PROPS)
    r = S.evaluate(tmp_path)
    assert set(r["handed_to_owner"]) == {"encrypt", "authenticate"} and "bootgen" in r["handed_to_owner"]["encrypt"]
    assert "security_encrypt" not in r["gates"] and "security_authenticate" not in r["gates"]    # never reported as a pass
    assert r["gates"]["security_profile_met"] is True


def test_a_missing_dump_fails_every_gate_it_would_prove(tmp_path):
    _build(tmp_path, "", PROPS)
    (tmp_path / "security_design.txt").unlink()
    r = S.evaluate(tmp_path)
    assert r["gates"]["security_profile_met"] is False and r["gates"]["security_readback_off"] is False


def test_a_policy_conflict_is_a_gate_of_its_own(tmp_path):
    _build(tmp_path, _dump(S.sysmon_init(S.limits_of("kr260"))), PROPS, conflict=["build.yaml asks for X but the pin is Y: the pin wins"])
    assert S.evaluate(tmp_path)["gates"]["security_policy_pin"] is False


def test_a_build_with_no_request_has_no_security_gates(tmp_path):
    assert S.evaluate(tmp_path) is None


# ---- key hygiene ---------------------------------------------------------------------------------------------------------------------------

def test_key_files_are_git_ignored_and_none_is_tracked():
    out = subprocess.run(["git", "check-ignore", "designs/x/build/base/b196_top.nky", "any.nky"], cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.split() == ["designs/x/build/base/b196_top.nky", "any.nky"]
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    assert not [f for f in tracked if re.search(r"\.nky|\.nkz|\.pem$|\.rsa$|\.key$", f, re.I)]


def test_no_flow_or_agent_file_writes_a_key_into_hardware():
    """The absolute rule of brief 196: no eFUSE, BBRAM or key-programming command anywhere in the files this brief adds or changes."""
    forbidden = re.compile(r"program_hw_efuse|program_hw_bbram|program_hw_device|create_hw_bitstream|\bxbbram|bbram_key|program_hw_cfgmem|"
                           r"efuse_program|\bpuf_|set_property\s+PROGRAM\.(EFUSE|BBRAM)|readback_hw_device|\bopen_hw_manager|\bconnect_hw_server", re.I)
    files = [ROOT / "flow" / "security.py", ROOT / "flow" / "security.tcl", ROOT / "flow" / "build.tcl",
             *(ROOT / "designs" / "b196_secure_demo").rglob("*.tcl"), *(ROOT / "designs" / "b196_secure_demo" / "rtl").glob("*.sv")]
    for f in files:
        code = "\n".join(ln for ln in f.read_text().splitlines() if not ln.lstrip().startswith(("#", "//")))
        text = re.sub(r'""".*?"""', "", code, flags=re.S) if f.suffix == ".py" else code
        assert not forbidden.search(text), f"{f.relative_to(ROOT)} names a hardware-programming command"

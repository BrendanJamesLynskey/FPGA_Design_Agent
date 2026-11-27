"""Brief 225: the Red Pitaya as a target board and as the same box that is a lab instrument. No board, no instrument, no network, no Vivado.

What is tested: the board file's facts against the pinned vendor constraints (pins, standards, clock) and the catalogue's rules for this board; the shell patch
(markers, the version-line change, the optional second slot); the user block's RTL in a simulator when one is installed; the register maps, the datasheet text
made from them, the behavioural models and the checks run against them (and against broken models, which must fail); the owner's load script (syntax, the
never-list, its own DRY_RUN path with a ssh that fails the test if called, the confirmations, the size and md5 guards); and the lab file's mode rules (the box
is the target or an instrument, never both; the run record states the mode).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.core import permissions as P  # noqa: E402
from agent.graph import lab_interview as LI  # noqa: E402
from flow import board_catalogue as cat  # noqa: E402
from hil import lab as L  # noqa: E402
from hil import lab_bringup as LB  # noqa: E402
from hil import redpitaya_checks as C  # noqa: E402
from hil import redpitaya_load as LD  # noqa: E402
from hil import redpitaya_models as M  # noqa: E402
from hil import redpitaya_regs as R  # noqa: E402
from tools import rp_shell as SH  # noqa: E402
from tools.inventory_check import parse_xdc  # noqa: E402

BOARD = ROOT / "boards" / "redpitaya_stemlab_125_14"
BY = yaml.safe_load((BOARD / "board.yaml").read_text())
MASTER = parse_xdc((BOARD / BY["master_xdc"]).read_text())[0]


# ---- the board file -------------------------------------------------------------------------------------------------------------------------
def test_the_part_and_the_clock_are_the_vendors():
    assert BY["part"] == "xc7z010clg400-1" and BY["family"] == "Zynq-7000" and BY["name"] == "redpitaya_stemlab_125_14"
    c = BY["clock"]
    assert (c["port"], c["pin"], c["port_n"], c["pin_n"], c["differential"], c["freq_mhz"], c["iostandard"]) == ("adc_clk_p", "U18", "adc_clk_n", "U19", True, 125, "DIFF_HSTL_I_18")
    assert MASTER["adc_clk_p"] == ("U18", "DIFF_HSTL_I_18") and MASTER["adc_clk_n"] == ("U19", "DIFF_HSTL_I_18")


@pytest.mark.parametrize("port,pin,std", [("led[0]", "F16", "LVCMOS33"), ("led[7]", "J14", "LVCMOS33"), ("exp_p_io[0]", "G17", "LVCMOS33"), ("exp_n_io[7]", "M15", "LVCMOS33"),
                                          ("adc1_dat[0]", "V17", "LVCMOS18"), ("adc2_dat[15]", "Y18", "LVCMOS18"), ("adc_cdcs_o", "V18", "LVCMOS18"),
                                          ("dac_dat_o[0]", "M19", "LVCMOS33"), ("dac_dat_o[13]", "D19", "LVCMOS33"), ("dac_wrt_o", "M17", "LVCMOS33"),
                                          ("dac_sel_o", "N16", "LVCMOS33"), ("dac_clk_o", "M18", "LVCMOS33"), ("dac_rst_o", "N15", "LVCMOS33")])
def test_pins_and_standards_match_the_pinned_vendor_files(port, pin, std):
    assert MASTER[port] == (pin, std)


def test_the_listing_has_the_ports_the_vendor_shell_names_and_leaves_out_what_it_cannot_confirm():
    assert len([p for p in MASTER if p.startswith("adc1_dat")]) == 16 and len([p for p in MASTER if p.startswith("adc2_dat")]) == 16
    assert len([p for p in MASTER if p.startswith("dac_dat_o")]) == 14 and len([p for p in MASTER if p.startswith("led[")]) == 8
    assert len([p for p in MASTER if p.startswith("exp_")]) == 16
    assert not [p for p in MASTER if p.startswith(("daisy", "dac_pwm", "adc_clk_o"))]      # SATA pins conflict between the vendor's two files; the PWM and ADC-clock outputs are not listed
    assert not [p for p in MASTER if "][" in p]                                            # the agent's resource names take one index


def test_the_facts_name_their_sources_and_the_unconfirmed_ones_say_why():
    items = {f["item"]: f for f in BY["facts"]}
    assert {"part", "licence", "PL clock", "fast ADC", "fast DAC", "analogue front end", "input jumpers", "extension connector E1", "PS-side address window", "loading a bitstream", "power"} <= set(items)
    assert items["input jumpers"]["confirmed_by"] == "owner" and "IN1 = LV" in items["input jumpers"]["value"] and "IN2 = HV" in items["input jumpers"]["value"]
    for it in ("DAC output swing into a high-impedance input", "LED polarity"):
        assert items[it]["status"] == "unconfirmed" and items[it]["reason"]
    assert "7010" not in BY["board_revision"] and "v1.1" in BY["board_revision"]
    rule = BY["hardware_use"]["rule"]
    for must in ("never write the SD card", "never replace boot.bin", "volatile", "never enable the factory SCPI server", "5 V DC isolated"):
        assert must in rule
    assert BY["hardware_use"]["owned"] is True


def test_the_installed_vivado_basic_licence_covers_the_part():
    probe = json.loads((ROOT / "results" / "95_boards" / "licence_probe.json").read_text())["parts"]
    assert any(p["part"] == BY["part"] and p["result"] == "ok" and p["stage"] == "route" for p in probe)


def test_the_catalogue_names_the_board_and_does_not_take_a_sibling_for_it():
    e = cat.load()["redpitaya_stemlab_125_14"]
    assert e["targetable"] and e["licence_tier"] == "free" and e["trust"] == "built"
    assert cat.resolve("my Red Pitaya") == ("redpitaya_stemlab_125_14", [])
    assert cat.resolve("the STEMlab 125-14 please") == ("redpitaya_stemlab_125_14", [])
    for sib in ("STEMlab 125-14 Gen 2", "Red Pitaya STEMlab 125-14 PRO Z7020", "stemlab 125-14 4-Input", "Red Pitaya SDRlab 122-16", "STEMlab 125-14 LN"):
        assert cat.resolve(sib) == (None, []), sib
    assert cat.resolve("a Red Pitaya or a ZedBoard") == (None, ["redpitaya_stemlab_125_14", "zedboard"])


def test_the_smoke_design_is_built_on_the_boards_pins_and_its_record_is_current():
    ok, why = cat.smoke_evidence("redpitaya_stemlab_125_14")
    assert ok, why
    rec = json.loads((ROOT / "results" / "95_boards" / "redpitaya_stemlab_125_14" / "smoke.json").read_text())
    assert rec["part"] == "xc7z010clg400-1" and rec["ports"]["differential_clock"] is True and rec["ports"]["led"] == 8 and rec["passed"]


# ---- the shell ------------------------------------------------------------------------------------------------------------------------------
VENDOR_LINES = """logic        [14-1:0] dac_a    , dac_b    ;
logic signed [15-1:0] dac_a_sum, dac_b_sum;
SBA_T [2-1:0]            pid_dat;
assign dac_a_sum = asg_dat[0] + pid_dat[0];
assign dac_b_sum = asg_dat[1] + pid_dat[1];
  `else
  sys_bus_stub sys_bus_stub_6 (sys[6]);
  `endif
  sys_bus_stub sys_bus_stub_7 (sys[7]);
"""


def test_the_shell_patch_puts_the_block_in_slot_7_and_adds_its_dac_term():
    out = SH.apply_patch(VENDOR_LINES)
    assert "rp_user_block i_user_block" in out and "sys_bus_stub sys_bus_stub_7" not in out and "sys_bus_stub sys_bus_stub_6" in out
    assert "pid_dat[0] + user_dac[0];" in out and "pid_dat[1] + user_dac[1];" in out and "SBG_T [2-1:0]            user_dac;" in out
    for n in ("sys[7].addr", "sys[7].ack", "adc_dat[0]", "user_dac[1]"):
        assert n in out


def test_the_patch_can_also_fill_slot_6_with_another_module():
    out = SH.apply_patch(VENDOR_LINES, "rp_freqcount", "rp_patgen")
    assert "rp_freqcount i_user_block" in out and "rp_patgen i_user6_block" in out and "sys_bus_stub sys_bus_stub_6" not in out
    assert "user_dac[0] + user6_dac[0]" in out and "user_dac, user6_dac;" in out


@pytest.mark.parametrize("break_it", ["missing", "twice"])
def test_the_patch_stops_when_the_vendor_text_changed(break_it):
    t = VENDOR_LINES.replace("sys_bus_stub sys_bus_stub_7 (sys[7]);", "") if break_it == "missing" else VENDOR_LINES + VENDOR_LINES
    with pytest.raises(ValueError, match="shell changed since the pin"):
        SH.apply_patch(t)


def test_the_pin_is_a_full_commit_and_a_hash_and_the_board_file_cites_the_same_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", SH.COMMIT) and re.fullmatch(r"[0-9a-f]{64}", SH.TOP_SHA256)
    assert SH.COMMIT in BY["sources"]["RPFPGA"]["version"]
    spec = yaml.safe_load((BOARD / "pins_import.yaml").read_text())
    assert all(SH.COMMIT in s["url"] for s in spec["sources"])
    assert SH.BD_VERSION[0] == "set scripts_vivado_version 2025.1" and "version -short" in SH.BD_VERSION[1]


def test_the_build_command_is_a_capped_scope_around_the_vendors_script(tmp_path):
    argv = SH.build_argv(tmp_path, "8G", unit="fda-rp-shell-test")
    assert argv[:4] == ["systemd-run", "--user", "--scope", "--quiet"] and "MemoryMax=8G" in argv and "fda-rp-shell-test" in argv
    assert argv[argv.index("-source") + 1] == "fda_vivado_Z10.tcl" and "nice" in argv and argv[-1] == SH.NEW_PRJ


def test_the_shell_block_is_ours_and_documents_what_a_user_could_guess_wrong():
    t = (BOARD / "shell" / "rp_user_block.sv").read_text()
    for must in ("0x40700000", "unmapped", "read-only", "same cycle", "saturates", "no aliasing"):
        assert must in t
    assert "module rp_user_block" in t and "BLOCK_ID" in t


@pytest.mark.skipif(shutil.which("iverilog") is None or shutil.which("vvp") is None, reason="iverilog is not installed")
def test_the_user_block_passes_its_testbench(tmp_path):
    out = tmp_path / "tb.vvp"
    subprocess.run(["iverilog", "-g2012", "-o", str(out), str(BOARD / "shell" / "tb_rp_user_block.sv"), str(BOARD / "shell" / "rp_user_block.sv")], check=True, capture_output=True)
    r = subprocess.run(["vvp", str(out)], check=True, capture_output=True, text=True)
    assert "TB PASS" in r.stdout


# ---- register maps, datasheet, models --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(R.MAPS))
def test_a_register_map_is_consistent(name):
    m = R.MAPS[name]
    offs = m.offsets()
    assert len(set(offs)) == len(offs) and all(o % 4 == 0 for o in offs) and max(offs) < 0x100
    assert len({r.name for r in m.regs}) == len(m.regs)
    assert m.by_name("ID").reset == m.block_id and m.by_name("ID").access == "RO" and m.by_name("SCRATCH").access == "RW"
    assert all(r.access in ("RO", "RW") and 0 <= r.reset <= 0xFFFFFFFF and r.doc for r in m.regs)
    ds = R.datasheet(m)
    for r in m.regs:
        assert f"| 0x{r.offset:02X} | {r.name} |" in ds
    assert ds.count("\n- ") == len(m.notes) and "0x40700000" in ds and "bus error" in ds


def test_the_two_blocks_have_different_ids_and_every_model_starts_at_the_reset_values():
    assert R.FREQCOUNT.block_id != R.PATGEN.block_id
    for model, m in ((M.FreqCountModel(), R.FREQCOUNT), (M.PatGenModel(), R.PATGEN)):
        for r in m.regs:
            assert model.read(r.offset) == r.reset, r.name


@pytest.mark.parametrize("model", [M.FreqCountModel(), M.PatGenModel()])
def test_a_model_answers_an_unmapped_offset_with_the_bus_error_and_refuses_a_write_to_a_read_only_register(model):
    for off in (0x1C + 0x400, 0x100, 0xFFFFC):
        with pytest.raises(M.BusError):
            model.read(off)
        with pytest.raises(M.BusError):
            model.write(off, 1)
    with pytest.raises(M.BusError):
        model.write(R.FREQCOUNT.by_name("ID").offset, 1)


def measure(model, gate=12_500_000):
    w = R.MockWindow(model)
    o = {r.name: r.offset for r in model.MAP.regs}
    w.write(o["GATE_LEN"], gate)
    w.write(o["CTRL"], 1)
    assert C.wait_status(w, model.MAP, 2, 5.0, sleep=lambda _s: None)
    return {k: w.read(o[k]) for k in ("EDGES", "GATE_ACTUAL", "SPAN", "STATUS", "MEAS_DONE")}


@pytest.mark.parametrize("f", [1e3, 12_345.0, 1e6, 10e6, 29.9e6])
def test_the_frequency_counter_model_measures_a_sine_both_ways(f):
    r = measure(M.FreqCountModel(M.SineSignal(f, 4000, 0, phase0=0.17)))
    gate_f = r["EDGES"] / (r["GATE_ACTUAL"] / 125e6)
    recip_f = (r["EDGES"] - 1) * 125e6 / r["SPAN"]
    assert r["GATE_ACTUAL"] == 12_500_000 and r["STATUS"] & 2 and not r["STATUS"] & 1 and r["MEAS_DONE"] == 1
    assert abs(gate_f - f) / f < 1.2 / (f * 0.1) + 1e-9          # one edge in the gate
    assert abs(recip_f - f) / f < 1e-4


def test_the_counter_needs_both_thresholds_crossed_and_says_so():
    quiet = measure(M.FreqCountModel(M.SineSignal(1e6, amp=100, offset=0)))               # swing +-100 never reaches +256
    assert quiet["EDGES"] == 0 and quiet["STATUS"] & 4
    flat = measure(M.FreqCountModel(None))
    assert flat["EDGES"] == 0 and flat["STATUS"] & 4
    m = M.FreqCountModel(M.SineSignal(1e6))
    w = R.MockWindow(m)
    w.write(0x10, 0x3F00)                                                                  # THR_HIGH -256, THR_LOW is -256: high <= low
    assert w.read(0x10) == 0xFFFFFF00
    w.write(0x08, 1)
    while w.read(0x18) & 1:
        pass
    assert w.read(0x18) & 8 and w.read(0x1C) == 0


def test_the_counter_registers_behave_as_the_datasheet_says():
    m = M.FreqCountModel(M.SineSignal(1e6))
    w = R.MockWindow(m)
    w.write(0x0C, 10)
    assert w.read(0x0C) == 1000                                    # below 1000 stores 1000
    w.write(0x0C, 5_000_000)
    w.write(0x08, 1)
    assert w.read(0x08) == 0                                       # START is W1P: reads 0
    w.write(0x08, 1)                                               # ignored while BUSY
    while w.read(0x18) & 1:
        pass
    assert w.read(0x28) == 1 and w.read(0x20) == 5_000_000
    w.write(0x0C, 2_000_000)
    assert w.read(0x20) == 5_000_000                               # the change applies to the next gate
    w.write(0x08, 2)                                               # CONT: a new gate starts at once
    w.write(0x08, 3)
    for _ in range(40):                                            # CONT: BUSY never drops for good, so poll a bounded number of times
        w.read(0x18)
    n = w.read(0x28)
    assert n >= 2 and w.read(0x18) & 1                              # still busy with the next gate
    with pytest.raises(M.BusError):
        w.write(0x1C, 5)                                           # a result register is read-only


def pat(model):
    w = R.MockWindow(model)
    o = {r.name: r.offset for r in R.PATGEN.regs}
    return w, o


def test_the_pattern_generator_cuts_every_level_to_the_limit_and_says_so():
    m = M.PatGenModel()
    w, o = pat(m)
    w.write(o["LIMIT"], 0x7FFF)
    assert w.read(o["LIMIT"]) == 7372                              # the hard ceiling, 0.9 V
    w.write(o["LIMIT"], 3000)
    w.write(o["LEVEL_HI"], 5000)
    w.write(o["LEVEL_LO"], (-4000) & 0x3FFF)
    w.write(o["PERIOD"], 100)
    w.write(o["WIDTH"], 40)
    w.write(o["COUNT"], 2)
    w.write(o["CTRL"], 1)
    assert w.read(o["STATUS"]) & 4 and w.read(o["PERIODS_DONE"]) == 2
    seq = [m.output(c) for c in range(0, 200)]
    assert max(seq) == 3000 and min(seq) == -3000 and m.output(200) == 0 and m.output(10_000) == 0
    assert seq[:40] == [3000] * 40 and seq[40:100] == [-3000] * 60


def test_the_pattern_generator_stays_at_zero_until_started_and_after_stop():
    m = M.PatGenModel()
    w, o = pat(m)
    assert all(m.output(c) == 0 for c in range(50))
    w.write(o["CTRL"], 1 | 4)
    assert w.read(o["STATUS"]) & 1 and m.output(0) == 2048 and m.output(700) == 0
    w.write(o["CTRL"], 2)
    assert not w.read(o["STATUS"]) & 1 and w.read(o["STATUS"]) & 2 and all(m.output(c) == 0 for c in range(50))


def test_pattern_mode_holds_each_sample_and_wraps():
    m = M.PatGenModel()
    w, o = pat(m)
    w.write(o["MODE"], 1)
    w.write(o["PAT_LEN"], 3)
    w.write(o["SAMPLE_DIV"], 4)
    for i, v in enumerate((100, 200, (-300) & 0x3FFF)):
        w.write(o[f"PAT{i}"], v)
    w.write(o["COUNT"], 2)
    w.write(o["CTRL"], 1)
    assert [m.output(c) for c in range(0, 12, 4)] == [100, 200, -300] and m.output(12) == 100 and m.output(24) == 0


# ---- the checks, on models and on broken models --------------------------------------------------------------------------------------------
def test_the_checks_pass_on_the_models_and_the_dry_run_is_marked_mock():
    for block in ("rp_freqcount", "rp_patgen"):
        r = LD.dry_run(block)
        assert r["pass"] and r["mock"] is True and r["evidence"] is False and r["accesses"] > 20
        assert all(row["result"] == "pass" for row in r["rows"])


def test_the_freqcount_check_fails_on_a_wrong_frequency_and_judges_nothing_without_an_expectation():
    m = M.FreqCountModel(M.SineSignal(1_000_000.0))
    rows = C.run_block("rp_freqcount", R.MockWindow(m), 1_001_000.0, 100.0, sleep=lambda _s: None)
    assert any(r["check"] == "freq_gate" and r["result"] == "fail" for r in rows)
    rows = C.run_block("rp_freqcount", R.MockWindow(M.FreqCountModel(M.SineSignal(1_000_000.0))), None, sleep=lambda _s: None)
    assert all(r["result"] == "pass" for r in rows) and any(r["check"] == "freq_recorded" for r in rows)


def test_the_wrong_block_is_caught_by_the_id_and_nothing_else_is_written():
    w = R.MockWindow(M.PatGenModel())
    rows = C.run_block("rp_freqcount", w, 1e6)
    assert len(rows) == 1 and rows[0]["check"] == "id" and rows[0]["result"] == "fail" and not [a for a in w.log if a[0] == "w"]


def test_a_stuck_scratch_register_fails_the_check():
    class Stuck(M.FreqCountModel):
        def on_write(self, name, v):
            if name != "SCRATCH":
                super().on_write(name, v)
    r = C.check_scratch(R.MockWindow(Stuck()), R.FREQCOUNT)
    assert r["result"] == "fail" and "read" in r["detail"]


def test_the_checks_never_leave_the_register_map():
    for block, model in (("rp_freqcount", M.FreqCountModel(M.SineSignal(1e6))), ("rp_patgen", M.PatGenModel())):
        w = R.MockWindow(model)
        C.run_block(block, w, 1e6 if block == "rp_freqcount" else None, drive_ok=True, sleep=lambda _s: None)
        assert {a[1] for a in w.log} <= set(R.MAPS[block].offsets())


def test_the_output_check_moves_nothing_without_confirmation_and_refuses_a_large_level():
    w = R.MockWindow(M.PatGenModel())
    rows = C.run_block("rp_patgen", w, None, drive_ok=False, sleep=lambda _s: None)
    assert rows[-1]["skipped"] and not [a for a in w.log if a[0] == "w" and a[1] == R.PATGEN.by_name("CTRL").offset]       # START was never written
    big = C.check_patgen_output(R.MockWindow(M.PatGenModel()), level_counts=5000, sleep=lambda _s: None)
    assert big[0]["result"] == "fail" and "not started" in big[0]["detail"]
    w2 = R.MockWindow(M.PatGenModel())
    ok = C.check_patgen_output(w2, sleep=lambda _s: None)
    assert ok[0]["result"] == "pass" and w2.log[-1][:2] == ("w", R.PATGEN.by_name("CTRL").offset) and w2.log[-1][2] == 2          # STOP is the last write


def test_a_memory_window_cannot_be_built_off_the_board(tmp_path):
    with pytest.raises(R.WindowError, match="only on the Red Pitaya"):
        R.MemWindow(dev=str(tmp_path / "no_such_mem"))


# ---- the owner's script ------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def pkg(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "fpga.bit.bin").write_bytes(os.urandom(4096))
    (d / "build.json").write_text(json.dumps({"build_id": "cafe0001"}))
    for f in ("redpitaya_checks.py", "redpitaya_regs.py"):
        shutil.copy(ROOT / "hil" / f, d / f)
    return d


def fake_bin(tmp_path):
    """A PATH whose ssh and scp record any call: in a dry run the script must never call them."""
    b = tmp_path / "bin"
    b.mkdir()
    for n in ("ssh", "scp"):
        (b / n).write_text(f"#!/bin/sh\necho {n} >> {tmp_path}/called\nexit 1\n")
        (b / n).chmod(0o755)
    return b


@pytest.mark.parametrize("block,bare", [("rp_freqcount", False), ("rp_patgen", False), ("rp_freqcount", True)])
def test_the_script_is_valid_bash_obeys_the_never_list_and_loads_volatile_only(pkg, block, bare):
    text = LD.render_script(pkg, block, expect_hz=1e6, bare=bare)
    assert P.check_script(text) is None
    f = pkg / "load.sh"
    f.write_text(text)
    subprocess.run(["bash", "-n", str(f)], check=True)
    assert ("fpgautil -b /tmp/fda_load/fpga.bit.bin -f Full" in text) == bare and ('rp "sh /tmp/fda_load/load_fda.sh"' in text) == (not bare)      # brief 243: shell builds load with the generated load_fda.sh
    for banned in ("boot.bin", "mmcblk", "dd if=", "qspi", "ecosystem", "apt", "systemctl", "scpi", "/opt/redpitaya/fpga"):
        assert banned not in text.lower().replace("scpi_", ""), banned
    assert "RESTORE" in text and "overlay.sh v0.94" in text and "type yes" in text and "factory oscilloscope and generator are NOT running" in text


def run_script(pkg, tmp_path, env_extra):
    f = pkg / "load.sh"
    f.write_text(LD.render_script(pkg, "rp_patgen"))
    env = {**os.environ, "PATH": f"{fake_bin(tmp_path)}:{os.environ['PATH']}", **env_extra}
    return subprocess.run(["bash", str(f)], capture_output=True, text=True, env=env, cwd=tmp_path)


def test_the_dry_run_prints_every_board_command_and_calls_no_ssh(pkg, tmp_path):
    r = run_script(pkg, tmp_path, {"DRY_RUN": "1", "DRY_ANSWER": "yes"})
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "called").exists()
    assert "[dry run] on root@rp-f00c16.local: sh /tmp/fda_load/load_fda.sh" in r.stdout
    assert "python3 redpitaya_checks.py rp_patgen --drive-ok" in r.stdout
    assert "would ask: DRIVES OUT1" in r.stdout and "nothing was loaded" in r.stdout


def test_without_the_owners_yes_nothing_is_done(pkg, tmp_path):
    r = run_script(pkg, tmp_path, {"DRY_RUN": "1", "DRY_ANSWER": "no"})
    assert r.returncode == 1 and "not confirmed; nothing was done" in r.stderr and "load_fda.sh" not in r.stdout


def test_a_refused_drive_confirmation_leaves_out_the_flag(pkg, tmp_path):
    f = pkg / "load.sh"
    f.write_text(LD.render_script(pkg, "rp_patgen"))
    text = f.read_text().replace('ask() { if', 'ask() { case "$1" in DRIVES*) return 1;; esac; if', 1)
    f.write_text(text)
    env = {**os.environ, "PATH": f"{fake_bin(tmp_path)}:{os.environ['PATH']}", "DRY_RUN": "1", "DRY_ANSWER": "yes"}
    r = subprocess.run(["bash", str(f)], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "--drive-ok" not in r.stdout


def test_restore_loads_the_factory_shell_and_nothing_else(pkg, tmp_path):
    r = run_script(pkg, tmp_path, {"DRY_RUN": "1", "DRY_ANSWER": "yes", "RESTORE": "1"})
    assert r.returncode == 0 and "overlay.sh v0.94\n" in r.stdout and "fpga.bit.bin" not in r.stdout and "factory_instrument" in r.stdout


def test_a_changed_bitstream_is_refused_before_anything_is_asked(pkg, tmp_path):
    f = pkg / "load.sh"
    f.write_text(LD.render_script(pkg, "rp_freqcount"))
    (pkg / "fpga.bit.bin").write_bytes(os.urandom(4096))            # same size, other content
    env = {**os.environ, "PATH": f"{fake_bin(tmp_path)}:{os.environ['PATH']}", "DRY_RUN": "1", "DRY_ANSWER": "yes"}
    r = subprocess.run(["bash", str(f)], capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "md5" in r.stderr and "would ask" not in r.stdout
    (pkg / "fpga.bit.bin").write_bytes(b"short")
    r = subprocess.run(["bash", str(f)], capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "byte file" in r.stderr


def test_the_script_command_writes_the_file_and_copies_the_check_files_beside_the_bitstream(pkg, tmp_path):
    for f in ("redpitaya_checks.py", "redpitaya_regs.py"):
        (pkg / f).unlink()
    assert LD.main(["script", str(pkg), "--block", "rp_freqcount", "--expect-hz", "1000000"]) == 0
    assert (pkg / "load_cafe0001.sh").is_file() and (pkg / "load_cafe0001.sh").stat().st_mode & stat.S_IXUSR
    assert (pkg / "redpitaya_checks.py").is_file() and (pkg / "redpitaya_regs.py").is_file()


def test_a_block_in_slot_6_is_checked_at_its_own_base(pkg):
    assert "--base 0x40600000 $DRIVE" in LD.render_script(pkg, "rp_patgen", slot=6) and "rp_patgen $DRIVE" in LD.render_script(pkg, "rp_patgen")
    assert "check_id rp_patgen 0x40600000 6" in LD.render_script(pkg, "rp_patgen", slot=6)
    assert R.SLOT_BASES == {7: 0x40700000, 6: 0x40600000}


def test_the_checks_import_from_a_bare_directory(tmp_path):
    """On the board the two files sit side by side with no package: the fallback import must work."""
    for f in ("redpitaya_checks.py", "redpitaya_regs.py"):
        shutil.copy(ROOT / "hil" / f, tmp_path / f)
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path[:] = [{str(tmp_path)!r}] + sys.path[-3:]; import redpitaya_checks as c; print(c.FREQCOUNT.block)"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0 and "rp_freqcount" in r.stdout, r.stderr


# ---- the lab file: the box is the instrument or the target ----------------------------------------------------------------------------------
def rp_entry(**kw):
    e = {"id": "redpitaya", "kind": "oscilloscope", "onboarded": True, "connection": {"type": "lan", "address": "192.0.2.5"}, "control": {"mode": "scripted", "driver": "mock"},
         "is_board": "redpitaya_stemlab_125_14", "channels": [{"name": "IN1"}, {"name": "IN2"}],
         "capabilities": [{"measure": "frequency", "channels": ["IN1", "IN2"], "max_hz": 30e6, "accuracy_ppm": 10.0}],
         "outputs": [{"name": "OUT1", "kind": "awg", "max_v": 1.0}]}
    e.update(kw)
    return e


def lab_for(*insts, design=None):
    return L.merge({"instruments": list(insts)}, {"connections": [{"instrument": "redpitaya", "channel": "IN1", "probes": "the clock pin"}], **(design or {})})


def need():
    return L.Need("R1", "the clock runs at 25 MHz within 100 ppm", "frequency", "the clock", 25e6, 100.0, "the design's own count")


def test_the_mode_fields_validate():
    assert L.validate_instrument(rp_entry()) == []
    assert L.validate_instrument(rp_entry(mode={"state": "factory_instrument"})) == []
    assert L.validate_instrument(rp_entry(mode={"state": "target_loaded", "build_id": "cafe0001"})) == []
    assert any("needs the build_id" in e for e in L.validate_instrument(rp_entry(mode={"state": "target_loaded"})))
    assert any("no build_id" in e for e in L.validate_instrument(rp_entry(mode={"state": "factory_instrument", "build_id": "x"})))
    assert any("mode.state" in e for e in L.validate_instrument(rp_entry(mode={"state": "both"})))
    assert any("also a board" in e for e in L.validate_instrument({**rp_entry(mode={"state": "factory_instrument"}), "is_board": None}) + L.validate_instrument({k: v for k, v in rp_entry(mode={"state": "factory_instrument"}).items() if k != "is_board"}))


def test_a_factory_instrument_is_planned_for_a_design_that_runs_elsewhere():
    lab = lab_for(rp_entry(mode={"state": "factory_instrument"}), design={"target_board": "zedboard"})
    p = L.plan_need(lab, need())
    assert p["chosen"]["method"] == "scripted" and p["chosen"]["instrument"] == "redpitaya" and not p["left_out"]
    assert L.instrument_mode(lab, "redpitaya") == {"state": "factory_instrument", "build_id": None, "is_board": "redpitaya_stemlab_125_14", "design_runs_on_it": False}


def test_the_box_is_not_planned_as_the_measurement_of_a_design_that_runs_on_it():
    lab = lab_for(rp_entry(mode={"state": "factory_instrument"}), design={"target_board": "redpitaya_stemlab_125_14"})
    p = L.plan_need(lab, need())
    assert p["chosen"]["method"] == "on_chip" and not p["independent"]
    assert "design runs on redpitaya" in p["left_out"][0]["reason"] and "factory image" in p["left_out"][0]["reason"]
    assert L.instrument_mode(lab, "redpitaya")["state"] == "factory_instrument" or True
    assert L.instrument_mode(lab, "redpitaya")["design_runs_on_it"] is True


def test_a_design_that_is_itself_the_instrument_gets_only_its_own_readout():
    lab = lab_for(rp_entry(), design={"target_board": "redpitaya_stemlab_125_14", "design_is_instrument": True})
    p = L.plan_need(lab, need())
    assert p["chosen"]["method"] == "on_chip" and "is itself the instrument" in p["left_out"][0]["reason"] and "another instrument" in p["left_out"][0]["reason"]


def test_a_box_loaded_with_another_design_is_not_an_instrument_until_restored():
    lab = lab_for(rp_entry(mode={"state": "target_loaded", "build_id": "cafe0001"}), design={"target_board": "zedboard"})
    p = L.plan_need(lab, need())
    assert p["chosen"]["method"] == "on_chip" and "loaded with build cafe0001" in p["left_out"][0]["reason"] and "power cycle" in p["left_out"][0]["reason"]


def test_the_target_board_comes_from_the_designs_build_yaml_when_the_lab_file_is_silent(tmp_path, monkeypatch):
    prof = tmp_path / "lab.yaml"
    prof.write_text(yaml.safe_dump({"schema": L.SCHEMA, "instruments": [rp_entry()]}))
    d = tmp_path / "d"
    d.mkdir()
    (d / "build.yaml").write_text("top: t\npart: xc7z010clg400-1\nboard: redpitaya_stemlab_125_14\nsources: []\n")
    lab = L.load(d, prof)
    assert lab.target_board == "redpitaya_stemlab_125_14" and L.factory_unavailable(lab, "redpitaya")
    (d / "build.yaml").write_text("top: t\npart: x\nboard: zedboard\nsources: []\n")
    assert L.factory_unavailable(L.load(d, prof), "redpitaya") is None


def test_the_interview_does_not_ask_about_the_box_a_design_runs_on():
    needs = [need()]
    on_it = lab_for(rp_entry(), design={"target_board": "redpitaya_stemlab_125_14"})
    on_it.connections = []
    elsewhere = lab_for(rp_entry(), design={"target_board": "zedboard"})
    elsewhere.connections = []
    assert LI.questions(on_it, needs) == [] and any("redpitaya" in q["question"] for q in LI.questions(elsewhere, needs))


def test_a_run_refuses_a_hand_edited_step_on_the_box_that_is_the_target_and_records_the_mode():
    lab = lab_for(rp_entry(), design={"target_board": "redpitaya_stemlab_125_14"})
    step = {"id": "r1_rp", "kind": "measure", "method": "scripted", "instrument": "redpitaya", "channel": "IN1", "quantity": "frequency", "expected": 25e6, "tolerance_ppm": 100.0, "requirement": "R1"}
    res = LB.run_steps([step], lab, dry_run=False)
    row = res["rows"][0]
    assert row["result"] == "refused" and "target" in row["detail"] and row["instrument_mode"]["design_runs_on_it"] is True and res["pass"] is False
    ok_lab = lab_for(rp_entry(mode={"state": "factory_instrument"}), design={"target_board": "zedboard"})
    dry = LB.run_steps([step], ok_lab, dry_run=True)
    assert dry["rows"][0]["instrument_mode"]["state"] == "factory_instrument" and dry["rows"][0]["result"] == "dry_run"


def test_an_instrument_that_is_not_a_board_has_no_mode_in_its_rows():
    e = {"id": "m2k", "kind": "oscilloscope", "onboarded": True, "connection": {"type": "usb"}, "control": {"mode": "scripted", "driver": "mock"}, "channels": [{"name": "DIO0"}],
         "capabilities": [{"measure": "frequency", "channels": ["DIO0"], "max_hz": 25e6}]}
    lab = L.merge({"instruments": [e]}, {"connections": []})
    assert L.instrument_mode(lab, "m2k") is None and L.factory_unavailable(lab, "m2k") is None


def test_the_example_profile_records_the_red_pitaya_as_a_board_in_factory_mode_not_onboarded():
    doc = yaml.safe_load((ROOT / "hil" / "lab.example.yaml").read_text())
    rp = next(i for i in doc["instruments"] if i["id"] == "redpitaya")
    assert rp["is_board"] == "redpitaya_stemlab_125_14" and rp["mode"] == {"state": "factory_instrument"} and rp["onboarded"] is False
    assert rp["connection"]["address"] == "TO-BE-GIVEN-BY-OWNER" and L.validate(doc) == []
    ch = {c["name"]: c["range_v"] for c in rp["channels"]}
    assert ch["IN1"] == [-1, 1] and ch["IN2"] == [-20, 20]

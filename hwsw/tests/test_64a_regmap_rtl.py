"""pytest entry (brief 64A): the generated register blocks under cocotb + Icarus, driven by the generated Python driver
and (for demo_accel) the C driver, with the brief 59A AXI4-Lite checker on the wires; then seeded RTL mutants, each of
which the same bench must fail."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from flow import cocotb_run
from hwsw import regmap
from hwsw.tests import regmap_tb

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
BUILD = ROOT / "build" / "64a"
DEMO = ROOT / "hwsw" / "examples" / "demo_accel.yaml"
STRESS = HERE / "data" / "stress.yaml"
LEAN = HERE / "data" / "lean.yaml"
LEAN_NOCAP = HERE / "data" / "lean_nocap.yaml"


PROFILES = ROOT / "hwsw" / "examples" / "profiles"


def _prepare(yaml_path: Path, tag: str, sv_text: str | None = None,
             spec: Path | None = None) -> tuple[regmap.RegMap, dict, list[Path]]:
    if spec is not None:                      # the demo map under a design's profile (it names none and no `unmapped`)
        yaml_path = BUILD / f"{tag}_map.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text("".join(ln for ln in DEMO.read_text().splitlines(True) if not ln.startswith("unmapped:")))
    m = regmap.load(yaml_path, spec=spec)
    out = BUILD / tag
    if out.exists():
        shutil.rmtree(out)
    regmap.generate(m, out)
    if sv_text is not None:                                     # a mutant of the generated RTL
        (out / f"{m.name}_regs.sv").write_text(sv_text)
    tb, lay = regmap_tb.write(m, out)
    env = {"REGMAP_YAML": str(yaml_path), "REGMAP_OUT": str(out), "REGMAP_LAYOUT": str(lay),
           "REGMAP_SPEC": str(spec) if spec else ""}
    return m, env, [out / f"{m.name}_regs.sv", tb, *regmap_tb.CHECKER_SRC]


def _c_driver(gen: Path) -> Path:
    exe = BUILD / "c_cosim"
    cc = shutil.which("gcc") or shutil.which("cc")
    subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "hwsw" / "examples"), "-I", str(gen),
                    str(HERE / "c_cosim_harness.c"), "-o", str(exe)], check=True)
    return exe


def test_demo_accel_block_with_python_and_c_drivers() -> None:
    m, env, src = _prepare(DEMO, "demo_accel")
    env["REGMAP_CDRV"] = str(_c_driver(Path(env["REGMAP_OUT"])))
    cocotb_run.run("regmap_64a_demo", f"{m.name}_regs_tb", src, "regmap_cocotb", HERE, seed=1, extra_env=env)


def test_stress_layouts() -> None:
    m, env, src = _prepare(STRESS, "stress")
    cocotb_run.run("regmap_64a_stress", f"{m.name}_regs_tb", src, "regmap_cocotb", HERE, seed=1, extra_env=env)


@pytest.mark.parametrize("y", [LEAN, LEAN_NOCAP], ids=["lean", "lean_nocap"])
def test_okay_setting_with_and_without_the_capture(y: Path) -> None:
    """The okay setting (a read and a write to a hole both answer OKAY), once with the capture at its default place and
    once with it left out; demo_accel simulates split, stress slverr."""
    m, env, src = _prepare(y, y.stem)
    cocotb_run.run(f"regmap_64a_{y.stem}", f"{m.name}_regs_tb", src, "regmap_cocotb", HERE, seed=1, extra_env=env)


@pytest.mark.parametrize("profile", ["house", "amd_compatible", "strict"])
def test_each_interface_profile_on_the_demo_map(profile: str) -> None:
    """Brief 73: the same map under each profile, through the 59A transactor with the protocol checker on the wires and
    the model built from the resolved settings (including the profile_settings test, which exercises every setting)."""
    m, env, src = _prepare(DEMO, f"profile_{profile}", spec=PROFILES / f"spec_{profile}.yaml")
    assert m.profile == profile
    cocotb_run.run(f"regmap_73_{profile}", f"{m.name}_regs_tb", src, "regmap_cocotb", HERE, seed=1, extra_env=env)


# Seeded faults in the generated RTL: (id, map, text to replace, replacement, the tests that must catch it).
MUTANTS = [
    ("clear_beats_set", DEMO,
     "else irq_status_done_o <= (irq_status_done_o & ~(wr_irq_status ? w_data[0:0] & w_bits[0:0] : 1'h0)) | irq_status_done_set_i;",
     "else irq_status_done_o <= (irq_status_done_o | irq_status_done_set_i) & ~(wr_irq_status ? w_data[0:0] & w_bits[0:0] : 1'h0);",
     ["set_beats_clear_in_the_same_clock"]),
    ("strobes_ignored", STRESS,
     "assign w_bits = {{8{w_strb[3]}}, {8{w_strb[2]}}, {8{w_strb[1]}}, {8{w_strb[0]}}};",
     "assign w_bits = 32'hffffffff;", ["byte_strobes"]),
    # all three unmapped settings are tested: split (demo_accel, the default), okay (lean) and slverr (stress); each
    # response, read and write, has a fault of its own
    ("split_write_answers_slverr", DEMO, "RESP_UNMAPPED_WR = 2'b00;", "RESP_UNMAPPED_WR = 2'b10;",
     ["unmapped_addresses"]),
    ("split_read_answers_okay", DEMO, "RESP_UNMAPPED_RD = 2'b10;", "RESP_UNMAPPED_RD = 2'b00;", ["unmapped_addresses"]),
    ("okay_read_answers_slverr", LEAN, "RESP_UNMAPPED_RD = 2'b00;", "RESP_UNMAPPED_RD = 2'b10;", ["unmapped_addresses"]),
    ("okay_write_answers_slverr", LEAN, "RESP_UNMAPPED_WR = 2'b00;", "RESP_UNMAPPED_WR = 2'b10;",
     ["unmapped_addresses"]),
    ("slverr_read_answers_okay", STRESS, "RESP_UNMAPPED_RD = 2'b10;", "RESP_UNMAPPED_RD = 2'b00;",
     ["unmapped_addresses"]),
    ("slverr_write_answers_okay", STRESS, "RESP_UNMAPPED_WR = 2'b10;", "RESP_UNMAPPED_WR = 2'b00;",
     ["unmapped_addresses"]),
    # the error capture: it keeps the last bad access instead of the first, a clear in the clock of a bad access loses
    # that access, the count wraps instead of saturating, a bad write is not recorded as a write, the interrupt ignores
    # its enable
    ("capture_keeps_the_last", DEMO, "            if (ecap_first) begin", "            if (1'b1) begin",
     ["error_capture_records_the_first_and_counts"]),
    ("capture_clear_beats_a_new_access", DEMO, "end else if (ecap_bad_rd || ecap_bad_wr) begin",
     "end else if ((ecap_bad_rd || ecap_bad_wr) && !ecap_clr) begin", ["error_capture_same_clock_races"]),
    ("capture_count_wraps", DEMO, "ecap_count <= ecap_sum[8] ? {8{1'b1}} : ecap_sum[7:0];",
     "ecap_count <= ecap_sum[7:0];", ["error_capture_records_the_first_and_counts"]),
    ("capture_write_recorded_as_read", DEMO, "ecap_is_write <= !ecap_bad_rd;", "ecap_is_write <= 1'b0;",
     ["error_capture_records_the_first_and_counts"]),
    ("capture_write_wins_the_same_clock", DEMO,
     "ecap_addr <= ecap_bad_rd ? {s_axil_araddr[11:2], 2'b00} : {aw_word, 2'b00};",
     "ecap_addr <= ecap_bad_wr ? {aw_word, 2'b00} : {s_axil_araddr[11:2], 2'b00};", ["error_capture_same_clock_races"]),
    ("capture_clear_ignores_strobe", DEMO, "assign ecap_clr    = wr_err_status && w_data[0] && w_bits[0];",
     "assign ecap_clr    = wr_err_status && w_data[0];", ["error_capture_records_the_first_and_counts"]),
    ("capture_clear_keeps_the_count", DEMO, "        end else if (ecap_clr) begin\n            ecap_sticky <= 1'b0;\n            ecap_count <= 8'h0;",
     "        end else if (ecap_clr) begin\n            ecap_sticky <= 1'b0;", ["error_capture_records_the_first_and_counts"]),
    ("capture_irq_ignores_enable", STRESS, "else irq_o <= (ecap_sticky & ecap_irq_en);",
     "else irq_o <= ecap_sticky;", ["error_capture_interrupt"]),
    # the snapshot's high part loaded one clock after the low part: the halves of a 64-bit counter disagree at a carry
    ("snapshot_halves_apart", DEMO,
     "        else if (snap_job_cycles) job_cycles_hi_value_shadow <= job_cycles_hi_value_i;",
     "        else if (snap_late) job_cycles_hi_value_shadow <= job_cycles_hi_value_i;\n"
     "    end\n    logic snap_late;\n    always_ff @(posedge aclk) begin\n        snap_late <= snap_job_cycles;",
     ["snapshot_reads_across_a_carry"]),
    ("b_before_w", DEMO, "assign wr_commit      = aw_got && w_got && !s_axil_bvalid;",
     "assign wr_commit      = aw_got && !s_axil_bvalid;", ["random_soak_against_model"]),
    ("w1s_lost", STRESS,
     "else events_set_o <= (events_set_o & ~events_set_clr_i) | (wr_events ? w_data[29:24] & w_bits[29:24] : 6'h0);",
     "else events_set_o <= (events_set_o | (wr_events ? w_data[29:24] & w_bits[29:24] : 6'h0)) & ~events_set_clr_i;",
     ["set_beats_clear_in_the_same_clock"]),
    ("irq_ignores_enable", DEMO, "else irq_o <= |(rd_irq_status & rd_irq_enable);", "else irq_o <= |rd_irq_status;",
     ["interrupt_line"]),
    ("pulse_held", DEMO, "else cmd_start_pulse_o <= wr_cmd ? w_data[0:0] & w_bits[0:0] : 1'h0;",
     "else if (wr_cmd) cmd_start_pulse_o <= w_data[0:0] & w_bits[0:0];", ["field_access_types"]),
    ("arready_while_rvalid", DEMO, "assign s_axil_arready = !s_axil_rvalid;", "assign s_axil_arready = 1'b1;",
     ["read_while_response_pending_and_unaligned"]),
]


@pytest.mark.parametrize("mid,yaml_path,old,new,tests", MUTANTS, ids=[x[0] for x in MUTANTS])
def test_rtl_mutant_is_caught(mid, yaml_path, old, new, tests) -> None:
    m = regmap.load(yaml_path)
    good = regmap.emit_sv(m)
    assert good.count(old) == 1, f"mutant {mid}: the text to replace is not in the generated RTL exactly once"
    m, env, src = _prepare(yaml_path, f"mut_{mid}", good.replace(old, new))
    env["REGMAP_OPS"] = "200"
    with pytest.raises(AssertionError):
        cocotb_run.run(f"regmap_64a_mut_{mid}", f"{m.name}_regs_tb", src, "regmap_cocotb", HERE, testcase=tests, seed=1,
                       extra_env=env)


# Brief 73: seeded faults in the strict profile's RTL, one per setting and response; each must fail the bench's
# profile_settings test (or the capture's count). Same shape as MUTANTS, with the demo map under the strict profile.
STRICT_SPEC = PROFILES / "spec_strict.yaml"
STRICT_MUTANTS = [
    ("unaligned_write_accepted", "if (aw_lo != 2'b00) begin", "if (1'b0) begin", ["profile_settings"]),
    ("unaligned_write_answers_okay", "wr_rej = 1'b1;\n            end else begin", "wr_rej = 1'b0;\n            end else begin",
     ["profile_settings"]),
    ("unaligned_read_answers_okay", "s_axil_rresp <= rd_unal ? RESP_SLVERR : rd_hit ? RESP_OKAY : RESP_UNMAPPED_RD;",
     "s_axil_rresp <= rd_hit ? RESP_OKAY : RESP_UNMAPPED_RD;", ["profile_settings"]),
    ("unaligned_read_returns_data", "s_axil_rdata <= rd_unal ? 32'h0 : rd_value;", "s_axil_rdata <= rd_value;",
     ["profile_settings"]),
    ("partial_write_accepted", "wr_rej = ((w_strb & 4'b1100) != 4'b0000 && (w_strb & 4'b1100) != 4'b1100)",
     "wr_rej = (1'b0 && (w_strb & 4'b1100) != 4'b1100)", ["profile_settings"]),
    ("rejected_write_still_applies", "wr_ctrl = !wr_rej;", "wr_ctrl = 1'b1;", ["profile_settings"]),
    ("rejected_write_answers_okay", "!wr_hit ? RESP_UNMAPPED_WR : wr_rej ? RESP_SLVERR : RESP_OKAY;",
     "!wr_hit ? RESP_UNMAPPED_WR : RESP_OKAY;", ["profile_settings"]),
    ("reserved_write_accepted", "32'hf000fe8e) != 32'h0)", "32'h00000000) != 32'h0)", ["profile_settings"]),
    ("reserved_check_ignores_strobe", "(w_data & w_bits & 32'hf000fe8e)", "(w_data & 32'hf000fe8e)", ["profile_settings"]),
    ("capture_misses_rejected_writes", "assign ecap_bad_wr = wr_commit && (!wr_hit || wr_rej);",
     "assign ecap_bad_wr = wr_commit && !wr_hit;", ["profile_settings"]),
    ("capture_misses_unaligned_reads", "(!rd_hit || rd_unal);", "!rd_hit;", ["profile_settings"]),
]


@pytest.mark.parametrize("mid,old,new,tests", STRICT_MUTANTS, ids=[x[0] for x in STRICT_MUTANTS])
def test_strict_rtl_mutant_is_caught(mid, old, new, tests) -> None:
    m, env, src = _prepare(DEMO, f"smut_{mid}", spec=STRICT_SPEC)
    good = regmap.emit_sv(m)
    assert good.count(old) == 1, f"mutant {mid}: the text to replace is not in the generated RTL exactly once"
    m, env, src = _prepare(DEMO, f"smut_{mid}", good.replace(old, new), spec=STRICT_SPEC)
    env["REGMAP_OPS"] = "200"
    with pytest.raises(AssertionError):
        cocotb_run.run(f"regmap_73_mut_{mid}", f"{m.name}_regs_tb", src, "regmap_cocotb", HERE, testcase=tests, seed=1,
                       extra_env=env)

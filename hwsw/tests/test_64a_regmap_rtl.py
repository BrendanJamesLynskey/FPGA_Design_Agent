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


def _prepare(yaml_path: Path, tag: str, sv_text: str | None = None) -> tuple[regmap.RegMap, dict, list[Path]]:
    m = regmap.load(yaml_path)
    out = BUILD / tag
    if out.exists():
        shutil.rmtree(out)
    regmap.generate(m, out)
    if sv_text is not None:                                     # a mutant of the generated RTL
        (out / f"{m.name}_regs.sv").write_text(sv_text)
    tb, lay = regmap_tb.write(m, out)
    env = {"REGMAP_YAML": str(yaml_path), "REGMAP_OUT": str(out), "REGMAP_LAYOUT": str(lay)}
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


# Seeded faults in the generated RTL: (id, map, text to replace, replacement, the tests that must catch it).
MUTANTS = [
    ("clear_beats_set", DEMO,
     "else irq_status_done_o <= (irq_status_done_o & ~(wr_irq_status ? w_data[0:0] & w_bits[0:0] : 1'h0)) | irq_status_done_set_i;",
     "else irq_status_done_o <= (irq_status_done_o | irq_status_done_set_i) & ~(wr_irq_status ? w_data[0:0] & w_bits[0:0] : 1'h0);",
     ["set_beats_clear_in_the_same_clock"]),
    ("strobes_ignored", STRESS,
     "assign w_bits = {{8{w_strb[3]}}, {8{w_strb[2]}}, {8{w_strb[1]}}, {8{w_strb[0]}}};",
     "assign w_bits = 32'hffffffff;", ["byte_strobes"]),
    # both unmapped settings are tested: OKAY (demo_accel, the default) and SLVERR (stress, the option)
    ("unmapped_slverr_on_okay_map", DEMO, "localparam logic [1:0] RESP_UNMAPPED = 2'b00;",
     "localparam logic [1:0] RESP_UNMAPPED = 2'b10;", ["unmapped_addresses"]),
    ("unmapped_okay_on_slverr_map", STRESS, "localparam logic [1:0] RESP_UNMAPPED = 2'b10;",
     "localparam logic [1:0] RESP_UNMAPPED = 2'b00;", ["unmapped_addresses"]),
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

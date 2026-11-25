#!/usr/bin/env python3
"""The benchmark set of brief 142: name -> (group, top, sources, generics). Shared by the Yosys and the Vivado runners.

Micro cases (rtl/micro): one feature each, top = file name. Real cases (rtl/real): the arith library of briefs 139a/139b, four of
brief 137's CORDIC points and the four K26 (KR260 10G) blocks of brief 101. Generics are passed to Yosys as `read_slang -G` and to
Vivado as `synth_design -generic`.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
RTL = HERE / "rtl"


def _micro():
    out = {}
    for f in sorted((RTL / "micro").glob("m*.sv")):
        out[f.stem] = dict(group="micro", top=f.stem, sources=[f], generics={})
    return out


def _real():
    a, b, k, c = RTL / "real" / "arith_139a", RTL / "real" / "arith_139b", RTL / "real" / "k26_b96", RTL / "real" / "cordic"
    out = {}

    def add(name, group, top, srcs, **g):
        out[name] = dict(group=group, top=top, sources=srcs, generics=g)

    def ar(d, prefix, top, name, **g):
        add(name, "arith", top, sorted(d.glob(prefix)), **g)

    ar(a, "adder_*.sv", "adder_ripple_ooc", "r01_adder_ripple32", WIDTH=32)
    ar(a, "adder_*.sv", "adder_pipelined_ooc", "r02_adder_pipelined32x4", WIDTH=32, STAGES=4)
    ar(a, "adder_*.sv", "adder_carry_select_ooc", "r03_adder_csel32", WIDTH=32, BLOCK=8)
    ar(a, "mult_*.sv", "mult_dsp_ooc", "r04_mult_dsp18", WA=18, WB=18, SIGNED=1, STAGES=3)
    ar(a, "mult_*.sv", "mult_dsp_ooc", "r05_mult_dsp35", WA=35, WB=35, SIGNED=1, STAGES=3)
    ar(a, "mult_*.sv", "mult_lut_array_ooc", "r06_mult_lutarray18", WA=18, WB=18, SIGNED=1, REG=1)
    ar(a, "mult_*.sv", "mult_booth_r4_ooc", "r07_mult_booth18", WA=18, WB=18, SIGNED=1, REG=1)
    ar(a, "mac_*.sv", "mac_dsp_ooc", "r08_mac_dsp", WA=16, WB=16, LANES=1, ACCW=40, SIGNED=1, NREG=3)
    ar(a, "mac_*.sv", "mac_dsp_cascade_ooc", "r09_mac_cascade4", WA=16, WB=16, LANES=4, ACCW=40, SIGNED=1)
    ar(a, "mac_*.sv", "mac_fabric_ooc", "r10_mac_fabric", WA=16, WB=16, LANES=1)
    add("r11_div_pipe16", "arith", "divider_ooc", sorted(b.glob("div*.sv")), VARIANT=2, W=16, PIPE=1)
    add("r12_div_iter16", "arith", "divider_ooc", sorted(b.glob("div*.sv")), VARIANT=0, W=16, PIPE=1)
    add("r13_isqrt_pipe16", "arith", "isqrt_ooc", sorted(b.glob("isqrt*.sv")), VARIANT=1, W=16, PIPE=1)
    add("r14_lznorm_tree32", "arith", "lzc_norm_ooc", sorted(b.glob("lz*.sv")), VARIANT=0, W=32, PIPE=1)
    add("r15_fxp_round", "arith", "fxp_round_ooc", sorted(b.glob("fxp*.sv")), VARIANT=0, W_IN=32, S=12, W_OUT=18, MODE=2, SAT=1)
    for p in sorted(c.glob("*.sv")):
        pid = {"iterative": "c01", "unrolled": "c02", "pipelined_w": "c03", "pipelined_m": "c04"}
        key = "pipelined_m" if "pipelined_m" in p.stem else "unrolled" if "unrolled" in p.stem else "iterative" if "iterative" in p.stem else "pipelined_w"
        add(f"{pid[key]}_{p.stem.split('_w')[0] if key != 'pipelined_w' else 'cordic_pipelined'}", "cordic", p.stem, [p])
    add("k01_crc64_rx", "k26", "ooc_wrap", [k / "b96_pkg.sv", k / "crc64_rx.sv", k / "wrap_crc64_rx.sv"])
    add("k02_pcs_tx", "k26", "ooc_wrap", [k / "b96_pkg.sv", k / "pcs_tx.sv", k / "wrap_pcs_tx.sv"])
    add("k03_lg_small_comb", "k26", "ooc_wrap", [k / "lg_small_comb.sv", k / "wrap_lg_small_comb.sv"])
    add("k04_adder_tree8", "k26", "ooc_wrap", [k / "adder_tree8.sv", k / "wrap_adder_tree8.sv"])
    return out


BENCH = {**_micro(), **_real()}

if __name__ == "__main__":
    for n, d in BENCH.items():
        print(n, d["group"], d["top"], d["generics"])

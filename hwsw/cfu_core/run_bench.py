#!/usr/bin/env python3
"""Build an ip_lib entry into the BRV32P RV32 core as a custom instruction and measure it against pure software
(brief 64A+). Simulation only (Icarus Verilog 12); nothing is changed in the core's own repository.

    python3 hwsw/cfu_core/run_bench.py                       # baseline + both crc32_step variants -> results/64a_hwsw/
    python3 hwsw/cfu_core/run_bench.py --variants word --no-baseline --out build/64a/cfu_quick.json

For each configuration:
  1. copy the pinned core (hwsw/cfu_core/brv32p, see PINNED.md) to build/64a/cfu/<config>/;
  2. apply hwsw/cfu_core/brv32p_cfu.patch (a custom-2 decode, the unit instance, its result and busy wiring), except for
     the baseline, which is the pinned core as it is;
  3. generate the unit with hwsw/cfu.py from ip_lib/crc32_step's function_unit contract at the chosen variant;
  4. compile hwsw/cfu_core/bench/crc_bench.c with riscv64-unknown-elf-gcc (-O2, rv32imc; the clmul kernel with Zbkb
     and Zbkc), the data and zlib's expected CRCs written here;
  5. simulate the SoC with the core's own test bench (tests/isa/tb_isa.v) and read the cycle of each BENCH_MARK.

The program checks every CRC against zlib (also after a misaligned-load trap and under 16 timer interrupts that land
on custom instructions) and returns 0 only if all match; the unit's simulation monitor (CFU_MONITOR) counts the kills
by the wrapper's state at the kill, recorded per configuration; a run that does not end in RESULT PASS is
an error. The baseline must give the same cycles as the patched core for the three software kernels (the patch must
not change anything else), which this script checks.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hwsw import cfu  # noqa: E402
from ip_lib.crc32_step.model import crc32_word  # noqa: E402

HERE = Path(__file__).resolve().parent
PINNED = HERE / "brv32p"
PATCH = HERE / "brv32p_cfu.patch"
BUILD = ROOT / "build" / "64a" / "cfu"
SIZES = [16, 64, 256, 1024]
KERNELS = ["table", "bitwise", "clmul", "cfu"]
CROSS = os.environ.get("CROSS", "riscv64-unknown-elf-")
CFLAGS = ["-O2", "-falign-loops=4", "-mabi=ilp32", "-mcmodel=medany", "-ffreestanding"]
MARCH, MARCH_ZK = "rv32imc_zicsr", "rv32imc_zicsr_zbkb_zbkc"


def sh(cmd, cwd=None, **kw):
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, **kw)
    if p.returncode:
        raise RuntimeError(f"{' '.join(map(str, cmd))} failed:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}")
    return p.stdout


def bench_data(path: Path) -> None:
    rng = random.Random(64)
    buf = bytes(rng.getrandbits(8) for _ in range(max(SIZES)))
    tab = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        tab.append(c)
    trap_expect = crc32_word(0x12345678, 0x9ABCDEF0)
    L = ["/* written by hwsw/cfu_core/run_bench.py: the buffer, the CRC table and zlib's expected values */",
         "#include <stdint.h>",
         f"#define NSIZES {len(SIZES)}",
         f"#define TRAP_EXPECT 0x{trap_expect:08x}u",
         f"static const int SIZES[NSIZES] = {{{', '.join(map(str, SIZES))}}};",
         "static const uint32_t crc_expect[NSIZES] = {" + ", ".join(f"0x{zlib.crc32(buf[:n]):08x}u" for n in SIZES) + "};",
         "static const uint32_t crc32_tab[256] = {" + ", ".join(f"0x{t:08x}u" for t in tab) + "};",
         "static const uint8_t crc_buf[" + str(len(buf)) + "] __attribute__((aligned(64))) = {" +
         ", ".join(str(b) for b in buf) + "};"]
    path.write_text("\n".join(L) + "\n")


def prepare(cfg: str, variant: str | None) -> Path:
    d = BUILD / cfg
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(PINNED, d)
    (d / "rtl" / "cfu").mkdir()
    if variant:
        sh(["patch", "-p1", "-s", "-i", PATCH], cwd=d)
        cfu.generate("crc32_step", variant, d / "rtl" / "cfu")
    return d


def build_program(d: Path, with_cfu: bool) -> tuple[Path, str]:
    b = d / "prog"
    b.mkdir()
    bench_data(b / "bench_data.h")
    tb = d / "tests" / "bench"
    if not with_cfu:                          # the baseline compiles the same program: the header only, no unit
        cfu.generate("crc32_step", "word", d / "prog" / "cfu_h")
    inc = ["-I", b, "-I", tb, "-I", d / "rtl" / "cfu", "-I", d / "prog" / "cfu_h"]
    sh([f"{CROSS}gcc", *CFLAGS, f"-march={MARCH_ZK}", *inc, "-c", tb / "crc32_zk.c", "-o", b / "crc32_zk.o"])
    defs = [f"-DHAVE_CFU={1 if with_cfu else 0}"]
    sh([f"{CROSS}gcc", *CFLAGS, f"-march={MARCH}", *defs, *inc, "-static", "-nostdlib", "-nostartfiles",
        "-T", tb / "link.ld", tb / "crt.S", HERE / "bench" / "crc_bench.c", tb / "crc32.c", b / "crc32_zk.o",
        "-o", b / "crc.elf"])
    sh([f"{CROSS}objcopy", "-O", "binary", b / "crc.elf", b / "crc.bin"])
    sh([sys.executable, d / "tests" / "isa" / "elf2hex.py", b / "crc.bin", b / "crc.hex"])
    (b / "crc.dis").write_text(sh([f"{CROSS}objdump", "-d", b / "crc.elf"]))
    tohost = next(ln.split()[0] for ln in sh([f"{CROSS}nm", b / "crc.elf"]).splitlines() if ln.endswith(" tohost"))
    return b, tohost


def simulate(d: Path, prog: Path, tohost: str, with_cfu: bool) -> dict:
    files = sorted((d / "rtl" / "core").glob("*.v")) + sorted((d / "rtl" / "cache").glob("*.v"))
    files += [d / "rtl" / "bus" / f for f in ("axi_interconnect.v", "axi_sram.v", "axi_periph_bridge.v")]
    files += sorted((d / "rtl" / "periph").glob("*.v")) + [d / "rtl" / "brv32p_soc.v", d / "tests" / "isa" / "tb_isa.v"]
    if with_cfu:
        files += [ROOT / "ip_lib" / "crc32_step" / "rtl" / "crc32_step.sv", d / "rtl" / "cfu" / "cfu_crc32_step.sv"]
    vvp = d / "tb.vvp"
    sh(["iverilog", "-g2012", "-DTB_MEM_DEPTH=16384", "-DCFU_MONITOR", "-o", vvp, "-I", d / "rtl" / "pkg", "-I", d / "rtl" / "core",
        "-I", d / "rtl" / "cfu", *files])
    marks = d / "marks.txt"
    out = sh(["vvp", "-n", vvp, f"+hex={prog / 'crc.hex'}", f"+tohost={tohost}", f"+marks={marks}", "+timeout=3000000"],
             cwd=d, timeout=3600)
    res = next((ln for ln in out.splitlines() if ln.startswith("RESULT")), "RESULT ERROR (no result line)")
    m = {}
    for ln in marks.read_text().splitlines() if marks.exists() else []:
        n, c = map(int, ln.split())
        m[n] = c
    return {"result": res, "marks": m, "monitor": monitor(out)}


def monitor(out: str) -> dict:
    """The wrapper's CFU_MONITOR lines, counted: each kill of a custom instruction in EX by the unit's state at that
    clock, and each start that had to wait for a killed operation still in the unit."""
    kills: dict[str, int] = {}
    waits = 0
    for ln in out.splitlines():
        if ln.startswith("CFU_MONITOR kill"):
            f = dict(x.split("=") for x in ln.split()[2:])
            if f["active"] == "0":
                k = "before_start"                     # the trap came in the first EX clock: the unit never started
            elif f["inflight"] == "1":
                k = "in_flight"                        # started, operation still marked in flight in the wrapper
            else:
                k = "result_held"                      # the unit had finished; its result was waiting in the wrapper
            kills[k] = kills.get(k, 0) + 1
        elif ln.startswith("CFU_MONITOR wait"):
            waits += 1
    return {"kills": dict(sorted(kills.items())), "starts_delayed_by_inflight": waits}


def kernels(marks: dict, with_cfu: bool) -> dict:
    out = {}
    for s, n in enumerate(SIZES):
        for k, name in enumerate(KERNELS):
            if name == "cfu" and not with_cfu:
                continue
            a, b = 16 * s + 2 * k, 16 * s + 2 * k + 1
            if a in marks and b in marks:
                out.setdefault(name, {})[str(n)] = {"cycles": marks[b] - marks[a],
                                                     "cycles_per_byte": round((marks[b] - marks[a]) / n, 3)}
    return out


def run(variants: list[str], baseline: bool) -> dict:
    tool = {"gcc": sh([f"{CROSS}gcc", "--version"]).splitlines()[0], "iverilog": sh(["iverilog", "-V"]).splitlines()[0]}
    pinned = (HERE / "PINNED.md").read_text().split("commit ")[1].split()[0] if (HERE / "PINNED.md").exists() else "?"
    rec = {"schema": "cfu_bench/1", "core": f"BRV32P (RISCV_RV32IMC_5stage) at {pinned}, pinned copy in hwsw/cfu_core/brv32p",
           "unit": "ip_lib/crc32_step via hwsw/cfu.py, custom-2 opcode, funct3 0, funct7 0",
           "program": "hwsw/cfu_core/bench/crc_bench.c, -O2, rv32imc_zicsr (clmul kernel: + zbkb_zbkc)",
           "simulator": tool["iverilog"], "compiler": tool["gcc"], "sizes_bytes": SIZES,
           "cycles": "from BENCH_MARK(2k) retiring to BENCH_MARK(2k+1) retiring, caches warmed by a first call",
           "configs": {}}
    cfgs = ([("baseline", None)] if baseline else []) + [(f"cfu_{v}", v) for v in variants]
    for cfg, v in cfgs:
        d = prepare(cfg, v)
        prog, tohost = build_program(d, v is not None)
        sim = simulate(d, prog, tohost, v is not None)
        if not sim["result"].startswith("RESULT PASS"):
            raise RuntimeError(f"{cfg}: {sim['result']} (a CRC differs from zlib, or the core trapped or hung)")
        rec["configs"][cfg] = {"variant": v, "latency_clocks": cfu.latency("crc32_step", v) if v else None,
                               "result": sim["result"], "kernels": kernels(sim["marks"], v is not None)}
        if v:
            rec["configs"][cfg]["monitor"] = sim["monitor"]
        print(f"{cfg}: {sim['result']}", flush=True)
    if baseline and variants:
        base = rec["configs"]["baseline"]["kernels"]
        for cfg, v in cfgs[1:]:
            for k in ("table", "bitwise", "clmul"):
                if rec["configs"][cfg]["kernels"][k] != base[k]:
                    raise RuntimeError(f"{cfg}: the patch changed the cycles of the software kernel {k}")
        rec["patch_is_transparent"] = "table, bitwise and clmul cycles equal in the baseline and every patched core"
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 hwsw/cfu_core/run_bench.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--variants", default="word,byte")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "results" / "64a_hwsw" / "cfu_crc32.json"))
    a = ap.parse_args(argv)
    rec = run([v for v in a.variants.split(",") if v], not a.no_baseline)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    for cfg, c in rec["configs"].items():
        for k, by in c["kernels"].items():
            print(f"{cfg:12s} {k:8s} " + "  ".join(f"{n:>5}B {v['cycles_per_byte']:7.3f} c/B" for n, v in by.items()))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

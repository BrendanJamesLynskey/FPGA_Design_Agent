#!/usr/bin/env python3
"""Yosys synth_xilinx over the brief 142 benchmark set; writes yosys/<family>/<variant>/<name>.json (cell counts) and, when asked, the EDIF.

    python3 yosys_run.py [--families xcup xc7] [--variants def flat tuned dff] [--names ...] [--jobs 2] [--edif-dir DIR]

Variants (all with -noiopad -noclkbuf, as out-of-context flows need):
  def    synth_xilinx -family F -top T                          (the options a user gets without reading the manual)
  flat   ... -flatten
  tuned  ... -flatten -widemux 5 [-uram on xcup]                (the options that switch on hard muxes and URAM inference)
  dff    ... -flatten -dff                                       (abc9 sees flip-flops)
  c8     xcup only: flat plus the draft CARRY8 mapping (drafts/pr_1)
abc9 is the default LUT mapper in this Yosys (0.70+385); there is no separate -abc9 switch.
"""
import argparse, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from manifest import BENCH  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "yosys"
OSS = Path(os.environ.get("FDA_OSS_CAD", Path.home() / ".local/opt/oss-cad-suite"))
OPTS = {"def": "", "flat": "-flatten", "tuned": "-flatten -widemux 5", "dff": "-flatten -dff", "c8": "-flatten"}
# c8 (xcup only): "flat" with the draft CARRY8 mapping of drafts/pr_1 (techmap run by hand with -D HAS_CARRY8, as the patched synth_xilinx would)
PATCHED_ARITH = Path(__file__).resolve().parents[1] / "drafts" / "pr_1" / "arith_map_carry8.v"


def run(name, fam, var, edif_dir):
    b = BENCH[name]
    d = OUT / fam / var
    d.mkdir(parents=True, exist_ok=True)
    gen = " ".join(f"-G {k}={v}" for k, v in b["generics"].items())
    opts = OPTS[var] + (" -uram" if var == "tuned" and fam == "xcup" else "")
    sj = d / f"{name}.stat.json"
    base = f"synth_xilinx -family {fam} -top {b['top']} -noiopad -noclkbuf {opts}"
    if var == "c8":
        synth = (f"{base} -run begin:fine; opt -full; xilinx_srl -variable -minlen 3; "
                 f"techmap -map +/techmap.v -D LUT_SIZE=6 -D HAS_CARRY8 -map {PATCHED_ARITH}; opt -fast; {base} -run map_cells:")
    else:
        synth = base
    cmds = (f"plugin -i slang; read_slang --top {b['top']} {gen} " + " ".join(map(str, b["sources"])) +
            f"; {synth}; tee -q -o {sj} stat -json -tech xilinx")
    if edif_dir:
        e = Path(edif_dir) / fam / var
        e.mkdir(parents=True, exist_ok=True)
        cmds += f"; write_edif -pvector bra {e / (name + '.edif')}; write_verilog -noattr {e / (name + '.v')}"
    env = dict(os.environ, PATH=f"{OSS}/bin:" + os.environ["PATH"])
    t0 = time.time()
    r = subprocess.run([str(OSS / "bin/yosys"), "-q", "-l", str(d / f"{name}.log"), "-p", cmds], capture_output=True, text=True, env=env, timeout=900)
    rec = dict(name=name, family=fam, variant=var, yosys_args=f"synth_xilinx -family {fam} -top {b['top']} -noiopad -noclkbuf {opts}".replace("  ", " "),
               seconds=round(time.time() - t0, 1), rc=r.returncode)
    if r.returncode == 0 and sj.exists():
        js = json.loads(sj.read_text())
        mods = js["modules"]
        top = mods.get(b["top"]) or next(iter(mods.values()))
        rec["cells"] = top.get("num_cells_by_type", {})
        rec["design_cells"] = js.get("design", {}).get("num_cells_by_type", rec["cells"])
    else:
        rec["error"] = (r.stderr or r.stdout)[-400:]
    (d / f"{name}.json").write_text(json.dumps(rec, indent=1))
    if sj.exists():
        sj.unlink()
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", nargs="+", default=["xcup", "xc7"])
    ap.add_argument("--variants", nargs="+", default=["def", "flat", "tuned", "dff"])
    ap.add_argument("--names", nargs="*")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--edif-dir")
    a = ap.parse_args()
    names = a.names or list(BENCH)
    todo = [(n, f, v) for n in names for f in a.families for v in a.variants]
    bad = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for rec in ex.map(lambda t: run(*t, a.edif_dir), todo):
            if "error" in rec:
                bad += 1
                print("FAIL", rec["name"], rec["family"], rec["variant"], rec["error"][-200:].replace("\n", " "))
    print(f"{len(todo)} runs, {bad} failed")


if __name__ == "__main__":
    main()

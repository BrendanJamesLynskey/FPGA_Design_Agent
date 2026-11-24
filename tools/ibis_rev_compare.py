#!/usr/bin/env python3
"""Brief 162 (owner decision 29c): does a newer, non-preliminary AMD IBIS file change brief 155's extraction?

    python3 tools/ibis_rev_compare.py [--old /opt/Xilinx/2025.2/data/parts/xilinx] [--new /opt/Xilinx/2026.1/data/parts/xilinx] [--out results/162_kr260_si/ibis_revision_check.csv]

Part 1 (byte comparison): the three files brief 155 uses, in the two Vivado releases installed here. Part 2 (extraction): the 2026.1 ``kintexuplus.ibs`` (File Rev 2.15,
25-OCT-2025, no "preliminary" note) against ``zynquplus.ibs`` (File Rev 2.11, 10-FEB-2022, "All models are preliminary"): the same HP LVCMOS18 / HD models'
output resistance into 50 ohm at the three corners, by the same code as brief 155 (``flow/offchip_model.r_launch``). Kintex/Artix UltraScale+ is a different
device family from the K26's Zynq UltraScale+; the comparison shows how far AMD's silicon-measured data differs, not what the K26 does.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow"))
sys.path.insert(0, str(ROOT / "tools"))
import ibis_extract as X     # noqa: E402
import offchip_model as M    # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def extract(path: Path, pattern: str, key: str) -> dict:
    text = path.read_text(errors="replace")
    out = {}
    rx = re.compile(pattern)
    for name, lines in X.split_models(text).items():
        m = rx.match(name)
        if not m:
            continue
        d = X.parse_model(lines)
        if not d.get("pulldown") or not d.get("pullup") or "vcc" not in d or not d["t2080_s"].get("r"):
            continue
        d.update(file=key, std=m.group(1), slew=m.group(2), setting=int(m.group(3)))
        out[name] = d
    return out


def drv(m: dict, corner: str) -> M.Driver:
    c = M.CORNERS.index(corner)
    return M.Driver(name="x", corner=corner, vcc=m["vcc"][c], pu=M.Curve(m["pullup"], c + 1), pd=M.Curve(m["pulldown"], c + 1), c_comp=m["c_comp_f"][c],
                    t2080_r=m["t2080_s"]["r"][c], t2080_f=m["t2080_s"]["f"][c], vinl=m["vinl"], vinh=m["vinh"], r_load_ibis=m["t2080_s"].get("r_load", 50.0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="/opt/Xilinx/2025.2/data/parts/xilinx")
    ap.add_argument("--new", default="/opt/Xilinx/2026.1/data/parts/xilinx")
    ap.add_argument("--out", default=str(ROOT / "results/162_kr260_si/ibis_revision_check.csv"))
    a = ap.parse_args()
    old, new = Path(a.old), Path(a.new)
    print("part 1: the files brief 155 uses, Vivado 2025.2 vs 2026.1")
    for fam in ("artix7", "zynq", "zynquplus"):
        po, pn = old / fam / "public/ibis" / f"{fam}.ibs", new / fam / "public/ibis" / f"{fam}.ibs"
        print(f"  {fam}: sha256[:12] {sha(po)} {sha(pn)} {'identical' if po.read_bytes() == pn.read_bytes() else 'DIFFERENT'}")
    zu = extract(old / "zynquplus/public/ibis/zynquplus.ibs", r"^(HP_LVCMOS18)_([FMS])_(\d+)$", "zynquplus")
    ku = extract(new / "kintexuplus/public/ibis/kintexuplus.ibs", r"^(HP_LVCMOS18)_([FMS])_(\d+)$", "kintexuplus")
    rows = []
    for name in sorted(set(zu) & set(ku), key=lambda n: (n.split("_")[2], int(n.split("_")[3]))):
        for corner in M.CORNERS:
            rz, rk = M.r_launch(drv(zu[name], corner), 50.0), M.r_launch(drv(ku[name], corner), 50.0)
            c = M.CORNERS.index(corner)
            rows.append({"model": name, "corner": corner, "r_pu_zynquplus_ohm": round(rz["r_pu"], 1), "r_pu_kintexuplus_ohm": round(rk["r_pu"], 1),
                         "r_pd_zynquplus_ohm": round(rz["r_pd"], 1), "r_pd_kintexuplus_ohm": round(rk["r_pd"], 1),
                         "t2080_rise_ns_zynquplus": round(zu[name]["t2080_s"]["r"][c] * 1e9, 3), "t2080_rise_ns_kintexuplus": round(ku[name]["t2080_s"]["r"][c] * 1e9, 3),
                         "c_comp_pf_zynquplus": round(zu[name]["c_comp_f"][c] * 1e12, 2), "c_comp_pf_kintexuplus": round(ku[name]["c_comp_f"][c] * 1e12, 2)})
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    worst = max(abs(r["r_pu_kintexuplus_ohm"] / r["r_pu_zynquplus_ohm"] - 1) for r in rows)
    print(f"part 2: {len(rows)} model-corner rows -> {a.out}; largest pull-up resistance difference {100 * worst:.1f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

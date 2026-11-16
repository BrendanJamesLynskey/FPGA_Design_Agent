#!/usr/bin/env python3
"""flow/lowbit.py: the brief 91 low-bit-format network generator as a flow tool (designs/b91_lowbit/lowbit is the
code; designs/b91_lowbit/docs/design.md defines the formats).

    python3 -m flow.lowbit train --data <npz> --fmt <format> --out <model.json> [--hidden 16 8] [--act-bits 4]
        [--epochs 30] [--seed 0]
        <npz> holds X_train, y_train, X_val, y_val (unsigned integer features, classes 0..2). Formats: binary_t3,
        binary_t7, ternary, int4, mxfp4, log4, log4_nz, log4p1. Needs torch (CPU).
    python3 -m flow.lowbit emit --model <model.json> --name <module> --fbits 8 8 4 ... --pipe comb|layer --out <module.sv>
        SystemVerilog with the arm ports (clk, rst, in_v, in_f, out_v, out_cls) and a LATENCY localparam.
    python3 -m flow.lowbit predict --model <model.json> --data <npz> --key X_val
        prints the twin's classes (the bit-exact reference for the RTL), one per line.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from designs.b91_lowbit.lowbit import model as M  # noqa: E402
from designs.b91_lowbit.lowbit import rtl as R  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--data", required=True)
    t.add_argument("--fmt", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--hidden", type=int, nargs="+", default=[16, 8])
    t.add_argument("--act-bits", type=int, default=4)
    t.add_argument("--epochs", type=int, default=30)
    t.add_argument("--seed", type=int, default=0)
    e = sub.add_parser("emit")
    e.add_argument("--model", required=True)
    e.add_argument("--name", required=True)
    e.add_argument("--fbits", type=int, nargs="+", required=True)
    e.add_argument("--pipe", default="comb", choices=["comb", "layer"])
    e.add_argument("--out", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--model", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--key", default="X_val")
    a = ap.parse_args(argv)
    if a.cmd == "train":
        z = np.load(a.data)
        cfg = M.Config(fmt=a.fmt, hidden=a.hidden, act_bits=a.act_bits, epochs=a.epochs, seed=a.seed)
        m = M.train(cfg, z["X_train"], z["y_train"], z["X_val"], z["y_val"])
        M.save(m, Path(a.out))
        print(f"val {m['val_accuracy']} (epoch {m['epoch_kept']}), {M.weight_stats(m)}")
    elif a.cmd == "emit":
        m = M.load(Path(a.model))
        if len(a.fbits) != len(m["input"]["thresholds"]):
            ap.error(f"--fbits has {len(a.fbits)} widths; the model has {len(m['input']['thresholds'])} features")
        Path(a.out).write_text(R.emit(m, a.name, a.fbits, pipe=a.pipe, source=a.model))
    else:
        m = M.load(Path(a.model))
        print("\n".join(str(int(c)) for c in M.twin_predict(m, np.load(a.data)[a.key])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

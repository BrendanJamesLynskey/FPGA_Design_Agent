#!/usr/bin/env python3
"""flow/lutgen.py: the brief 89 LUT-network generator as a flow tool (designs/b89_lutnet_gen/lutgen is the code;
docs/generator.md there is the datasheet).

    python3 -m flow.lutgen train --data <npz> --config <json> --out <model.json>
        <npz> holds X_train, y_train, X_val, y_val (unsigned integer features, classes 0..2); <json> is a
        lutgen Config as a dict (missing fields take their defaults). Needs torch (CPU).
    python3 -m flow.lutgen emit --model <model.json> --name <module> --fbits 8 8 4 ... --pipe comb|layer|N
        [--reg-encoder] --out <module.sv>
        SystemVerilog with the arm ports (clk, rst, in_v, in_f, out_v, out_cls) and a LATENCY localparam.
    python3 -m flow.lutgen predict --model <model.json> --data <npz> --key X_val
        prints the twin's classes (the bit-exact reference for the RTL), one per line.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from designs.b89_lutnet_gen.lutgen import model as M  # noqa: E402
from designs.b89_lutnet_gen.lutgen import rtl as R  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--data", required=True)
    t.add_argument("--config", required=True)
    t.add_argument("--out", required=True)
    e = sub.add_parser("emit")
    e.add_argument("--model", required=True)
    e.add_argument("--name", required=True)
    e.add_argument("--fbits", type=int, nargs="+", required=True)
    e.add_argument("--pipe", default="layer")
    e.add_argument("--reg-encoder", action="store_true")
    e.add_argument("--out", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--model", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--key", default="X_val")
    a = ap.parse_args(argv)
    if a.cmd == "train":
        z = np.load(a.data)
        m = M.train(M.Config.from_dict(json.loads(Path(a.config).read_text())), z["X_train"], z["y_train"],
                    z["X_val"], z["y_val"])
        M.save(m, Path(a.out))
        print(f"val {m['val_accuracy']} (epoch {m['epoch_kept']}), table bits {M.table_bits(m)['table_bits_total']}")
    elif a.cmd == "emit":
        pipe = int(a.pipe) if a.pipe.isdigit() else a.pipe
        m = json.loads(Path(a.model).read_text())
        if len(a.fbits) != len(m["thresholds"]):
            ap.error(f"--fbits has {len(a.fbits)} widths; the model has {len(m['thresholds'])} features")
        Path(a.out).write_text(R.emit(m, a.name, a.fbits, pipe=pipe, reg_encoder=a.reg_encoder, source=a.model))
    else:
        m = json.loads(Path(a.model).read_text())
        print("\n".join(str(int(c)) for c in M.twin_predict(m, np.load(a.data)[a.key])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

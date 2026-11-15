"""Arm (b) through hls4ml: the same quantised MLP as the hand RTL (results/b87/models/mlp.json), converted by hls4ml
with fixed-point types chosen to reproduce the integer model, checked in hls4ml's C simulation over the test split,
then synthesised with Vitis HLS (`vitis-run --mode hls`).

    python3 -m designs.b87_ml_trading.model.hls4ml_arm --out build/b87/hls4ml [--synth] [--clock 2.5]

Writes results/b87/hls4ml_csim.json (agreement with the integer model, test accuracy) and, with --synth, copies the
HLS report summary to results/b87/hls4ml_synth/.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np

from . import arms as A
from . import lobsim as L

ROOT = Path(__file__).resolve().parents[3]
PART = "xck26-sfvc784-2LV-c"


def torch_model(q):
    import torch

    class M(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.fc0 = torch.nn.Linear(7, 16)
            self.relu0 = torch.nn.ReLU()
            self.fc1 = torch.nn.Linear(16, 8)
            self.relu1 = torch.nn.ReLU()
            self.fc2 = torch.nn.Linear(8, 3)

        def forward(self, x):
            return self.fc2(self.relu1(self.fc1(self.relu0(self.fc0(x)))))

    m = M()
    with torch.no_grad():
        for i, fc in enumerate((m.fc0, m.fc1, m.fc2)):
            fc.weight[:] = torch.tensor(np.array(q["W"][i]) / 2.0 ** q["fw"][i], dtype=torch.float64)
            fc.bias[:] = torch.tensor(np.array(q["b"][i]) / 2.0 ** (q["fw"][i] + q["fin"][i]), dtype=torch.float64)
    return m.double().eval()


def config(q):
    def fx(w, frac, signed=True, extra=""):
        return f"ap_{'' if signed else 'u'}fixed<{w},{w - frac}{extra}>"

    c = {"Model": {"Precision": "ap_fixed<24,12>", "ReuseFactor": 1, "Strategy": "Latency"}, "LayerName": {}}
    ln = c["LayerName"]
    ln["fc0_input"] = {"Precision": {"result": fx(10, q["fin"][0])}}
    for i in range(3):
        fw, fin = q["fw"][i], q["fin"][i]
        acc = fx(26, fw + fin)
        ln[f"fc{i}"] = {"Precision": {"weight": fx(8, fw), "bias": fx(26, fw + fin), "result": acc, "accum": acc},
                        "ReuseFactor": 1}
        if i < 2:
            ln[f"relu{i}"] = {"Precision": {"result": fx(8, q["fa"][i], False, ",AP_TRN,AP_SAT")}}
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "b87" / "hls4ml"))
    ap.add_argument("--synth", action="store_true")
    ap.add_argument("--clock", type=float, default=2.5)
    a = ap.parse_args()
    import hls4ml
    q = json.loads((ROOT / "results" / "b87" / "models" / "mlp.json").read_text())
    m = torch_model(q)
    cfg = config(q)
    hm = hls4ml.converters.convert_from_pytorch_model(m, input_shape=(None, 7), hls_config=cfg, output_dir=a.out,
                                                      backend="Vitis", part=PART, clock_period=a.clock,
                                                      io_type="io_parallel", project_name="mlp_hls4ml")
    hm.compile()
    X, y, g = L.split("test")
    xin = ((X - np.array(q["offsets"])) / 2.0 ** q["fin"][0]).astype(np.float64)
    logits = hm.predict(np.ascontiguousarray(xin))
    ref = A.mlp_logits_int(q, X) / 2.0 ** (q["fw"][2] + q["fin"][2])
    pred = np.argmax(logits, axis=1)
    rec = {"hls4ml": hls4ml.__version__, "backend": "Vitis", "part": PART, "io_type": "io_parallel",
           "strategy": "Latency", "reuse_factor": 1, "clock_target_ns": a.clock, "config": cfg,
           "test_samples": int(len(X)),
           "logits_bit_exact_with_integer_model": bool(np.array_equal(logits, ref)),
           "max_abs_logit_difference": float(np.max(np.abs(logits - ref))),
           "class_agreement_with_integer_model": float((pred == A.mlp_predict_int(q, X)).mean()),
           "test_accuracy_pooled": float((pred == y).mean())}
    out = ROOT / "results" / "b87"
    if a.synth:
        os.environ["PATH"] = "/opt/Xilinx/2026.1/Vitis/bin:" + os.environ["PATH"]
        t0 = time.time()
        try:
            rep = hm.build(csim=False, synth=True, export=False, vsynth=False)
            rec["synth_report"] = rep
        except Exception as e:                                   # record the exact error
            rec["synth_error"] = repr(e)
        rec["synth_seconds"] = round(time.time() - t0, 1)
        d = out / "hls4ml_synth"
        d.mkdir(exist_ok=True)
        for f in Path(a.out).rglob("*_csynth.rpt"):
            shutil.copy(f, d / f.name)
        for f in Path(a.out).rglob("vitis_hls.log"):
            shutil.copy(f, d / "vitis_hls.log")
    (out / "hls4ml_csim.json").write_text(json.dumps(rec, indent=1, default=str))
    print(json.dumps({k: v for k, v in rec.items() if k not in ("config", "synth_report")}, indent=1, default=str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""summarise.py (brief 129): the measured table of results/129_iob_packing from the per-variant io_times.csv files.
    python3 results/129_iob_packing/summarise.py            # prints the Markdown table (and writes measured.md)
Per variant: the registers packed, and for the RMII inputs (ETH_CRSDV, ETH_RXERR, ETH_RXD) the worst setup and hold slack and the
largest data-path delay; for the outputs (ETH_TXEN, ETH_TXD) the worst setup and hold slack and the largest data-path delay (the
clock-to-out at the pin, from the launching clock edge)."""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ["packed", "unpacked", "gate_in", "gate_out", "fanout_out", "packed_Explore", "unpacked_Explore", "packed_AltSpreadLogic_high",
         "unpacked_AltSpreadLogic_high"]


def row(name: str) -> dict:
    rows = list(csv.DictReader((HERE / "runs" / name / "io_times.csv").open()))
    out = {"variant": name}
    for d in ("in", "out"):
        for t in ("setup", "hold"):
            xs = [float(r["slack_ns"]) for r in rows if r["dir"] == d and r["type"] == t and r["slack_ns"]]
            out[f"{d}_{t}"] = min(xs)
        dp = [float(r["datapath_ns"]) for r in rows if r["dir"] == d and r["type"] == "setup" and r["datapath_ns"]]
        out[f"{d}_path"] = max(dp)
    ck = json.loads((HERE / "runs" / name / "iob_summary.json").read_text())
    out["packed_regs"] = f"{ck['packed']}/{ck['registers']}"
    out["check"] = ck["verdict"]
    return out


def main() -> None:
    names = [n for n in ORDER if (HERE / "runs" / n / "io_times.csv").is_file()]
    head = ("| Variant | Registers in the I/O block | Input setup slack | Input hold slack | Input data path | Output setup slack | "
            "Output hold slack | Output data path (clock to pin) | iob check |\n|---|---|---|---|---|---|---|---|---|\n")
    body = ""
    for n in names:
        r = row(n)
        body += (f"| {n} | {r['packed_regs']} | {r['in_setup']:+.3f} | {r['in_hold']:+.3f} | {r['in_path']:.3f} | {r['out_setup']:+.3f} | "
                 f"{r['out_hold']:+.3f} | {r['out_path']:.3f} | {r['check']} |\n")
    (HERE / "measured.md").write_text(head + body)
    sys.stdout.write(head + body)


if __name__ == "__main__":
    main()

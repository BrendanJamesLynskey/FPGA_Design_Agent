#!/usr/bin/env python3
"""Part A of 82P5: how each of the six 82P4 runs decoded the register-number field of a read or write packet, in the model, the
RTL and the bench helpers. Reads the private run archives (KB results_private/benchmark/v2/runs/b82p4/artifacts/<run>/run_dir.tar.gz),
extracts the lines that decode or build the field, writes register_width_by_run.json. Nothing here is scored.

    python3 register_width_by_run.py <kb results_private b82p4 artifacts dir> > register_width_by_run.json
"""
import io
import json
import re
import sys
import tarfile
from pathlib import Path

RUNS = {"A r1": "20261119-231744-448e", "B r1": "20261120-022213-afd9", "A r2": "20261120-041922-a5da",
        "B r2": "20261120-072336-553a", "A r3": "20261120-075215-97ce", "B r3": "20261120-104735-68eb"}
PAT = {"model.py": re.compile(r"\b(pl|pay)\[[0-9:]+\]|r = pl|reg = |need = \{"),
       "rtl": re.compile(r"\b(regno|reg_n|d_reg)\b\s*=|assign r\s+=|wire \[\d+:0\]\s+(regno|d_reg)"),
       "bench": re.compile(r"def (rd_pkt|wr_pkt|rd_pl|wr_pl|rdp|wrp|rd|wr)\(|^\s+return mk\((1|2),")}


def main(adir: Path) -> None:
    out = {}
    for name, rid in RUNS.items():
        with tarfile.open(adir / rid / "run_dir.tar.gz") as t:
            files = {m.name.split(f"{rid}/v2_e_udp_endpoint/", 1)[1]: m for m in t.getmembers()
                     if m.isfile() and f"{rid}/v2_e_udp_endpoint/" in m.name}
            rec = {}
            for rel, m in sorted(files.items()):
                kind = "model.py" if rel == "model.py" else "rtl" if rel.startswith("rtl/") and rel.endswith(".sv") \
                    else "bench" if rel.startswith("tests/") and rel.endswith(".py") and "test_v2" not in rel else None
                if not kind:
                    continue
                for i, ln in enumerate(t.extractfile(m).read().decode(errors="replace").splitlines(), 1):
                    if PAT[kind].search(ln):
                        rec.setdefault(kind, []).append(f"{rel}:{i}: {ln.strip()}"[:200])
        out[name] = {"run": rid, **rec}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))

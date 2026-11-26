"""Brief 210: the requirements report of t1_dimmer_counter on its committed reference run, before and after the board run.

    python3 results/210_requirements/make_t1_records.py

Inputs (all committed): the reference simulation run flow/tests/data/ref_t1_sim, formal status files written here as PASS (the formal jobs
were run in brief 143c; this script writes their pass status so that the matrix can be built without SymbiYosys), and the f0b bring-up record.
Outputs: t1_before_board.json (no bring-up record: the hardware rows are pending), t1_after_board.json (the bring-up record present), and
REQUIREMENTS_REPORT_t1.md, the after-board report as it reads. The analysis rows stay pending in both: this reference run has no build gates file.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import requirements_report as rr          # noqa: E402
from flow import traceability as tr                 # noqa: E402

T1 = ROOT / "designs" / "t1_dimmer_counter"
OUT = Path(__file__).resolve().parent
BRINGUP = ROOT / "results" / "f0b" / "t1_dimmer_counter_bringup.json"


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    for job in ("debounce", "scan"):
        for task in tr.sby_tasks(T1 / "verif" / "formal" / f"{job}.sby"):
            (tmp / "formal" / f"{job}_{task}").mkdir(parents=True)
            (tmp / "formal" / f"{job}_{task}" / "status").write_text("PASS 0\n")
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    request = (T1 / "spec.md").read_text()
    for name, hw in (("t1_before_board", None), ("t1_after_board", BRINGUP)):
        t = tr.build(T1, ROOT / "flow" / "tests" / "data" / "ref_t1_sim", formal=tmp / "formal", hw=hw,
                     defer=("analysis",) + (("hardware",) if hw is None else ()))
        rep = rr.build_report(T1, t, spec, request, {"level": "loose", "source": "default"})
        rep["generated"] = "2026-11-25"                        # a fixed date: the record is the same each time it is made
        (OUT / f"{name}.json").write_text(json.dumps(rep, indent=1) + "\n")
        if hw:
            (OUT / "REQUIREMENTS_REPORT_t1.md").write_text(rr.to_markdown(rep))
        print(name, rep["headline"])
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()

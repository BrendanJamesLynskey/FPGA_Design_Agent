"""Brief 114 post-hoc: re-compare the stored reader facts of every run with the CURRENT comparator (no model call), into runs_v2/<arm>/.

    python3 results/114_doc_crossread/rescore.py --priv-dir ../FPGA_Design_Agent_Knowledge/results_private/b114_doc_crossread

The scored records in runs/ were made by the comparator frozen in PREREGISTRATION.md; this rewrites the same rows with the comparator after the post-hoc fixes
listed there (same reader replies, so the reader is held constant). The reader facts are in the private directory; without it this script cannot run
(the public records keep only the rows).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import doc_crossread as D  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import SPEC, public_record  # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--priv-dir", type=Path, required=True)
    a = ap.parse_args()
    cases = {c["id"]: c for c in SPEC["cases"]}
    for arm_dir in sorted(p for p in a.priv_dir.iterdir() if p.is_dir()):
        for raw in sorted(arm_dir.glob("*_raw.json")):
            run = json.loads(raw.read_text())
            cid, k = raw.name.removesuffix("_raw.json").rsplit("_r", 1)
            c = cases[cid]
            old = json.loads((HERE / "runs" / arm_dir.name / f"{cid}_r{k}.json").read_text())
            code = [HERE / "cases" / c.get("code_case", cid) / "code" / n for n in c["code"]]
            cx = D.extract_code(code)
            facts = run["reader_facts"]
            cmp = D.compare(facts, cx)
            document = {"source": old["document"]["source"], "pages": old["document"]["pages"], "sha256": old["document"]["sha256"], "chars": old["document"]["chars"]}
            rec = D.to_record(document=document, code=cx, cmp=cmp, read={"facts": facts, "problems": run["reader_problems"], "repairs": old["reader"].get("repairs", 0),
                                                              "seconds": old["reader"].get("seconds", 0), "prompts": old["reader"].get("prompts", {}),
                                                              "prompt_hashes": old["reader"].get("prompt_hashes", {})},
                              topic=c["topic"], target=c["target"], model_info=old.get("model"), usage=old.get("usage"), source_of_facts="stored reply (post-hoc comparator)")
            rec["run"] = old["run"]
            out = HERE / "runs_v2" / arm_dir.name
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{cid}_r{k}.json").write_text(json.dumps(public_record(rec), indent=1) + "\n")


if __name__ == "__main__":
    main()

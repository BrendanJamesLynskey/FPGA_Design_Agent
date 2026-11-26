"""Data for site/src/traceability.html (brief 116): the specification-to-evidence matrices, computed by flow/trace_v1.py.

    site/data/traceability.json   what the page reads (written by site/export.py)

Nothing is typed here. Every status, count and bound is read by flow/trace_v1.py from the testplans (designs/*/verif/testplan.yaml) and the
committed evidence files they name. The page's own prose holds no number.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from flow import trace_v1
    all_ = trace_v1.collect_all()
    for d in all_["designs"]:
        for i in d["items"]:
            i.pop("checks", None)
    import verified                                    # brief 144: each design's verification label, for its panel
    all_["verified"] = {r["path"]: r for r in verified.records()}
    return {"content": all_, "check": all_}

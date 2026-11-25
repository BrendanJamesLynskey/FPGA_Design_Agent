"""Event coverage for the frame-based benches (arith brief 161): the bench calls cover.hit("name") when something of interest happens (a frame, an inverse frame, a negative exponent, a refused
commit ...); coverage.yaml of the packaged harness lists the bins with their minimum hit counts (and an optional `min_if`, a Python expression over the parameters `p`, below which a bin is not
required, e.g. a bin that needs a large N); the runner checks the dumped file. Without ARITH_COVER_FILE the object counts nothing and costs nothing."""
from __future__ import annotations

import json
import os


class Cover:
    def __init__(self):
        path = os.environ.get("ARITH_COVER_FILE")
        self.out = os.environ.get("ARITH_COVER_OUT")
        self.bins = {}
        if path:
            import yaml
            self.bins = {b["name"]: {"min": b["min"], "min_if": b.get("min_if"), "hits": 0} for b in yaml.safe_load(open(path))["bins"]}

    def hit(self, name: str, n: int = 1) -> None:
        if name in self.bins:
            self.bins[name]["hits"] += n

    def dump(self) -> None:
        if self.out and self.bins:
            json.dump({"bins": [{"name": k, **v} for k, v in self.bins.items()]}, open(self.out, "w"), indent=1)


_C = Cover()


def cover() -> Cover:
    return _C

"""Stage 0 (no new RTL): when does each input of the decision model become known, and which one is last?

Read from the RTL (feed_rx.sv: byte offsets and the clock each field is registered; book.sv: the entry is read when
the instrument field completes; ml_feat.sv: what each feature is a function of) and from the measured integration
clocks (results/b93/integration_*_latency.json). Output: results/b93/stage0.json, printed as the table
docs/what_we_found.md section 1 quotes.

    python -m designs.b93_precompute.model.stage0
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
R = ROOT / "results" / "b93"

# Bench Feed v1 message (docs/bench_feed_v1.md): byte offset within the 16-byte message; clock numbering: clock 0 is the
# clock msg_inst_v is high (offset 3 has just been registered by feed_rx); one byte per clock at 1 Gb/s with the 8 ns clock.
BENCH = [
    {"input": "type", "offset": "0", "known_clock": -3, "used_by_model": "no (sets the NEXT message's trade sign)"},
    {"input": "side", "offset": "1", "known_clock": -2, "used_by_model": "no (as type)"},
    {"input": "instrument", "offset": "2-3", "known_clock": 0, "used_by_model": "yes: selects the book entry; equality with the tracked instrument gates the unit"},
    {"input": "price", "offset": "4-7", "known_clock": 4, "used_by_model": "no (rules use it; the book is updated from it after the message)"},
    {"input": "size", "offset": "8-11", "known_clock": 8, "used_by_model": "no"},
    {"input": "book entry (bid/ask price and size)", "offset": "from the book RAM", "known_clock": 1, "used_by_model": "yes: the book BEFORE this message"},
    {"input": "previous snapshot, OFI window, trade window, last direction", "offset": "state", "known_clock": "before the frame", "used_by_model": "yes"},
]
FEATURES = [
    {"feature": "f0 bid size", "bits": 8, "depends_on": "book entry", "class": "early field (instrument), shallow logic"},
    {"feature": "f1 ask size", "bits": 8, "depends_on": "book entry", "class": "early field (instrument), shallow logic"},
    {"feature": "f2 spread", "bits": 4, "depends_on": "book entry (two prices)", "class": "early field (instrument), a 32-bit subtract and compare"},
    {"feature": "f3 imbalance bucket", "bits": 3, "depends_on": "f0, f1", "class": "early field, seven compares of shifted sizes"},
    {"feature": "f4 trade-sign sum", "bits": 5, "depends_on": "trade window, previous message's type and side", "class": "pure function of state known before the frame"},
    {"feature": "f5 order-flow imbalance", "bits": 8, "depends_on": "book entry, previous snapshot, OFI window", "class": "early field, deepest logic: four 32-bit compares, a 35-bit sum, a clip, a window update"},
    {"feature": "f6 last mid direction", "bits": 2, "depends_on": "book entry, previous snapshot, last direction", "class": "early field, two 33-bit sums and a compare"},
]
# Nasdaq TotalView-ITCH 5.0, section 1.3.1 (offsets from the published specification, read from its text)
ITCH = [("message type", 0, 1), ("stock locate", 1, 2), ("tracking number", 3, 2), ("timestamp", 5, 6), ("order reference", 11, 8),
        ("buy/sell", 19, 1), ("shares", 20, 4), ("stock (symbol)", 24, 8), ("price", 32, 4)]


def main() -> int:
    m = {p: json.loads((R / f"integration_gbt_pre{p}_latency.json").read_text())["modes"]["speculative_model_on"] for p in (0, 1, 2, 3)}
    out = {
        "bench_feed_v1": BENCH, "features_87": FEATURES,
        "last_arriving_input_of_the_model": {
            "input": "the book entry read for the message (its address is the instrument field, offset 2-3)",
            "clock_known": 1, "price_field_complete_clock": 4, "slack_clocks_before_price": 3,
            "width_after_87_quantisation_bits": 38,
            "note": "the packed feature vector is 38 bits; inside the feature unit f5 (8 bits) is the deepest. No input depends on the message's own price, size, type or side."},
        "ml_decision_depends_on_price_field": False,
        "itch_5_0_add_order": {"fields": [{"name": n, "offset": o, "bytes": b} for n, o, b in ITCH], "length": 36,
                               "conclusion": "the book key (stock locate at offset 1, or the stock symbol at 24-31) arrives 4 to 31 bytes before the price (32-35); under the 87 definition of the features the conclusion is the same as for Bench Feed v1. A model with the order's own price or shares as an input would have the price (offset 32, 4 bytes) as its last input."},
        "measured_clocks_after_instrument_field": {
            "baseline_87": m[0]["class_valid_clocks_after_instrument_field"],
            "early_features": m[1]["class_valid_clocks_after_instrument_field"],
            "table_fill1": m[2]["class_valid_clocks_after_instrument_field"],
            "table_fill2": m[3]["class_valid_clocks_after_instrument_field"],
            "rule_decision_visible": 5},
    }
    (R / "stage0.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["last_arriving_input_of_the_model"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

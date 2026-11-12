"""Natural language -> rule: the agent writes a rule from a sentence, and code checks it.

The model (openai/gpt-6-luna, a hosted language model reached through OpenRouter with provider data collection
disabled) is given the rule schema and
the table's limits and asked for one JSON rule. model/rules.py validate() then checks it; on a refusal the error goes
back to the model once. Nothing the model says is trusted: the validator decides, and the fixtures' `expect` blocks
(written by hand, from the sentence alone) decide whether the rule means what the sentence said.

    python3 -m designs.b58a_trigger.host.nl_rule --record     # live: calls luna, writes rules/fixtures/*.json
    python3 -m designs.b58a_trigger.host.nl_rule --check      # offline (CI): re-checks every recorded fixture

Spend: capped by --max-usd (default 2.00); cost is the provider-reported figure, appended to results/spend_ledger.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

from designs.b58a_trigger.model import rules as rl

HERE = Path(__file__).resolve().parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
FIXTURES = DESIGN / "rules" / "fixtures"
SCHEMA = DESIGN / "rules" / "rule_schema.json"
MODEL = "openai/gpt-6-luna"
LIMITS = rl.Limits(max_qty=100, band=500, max_pos=1000)

# The sentences and what each must mean, written from the sentence alone. `refuse`: the validator must refuse the
# rule (the request breaks a limit), whatever the model writes.
CASES = [
    {"id": "nl01", "nl": "When instrument 7's ask drops below 101.25, send a buy for 10.",
     "expect": {"types": ["ADD", "MODIFY"], "side": 2, "inst": 7, "op": 1, "threshold": 10125,
                "order": {"side": "buy", "qty": 10}}},
    {"id": "nl02", "nl": "If anything trades above 99.50, sell 3 at one tick (0.01) under the trade price.",
     "expect": {"types": ["TRADE"], "inst": None, "op": 3, "threshold": 9950,
                "order": {"side": "sell", "qty": 3, "mode": "offset", "value": -1}}},
    {"id": "nl03", "nl": "Raise pin 1 and log it whenever a new bid on instrument 12 crosses the best ask.",
     "expect": {"types": ["ADD"], "side": 1, "inst": 12, "book": 2, "order": None, "pin": 1, "log": True}},
    {"id": "nl04", "nl": "Buy 5 of instrument 3 at 100.00 when its ask falls to 100.00 or lower; at most once per millisecond.",
     "expect": {"side": 2, "inst": 3, "op": 2, "threshold": 10000, "order": {"side": "buy", "qty": 5, "mode": "fixed",
                "value": 10000}, "holdoff": 125000}},
    {"id": "nl05", "nl": "Sell 20 of instrument 0 at the message price when a bid on it improves the best bid and is at least 102.",
     "expect": {"side": 1, "inst": 0, "op": 4, "threshold": 10200, "book": 1,
                "order": {"side": "sell", "qty": 20, "mode": "message"}}},
    {"id": "nl06", "nl": "Log every cancel on instrument 4.",
     "expect": {"types": ["CANCEL"], "inst": 4, "order": None, "log": True}},
    {"id": "nl07", "nl": "Buy 5000 of instrument 2 whenever anything trades.", "refuse": "qty"},
    {"id": "nl08", "nl": "When instrument 9's bid goes above 101, sell 1 at a fixed 50.00.", "refuse": "band"},
    # a threshold finer than the price grid: "below 98.755" is the same set of prices as "<= 98.75" or "< 98.76";
    # checked by enumerating prices, not by the form the model chose (first recorded expectation, "refuse", was wrong)
    {"id": "nl09", "nl": "When the ask on instrument 1 is modified to below 98.755, buy 2.",
     "expect": {"types": ["MODIFY"], "side": 2, "inst": 1, "price_lt": 9875.5, "order": {"side": "buy", "qty": 2}}},
    {"id": "nl10", "nl": "Buy 4 of instrument 6 at the ask price plus 0.05 whenever an ask is added under 100.",
     "expect": {"types": ["ADD"], "side": 2, "inst": 6, "op": 1, "threshold": 10000,
                "order": {"side": "buy", "qty": 4, "mode": "offset", "value": 5}}},
]

SYSTEM = """You turn one plain-English trading-rule sentence into ONE JSON object that follows this JSON Schema.
This is a mock bench system with our own made-up message format; there is no real market.
Facts: prices are in currency units with at most two decimals; message types are ADD, MODIFY, CANCEL, TRADE;
"side" in match is the side of the market-data message (bid or ask); the order side is buy or sell; the clock is
8 ns (125 MHz), so holdoff_cycles = time / 8 ns. A "drop below" or "falls under" a price on the ask means new ask
prices from ADD or MODIFY messages. Limits the board enforces: order size at most {max_qty}; an order price at most
{band} from the price that triggered it. If the sentence asks for something outside the limits, still write the
rule as asked (the checker will refuse it). Reply with the JSON object only, no prose, no code fence.

Schema:
{schema}
"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("the model's reply contained no JSON rule")
    return json.loads(m.group(0))


def check_meaning(norm: dict, expect: dict) -> list[str]:
    """Differences between a validated rule and what the sentence meant (empty = it means it)."""
    bad = []
    if "types" in expect:
        want = sorted(rl.TYPES[t] for t in expect["types"])
        if sorted(norm["types"]) != want:
            bad.append(f"types {norm['types']} != {want}")
    for k in ("side", "inst", "op", "threshold", "book", "pin", "log", "holdoff"):
        if k in expect and norm[k] != expect[k]:
            bad.append(f"{k} {norm[k]!r} != {expect[k]!r}")
    if "price_lt" in expect:
        lim = expect["price_lt"]
        ops = {1: lambda p, t: p < t, 2: lambda p, t: p <= t, 3: lambda p, t: p > t, 4: lambda p, t: p >= t}
        f = ops.get(norm["op"])
        lo = int(lim) - 500
        if f is None or any(f(p, norm["threshold"]) != (p < lim) for p in range(max(0, lo), int(lim) + 500)):
            bad.append(f"price condition {norm['op']} {norm['threshold']} is not 'below {lim / 100}'")
    if "order" in expect:
        eo, no = expect["order"], norm["order"]
        if eo is None:
            if no is not None:
                bad.append("an order where none was asked for")
        elif no is None:
            bad.append("no order")
        else:
            for k, v in eo.items():
                if no.get(k) != v:
                    bad.append(f"order.{k} {no.get(k)!r} != {v!r}")
    return bad


def classify_refusal(err: str) -> str:
    if "maximum order size" in err:
        return "qty"
    if "price band" in err:
        return "band"
    if "two decimals" in err:
        return "decimals"
    return "other"


def record(max_usd: float) -> dict:
    from agent.graph.llm import OpenRouterClient          # the project's client: data collection denied, no Fable/Opus
    client = OpenRouterClient(model=MODEL)
    system = SYSTEM.format(max_qty=LIMITS.max_qty, band=f"{LIMITS.band / 100:.2f}", schema=SCHEMA.read_text())
    FIXTURES.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    run_id = time.strftime("%Y%m%d-%H%M%S")
    for c in CASES:
        if spent >= max_usd:
            raise SystemExit(f"spend cap of ${max_usd:.2f} reached (spent ${spent:.4f}); stopping")
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": c["nl"]}]
        turns = []
        for attempt in range(2):
            r = client(msgs)
            spent += r.cost if r.cost is not None else 0.05
            turn = {"reply": r.text, "cost_usd": r.cost, "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens}
            try:
                rule = _extract_json(r.text)
                turn["rule"] = rule
                rl.validate(rule, LIMITS)
                turn["validator"] = "ok"
                turns.append(turn)
                break
            except (ValueError, rl.RuleError) as e:
                turn["validator"] = f"refused: {e}"
                turns.append(turn)
                if c.get("refuse"):
                    break                                   # a refusal was the right outcome: do not argue it away
                msgs += [{"role": "assistant", "content": r.text},
                         {"role": "user", "content": f"The checker refused that rule: {e}. Reply with a corrected JSON object only."}]
        fx = {"id": c["id"], "nl": c["nl"], "model": MODEL, "run_id": run_id, "limits": LIMITS.__dict__,
              "turns": turns, **({"expect": c["expect"]} if "expect" in c else {"refuse": c["refuse"]})}
        (FIXTURES / f"{c['id']}.json").write_text(json.dumps(fx, indent=1) + "\n")
    with (ROOT / "results" / "spend_ledger.csv").open("a", newline="") as f:
        csv.writer(f).writerow([time.strftime("%Y-%m-%d"), "58a_nl_rules", run_id, MODEL, "nl_to_rule", "",
                                f"{spent:.6f}", f"provider-reported; deny; {len(CASES)} sentences, at most 2 turns each"])
    return {"spent_usd": spent, "cases": len(CASES)}


def check() -> dict:
    """Offline: every recorded fixture's last rule re-validated and checked against its sentence's meaning."""
    out = {"meant": [], "wrong": [], "refused_right": [], "refused_wrong": [], "not_refused": [],
           "notes": {"nl09": "the expectation was changed after the model's reply was seen: it was first 'must be "
                             "refused' (a threshold finer than the price grid); the model wrote <= 98.75, the same set "
                             "of hundredth prices as 'below 98.755', so the check became an enumeration of prices"}}
    for c in CASES:
        fx = json.loads((FIXTURES / f"{c['id']}.json").read_text())
        last = fx["turns"][-1]
        rule = last.get("rule")
        try:
            norm = rl.validate(rule, LIMITS) if rule is not None else None
            err = None if norm else "no rule"
        except rl.RuleError as e:
            norm, err = None, str(e)
        if "refuse" in c:
            if norm is not None:
                out["not_refused"].append(c["id"])
            elif classify_refusal(err) == c["refuse"]:
                out["refused_right"].append(c["id"])
            else:
                out["refused_wrong"].append((c["id"], err))
        elif norm is None:
            out["wrong"].append((c["id"], f"refused: {err}"))
        else:
            diff = check_meaning(norm, c["expect"])
            (out["wrong"] if diff else out["meant"]).append((c["id"], diff) if diff else c["id"])
            if not diff:
                rl.words(norm)                              # loads as register words
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--max-usd", type=float, default=2.0)
    a = ap.parse_args()
    if a.record:
        print(record(a.max_usd))
    print(json.dumps(check(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

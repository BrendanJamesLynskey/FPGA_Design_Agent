"""Rule table: the JSON form people (and the agent) write, its validator, and the six register words per rule.

The schema is rules/rule_schema.json; this module is the validator the loader runs (it needs no jsonschema package)
plus the checks a schema cannot express (prices in whole hundredths, an order the interlocks would always block).
docs/rule_table.md has the word layout, which rtl/rules.sv decodes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

TYPES = {"ADD": 1, "MODIFY": 2, "CANCEL": 3, "TRADE": 4}
SIDES = {"any": 0, "bid": 1, "ask": 2}
OPS = {"<": 1, "<=": 2, ">": 3, ">=": 4}
BOOK = {"none": 0, "improves": 1, "crosses": 2}
NRULES = 8
MAX_U32 = 0xFFFFFFFF


class RuleError(ValueError):
    pass


def hundredths(v: Any, what: str) -> int:
    """A price in currency units (number or string, at most two decimals) as whole hundredths."""
    try:
        d = Decimal(str(v))
    except InvalidOperation as e:
        raise RuleError(f"{what}: not a number: {v!r}") from e
    h = d * 100
    if h != h.to_integral_value():
        raise RuleError(f"{what}: {v} has more than two decimals")
    return int(h)


def _req(d: dict, k: str, where: str) -> Any:
    if k not in d:
        raise RuleError(f"{where}: '{k}' is required")
    return d[k]


def _only(d: dict, keys: set[str], where: str) -> None:
    extra = set(d) - keys
    if extra:
        raise RuleError(f"{where}: unknown field(s) {sorted(extra)}")


@dataclass
class Limits:
    """The interlock settings a rule is checked against (the same values the board is loaded with)."""
    max_qty: int = 100
    band: int = 500        # hundredths
    max_pos: int = 1000


def validate(rule: dict, limits: Limits | None = None) -> dict:
    """Check one rule; return it normalised (prices in hundredths). Raises RuleError with the reason."""
    if not isinstance(rule, dict):
        raise RuleError("a rule is a JSON object")
    lim = limits or Limits()
    _only(rule, {"name", "enable", "match", "action", "holdoff_cycles", "comment"}, "rule")
    name = str(rule.get("name", ""))
    m = _req(rule, "match", "rule")
    a = _req(rule, "action", "rule")
    if not isinstance(m, dict) or not isinstance(a, dict):
        raise RuleError("match and action are objects")
    _only(m, {"types", "side", "instrument", "price", "book"}, "match")
    _only(a, {"order", "pin", "log"}, "action")
    types = _req(m, "types", "match")
    if not isinstance(types, list) or not types or any(t not in TYPES for t in types):
        raise RuleError(f"match.types: a non-empty list of {sorted(TYPES)}")
    side = m.get("side", "any")
    if side not in SIDES:
        raise RuleError(f"match.side: one of {sorted(SIDES)}")
    inst = m.get("instrument", "any")
    if inst != "any" and not (isinstance(inst, int) and 0 <= inst <= 0xFFFF):
        raise RuleError("match.instrument: 'any' or an integer 0..65535")
    price = m.get("price")
    p_op, p_val = 0, 0
    if price is not None:
        _only(price, {"op", "value"}, "match.price")
        if _req(price, "op", "match.price") not in OPS:
            raise RuleError(f"match.price.op: one of {sorted(OPS)}")
        p_op = OPS[price["op"]]
        p_val = hundredths(_req(price, "value", "match.price"), "match.price.value")
        if not 0 <= p_val <= MAX_U32:
            raise RuleError("match.price.value: out of range")
    book = m.get("book", "none")
    if book not in BOOK:
        raise RuleError(f"match.book: one of {sorted(BOOK)}")
    order = a.get("order")
    o = None
    if order is not None:
        _only(order, {"side", "qty", "price"}, "action.order")
        oside = _req(order, "side", "action.order")
        if oside not in ("buy", "sell"):
            raise RuleError("action.order.side: buy or sell")
        qty = _req(order, "qty", "action.order")
        if not isinstance(qty, int) or qty < 1:
            raise RuleError("action.order.qty: a whole number of at least 1")
        if qty > lim.max_qty:
            raise RuleError(f"action.order.qty: {qty} is above the interlock's maximum order size {lim.max_qty}: "
                            "every order would be refused")
        op = _req(order, "price", "action.order")
        _only(op, {"mode", "value"}, "action.order.price")
        mode = _req(op, "mode", "action.order.price")
        if mode not in ("fixed", "message", "offset"):
            raise RuleError("action.order.price.mode: fixed, message or offset")
        val = 0
        if mode in ("fixed", "offset"):
            val = hundredths(_req(op, "value", "action.order.price"), "action.order.price.value")
        if mode == "offset" and abs(val) > lim.band:
            raise RuleError(f"action.order.price.value: an offset of {val / 100:.2f} is outside the price band "
                            f"{lim.band / 100:.2f}: every order would be refused")
        if mode == "fixed" and p_op and abs(val - p_val) > lim.band:
            raise RuleError(f"action.order.price.value: {val / 100:.2f} is more than the price band "
                            f"{lim.band / 100:.2f} from the trigger price {p_val / 100:.2f}")
        o = {"side": oside, "qty": qty, "mode": mode, "value": val}
    pin = a.get("pin")
    if pin not in (None, 0, 1):
        raise RuleError("action.pin: null, 0 or 1")
    log = a.get("log", False)
    if not isinstance(log, bool):
        raise RuleError("action.log: true or false")
    if o is None and pin is None and not log:
        raise RuleError("action: the rule does nothing (no order, pin or log)")
    hold = rule.get("holdoff_cycles", 0)
    if not isinstance(hold, int) or not 0 <= hold <= MAX_U32:
        raise RuleError("holdoff_cycles: a whole number 0..4294967295")
    en = rule.get("enable", True)
    if not isinstance(en, bool):
        raise RuleError("enable: true or false")
    return {"name": name, "enable": en, "types": [TYPES[t] for t in types], "side": SIDES[side],
            "inst": None if inst == "any" else inst, "op": p_op, "threshold": p_val, "book": BOOK[book],
            "order": o, "pin": pin, "log": log, "holdoff": hold}


def validate_table(rules: list[dict], limits: Limits | None = None) -> list[dict]:
    if not isinstance(rules, list) or len(rules) > NRULES:
        raise RuleError(f"a rule table is a list of at most {NRULES} rules")
    return [validate(r, limits) for r in rules]


def words(n: dict) -> list[int]:
    """The six register words of a normalised rule (docs/rule_table.md)."""
    c = int(n["enable"])
    for t in n["types"]:
        c |= 1 << t
    c |= n["side"] << 5
    c |= (n["inst"] is None) << 7
    c |= n["op"] << 8
    c |= n["book"] << 11
    o = n["order"]
    val = 0
    if o:
        c |= 1 << 13
        c |= (o["side"] == "sell") << 14
        c |= {"fixed": 0, "message": 1, "offset": 2}[o["mode"]] << 15
        val = o["value"] & MAX_U32
    if n["pin"] is not None:
        c |= 1 << 17
        c |= n["pin"] << 18
    c |= int(n["log"]) << 19
    return [c, n["inst"] or 0, n["threshold"], o["qty"] if o else 0, val, n["holdoff"]]


def table_words(norm: list[dict]) -> list[list[int]]:
    """Eight rules of six words; unused rules are all zero (disabled)."""
    out = [words(n) for n in norm]
    return out + [[0] * 6 for _ in range(NRULES - len(out))]

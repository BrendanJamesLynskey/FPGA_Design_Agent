#!/usr/bin/env python3
"""IP-library retrieval (brief 150, review 147 F2): find a library entry from a plain-English request, rank its variants
against a budget, part and clock, show its contract, and say "nothing fits" when nothing does.

    python3 -m flow.iplookup search "answer ping requests" [--part P] [--clock-ns N] [--budget dsp=0] [--language sv]
    python3 -m flow.iplookup show fir [--params TAPS=32] [--variant serial]

The same functions are the agent's ``ip_lookup`` tool (agent/core/tools.py) and ``python -m agent ip`` (agent/ip_cmd.py).
Plain Python: no key, no Vivado, no model. It builds on ``flow.ipvariants`` (``choose``, ``variant_costs``, ``measured``)
and never invents a figure: costs and Fmax come from ip.yaml predictions and ``ip_lib/<entry>/char/<part>.json`` only.

How the match is made (what a user could guess wrong):

- A request is scored against each entry's name, one-line summary, variant summaries, interface signals, parameter names and
  the first paragraph of its README, by term overlap weighted by how rare each word is across the library (BM25), after a
  light stemmer ("receive", "received", "receiving" agree) and a small table of abbreviations (ALIASES below).
- A match needs at least two matching words (or the entry's own name). Below that the answer is "nothing fits" and the
  nearest entries are listed as a *nearest miss*, labelled as such. A near miss is not a recommendation: read its summary.
- ``fits`` says the entry matches the request. Whether a *variant* fits the budget, clock and II is a second, separate
  answer from ``flow.ipvariants.choose`` and is only given for the top hits. A variant is "fits", "does not fit" (a known
  figure is over the limit) or "unknown" (a figure was never measured at that point, so nothing can be said: not a rejection).
- The library has no VHDL, no FIFO or clock-crossing block and nothing for non-Artix-7 costs; the answer says so.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

if __package__ in (None, ""):                         # run as a script from flow/
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import ipvariants as iv

ROOT = iv.ROOT
IP = iv.IP

STOP = frozenset("""a an the and or of to in on for with from by at as is are be it its this that these those i me my we our you your
need needs want wants use using used make makes like can could should would will do does how what which who into over per via
some any all one two three each every than then so also not no only more most very much many etc eg ie fpga block core module
design implement implementation bit bits engine interface rate memory work out which pull pass change""".split())

#: abbreviations and near-words an FPGA engineer uses for what the entries say in other words. Kept short and general (a word
#: and what it stands for), not a copy of any entry's text. Each value is a space-separated list added to the request's words.
ALIASES = {
    "tcam": "ternary match", "cam": "match exact", "ping": "icmp echo", "ethernet": "mac", "gigabit": "rgmii 1000",
    "gbe": "rgmii 1000", "mdc": "mdio", "phy": "mdio", "routing": "prefix lpm", "route": "prefix lpm", "router": "prefix lpm",
    "hash": "exact match", "dds": "phase accumulator", "nco": "phase accumulator", "waveform": "sine triangle saw square",
    "generator": "source", "scope": "capture trigger", "axi4lite": "axi4-lite", "axil": "axi4-lite", "crossbar": "xbar",
    "interconnect": "xbar crossbar", "switch": "l2 vlan", "filter": "fir", "lowpass": "fir", "low-pass": "fir filter", "high-pass": "fir filter", "band-pass": "fir filter", "bandpass": "fir filter", "ip": "ipv4", "mcast": "multicast",
    "multicast": "igmp", "dhcp": "udp", "datagram": "udp", "checksum": "crc", "scheduler": "queue", "scheduling": "queue",
    "ttl": "rewrite", "hop": "rewrite", "histogram": "code-density dnl inl", "linearity": "dnl inl",
}

#: the part of the request that is not about a function (a language or a tool word) is dropped before matching
_FIELD_BOOST = {"name": 4.0, "summary": 2.0, "variants": 1.0, "iface": 1.0, "readme": 0.7}
_K1, _B = 1.4, 0.6
#: an entry matches when its score reaches this and at least two distinct request words matched (or one is its own name)
USE_ALIASES = True            # False only for the measurement's ablation (results/150_ip_lookup)
MIN_SCORE = 3.0
MIN_TERMS = 2
#: and the matching words must carry at least this share of the request's weight; a word the library has never seen
#: ("ddr3", "xgmii", "uart") counts against the entry at UNKNOWN_WEIGHT of the rarest known word, so a request about
#: something the library lacks is not answered by an entry that shares only its generic words
MIN_COVERAGE = 0.45
UNKNOWN_WEIGHT = 0.5

HOUSE_ANSWERS = (
    # (words that trigger, the answer when the library has nothing). Documented in docs/ip_lookup.md.
    ({"fifo", "cdc", "synchroniser", "synchronizer", "crossing", "clock-domain"},
     "The library has no FIFO or clock-crossing block. The house answer is AMD's XPM macros (xpm_fifo_async, xpm_cdc_*): "
     "instantiate them, and flow/xpm_cdc.tcl applies their timing exceptions in this flow."),
)


#: the stage-1 bullet (agent/graph/run.py appends it to the stage's conventions when the tool is offered)
IP_LOOKUP_CONVENTION = """
- IP library: before you design a block that a standard function could cover (a CRC, a filter, an Ethernet or IP-stack
  block, a match table, a crossbar, a waveform source), call `ip_lookup` (action search, with the function in words; the
  part, clock and budget if you know them). It answers "nothing fits" when no entry does: then write the block fresh; do not
  force a near miss. When an entry fits, read its contract with action show and use it instead of rewriting it: name it in
  ARCHITECTURE.md under "Library entries considered" with one line each on why it was taken or not (a taken entry's variant,
  parameters and the costs the answer gave). A variant marked "unknown" is not a rejection: it means a figure (usually Fmax)
  was never measured at that point; judge it from the contract and the latency, or ask for the answer again without a clock. Every call is logged to build/ip_lookup.jsonl. The library is SystemVerilog and
  Artix-7 costed; it has no FIFO or clock-crossing block (use AMD's XPM macros).
"""


# --- text -------------------------------------------------------------------------------------------------------------
def stem(w: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ers", "er", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf) and not w.endswith("ss"):
            return w[: -len(suf)]
    return w


_FAST = re.compile(r"\b(?:10|25|40|100)\s*-?\s*(?:g|gb|gbe|gbps|gigabit)\b", re.I)


def normalise(query: str) -> str:
    """'10 Gigabit' and its kin name a speed the library's MACs (10/100/1000 Mb/s) do not have: they become the word
    'multigigabit' (unknown to the library), so 'gigabit' is not read as 1000 Mb/s."""
    return _FAST.sub(" multigigabit ", query)


def tokens(text: str, expand: bool = False) -> list[str]:
    out: list[str] = []
    for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()):
        parts = [w] + (w.split("-") if "-" in w else [])
        for p in parts:
            if p in STOP or len(p) < 2:
                continue
            out.append(stem(p))
            if expand and USE_ALIASES and p in ALIASES:
                out += [stem(a) for a in re.findall(r"[a-z0-9]+", ALIASES[p])]
    return out


def _snake(name: str) -> str:
    return name.replace("_", " ")


def _readme_first_paragraph(block: str) -> str:
    f = IP / block / "README.md"
    if not f.exists():
        return ""
    para: list[str] = []
    for line in f.read_text().splitlines():
        s = line.strip()
        if s.startswith("#") or s.startswith("|") or s.startswith("```"):
            if para:
                break
            continue
        if not s:
            if para:
                break
            continue
        para.append(s)
    return " ".join(para)[:900]


_INDEX: dict | None = None


def _index() -> dict:
    """{block: {field: [tokens]}} plus document frequencies; built once per process from ip.yaml and README.md."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    docs: dict[str, dict[str, list[str]]] = {}
    for b in iv.entries():
        y = iv._yaml(b)
        iface = " ".join(f"{i.get('name', '')} {i.get('type', '')} {i.get('signals', '')} {i.get('note', '')}"
                         for i in (y.get("interfaces") or []))
        iface += " " + " ".join(f"{k} {v.get('note', '')}" for k, v in (y.get("parameters") or {}).items())
        var = " ".join(f"{k} {v.get('summary', '')} {v.get('when', '')[:200]}" for k, v in (y.get("variants") or {}).items())
        docs[b] = {"name": tokens(_snake(b)) + tokens(b), "summary": tokens(y.get("summary", "")),
                   "variants": tokens(var), "iface": tokens(iface), "readme": tokens(_readme_first_paragraph(b))}
    df: dict[str, int] = {}
    for d in docs.values():
        for t in {t for f in d.values() for t in f}:
            df[t] = df.get(t, 0) + 1
    n = len(docs)
    avg = sum(sum(len(f) for f in d.values()) for d in docs.values()) / max(1, n)
    _INDEX = {"docs": docs, "df": df, "n": n, "avg": avg}
    return _INDEX


def _idf(t: str) -> float:
    ix = _index()
    df = ix["df"].get(t, 0)
    return math.log(1 + (ix["n"] - df + 0.5) / (df + 0.5)) if df else 0.0


def coverage(hit: list[str], qterms: list[str]) -> float:
    """Share of the request's weight carried by the words that matched this entry."""
    top = max((_idf(t) for t in _index()["df"]), default=1.0)
    allq = list(dict.fromkeys(qterms))
    tot = sum(_idf(t) if _idf(t) else UNKNOWN_WEIGHT * top for t in allq)
    return sum(_idf(t) for t in hit) / tot if tot else 0.0


def _score(block: str, qterms: list[str]) -> tuple[float, list[str]]:
    ix = _index()
    d = ix["docs"][block]
    length = sum(len(f) for f in d.values())
    score, hit = 0.0, []
    for t in dict.fromkeys(qterms):
        df = ix["df"].get(t, 0)
        if not df:
            continue
        idf = math.log(1 + (ix["n"] - df + 0.5) / (df + 0.5))
        tf = sum(_FIELD_BOOST[f] * toks.count(t) for f, toks in d.items())
        if tf <= 0:
            continue
        score += idf * tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * length / ix["avg"]))
        hit.append(t)
    return score, hit


# --- entry facts ------------------------------------------------------------------------------------------------------
def languages(block: str) -> list[str]:
    y = iv._yaml(block)
    ext = {Path(p).suffix.lower() for p in y.get("rtl") or []}
    return sorted(({"sv": "sv", "v": "v", "vhd": "vhdl", "vhdl": "vhdl"}[e.lstrip(".")] for e in ext
                   if e.lstrip(".") in ("sv", "v", "vhd", "vhdl")))


def verified_status(block: str) -> dict:
    """The entry's verification label from ip_lib/<entry>/verified.json (brief 144), or "unknown" when the record is absent
    (it is not on every branch). The label is read, never computed or upgraded here."""
    f = IP / block / "verified.json"
    if not f.is_file():
        return {"label": "unknown", "basis": "no ip_lib/%s/verified.json in this checkout (brief 144's record); the entry's own "
                "declared status is shown separately and is not a verification" % block}
    try:
        d = json.loads(f.read_text())
    except ValueError:
        return {"label": "unknown", "basis": "verified.json is not valid JSON"}
    unmet = [c.get("title") for c in d.get("criteria", []) if c.get("state") not in ("met", "pass", "passed")]
    return {"label": d.get("label_kind") or "unknown", "text": d.get("label"), "unmet_criteria": unmet[:8],
            "record": f"ip_lib/{block}/VERIFIED.md"}


def contract(block: str) -> dict:
    y = iv._yaml(block)
    return {"top": y.get("top"), "interfaces": y.get("interfaces") or [], "clocks": y.get("clocks") or [],
            "resets": y.get("resets") or [], "parameters": y.get("parameters") or {}, "latency": y.get("latency"),
            "throughput": y.get("throughput"), "limits": y.get("limits"), "depends": y.get("depends") or [],
            "boundary": y.get("boundary")}


def _measured_row(block: str, part: str | None) -> dict | None:
    try:
        rows = [r for r in iv.measured(block, part) if r.get("status", "ok") == "ok"]
    except Exception:                                    # noqa: BLE001 (no characterisation file for this part)
        return None
    if not rows:
        return None
    r = rows[0]
    return {k: r.get(k) for k in ("variant", "params", "lut", "ff", "bram_tiles", "dsp", "fmax_mhz", "wns_ns", "power_w",
                                  "part", "clock_ns", "tool") if r.get(k) is not None}


def _ports(block: str) -> list[tuple[str, str]]:
    """(direction, name) of the top module's ports, read from the RTL header; [] when it cannot be read."""
    y = iv._yaml(block)
    top = y.get("top")
    for rel in y.get("rtl") or []:
        f = IP / block / rel
        if not f.suffix == ".sv" and not f.suffix == ".v":
            continue
        text = re.sub(r"//[^\n]*|/\*.*?\*/", "", f.read_text(), flags=re.S)
        m = re.search(rf"\bmodule\s+{re.escape(str(top))}\b", text)
        if not m:
            continue
        i, depth, start, groups = m.end(), 0, None, []
        while i < len(text):
            c = text[i]
            if c == "(":
                depth += 1
                if depth == 1:
                    start = i + 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    groups.append(text[start:i])
                    if len(groups) == 2 or not re.match(r"\s*\(", text[i + 1:]):
                        break
            elif c == ";" and depth == 0:
                break
            i += 1
        ports_text = groups[-1] if groups else ""
        if len(groups) == 1 and "#" in text[m.end():m.end() + 4]:
            ports_text = ""
        out = []
        for decl in re.split(r",(?![^\[]*\])", ports_text):
            d = decl.strip()
            mm = re.match(r"(input|output|inout)\b", d)
            ident = re.findall(r"[A-Za-z_]\w*", re.sub(r"\[[^\]]*\]", " ", d.split("=")[0]))
            if mm and ident:
                out.append((mm.group(1), ident[-1]))
        return out
    return []


def snippet(block: str, params: dict | None = None, instance: str | None = None, language: str = "sv") -> str:
    """An instantiation template in SystemVerilog: every parameter at the value given (or the default), every port connected
    to a wire of the same name for the user to rename. Not a verified integration: it shows names, not what to connect."""
    if language != "sv":
        return f"-- no {language} version of {block} exists in the library (languages: {', '.join(languages(block)) or 'none'})"
    y = iv._yaml(block)
    top = y.get("top", block)
    p = {**iv.defaults(block), **(params or {})}
    plist = ",\n".join(f"        .{k}({json.dumps(v) if isinstance(v, str) else v})" for k, v in p.items() if k in (y.get("parameters") or {}))
    ports = _ports(block)
    conn = ",\n".join(f"        .{n}({n})" for _, n in ports)
    head = f"    {top} #(\n{plist}\n    ) {instance or 'u_' + block} (\n" if plist else f"    {top} {instance or 'u_' + block} (\n"
    return head + conn + "\n    );" + ("" if ports else "   // (ports could not be read from the RTL header: see ip.yaml interfaces)")


# --- the lookup -------------------------------------------------------------------------------------------------------
_UNKNOWN = re.compile(r"not measured|not known at this point")


def _fit_status(v: dict) -> str:
    """"fits", "does not fit" (a figure is known and over the limit) or "unknown" (every reason is a figure nobody has
    measured at this point, for example the Fmax of a register-to-register path with no clocked path to time): not a rejection."""
    if v["fits"]:
        return "fits"
    if v["reasons"] and all(_UNKNOWN.search(r) for r in v["reasons"]):
        return "unknown"
    return "does not fit"


def lookup(query: str, part: str | None = None, clock_ns: float | None = None, budget: dict | None = None,
           need_ii: int | None = None, objective: str = "area", language: str = "sv", params: dict | None = None,
           k: int = 3) -> dict:
    """Entries that answer ``query``, best first.

    Returns ``{query, fits: bool, hits: [...], nearest_miss: [...], notes: [...]}``. Each hit has: ``block``, ``score``,
    ``matched`` (the request's words that matched, after stemming), ``summary``, ``languages``, ``verified`` (the label, or
    "unknown"), ``declared_status`` (the entry's own words, not a verification), ``variants`` (flow.ipvariants.choose at the
    given point: which fit and why not), ``measured`` (the nearest characterised row, with its part and tool), ``contract``
    and ``snippet``. With nothing matching, ``hits`` is empty, ``fits`` False and ``nearest_miss`` lists the best entries
    that did not meet the rule, with their matched words."""
    notes: list[str] = []
    if part is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", part):
        raise ValueError(f"part {part!r} is not a device part name")
    asked, query = query, normalise(query)
    qterms = tokens(query, expand=True)
    low = {w for w in re.findall(r"[a-z0-9-]+", query.lower())}
    qstems = set(tokens(query))
    ranked = []
    for b in iv.entries():
        s, hit = _score(b, qterms)
        nm = tokens(_snake(b))
        own = bool(nm) and all(t in qstems for t in nm)       # the request names the entry itself
        ranked.append((s, b, hit, own, coverage(hit, qterms)))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    good = [r for r in ranked if r[0] >= MIN_SCORE and (len(r[2]) >= MIN_TERMS or r[3]) and r[4] >= MIN_COVERAGE]
    if language not in ("sv", "v", "vhdl"):
        raise ValueError(f"language must be sv, v or vhdl, not {language!r}")

    def row(r, with_detail: bool) -> dict:
        s, b, hit, _, cov = r
        y = iv._yaml(b)
        out = {"block": b, "score": round(s, 2), "matched": hit, "coverage": round(cov, 2), "summary": " ".join(str(y.get("summary", "")).split()),
               "languages": languages(b)}
        if with_detail:
            out["language_ok"] = language in languages(b) or (language == "v" and "sv" in languages(b))
            out["verified"] = verified_status(b)
            out["declared_status"] = " ".join(str(y.get("status", "")).split())
            out["contract"] = contract(b)
            out["measured"] = _measured_row(b, part)
            out["snippet"] = snippet(b, params, language=language)
            if y.get("variants"):
                try:
                    rows = iv.choose(b, params or {}, part=part, budget=budget or {}, clock_ns=clock_ns, need_ii=need_ii,
                                     objective=objective)
                    out["variants"] = [{"variant": v["variant"], "fits": v["fits"], "status": _fit_status(v), "reasons": v["reasons"],
                                        "latency": (v.get("predicted") or {}).get("latency"),
                                        "ii": (v.get("predicted") or {}).get("ii"), "cost": v.get("cost"),
                                        "note": v.get("note")} for v in rows]
                except ValueError as ex:
                    out["variants_error"] = str(ex)
        return out

    hits = [row(r, True) for r in good[:k]]
    if language == "vhdl":
        notes.append("no ip_lib entry has a VHDL version (0 .vhd files); every hit is SystemVerilog and is marked language_ok false")
    if not hits:
        notes.append("nothing in the library fits this request (fewer than two matching words, or a weak match); the nearest "
                     "entries below are near misses, listed so you can check, not recommended")
        words = set(low)
        for triggers, answer in HOUSE_ANSWERS:
            if words & triggers:
                notes.append(answer)
    nearest = [] if hits else [row(r, False) for r in ranked[:3] if r[0] > 0]
    if hits and not any(h["language_ok"] for h in hits):
        notes.append(f"the entries that match are not available in {language}: the library's languages are "
                     f"{', '.join(sorted({x for h in hits for x in h['languages']}))}")
    return {"query": asked, "fits": any(h["language_ok"] for h in hits), "hits": hits, "nearest_miss": nearest, "notes": notes,
            "part": part or iv.DEFAULT_PART, "library_entries": len(iv.entries()),
            "costs_note": "costs and Fmax are Artix-7 (xc7a100tcsg324-1) measurements unless a row names another part"}


def show(block: str, params: dict | None = None, variant: str | None = None, language: str = "sv",
         part: str | None = None) -> dict:
    y = iv._yaml(block)                                  # raises ValueError for an unknown entry
    p = dict(params or {})
    if variant and y.get("variant_param"):
        p[y["variant_param"]] = variant
    return {"block": block, "version": y.get("version"), "summary": " ".join(str(y.get("summary", "")).split()),
            "languages": languages(block), "verified": verified_status(block),
            "declared_status": " ".join(str(y.get("status", "")).split()), "contract": contract(block),
            "variants": {k: {"summary": v.get("summary"), "when": v.get("when"), "latency": v.get("latency"), "ii": v.get("ii"),
                             "uses": v.get("uses")} for k, v in (y.get("variants") or {}).items()},
            "measured": _measured_row(block, part), "snippet": snippet(block, p, language=language),
            "files": sorted(str(x.relative_to(IP / block)) for x in (IP / block / "rtl").glob("*")) if (IP / block / "rtl").is_dir() else [],
            "readme": f"ip_lib/{block}/README.md"}


# --- rendering and the command ----------------------------------------------------------------------------------------
def render(res: dict) -> str:
    lines = [f"request: {res['query']}", f"library: {res['library_entries']} entries; fits: {'yes' if res['fits'] else 'NO (nothing fits)'}"]
    for h in res["hits"]:
        lines.append(f"\n{h['block']}  score {h['score']}  matched: {', '.join(h['matched'])}")
        lines.append(f"  {h['summary'][:300]}")
        lines.append(f"  languages: {', '.join(h['languages'])}; verified label: {h['verified']['label']}"
                     + ("" if h["language_ok"] else "  (NOT in the language you asked for)"))
        for v in h.get("variants", []):
            lines.append(f"  variant {v['variant']}: {v['status'] if v['fits'] or v['status'] == 'unknown' else 'does not fit'}"
                         f"{'' if v['fits'] else ': ' + '; '.join(v['reasons'])[:160]}"
                         f" (latency {v['latency']}, II {v['ii']})")
        if h.get("measured"):
            m = h["measured"]
            lines.append(f"  measured: {', '.join(f'{k} {m[k]}' for k in ('variant', 'lut', 'ff', 'bram_tiles', 'dsp', 'fmax_mhz') if k in m)}"
                         f" on {m.get('part')} ({m.get('tool')})")
    for h in res["nearest_miss"]:
        lines.append(f"\nnear miss (not a recommendation): {h['block']}  score {h['score']}  matched: {', '.join(h['matched'])}\n  {h['summary'][:200]}")
    for n in res["notes"]:
        lines.append(f"\nnote: {n}")
    lines.append(f"\n{res['costs_note']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m flow.iplookup", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="find entries for a request")
    s.add_argument("words", nargs="+")
    s.add_argument("--part"), s.add_argument("--clock-ns", type=float), s.add_argument("--budget", default="")
    s.add_argument("--need-ii", type=int), s.add_argument("--objective", default="area", choices=["area", "fabric", "throughput", "fmax"])
    s.add_argument("--language", default="sv", choices=["sv", "v", "vhdl"]), s.add_argument("--params", default="")
    s.add_argument("-k", type=int, default=3), s.add_argument("--json", action="store_true")
    w = sub.add_parser("show", help="the contract, variants and an instantiation snippet of one entry")
    w.add_argument("block"), w.add_argument("--params", default=""), w.add_argument("--variant"), w.add_argument("--part")
    w.add_argument("--language", default="sv", choices=["sv", "v", "vhdl"])
    a = ap.parse_args(argv)
    try:
        if a.cmd == "search":
            res = lookup(" ".join(a.words), a.part, a.clock_ns, iv._kv(a.budget), a.need_ii, a.objective, a.language,
                         iv._kv(a.params), a.k)
            print(json.dumps(res, indent=1) if a.json else render(res))
        else:
            print(json.dumps(show(a.block, iv._kv(a.params), a.variant, a.language, a.part), indent=1))
    except ValueError as ex:
        print(f"iplookup: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

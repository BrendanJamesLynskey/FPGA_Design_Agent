"""Two constraint rules from brief 105A (owner decisions 6 and 7, 2026-11-19): the configuration-voltage gate and the
blanket asynchronous clock group flag.

**CFGBVS / CONFIG_VOLTAGE (decision 6).** Vivado reports DRC CFGBVS-1 as a Warning, so ``drc_clean`` (Errors and Critical
Warnings) lets a design with no declared configuration-bank voltage through, and the bitstream is written. The rule here
raises CFGBVS-1 and CFGBVS-2 to a gate failure, but only for a board whose configuration voltage is *confirmed* in its board
file: ``boards/<board>/board.yaml`` ``config`` has ``cfgbvs`` and ``config_voltage`` and cites at least one source (``source:``)
and carries no ``status`` (``unconfirmed`` or ``assumption``). For such a board the flow also sets the two properties itself
(``flow/prepare.py`` writes ``board_config.xdc``, read last, so the board file wins). On any other board the rows stay
advisory, as before, and the flow sets nothing.

**XPM SIM_ASSERT_CHK (decision 8).** AMD's ``xpm_cdc_*`` macros default ``SIM_ASSERT_CHK`` to 0, which turns off their own simulation
warnings for misuse (a source that changes faster than the destination clock can sample, a Gray bus that jumps by more than one
code). The house default is 1. :func:`xpm_sim_findings` flags an instance (of a macro that has the parameter) that sets it to
anything but 1 or leaves it out. Advisory (never blocks): it changes simulation messages only.

**Blanket asynchronous clock groups (decision 7).** ``set_clock_groups -asynchronous`` removes timing from every path
between its groups, including crossings nobody declared. :func:`async_group_findings` flags, for owner review, (a) every
clock pair that report_clock_interaction classes ``Asynchronous Groups`` and that has endpoints between the two clocks, and
(b) any one command whose groups cover every clock of the design. It is advisory: nothing here returns a blocking finding.

    python3 flow/constraint_gates.py <build dir>      # prints both verdicts for a finished build
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFGBVS_RULES = ("CFGBVS-1", "CFGBVS-2")
UNCONFIRMED = ("unconfirmed", "assumption")


# ---------------------------------------------------------------------------------------------------------------------
# rule 1: configuration bank voltage
# ---------------------------------------------------------------------------------------------------------------------
def board_config(board: str | None, root: Path = ROOT) -> dict[str, Any] | None:
    """``boards/<board>/board.yaml`` ``config`` plus ``confirmed``; None when the board has no config block (UltraScale+
    and Zynq boards, whose configuration voltage the DRC does not ask for)."""
    if not board:
        return None
    f = root / "boards" / board / "board.yaml"
    if not f.is_file():
        return None
    cfg = (yaml.safe_load(f.read_text()) or {}).get("config")
    if not isinstance(cfg, dict):
        return None
    out = dict(cfg)
    out["board"] = board
    out["confirmed"] = (cfg.get("cfgbvs") in ("VCCO", "GND") and cfg.get("config_voltage") is not None
                        and bool(cfg.get("source")) and "status" not in cfg)
    return out


def xdc_lines(cfg: dict[str, Any] | None) -> list[str]:
    """The two properties the flow sets for a confirmed board; nothing for any other."""
    if not cfg or not cfg.get("confirmed"):
        return []
    return [f"set_property CFGBVS {cfg['cfgbvs']} [current_design]",
            f"set_property CONFIG_VOLTAGE {cfg['config_voltage']} [current_design]"]


def cfgbvs_rows(drc_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in drc_rows if r["rule"] in CFGBVS_RULES]


def cfgbvs_verdict(drc_rows: list[dict[str, Any]], cfg: dict[str, Any] | None) -> dict[str, Any]:
    """``applies``: the board's voltage is confirmed, so the rows block. ``rows``: the CFGBVS rows of the DRC. ``ok``: the gate
    value (True when it does not apply)."""
    rows = cfgbvs_rows(drc_rows)
    applies = bool(cfg and cfg.get("confirmed"))
    return {"applies": applies, "board": (cfg or {}).get("board"), "rows": [f"{r['rule']} ({r['severity']}) x{r['count']}" for r in rows],
            "ok": not (applies and rows)}


_SET_PROP = re.compile(r"set_property\s+(CFGBVS|CONFIG_VOLTAGE)\s+(\S+)\s+\[current_design\]", re.I)


def xdc_declared(xdcs: list[Path]) -> dict[str, str]:
    """CFGBVS / CONFIG_VOLTAGE values the design's own XDCs set (last one wins)."""
    out: dict[str, str] = {}
    for x in xdcs:
        try:
            text = x.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = _SET_PROP.search(line)
            if m:
                out[m.group(1).upper()] = m.group(2).strip("{}")
    return out


def cfgbvs_mismatch(cfg: dict[str, Any] | None, declared: dict[str, str]) -> list[str]:
    """A design XDC that states a value other than the confirmed board's (the flow's board_config.xdc is read last and wins)."""
    if not cfg or not cfg.get("confirmed"):
        return []
    want = {"CFGBVS": str(cfg["cfgbvs"]), "CONFIG_VOLTAGE": str(cfg["config_voltage"])}
    out = []
    for k, v in declared.items():
        try:
            same = float(v) == float(want[k]) if k == "CONFIG_VOLTAGE" else v == want[k]
        except ValueError:
            same = False
        if not same:
            out.append(f"{k} {v} in the design's XDC, {want[k]} in the board file")
    return out


# ---------------------------------------------------------------------------------------------------------------------
# rule 2: blanket asynchronous clock groups
# ---------------------------------------------------------------------------------------------------------------------
def parse_clock_pairs(text: str) -> list[dict[str, Any]]:
    """report_clock_interaction rows: {from, to, constraints, endpoints}. The table is fixed width; the column spans come from
    the dashed rule under the header. ``endpoints`` is the larger of the setup and hold total-endpoint counts (0 when blank)."""
    lines = text.splitlines()
    rule = next((i for i, ln in enumerate(lines) if re.match(r"^-{5,}(\s+-+)+\s*$", ln)), None)
    if rule is None:
        return []
    spans = [(m.start(), m.end()) for m in re.finditer(r"-+", lines[rule])]
    if len(spans) < 15:
        return []
    rows = []
    for ln in lines[rule + 1:]:
        if not ln.strip():
            break

        def col(i: int) -> str:
            a, b = spans[i]
            return ln[a:b].strip() if i < len(spans) - 1 else ln[a:].strip()
        nums = []
        for i in (6, 12):
            v = col(i)
            nums.append(int(v) if v.isdigit() else 0)
        rows.append({"from": col(0), "to": col(1), "constraints": col(len(spans) - 1), "endpoints": max(nums)})
    return rows


def _is_hub(name: str) -> bool:
    return "dbg_hub" in name and "TCK" in name


def async_pair_findings(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairs the report classes ``Asynchronous Groups`` with endpoints between them (the debug hub's own TCK pairs are required to be
    asynchronous by brief 48 and are left out)."""
    out = []
    for r in pairs:
        if "Asynchronous Groups" not in r["constraints"] or r["from"] == r["to"] or r["endpoints"] <= 0:
            continue
        if _is_hub(r["from"]) or _is_hub(r["to"]):
            continue
        out.append({"code": "XDC-ASYNC-PATHS", "where": f"{r['from']} -> {r['to']}", "endpoints": r["endpoints"],
                    "message": f"set_clock_groups -asynchronous removes timing from {r['endpoints']} endpoint(s) between {r['from']} and "
                               f"{r['to']}; confirm each crossing is declared and bounded (set_max_delay -datapath_only, "
                               f"set_bus_skew), or constrain this pair on its own"})
    return out


def _tcl_lines(text: str) -> list[str]:
    """Commands of an XDC: comments dropped, backslash continuations joined."""
    text = re.sub(r"\\\s*\n", " ", text)
    cmds = []
    for ln in text.splitlines():
        s = ln.split("#", 1)[0] if not re.search(r"\{[^}]*#", ln) else ln
        if s.strip():
            cmds.append(s.strip())
    return cmds


def clock_groups(xdc_text: str) -> list[dict[str, Any]]:
    """Each ``set_clock_groups -asynchronous`` command: {line, groups: [[names]], unresolved}. A group member that is not a plain
    name list (``-of_objects``, a nested command other than get_clocks) sets ``unresolved``."""
    out = []
    for cmd in _tcl_lines(xdc_text):
        if not re.match(r"set_clock_groups\b", cmd) or not re.search(r"-asynchronous\b", cmd):
            continue
        groups, unresolved = [], False
        for g in re.split(r"-group\b", cmd)[1:]:
            names: list[str] = []
            for br in re.findall(r"\[([^\[\]]*)\]", g):
                if not br.strip().startswith("get_clocks") or "-of_objects" in br:
                    unresolved = True
                    continue
                body = re.sub(r"-\w+", " ", br.replace("get_clocks", " "))
                names += [t for t in re.split(r"[\s{}]+", body) if t]
            rest = re.sub(r"\[[^\[\]]*\]", " ", g)
            rest = re.sub(r"-\w+(\s+\S+)?\s*$", " ", rest)
            names += [t for t in re.split(r"[\s{}]+", rest) if t and not t.startswith("-")]
            groups.append(names)
        out.append({"cmd": cmd[:200], "groups": groups, "unresolved": unresolved})
    return out


def covers_all(group_cmds: list[dict[str, Any]], clocks: list[str]) -> list[dict[str, Any]]:
    """Commands whose groups between them name every clock of the design (patterns match by fnmatch)."""
    out = []
    real = [c for c in clocks if not _is_hub(c)]
    if len(real) < 2:
        return out
    for gc in group_cmds:
        if gc["unresolved"] or len(gc["groups"]) < 2:
            continue
        hit = {c for c in real if any(fnmatch.fnmatchcase(c, pat) for g in gc["groups"] for pat in g)}
        if hit == set(real):
            out.append(gc)
    return out


def async_group_findings(clock_interaction_text: str, xdc_texts: list[str]) -> list[dict[str, Any]]:
    """All advisory findings for rule 2 (never blocking)."""
    pairs = parse_clock_pairs(clock_interaction_text) if clock_interaction_text else []
    out = async_pair_findings(pairs)
    clocks = sorted({r["from"] for r in pairs} | {r["to"] for r in pairs})
    for t in xdc_texts:
        for gc in covers_all(clock_groups(t), clocks):
            out.append({"code": "XDC-ASYNC-ALL", "where": gc["cmd"], "endpoints": None,
                        "message": "one set_clock_groups -asynchronous names every clock of the design, so no path between two clocks is "
                                   "timed; replace it with per-crossing set_max_delay -datapath_only on the declared crossings"})
    for f in out:
        f["blocking"] = False
    return out


# ---------------------------------------------------------------------------------------------------------------------
# rule 3: XPM SIM_ASSERT_CHK
# ---------------------------------------------------------------------------------------------------------------------
#: the xpm_cdc macros that have the parameter (UG974); xpm_cdc_async_rst has none, so it is never a finding
XPM_WITH_SIM_ASSERT = ("single", "array_single", "sync_rst", "pulse", "gray", "handshake")
_XPM_INST = re.compile(r"(?<![\w.$])xpm_cdc_(%s)\b\s*(#\s*\()?" % "|".join(XPM_WITH_SIM_ASSERT))


def _strip_comments(text: str) -> str:
    """Comments and string literals blanked, newlines kept (so line numbers stay right)."""
    def blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"', blank, text, flags=re.S)


def xpm_sim_findings(text: str, where: str = "") -> list[dict[str, Any]]:
    """Instances of an xpm_cdc macro with the parameter whose ``SIM_ASSERT_CHK`` is not 1 (set to something else, or left at AMD's
    default 0). A bare module name followed by an instance name (no ``#(``) is an instance too; a mention in a comment or string is not."""
    t = _strip_comments(text)
    out = []
    for m in _XPM_INST.finditer(t):
        line = t.count("\n", 0, m.start()) + 1
        if m.group(2):
            i, depth = m.end(), 1
            while depth and i < len(t):
                depth += (t[i] == "(") - (t[i] == ")")
                i += 1
            body, after = t[m.end():i - 1], t[i:i + 80]
        else:
            body, after = "", t[m.end():m.end() + 80]
        if not re.match(r"\s*\w+\s*\(", after) and not re.match(r"\s*\w+\s*;", after):     # a module header or a port list, not an instance
            continue
        s = re.search(r"\.SIM_ASSERT_CHK\s*\(\s*([^)]*?)\s*\)", body)
        val = s.group(1) if s else None
        if val == "1":
            continue
        out.append({"code": "XPM-SIM-01", "where": f"{where}:{line}" if where else str(line), "macro": f"xpm_cdc_{m.group(1)}",
                    "value": val, "blocking": False,
                    "message": f"xpm_cdc_{m.group(1)} has SIM_ASSERT_CHK " + (f"set to {val}" if val is not None else "at AMD's default 0")
                               + ", which turns off the macro's simulation warnings; set .SIM_ASSERT_CHK(1) (house default, simulation only)"})
    return out


_XPM_INST_VHDL = re.compile(r"(?i):\s*(?:entity\s+(?:\w+\.)?|component\s+)?xpm_cdc_(%s)\b" % "|".join(XPM_WITH_SIM_ASSERT))


def xpm_sim_findings_vhdl(text: str, where: str = "") -> list[dict[str, Any]]:
    """The VHDL twin of :func:`xpm_sim_findings` (brief 153): an instance ``label : xpm_cdc_single ...``, ``label : entity xpm.xpm_cdc_single
    ...`` or ``label : component xpm_cdc_single ...`` whose ``generic map`` has no ``SIM_ASSERT_CHK => 1``. A component declaration (no
    label before the name) and a mention in a comment or string are not instances. The instance statement ends at its ``;``."""
    from flow.sources import strip_comments
    t = re.sub(r'"(?:[^"\n]|"")*"', lambda m: " " * len(m.group(0)), strip_comments(text, "vhdl"))
    out = []
    for m in _XPM_INST_VHDL.finditer(t):
        end = t.find(";", m.end())
        body = t[m.end():end if end >= 0 else len(t)]
        gm = re.search(r"(?i)\bgeneric\s+map\s*\(", body)
        s = None
        if gm:
            i, depth = gm.end(), 1
            while depth and i < len(body):
                depth += (body[i] == "(") - (body[i] == ")")
                i += 1
            s = re.search(r"(?i)\bSIM_ASSERT_CHK\s*=>\s*([^,)\s]+)", body[gm.end():i])
        val = s.group(1) if s else None
        if val == "1":
            continue
        line = t.count("\n", 0, m.start()) + 1
        out.append({"code": "XPM-SIM-01", "where": f"{where}:{line}" if where else str(line), "macro": f"xpm_cdc_{m.group(1).lower()}",
                    "value": val, "blocking": False,
                    "message": f"xpm_cdc_{m.group(1).lower()} has SIM_ASSERT_CHK " + (f"set to {val}" if val is not None else "at AMD's default 0")
                               + ", which turns off the macro's simulation warnings; set SIM_ASSERT_CHK => 1 (house default, simulation only)"})
    return out


def evaluate(d: Path, xdcs: list[Path], board: str | None, root: Path = ROOT) -> dict[str, Any]:
    """Both rules for a finished build directory (flow/gates.py calls the pieces; this is the command-line summary)."""
    from flow.gates import parse_rule_table
    cfg = board_config(board, root)
    drc = parse_rule_table((d / "drc.rpt").read_text(errors="replace")) if (d / "drc.rpt").is_file() else []
    ci = (d / "clock_interaction_route.rpt")
    return {"config_voltage": cfgbvs_verdict(drc, cfg),
            "async_groups": async_group_findings(ci.read_text(errors="replace") if ci.is_file() else "",
                                                 [x.read_text(errors="replace") for x in xdcs if x.is_file()])}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    bd = Path(sys.argv[1]).resolve()
    prep = json.loads((bd / "prepare.json").read_text())
    xs = [ROOT / f for f in prep.get("files", []) if f.endswith(".xdc")]
    print(json.dumps(evaluate(bd, xs, prep.get("board")), indent=1))

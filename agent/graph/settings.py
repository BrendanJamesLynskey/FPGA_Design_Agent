"""Proposed settings: the agent reads an input folder and proposes the variable levers it can read, each with its source. The user confirms or edits
every value **in the spec interview** (brief 194, docs/agent_levers.md): there is no separate confirmation screen.

``propose(folder)`` writes ``proposed_settings.yaml``, which is the interview's input (``agent run --settings <file>``). Every setting has ``value``,
``sources`` (file and where), ``conflicts`` (another source that says something else), ``confidence`` and ``status`` (``proposed``: read from a
source; ``ask``: nothing readable, the value is empty and nothing is guessed). ``questions(doc)`` turns each setting into one interview question
whose default is the proposed value and whose reason names its source and any conflict; ``resolve(doc, answers)`` turns the answers into the
confirmed settings (the interview's output, ``confirmed_settings.yaml`` in the design) and lists what is still unconfirmed: a setting with no
value (a person must give it), or a setting with an open conflict that only the default decided. The run cannot leave the interview while that
list is not empty.

Sources, in the order they are read: ``board_facts.yaml`` (the design-package ingest of brief 174, ``python -m flow.package ingest``, each fact
with its source), a ``board.yaml`` in the folder, the board catalogue under ``boards/``, and the spec in the folder for the suggested profile. An
ingest that is not there is no error: the settings it would have given are asked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from agent.graph import assurance, profiles

ROOT = Path(__file__).resolve().parents[2]
KEYS = ("board", "part", "speed_grade", "reference_clocks", "io_standards", "phys", "interfaces", "profile")
FILE = "proposed_settings.yaml"
_INTERFACE_KEYS = ("uart", "jtag", "ethernet", "usb", "pcie", "hdmi", "vga", "sd", "qspi", "ddr", "pmod", "audio", "mic")
_PART = re.compile(r"^(x[a-z0-9]+?)(-?)([0-9]L?[A-Z]*|-[0-9]L?V?-[a-z])$")


class SettingsError(ValueError):
    pass


def _entry(value: Any = None, sources: list[str] | None = None, confidence: str = "high") -> dict[str, Any]:
    return {"value": value, "sources": sources or [], "conflicts": [], "confidence": confidence, "status": "proposed" if value not in (None, "", []) else "ask"}


def _facts(folder: Path) -> tuple[dict[str, Any], str | None]:
    f = folder / "board_facts.yaml"
    if not f.is_file():
        return {}, None
    try:
        d = yaml.safe_load(f.read_text()) or {}
    except yaml.YAMLError:
        return {}, None
    return (d.get("facts", d) if isinstance(d, dict) else {}), str(f)


def _fact_value(v: Any) -> tuple[Any, str]:
    """A fact is a plain value or {value, source, confidence}."""
    if isinstance(v, dict) and "value" in v:
        src = v.get("source")
        return v["value"], (src if isinstance(src, str) else yaml.safe_dump(src, default_flow_style=True).strip()) if src else ""
    return v, ""


def _catalogue_board(folder: Path, hints: list[str]) -> tuple[str | None, str]:
    """The catalogue board the folder is about: a folder or file name, or a board name in a hint, that equals a catalogue entry."""
    names = sorted(p.name for p in (ROOT / "boards").iterdir() if (p / "board.yaml").is_file())
    cands = [folder.name.lower(), *[h.lower() for h in hints], *[p.name.lower() for p in folder.iterdir()]]
    for n in sorted(names, key=len, reverse=True):
        for c in cands:
            if n in re.sub(r"[^a-z0-9_]", "_", c):
                return n, f"the name '{c}' contains the catalogue board {n}"
    return None, ""


def propose(folder: Path, board_hint: str | None = None) -> dict[str, Any]:
    folder = Path(folder)
    if not folder.is_dir():
        raise SettingsError(f"{folder} is not a folder")
    facts, facts_file = _facts(folder)
    s: dict[str, dict[str, Any]] = {k: _entry() for k in KEYS}

    def put(key: str, value: Any, src: str, confidence: str = "high") -> None:
        e = s[key]
        if value in (None, "", []):
            return
        if e["value"] in (None, "", []):
            e.update(value=value, sources=[src], confidence=confidence, status="proposed")
        elif e["value"] != value:
            e["conflicts"].append({"value": value, "source": src})
        else:
            e["sources"].append(src)

    # 1. the design-package ingest, when there is one
    if facts:
        for k in ("board", "part", "speed_grade"):
            if k in facts:
                v, src = _fact_value(facts[k])
                put(k, v, f"{facts_file}: {src}" if src else facts_file)
        for k, name in (("reference_clocks", "reference_clocks"), ("io_standards", "io_standards"), ("phys", "phys"), ("interfaces", "interfaces")):
            if name in facts:
                v, src = _fact_value(facts[name])
                put(k, v, f"{facts_file}: {src}" if src else facts_file)
    # 2. the catalogue board named by the facts, the hint or the folder
    named = (s["board"]["value"] if isinstance(s["board"]["value"], str) else None) or board_hint
    cat, why = (named, "the board named by the ingest or the caller") if named and (ROOT / "boards" / str(named) / "board.yaml").is_file() else _catalogue_board(folder, [str(named or "")])
    if cat:
        b = yaml.safe_load((ROOT / "boards" / cat / "board.yaml").read_text()) or {}
        src = f"boards/{cat}/board.yaml"
        put("board", cat, f"{src} ({why})", "medium")
        if b.get("part"):
            put("part", b["part"], src)
            m = re.search(r"-(\d)(L?)(?=[A-Z]*(?:-[a-z])?$)", str(b["part"]))
            put("speed_grade", f"-{m.group(1)}{m.group(2)}" if m else None, f"{src} (the part's suffix)")
        clk = b.get("clock")
        if isinstance(clk, dict) and clk.get("freq_mhz"):
            put("reference_clocks", [{"port": clk.get("port"), "pin": clk.get("pin"), "freq_mhz": clk["freq_mhz"]}], f"{src} clock:")
        ios = b.get("iostandards")
        if isinstance(ios, dict) and ios.get("default"):
            put("io_standards", {"default": ios["default"], "exceptions": [e.get("iostandard") + " on " + ",".join(e.get("ports", [])) for e in ios.get("exceptions", [])]}, f"{src} iostandards:")
        phys = [str(k) for k in b if "phy" in str(k).lower() or str(k).lower() in ("ethernet", "eth", "lan")]
        put("phys", phys, f"{src} (keys naming a PHY)", "low")
        put("interfaces", [k for k in b if str(k).lower() in _INTERFACE_KEYS], f"{src} (interface keys)", "medium")
    # 3. the suggested profile, from the spec in the folder
    spec = {}
    for f in ("spec.yaml", "spec.md"):
        p = folder / f
        if p.is_file():
            try:
                spec = yaml.safe_load(p.read_text()) if f.endswith(".yaml") else {"requirements": [{"text": p.read_text()[:4000]}]}
            except yaml.YAMLError:
                spec = {}
            spec = spec if isinstance(spec, dict) else {}
            break
    prof, why_p = assurance.propose_profile(spec)
    s["profile"].update(value=prof, sources=[f"agent.graph.assurance.propose_profile: {why_p}"], confidence="low" if not spec else "medium", status="proposed")
    # an Xilinx part from the constraint files is not parsed here; a missing part stays a question
    out = {"schema": "fpga-design-agent/settings/v1", "folder": str(folder), "ingest": facts_file, "settings": s,
           "note": "Every value is waiting for you. Edit a value, then set its status to confirmed (or run `agent settings confirm`). A value with status ask is empty on purpose: nothing was readable and nothing is guessed."}
    return out


def write(folder: Path, out: dict[str, Any], dest: Path | None = None) -> Path:
    dest = dest or Path(folder) / FILE
    dest.write_text(yaml.safe_dump(out, sort_keys=False))
    return dest


SENTINEL = "(not given: please give a value)"


def load_proposals(path: Path) -> dict[str, Any]:
    d = yaml.safe_load(Path(path).read_text())
    if not isinstance(d, dict) or d.get("schema") != "fpga-design-agent/settings/v1" or not isinstance(d.get("settings"), dict):
        raise SettingsError(f"{path} is not a settings file")
    return d


def apply_flags(doc: dict[str, Any], board: str | None, profile: str | None) -> dict[str, Any]:
    """An explicit ``--board`` or ``--verif-profile`` is the user's own choice: it becomes the proposed value, with the command line as its source."""
    for key, v in (("board", board), ("profile", profile)):
        if v:
            e = doc["settings"][key]
            if e["value"] != v:
                e["sources"] = [*e.get("sources", []), "the command line"]
                e["value"], e["status"], e["conflicts"] = v, "proposed", []
    return doc


def questions(doc: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(key, text, default, reason) for every setting: the default is the proposed value (a sentinel when there is none)."""
    out = []
    for k in KEYS:
        e = doc["settings"].get(k)
        if e is None:
            continue
        has = e["value"] not in (None, "", [])
        default = json.dumps(e["value"]) if has else SENTINEL
        if has:
            reason = "read from: " + ("; ".join(e.get("sources") or ["(no source recorded)"]))
            if e.get("conflicts"):
                reason += ". CONFLICT, please choose: " + "; ".join(f"{json.dumps(c['value'])} from {c['source']}" for c in e["conflicts"])
        else:
            reason = "nothing in the folder gives this value, and nothing is guessed: it must come from you"
        out.append((k, f"Confirm the setting '{k}'. Answer with the value to use (JSON; a plain word is taken as text).", default, reason))
    return out


def _parse(text: str, proposed: Any) -> Any:
    t = (text or "").strip()
    try:
        v = json.loads(t)
    except ValueError:
        return t
    if isinstance(proposed, str) and not isinstance(v, str):
        return t                              # "-1" for a speed grade is text, not a number
    return v


def resolve(doc: dict[str, Any], answers: dict[str, tuple[str | None, str]]) -> tuple[dict[str, Any], list[str]]:
    """The confirmed values and the unconfirmed list. ``answers``: key -> (answer text, status) with status ``answered`` (a person or the oracle
    gave it) or ``defaulted``. A default decides only a setting that has a value and no conflict."""
    values: dict[str, Any] = {}
    bad: list[str] = []
    for k in KEYS:
        e = doc["settings"].get(k)
        if e is None:
            continue
        text, status = answers.get(k, (None, "defaulted"))
        if status == "defaulted" or text in (None, "", SENTINEL, "not specified"):
            v = e["value"]
            if v in (None, "", []):
                bad.append(f"{k}: nothing was proposed and nobody gave a value")
                continue
            if e.get("conflicts"):
                bad.append(f"{k}: the sources disagree and only the default decided; choose one")
                continue
            values[k] = v
        else:
            v = _parse(text, e["value"])
            if v in (None, "", []):
                bad.append(f"{k}: the answer is empty")
                continue
            values[k] = v
    return values, bad


def confirmed_document(doc: dict[str, Any], values: dict[str, Any], answers: dict[str, tuple[str | None, str]]) -> dict[str, Any]:
    out = {"schema": "fpga-design-agent/settings/v1", "folder": doc.get("folder"), "settings": {}}
    for k, v in values.items():
        e = dict(doc["settings"][k])
        by = answers.get(k, (None, "defaulted"))[1]
        e.update(value=v, status="confirmed", conflicts=[], confirmed_by="interview: " + by + (" (value edited)" if v != doc["settings"][k]["value"] else ""))
        out["settings"][k] = e
    return out

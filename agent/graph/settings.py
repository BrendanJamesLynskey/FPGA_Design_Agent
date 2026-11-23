"""Proposed settings: the agent reads an input folder and proposes the variable levers it can read, each with its source; the user confirms
or edits every value before the real run starts (brief 194, docs/agent_levers.md).

``propose(folder)`` writes ``proposed_settings.yaml``. Every setting has ``value``, ``sources`` (file and where), ``conflicts`` (another source
that says something else), ``confidence`` and ``status``: ``proposed`` (read from a source, waiting for the user), ``ask`` (nothing readable:
the value is empty and the user must give it; nothing is guessed) or ``confirmed`` (the user, by ``agent settings confirm`` or the Navigator).
``load_confirmed(file)`` is what ``agent run --settings`` calls: it refuses a file with any setting that is not confirmed, or that is
confirmed with an empty value.

Sources, in the order they are read: ``board_facts.yaml`` (the design-package ingest of brief 174, ``python -m flow.package ingest``, each fact
with its source), a ``board.yaml`` or Xilinx constraint files in the folder, the board catalogue under ``boards/``, and the spec in the folder
for the suggested profile. An ingest that is not there is no error: the settings it would have given are asked.
"""

from __future__ import annotations

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


def confirm(path: Path, keys: list[str] | None = None) -> list[str]:
    """What ``agent settings confirm`` does: mark the named settings (or every one that has a value and no conflict) as confirmed. A value
    that is empty or has an open conflict cannot be confirmed by this call; the user edits the file."""
    d = yaml.safe_load(Path(path).read_text())
    done = []
    for k, e in d["settings"].items():
        if keys and k not in keys:
            continue
        if e["value"] in (None, "", []) or e.get("conflicts"):
            continue
        e["status"] = "confirmed"
        done.append(k)
    Path(path).write_text(yaml.safe_dump(d, sort_keys=False))
    return done


def load_confirmed(path: Path) -> dict[str, Any]:
    """The values of a fully confirmed settings file, or SettingsError naming every setting that is not."""
    d = yaml.safe_load(Path(path).read_text())
    if not isinstance(d, dict) or d.get("schema") != "fpga-design-agent/settings/v1":
        raise SettingsError(f"{path} is not a settings file")
    bad = []
    for k, e in d["settings"].items():
        if e.get("status") != "confirmed":
            bad.append(f"{k}: {e.get('status')}")
        elif e["value"] in (None, "", []):
            bad.append(f"{k}: confirmed with an empty value")
        elif e.get("conflicts"):
            bad.append(f"{k}: confirmed with an open conflict (remove the other source's value once you have chosen)")
    if bad:
        raise SettingsError("settings not confirmed, the run does not start: " + "; ".join(bad))
    return {k: e["value"] for k, e in d["settings"].items()}


def apply_to_args(values: dict[str, Any], board: str | None, verif_profile: str | None) -> tuple[str, str]:
    """(board, profile) the run uses. A command-line flag that disagrees with a confirmed value is refused, not silently overridden."""
    b, p = values.get("board"), values.get("profile")
    if board and b and board != b:
        raise SettingsError(f"--board {board} disagrees with the confirmed board {b}")
    if verif_profile and p and verif_profile != p:
        raise SettingsError(f"--verif-profile {verif_profile} disagrees with the confirmed profile {p}")
    if p and p not in profiles.PROFILES:
        raise SettingsError(f"unknown profile {p!r}")
    return b or board, p or verif_profile

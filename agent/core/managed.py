"""Managed projects (brief 102, stage 1): a manifest of components, ownership enforced in the tools, and scoped requests.

A design directory may hold a ``project.yaml`` (schema ``fda-managed-project/1``). Each component lists the files it owns
(``paths``), an **ownership** and a **level**:

- ``owned``    the agent may edit it (inside the request's scope);
- ``frozen``   the agent may read it and never edit it (an imported block, or one the owner has signed off);
- ``excluded`` hidden from the agent's tools: reads and listings refuse, the manifest view leaves it out. It is still
  built and signed off with the rest: the build reads ``build.yaml``, not the agent's view, and a ``build.yaml`` that
  drops an excluded (or any) component is refused (:meth:`ManagedPolicy.check_build`).

Levels: ``rtl``, ``netlist`` (EDIF or a post-synthesis checkpoint), ``placed_routed``, ``vendor_ip``, ``encrypted_ip``. Stage 1
implements ``rtl`` and ``netlist`` imports (flow/managed_import.py); stage 2 adds ``placed_routed`` (a routed checkpoint locked
with ``lock_design -level routing``, always frozen, with a ``placement`` keep-out region the placement tools and the constraints
must respect: :meth:`ManagedPolicy.check_xdc`, :meth:`ManagedPolicy.check_rw`); ``vendor_ip`` and ``encrypted_ip`` validate and are
enforced the same way.

**Ownership is enforced in :class:`agent.core.security.PathJail`**, which every file tool already goes through: the jail
holds a :class:`ManagedPolicy` and calls it with the resolved, design-relative path (``..`` and symlinks already resolved).
A write also needs the path's component to be in the request's **scope**; a write to a file that declares a component's
module with a different port list than the manifest's interface contract is refused and flagged for the owner.

A **scope** (:class:`Scope`) is the set of components one request may touch (default: every owned component). It is
resolved by :func:`resolve_request` from ``--scope`` names or hierarchy paths, or from free text; an ambiguous request
produces a question, never edits. The scope, the plan and the provenance report are written to ``build/managed/``.

**Trust labels** (:func:`trust`) are computed, never declared: ``documented`` (provenance complete, hash matches),
``verified`` (an evidence file written by the flow records its own tests passing on this content), ``built`` (verified, and
a build in this project passed every gate on this content). Evidence lives in ``build/managed/evidence/``, which the agent
cannot write.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


SCHEMA = "fda-managed-project/1"
MANIFEST = "project.yaml"
OWNERSHIP = ("owned", "frozen", "excluded")
LEVELS = ("rtl", "netlist", "placed_routed", "vendor_ip", "encrypted_ip")
TRUST = ("none", "documented", "verified", "built")
MANAGED_DIR = Path("build") / "managed"
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOP_KEYS = {"schema", "name", "top", "unclaimed", "components", "approved_contract_changes"}
_COMP_KEYS = {"name", "ownership", "level", "module", "instance", "paths", "build_sources", "netlist", "aliases", "interface",
              "provenance", "reference_rtl", "description", "placement"}
_PROV_KEYS = {"origin", "version", "licence", "sha256", "tests"}
_PLACE_KEYS = {"lock", "region", "anchor", "timing_tolerance_ps"}
_SLICE_RANGE = re.compile(r"^SLICE_X(\d+)Y(\d+):SLICE_X(\d+)Y(\d+)$")
_DIRS = ("input", "output", "inout")


# --- the manifest -------------------------------------------------------------------------------------------------

@dataclass
class Component:
    name: str
    ownership: str
    level: str
    paths: list[str]
    module: str | None = None
    instance: str | None = None
    build_sources: list[str] = field(default_factory=list)       # repo-relative, as build.yaml lists them (rtl level)
    netlist: dict[str, Any] = field(default_factory=dict)        # {file, format: edif|checkpoint, cell}
    aliases: list[str] = field(default_factory=list)
    interface: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    reference_rtl: list[str] = field(default_factory=list)       # design-relative RTL the netlist must be equivalent to
    description: str = ""
    placement: dict[str, Any] = field(default_factory=dict)      # placed_routed: {lock: routing, region: SLICE_XaYb:SLICE_XcYd, anchor, timing_tolerance_ps}


@dataclass
class Project:
    name: str
    top: str
    components: list[Component]
    design: Path
    unclaimed: str = "owned"
    approved_contract_changes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def component(self, name: str) -> Component | None:
        return next((c for c in self.components if c.name == name), None)

    def owned(self) -> list[Component]:
        return [c for c in self.components if c.ownership == "owned"]


def _glob_re(pat: str) -> re.Pattern[str]:
    """A manifest path pattern as a regex over design-relative posix paths: ``**`` any depth, ``*`` within a name, a bare
    directory or ``dir/`` or ``dir/**`` everything under it (and the directory itself)."""
    p = pat.rstrip("/")
    if not any(ch in p for ch in "*?["):
        return re.compile(rf"^{re.escape(p)}(/.*)?$")
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            out += ".*"
            i += 2
        elif p[i] == "*":
            out += "[^/]*"
            i += 1
        elif p[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    base = p[:-3] if p.endswith("/**") else None            # 'dir/**' also matches 'dir' itself (a directory read)
    return re.compile(rf"^{out}$" + (f"|^{re.escape(base)}$" if base else ""))


def validate(raw: Any, design: Path | None = None) -> list[str]:
    """Every problem in a parsed manifest (empty: valid). Declared trust, unknown keys, bad names, overlapping claims that
    could hide a path from its stricter owner, and (when ``design`` is given) missing files are all reported."""
    errs: list[str] = []
    if not isinstance(raw, dict):
        return ["the manifest must be a mapping"]
    if raw.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA!r}")
    for k in sorted(set(raw) - _TOP_KEYS):
        errs.append(f"unknown top-level key {k!r}")
    if not isinstance(raw.get("top"), str) or not _ID.match(str(raw.get("top", ""))):
        errs.append("top must be a plain identifier")
    if raw.get("unclaimed", "owned") not in ("owned", "frozen"):
        errs.append("unclaimed must be owned or frozen")
    if not isinstance(raw.get("approved_contract_changes", []), list):
        errs.append("approved_contract_changes must be a list of component names")
    comps = raw.get("components")
    if not isinstance(comps, list) or not comps:
        return errs + ["components must be a non-empty list"]
    seen: set[str] = set()
    for i, c in enumerate(comps):
        where = f"components[{i}]"
        if not isinstance(c, dict):
            errs.append(f"{where} must be a mapping")
            continue
        name = c.get("name")
        where = f"component {name!r}" if isinstance(name, str) else where
        if not isinstance(name, str) or not _ID.match(name):
            errs.append(f"{where}: name must be a plain identifier")
        elif name in seen:
            errs.append(f"{where}: duplicate name")
        seen.add(str(name))
        for k in sorted(set(c) - _COMP_KEYS):
            errs.append(f"{where}: unknown key {k!r}" + (" (trust is computed from evidence, never declared)" if k == "trust" else ""))
        if c.get("ownership") not in OWNERSHIP:
            errs.append(f"{where}: ownership must be one of {OWNERSHIP}")
        if c.get("level") not in LEVELS:
            errs.append(f"{where}: level must be one of {LEVELS}")
        paths = c.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
            errs.append(f"{where}: paths must be a non-empty list of design-relative patterns")
        else:
            for p in paths:
                if (p.startswith("/") or ".." in Path(p).parts or "\x00" in p or "\\" in p or "[" in p or p != p.strip()
                        or "//" in p or any(part in (".", "") for part in p.rstrip("/").split("/"))):
                    errs.append(f"{where}: path {p!r} must be a normalised design-relative pattern (no '..', '.', '//', backslash, '[' or spaces)")
        if c.get("level") == "netlist":
            nl = c.get("netlist") or {}
            if nl.get("format") not in ("edif", "checkpoint") or not nl.get("file"):
                errs.append(f"{where}: a netlist component needs netlist: {{file, format: edif|checkpoint}}")
            if nl.get("format") == "checkpoint" and not nl.get("cell"):
                errs.append(f"{where}: a checkpoint import needs netlist.cell (the black-box instance it fills)")
            if not c.get("module"):
                errs.append(f"{where}: a netlist component needs its module name")
        if c.get("level") == "placed_routed":
            nl, pl = c.get("netlist") or {}, c.get("placement") or {}
            if c.get("ownership") != "frozen":
                errs.append(f"{where}: a placed_routed component is frozen (the agent may place around a locked block, never inside it)")
            if nl.get("format") != "checkpoint" or not nl.get("file") or not nl.get("cell"):
                errs.append(f"{where}: a placed_routed component needs netlist: {{file, format: checkpoint, cell}} (the locked routed checkpoint)")
            if not c.get("module") or not c.get("instance"):
                errs.append(f"{where}: a placed_routed component needs its module and instance")
            if pl.get("lock") != "routing":
                errs.append(f"{where}: placement.lock must be 'routing' (lock_design -level routing)")
            if not isinstance(pl.get("region"), str) or not _SLICE_RANGE.match(pl.get("region", "")):
                errs.append(f"{where}: placement.region must be a slice range such as SLICE_X26Y70:SLICE_X37Y89 (the keep-out)")
            if not isinstance(pl.get("timing_tolerance_ps", 0), int) or isinstance(pl.get("timing_tolerance_ps", 0), bool) or pl.get("timing_tolerance_ps", 0) < 0:
                errs.append(f"{where}: placement.timing_tolerance_ps must be a whole number of picoseconds, 0 or more")
            for k in sorted(set(pl) - _PLACE_KEYS):
                errs.append(f"{where}: unknown placement key {k!r}")
        elif c.get("placement") is not None:
            errs.append(f"{where}: placement belongs to a placed_routed component")
        if c.get("level") == "rtl" and not (c.get("build_sources") or []):
            errs.append(f"{where}: an rtl component lists its build_sources so a build.yaml that drops it is refused")
        for k in ("interface", "netlist", "provenance", "placement"):
            if c.get(k) is not None and not isinstance(c.get(k), dict):
                errs.append(f"{where}: {k} must be a mapping")
        for k in ("aliases", "build_sources", "reference_rtl"):
            if c.get(k) is not None and not (isinstance(c.get(k), list) and all(isinstance(x, str) for x in c[k])):
                errs.append(f"{where}: {k} must be a list of strings")
        if not isinstance(c.get("interface") or {}, dict) or not isinstance(c.get("provenance") or {}, dict) or not isinstance(c.get("netlist") or {}, dict):
            continue
        prov = c.get("provenance") or {}
        for k in sorted(set(prov) - _PROV_KEYS):
            errs.append(f"{where}: unknown provenance key {k!r}")
        iface = c.get("interface") or {}
        for p in iface.get("ports") or []:
            if not isinstance(p, dict) or not _ID.match(str(p.get("name", ""))) or p.get("dir") not in _DIRS:
                errs.append(f"{where}: interface port {p!r} needs name and dir (input|output|inout)")
    return errs


def load(design: Path) -> Project | None:
    """The design's managed project, or None when it has no ``project.yaml``. Raises ValueError on an invalid manifest."""
    f = Path(design) / MANIFEST
    if not f.is_file():
        return None
    raw = yaml.safe_load(f.read_text())
    errs = validate(raw, Path(design))
    if errs:
        raise ValueError("invalid project.yaml: " + "; ".join(errs))
    comps = [Component(name=c["name"], ownership=c["ownership"], level=c["level"], paths=list(c["paths"]),
                       module=c.get("module"), instance=c.get("instance"), build_sources=list(c.get("build_sources") or []),
                       netlist=dict(c.get("netlist") or {}), aliases=[a.lower() for a in c.get("aliases") or []],
                       interface=dict(c.get("interface") or {}), provenance=dict(c.get("provenance") or {}),
                       reference_rtl=list(c.get("reference_rtl") or []), description=c.get("description", ""),
                       placement=dict(c.get("placement") or {}))
             for c in raw["components"]]
    return Project(name=raw.get("name") or Path(design).name, top=raw["top"], components=comps, design=Path(design).resolve(),
                   unclaimed=raw.get("unclaimed", "owned"), approved_contract_changes=list(raw.get("approved_contract_changes") or []),
                   raw=raw)


def from_design(design: Path, write: bool = False) -> dict[str, Any]:
    """The converter for today's design directories: one component, owned, covering the whole design, so nothing changes.
    ``build.yaml`` supplies the top and the sources. ``write=True`` writes ``project.yaml`` unless one exists."""
    design = Path(design)
    cfg = yaml.safe_load((design / "build.yaml").read_text()) or {}
    raw = {"schema": SCHEMA, "name": design.name, "top": cfg["top"],
           "components": [{"name": design.name.replace("-", "_"), "ownership": "owned", "level": "rtl", "paths": ["**"],
                           "build_sources": [s for s in cfg.get("sources", []) if str(s).startswith(f"designs/{design.name}/")]
                           or list(cfg.get("sources", [])), "module": cfg["top"],
                           "description": "the whole design (converted from a design directory)"}]}
    if write and not (design / MANIFEST).exists():
        (design / MANIFEST).write_text(yaml.safe_dump(raw, sort_keys=False))
    return raw


# --- hashing and trust --------------------------------------------------------------------------------------------

def component_files(project: Project, comp: Component) -> list[Path]:
    """The files matching the component's paths, and the netlist, simulation netlist and reference RTL it names (the evidence covers them)."""
    pats = [_glob_re(p) for p in comp.paths]
    extra = {x for x in [comp.netlist.get("file"), comp.netlist.get("sim_file"), *comp.reference_rtl] if x}
    out = []
    for p in sorted(project.design.rglob("*")):
        if p.is_file() and "build" not in p.relative_to(project.design).parts[:1]:
            rel = p.relative_to(project.design).as_posix()
            if (any(r.match(rel) for r in pats) or rel in extra) and rel != MANIFEST:
                out.append(p)
    return out


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def component_hash(project: Project, comp: Component) -> str:
    """One SHA-256 over the component's files (relative name and content hash, sorted)."""
    h = hashlib.sha256()
    raw = next((c for c in project.raw.get("components", []) if c.get("name") == comp.name), {})
    h.update(b"manifest\0" + json.dumps(raw, sort_keys=True, default=str).encode() + b"\n")      # a changed contract, region or tolerance is new content
    for p in component_files(project, comp):
        h.update(f"{p.relative_to(project.design).as_posix()}\0{sha256_file(p)}\n".encode())
    return h.hexdigest()


def evidence_path(project: Project, comp: Component) -> Path:
    return project.design / MANAGED_DIR / "evidence" / f"{comp.name}.json"


def write_evidence(project: Project, comp: Component, kind: str, data: dict[str, Any]) -> Path:
    """The flow records evidence here (``kind`` is ``verified`` or ``built``); the record names the content it covers."""
    assert kind in ("verified", "built", "placement")
    f = evidence_path(project, comp)
    cur = json.loads(f.read_text()) if f.is_file() else {}
    cur[kind] = {**data, "component_sha256": component_hash(project, comp), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cur, indent=1) + "\n")
    return f


def provenance_gaps(project: Project, comp: Component) -> list[str]:
    """What is missing for ``documented``: origin, version, licence and a source hash that matches the files now."""
    prov, gaps = comp.provenance, []
    for k in ("origin", "version", "licence"):
        if not prov.get(k):
            gaps.append(f"provenance.{k} is missing")
    if comp.level in ("netlist", "placed_routed"):
        f = project.design / (comp.netlist.get("file") or "")
        if not f.is_file():
            gaps.append(f"netlist file {comp.netlist.get('file')!r} is missing")
        elif prov.get("sha256") != sha256_file(f):
            gaps.append("provenance.sha256 does not match the netlist file")
    if not comp.interface.get("ports"):
        gaps.append("no interface contract (interface.ports)")
    return gaps


def trust(project: Project, comp: Component) -> tuple[str, list[str]]:
    """(label, why not higher). Computed from the manifest and the evidence files, never declared."""
    gaps = provenance_gaps(project, comp)
    if gaps:
        return "none", gaps
    f = evidence_path(project, comp)
    ev = json.loads(f.read_text()) if f.is_file() else {}
    h = component_hash(project, comp)
    v = ev.get("verified") or {}
    if not (v.get("passed") is True and v.get("component_sha256") == h):
        return "documented", ["no passing own-tests evidence for the current content" if not v else "verified evidence is stale or failed"]
    if comp.level == "placed_routed":
        pe = ev.get("placement") or {}
        if not (pe.get("passed") is True and pe.get("component_sha256") == h and pe.get("placements_tried") in range(2, 10_000)):
            return "verified", ["no passing placement evidence (the block's internal timing across every placement tried) for the current content"
                                if not pe else "placement evidence is stale, failed, or covers fewer than two placements"]
    b = ev.get("built") or {}
    if not (b.get("gates_clean") is True and b.get("component_sha256") == h):
        return "verified", ["no build in this project with every gate clean on the current content"]
    return "built", []


# --- scope --------------------------------------------------------------------------------------------------------

@dataclass
class Scope:
    components: tuple[str, ...]
    source: str = "default"                 # default | explicit | resolved
    request: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"components": list(self.components), "source": self.source, "request": self.request, "note": self.note}


@dataclass
class Resolution:
    scope: Scope | None
    question: str | None = None
    notes: list[str] = field(default_factory=list)


def default_scope(project: Project) -> Scope:
    return Scope(tuple(c.name for c in project.owned()), "default", "", "default scope: every owned component")


def _by_path(project: Project, hier: str) -> Component | None:
    """The component whose ``instance`` is the longest prefix of a hierarchy path (``u_core/u_mac`` -> the u_core/u_mac component)."""
    h = hier.strip("/.")
    best = None
    for c in project.components:
        i = (c.instance or "").strip("/")
        if i and (h == i or h.startswith(i + "/")) and (best is None or len(i) > len(best.instance.strip("/"))):
            best = c
    return best


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def resolve_request(project: Project, text: str = "", scope_arg: list[str] | None = None) -> Resolution:
    """The scope of one request. ``scope_arg`` (``--scope crc,pcs_rx``: component names or hierarchy paths) wins; else the
    free text is matched to visible components; else the default (every owned component). A match that is ambiguous, or a
    request naming only frozen parts, returns a **question** and no scope: the agent edits nothing until it is answered.
    Excluded components never match (the agent does not know them)."""
    visible = [c for c in project.components if c.ownership != "excluded"]
    if scope_arg:
        picked: list[str] = []
        for a in scope_arg:
            a = a.strip()
            c = project.component(a) or _by_path(project, a)
            if c is None or c.ownership == "excluded":
                return Resolution(None, f"scope entry {a!r} is not a component or hierarchy path of this project; "
                                        f"components: {', '.join(x.name for x in visible)}")
            if c.ownership != "owned":
                return Resolution(None, f"{c.name} is {c.ownership}: it cannot be edited and so cannot be in a scope; "
                                        f"owned components: {', '.join(x.name for x in project.owned())}")
            if c.name not in picked:
                picked.append(c.name)
        return Resolution(Scope(tuple(picked), "explicit", text, "explicit --scope"))
    if not text.strip():
        return Resolution(default_scope(project))
    words, low = _words(text), text.lower()
    direct, via_alias = [], []
    for c in visible:
        names = {c.name.lower(), (c.module or "").lower(), ((c.instance or "").strip("/").split("/")[-1]).lower()} - {""}
        if any(re.search(rf"(?<![a-z0-9_]){re.escape(n)}(?![a-z0-9_])", low) for n in names):
            direct.append(c)
        elif words & set(c.aliases):
            via_alias.append(c)
    hit = direct or via_alias
    frozen = [c for c in hit if c.ownership == "frozen"]
    own_hit = [c for c in hit if c.ownership == "owned"]
    owned_names = ", ".join(c.name for c in project.owned())
    if frozen and not own_hit:
        return Resolution(None, f"the request matches {', '.join(c.name for c in frozen)}, which is frozen and cannot be edited. "
                                f"Which owned component should change? Owned: {owned_names}")
    if own_hit and (direct or len(own_hit) == 1):
        notes = [f"{c.name} is frozen: read only, not touched" for c in frozen]
        return Resolution(Scope(tuple(c.name for c in own_hit), "resolved", text, "resolved from the request text"), None, notes)
    if len(own_hit) > 1:
        return Resolution(None, f"the request could mean {' or '.join(c.name for c in own_hit)}; which one (or both)? "
                                f"Say it with --scope or name the component")
    owned = project.owned()
    if len(owned) == 1:
        return Resolution(Scope((owned[0].name,), "default", text, "the only owned component"))
    return Resolution(None, f"the request does not say which component to change. Owned components: {owned_names}")


def build_coverage_problems(project: Project, cfg: dict[str, Any]) -> list[str]:
    """What a build.yaml fails to build: each component's ``build_sources`` exactly as listed, and each netlist component's file as the
    exact repo-relative path ``designs/<design>/<file>`` (no suffix match, no ``..``). Used by the agent's tools and by flow/prepare.py."""
    srcs = set(map(str, cfg.get("sources") or []))
    nets = {str(n.get("file") if isinstance(n, dict) else n) for n in cfg.get("netlists") or []}
    rel = f"{project.design.parent.name}/{project.design.name}"
    miss = []
    for c in project.components:
        who = "*" if c.ownership == "excluded" else c.name
        miss += [f"{s} (component {who})" for s in c.build_sources if s not in srcs]
        if c.level in ("netlist", "placed_routed") and f"{rel}/{c.netlist.get('file') or ''}" not in nets:
            miss.append(f"netlist {rel}/{c.netlist.get('file')} (component {who})")
    allowed = {f"{rel}/{c.netlist.get('file')}" for c in project.components if c.level in ("netlist", "placed_routed")}
    miss += [f"netlist {n} is not a netlist component of project.yaml" for n in sorted(nets - allowed)]
    return miss


# --- the policy the path jail calls -------------------------------------------------------------------------------

_RANK = {"excluded": 0, "frozen": 1, "owned": 2}


class ManagedPolicy:
    """Ownership and scope for one session. ``classify`` maps a design-relative path to its component (the strictest claim
    wins when patterns overlap, so a broad owned pattern can never unlock a frozen or excluded file)."""

    def __init__(self, project: Project, scope: Scope | None = None):
        self.project = project
        self.scope = scope or default_scope(project)
        self._pats = [(c, [_glob_re(p) for p in c.paths]) for c in project.components]
        self._baseline: dict[str, str] | None = None

    # -- classification
    def classify(self, rel: str) -> Component | None:
        rel = rel.strip("/")
        hits = [c for c, pats in self._pats if any(r.match(rel) for r in pats)]
        return min(hits, key=lambda c: _RANK[c.ownership]) if hits else None

    def _refuse(self, msg: str, rule: str = "managed") -> None:
        from agent.core.security import SecurityError      # lazy: flow/prepare.py imports this module with only PyYAML installed
        raise SecurityError(rule, msg)

    def check(self, rel: str, write: bool) -> None:
        """Called by PathJail.resolve with the resolved design-relative path. Raises SecurityError."""
        rel = "" if rel in (".", "") else rel
        if rel == MANIFEST:
            if write:
                self._refuse("project.yaml is the owner's manifest: ownership, scope and contracts are not the agent's to change")
            return                                                  # reading it is served as the filtered agent view
        if write and (rel == MANAGED_DIR.as_posix() or rel.startswith(MANAGED_DIR.as_posix() + "/")):
            self._refuse("build/managed/ (evidence, scope, flags, provenance) is written by the flow")
        c = self.classify(rel)
        if c is None:
            if write and self.project.unclaimed == "frozen" and not rel.startswith("build/") and rel != "":
                self._refuse(f"{rel} is not part of any component and the project keeps unclaimed files frozen")
            return
        if c.ownership == "excluded":
            self._refuse(f"{rel!r} is not available: it is outside this project's managed view")
        if write:
            if c.ownership == "frozen":
                self._refuse(f"{rel} belongs to the frozen component {c.name!r}: it is read-only. To change it, ask the owner to "
                             f"re-import or unfreeze it")
            if c.name not in self.scope.components:
                self._refuse(f"{rel} belongs to {c.name!r}, which is outside this request's scope ({', '.join(self.scope.components) or 'empty'}). "
                             f"Widening the scope needs a new explicit request", "managed-scope")

    def check_real(self, real: Path, write: bool) -> None:
        """Extra checks on the file itself: a second hard link would let a write through an owned name change a frozen file."""
        if write and real.exists() and real.is_file():
            if os.stat(real).st_nlink > 1:
                self._refuse(f"{real.name} has more than one hard link: a write could change another file")

    # -- content checks at write time
    def check_content(self, rel: str, content: str) -> None:
        if rel == "build.yaml":
            try:
                cfg = yaml.safe_load(content) or {}
            except yaml.YAMLError:
                return                                              # write_file's own artefact check reports a malformed one
            self.check_build(cfg)
            return
        if rel.lower().endswith((".xdc", ".tcl")) or self._is_listed_constraint(rel):
            self.check_xdc(rel, content)
            return
        c = self.classify(rel)
        if c is None or c.ownership != "owned" or not c.module or not c.interface.get("ports"):
            return
        if c.name in self.project.approved_contract_changes:
            return
        if not re.search(rf"\bmodule\s+{re.escape(c.module)}\b", re.sub(r"//[^\n]*|/\*.*?\*/", "", content, flags=re.S)):
            return                                                  # the file does not declare the contract's module
        got = parse_module_ports(content, c.module)
        diff = interface_diff(c.interface["ports"], got)
        if diff:
            self._flag(c, rel, diff)
            self._refuse(f"{rel} would change the interface contract of {c.name!r} ({'; '.join(diff[:4])}). That affects the "
                         f"components around it: the change is refused and flagged for the owner, who approves it by "
                         f"listing {c.name!r} under approved_contract_changes in project.yaml", "managed-contract")

    def _flag(self, c: Component, rel: str, diff: list[str]) -> None:
        f = self.project.design / MANAGED_DIR / "contract_flags.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a") as fh:
            fh.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "component": c.name, "file": rel, "diff": diff,
                                 "scope": list(self.scope.components), "status": "refused, awaiting owner approval"}) + "\n")

    def check_build(self, cfg: dict[str, Any]) -> None:
        """The whole design is always built: every component's sources (or netlist) must be in build.yaml, excluded or not."""
        miss = build_coverage_problems(self.project, cfg)
        if cfg.get("top") != self.project.top:
            miss.append(f"top {self.project.top!r} (build.yaml names {cfg.get('top')!r})")
        rel = f"{self.project.design.parent.name}/{self.project.design.name}"
        have = {str(n.get("file")): n for n in cfg.get("netlists") or [] if isinstance(n, dict)}
        for c in self.project.components:
            if c.level in ("netlist", "placed_routed"):
                n = have.get(f"{rel}/{c.netlist.get('file')}")
                if n is not None and (n.get("format") != c.netlist.get("format") or n.get("cell") != c.netlist.get("cell")):
                    miss.append(f"netlist {c.netlist.get('file')} with format {c.netlist.get('format')!r} and cell {c.netlist.get('cell')!r} (component {c.name})")
        for f in cfg.get("constraints") or []:                 # a constraints file under any name is checked against the keep-outs
            p = self.project.design.parent.parent / str(f)
            if p.is_file() and p.resolve().is_relative_to(self.project.design):
                self.check_xdc(p.relative_to(self.project.design).as_posix(), p.read_text(errors="replace"), force=True)
        if miss:
            self._refuse("build.yaml must still build every component: missing " + ", ".join(miss) +
                         " (excluded or frozen parts are part of the build and the sign-off)", "managed-build")

    # -- placed-and-routed components (stage 2): the keep-out region and the placement tools
    def keepouts(self) -> list[tuple[Component, tuple[int, int, int, int]]]:
        """Each placed_routed component with its keep-out rectangle (slice columns and rows, inclusive)."""
        return [(c, slice_rect(c.placement["region"])) for c in self.project.components if c.level == "placed_routed" and c.placement.get("region")]

    def check_xdc(self, rel: str, content: str, force: bool = False) -> None:
        """A constraints file (``.xdc``) the agent writes may not place anything inside a placed-and-routed component's keep-out region or
        constrain its cells: a pblock slice range overlapping the region, a ``LOC`` on a slice inside it, or a placement property
        (``LOC``, ``BEL``, ``PBLOCK``, ``IS_*_FIXED``, ``FIXED_ROUTE``, ``DONT_TOUCH``) or ``add_cells_to_pblock`` on a cell of its instance. Timing
        exceptions are not placement and are not checked here. Clock-region pblocks are not evaluated (a documented gap): Vivado
        itself cannot move a locked cell."""
        ko = self.keepouts()
        if not ko or not (force or rel.lower().endswith((".xdc", ".tcl")) or self._is_listed_constraint(rel)):
            return
        text = re.sub(r"\\\n", " ", content)
        for raw in re.split(r"[\n;]", text):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            for c, rect in ko:
                inst = c.instance or ""
                low = line.lower()
                names_inst = bool(re.search(rf"(?<![a-z0-9_$]){re.escape(inst.lower())}(?![a-z0-9_$])", low))
                for tok in re.findall(r"[^\s\[\]{}]+", low):        # a wildcard pattern that could select the instance's cells or nets
                    if any(ch in tok for ch in "*?") and any(fnmatch.fnmatchcase(pr, tok) for pr in (inst.lower(), inst.lower() + "/x", inst.lower() + "/a/b")):
                        names_inst = True
                places = bool(re.search(r"\b(loc|bel|pblock|is_loc_fixed|is_bel_fixed|is_route_fixed|fixed_route|route|dont_touch|lock_pins)\b|add_cells_to_pblock|"
                                        r"resize_pblock|unplace_cell|place_cell|reset_property", low))
                captured = names_inst and bool(re.match(r"set\s+\w+\s+\[?\s*get_(cells|nets)", low))      # a variable holding the block's objects
                if names_inst and (places or captured):
                    self._refuse(f"{rel}: {line[:100]!r} constrains the placement of {c.name!r}, a placed-and-routed block that is locked: "
                                 f"place around it, never inside it", "managed-keepout")
                if re.search(r"\bresize_pblock\b|\bLOC\b", line, re.I):
                    for m in re.finditer(r"SLICE_X(\d+)Y(\d+)(?::SLICE_X(\d+)Y(\d+))?", line, re.I):
                        x0, y0 = int(m.group(1)), int(m.group(2))
                        x1, y1 = int(m.group(3) or x0), int(m.group(4) or y0)
                        if rects_overlap((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), rect):
                            self._refuse(f"{rel}: {m.group(0)} overlaps the keep-out region {c.placement['region']} of {c.name!r} (a locked "
                                         f"placed-and-routed block): place around it, never inside it", "managed-keepout")

    def _is_listed_constraint(self, rel: str) -> bool:
        f = self.project.design / "build.yaml"
        try:
            cfg = yaml.safe_load(f.read_text()) or {}
        except (OSError, yaml.YAMLError):
            return False
        base = f"{self.project.design.parent.name}/{self.project.design.name}/"
        return any(str(x) in (rel, base + rel) for x in cfg.get("constraints") or [])

    def check_rw(self, tool: str, args: dict[str, Any]) -> None:
        """The RapidWright tools' arguments against the placed-and-routed components: no cell pattern or net name that selects a cell or net
        inside one, no whole-design RWRoute (it may re-route locked nets). ``rw_relocate_block`` is checked in the tool (it moves a block as a whole)."""
        for c, _ in self.keepouts():
            inst = c.instance or ""
            if tool == "rw_place_chain":
                for pat in args.get("cells") or []:
                    if any(fnmatch.fnmatchcase(probe, pat) for probe in (inst, f"{inst}/x", f"{inst}/a/b", f"{inst}/x_reg[0]")) or pat.startswith(inst + "/"):
                        self._refuse(f"cell pattern {pat!r} could select cells inside {c.name!r} ({inst}), a locked placed-and-routed block: "
                                     f"name the owned cells explicitly", "managed-keepout")
            elif tool == "rw_route":
                if args.get("mode") == "full":
                    self._refuse(f"rw_route mode full may re-route the locked nets of {c.name!r}: use mode nets on owned nets, or Vivado's router "
                                 f"(rw_referee route=true), which keeps locked routing", "managed-keepout")
                owned = [(o.instance or "") + "/" for o in self.project.owned() if o.instance]
                for n in args.get("nets") or []:
                    if n == inst or n.startswith(inst + "/"):
                        self._refuse(f"net {n!r} is inside {c.name!r} ({inst}), a locked placed-and-routed block", "managed-keepout")
                    if not any(n.startswith(o) for o in owned):       # a boundary net (clk, a port net) has pins inside the block: unrouting it could free its nodes
                        self._refuse(f"net {n!r} is not under an owned component's instance: it may have pins inside {c.name!r} (a locked block), "
                                     f"so it is not re-routed here", "managed-keepout")

    def placed_by_file(self, rel: str) -> Component | None:
        return next((c for c in self.project.components if c.level == "placed_routed" and c.netlist.get("file") == rel), None)

    # -- the filtered view the agent reads as project.yaml
    def agent_view(self) -> str:
        """project.yaml as the agent sees it: excluded components are absent, frozen ones show contract and provenance
        (no paths of excluded parts), owned ones show their scope state."""
        comps = []
        for c in self.project.components:
            if c.ownership == "excluded":
                continue
            comps.append({"name": c.name, "ownership": c.ownership, "level": c.level, "paths": c.paths, "module": c.module,
                          "instance": c.instance, "in_scope": c.name in self.scope.components, "interface": c.interface or None,
                          "provenance": {k: v for k, v in c.provenance.items() if k != "tests"} or None,
                          "trust": trust(self.project, c)[0]})
        return yaml.safe_dump({"schema": SCHEMA, "name": self.project.name, "top": self.project.top,
                               "scope": self.scope.as_dict(), "components": comps,
                               "note": "components not listed are outside your view; they are built and signed off with the design"},
                              sort_keys=False)

    # -- tool output
    def scrub(self, text: str) -> str:
        """Tool output (lint, simulation and build logs) with the lines about an excluded component's files removed: a tool that prints
        a warning prints the source line under it. Best effort on text the agent's tools return; the reports of the whole-design build
        (``build/``) still name excluded cells, which is the sign-off's truth and not hidden (a documented gap)."""
        names = sorted({p.relative_to(self.project.design).as_posix() for c in self.project.components if c.ownership == "excluded"
                        for p in component_files(self.project, c)} | {Path(p).name for c in self.project.components
                                                                       if c.ownership == "excluded" for p in map(str, component_files(self.project, c))},
                       key=len, reverse=True)
        if not names:
            return text
        pat = re.compile("|".join(re.escape(n) for n in names))
        out, skip = [], False
        for line in text.splitlines():
            if pat.search(line):
                if not skip:
                    out.append("[lines about an excluded component removed]")
                skip = True
                continue
            if skip and re.match(r"^\s*(\d+\s*\||\|)|^\s*\^|^\s+:|^\s+\.\.\.", line):
                continue
            skip = False
            out.append(line)
        return "\n".join(out) + ("\n" if text.endswith("\n") else "")

    # -- tools that run design code: nothing frozen or excluded may change underneath
    def snapshot(self) -> None:
        self._baseline = self._hashes()

    def _hashes(self) -> dict[str, str]:
        out = {p: sha256_file(self.project.design / p) for p in (MANIFEST, (MANAGED_DIR / "scope.json").as_posix())
               if (self.project.design / p).is_file()}
        for c in self.project.components:
            if c.ownership in ("frozen", "excluded"):
                for p in component_files(self.project, c):
                    out[p.relative_to(self.project.design).as_posix()] = sha256_file(p)
        return out

    def integrity_violations(self) -> list[str]:
        if self._baseline is None:
            self.snapshot()
            return []
        now = self._hashes()
        return sorted(p for p in set(now) | set(self._baseline) if now.get(p) != self._baseline.get(p))


# --- interface contracts ------------------------------------------------------------------------------------------

def slice_rect(text: str) -> tuple[int, int, int, int]:
    """``SLICE_X26Y70:SLICE_X37Y89`` as (x0, y0, x1, y1)."""
    m = _SLICE_RANGE.match(text)
    if not m:
        raise ValueError(f"not a slice range: {text!r}")
    x0, y0, x1, y1 = (int(v) for v in m.groups())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _eval_width(expr: str, params: dict[str, int]) -> int | None:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        def ev(n):
            if isinstance(n, ast.Expression):
                return ev(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, int):
                return n.value
            if isinstance(n, ast.Name):
                return params[n.id]
            if isinstance(n, ast.BinOp):
                a, b = ev(n.left), ev(n.right)
                return {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b}[type(n.op)] if type(n.op) in (ast.Add, ast.Sub, ast.Mult) else None
            raise KeyError
        return ev(tree)
    except (SyntaxError, KeyError, TypeError):
        return None


def _paren(text: str, start: int) -> str:
    depth = 0
    for i in range(start, len(text)):
        depth += (text[i] == "(") - (text[i] == ")")
        if depth == 0:
            return text[start:i + 1]
    return text[start:]


def parse_module_ports(text: str, module: str) -> list[dict[str, Any]]:
    """The ANSI port list of ``module`` in SystemVerilog source: name, dir, width (None when an expression is not a plain
    integer expression of the module's parameter defaults). Comments are removed first. Non-ANSI headers are not read."""
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
    m = re.search(rf"\bmodule\s+{re.escape(module)}\b\s*", text)
    if not m:
        return []
    i, ptxt = m.end(), ""
    if text[i:i + 1] == "#":
        j = text.index("(", i)
        ptxt = _paren(text, j)
        i = j + len(ptxt)
        while text[i:i + 1].isspace():
            i += 1
    if text[i:i + 1] != "(":
        return []
    body = _paren(text, i)
    m = type("M", (), {"group": lambda self, k: {"params": ptxt[1:-1], "ports": body[1:-1]}[k]})()
    params = {k: int(v) for k, v in re.findall(r"\b(\w+)\s*=\s*(\d+)\b", m.group("params") or "")}
    ports, cur_dir, cur_w = [], None, 1
    for item in (x.strip() for x in m.group("ports").split(",")):
        if not item:
            continue
        d = re.match(r"(input|output|inout)\b", item)
        if d:
            cur_dir, cur_w = d.group(1), 1
            rng = re.search(r"\[([^\]:]+):([^\]]+)\]", item)
            if rng:
                hi, lo = _eval_width(rng.group(1), params), _eval_width(rng.group(2), params)
                cur_w = hi - lo + 1 if hi is not None and lo is not None else None
        name = re.search(r"([A-Za-z_]\w*)\s*(?:=.*)?$", item)
        if cur_dir and name:
            ports.append({"name": name.group(1), "dir": cur_dir, "width": cur_w})
    return ports


def interface_diff(contract: list[dict[str, Any]], got: list[dict[str, Any]]) -> list[str]:
    """Differences between a contract's ports and a module's ports (names, directions, and widths where both are known)."""
    want = {p["name"]: p for p in contract}
    have = {p["name"]: p for p in got}
    out = [f"missing port {n}" for n in want if n not in have] + [f"extra port {n}" for n in have if n not in want]
    for n in want.keys() & have.keys():
        a, b = want[n], have[n]
        if a["dir"] != b["dir"]:
            out.append(f"{n}: direction {b['dir']} != contract {a['dir']}")
        elif a.get("width") is not None and b.get("width") is not None and int(a["width"]) != int(b["width"]):
            out.append(f"{n}: width {b['width']} != contract {a['width']}")
    return sorted(out)


def ipxact_ports(xml_text: str) -> list[dict[str, Any]]:
    """Ports from an IP-XACT (IEEE 1685-2014) component: ``ipxact:ports/ipxact:port`` with a wire direction and vector. The
    converter behind ``interface.ports`` where a vendor or a producer ships IP-XACT."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    ns = {"i": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda t: f"i:{t}") if ns else (lambda t: t)
    out = []
    for p in root.iter(("{%s}port" % ns["i"]) if ns else "port"):
        name = p.findtext(q("name"), namespaces=ns)
        wire = p.find(q("wire"), ns)
        if name is None or wire is None:
            continue
        d = {"in": "input", "out": "output", "inout": "inout"}.get((wire.findtext(q("direction"), namespaces=ns) or "").strip())
        width = 1
        v = wire.find(f"{q('vectors')}/{q('vector')}", ns)
        if v is not None:
            try:
                width = abs(int(v.findtext(q("left"), namespaces=ns)) - int(v.findtext(q("right"), namespaces=ns))) + 1
            except (TypeError, ValueError):
                width = None
        if d:
            out.append({"name": name.strip(), "dir": d, "width": width})
    return out


# --- run record and provenance ------------------------------------------------------------------------------------

def start_run(project: Project, resolution_scope: Scope) -> dict[str, Any]:
    """Write the scope and the plan (the components the request will touch) before the agent runs. The scope record is the
    run record's ``scope`` field; a later run with a new request writes its own and keeps the old ones in ``history``."""
    d = project.design / MANAGED_DIR
    d.mkdir(parents=True, exist_ok=True)
    f = d / "scope.json"
    hist = json.loads(f.read_text()).get("history", []) if f.is_file() else []
    if f.is_file():
        hist.append({k: v for k, v in json.loads(f.read_text()).items() if k != "history"})
    rec = {**resolution_scope.as_dict(), "time": time.strftime("%Y-%m-%d %H:%M:%S"),
           "plan": {"will_touch": list(resolution_scope.components),
                    "read_only": [c.name for c in project.components if c.ownership == "frozen"],
                    "not_in_scope_owned": [c.name for c in project.owned() if c.name not in resolution_scope.components]},
           "history": hist}
    f.write_text(json.dumps(rec, indent=1) + "\n")
    return rec


def load_scope(project: Project) -> Scope | None:
    f = project.design / MANAGED_DIR / "scope.json"
    if not f.is_file():
        return None
    r = json.loads(f.read_text())
    return Scope(tuple(r["components"]), r.get("source", "explicit"), r.get("request", ""), r.get("note", ""))


def provenance_report(project: Project, before: dict[str, str] | None = None) -> dict[str, Any]:
    """What was theirs and what was ours: per component its ownership, level, origin, licence, hash, trust and files; the scope
    and the plan; the files changed since ``before`` (a {path: sha256} map taken at the start of the run); and the refusals."""
    scope = load_scope(project) or default_scope(project)
    comps = []
    for c in project.components:
        t, why = trust(project, c)
        comps.append({"name": c.name, "ownership": c.ownership, "level": c.level,
                      "origin": c.provenance.get("origin") or ("this project" if c.ownership == "owned" else None),
                      "version": c.provenance.get("version"), "licence": c.provenance.get("licence"),
                      "sha256": component_hash(project, c), "trust": t, "trust_gaps": why,
                      "files": [p.relative_to(project.design).as_posix() for p in component_files(project, c)],
                      "theirs": c.ownership != "owned", "in_scope": c.name in scope.components})
    now = {p.relative_to(project.design).as_posix(): sha256_file(p) for c in project.components for p in component_files(project, c)}
    changed = sorted(p for p in set(now) | set(before or {}) if before is not None and now.get(p) != before.get(p))
    audit = project.design / "build" / "audit.jsonl"
    refusals = []
    if audit.is_file():
        for line in audit.read_text().splitlines():
            r = json.loads(line)
            if r.get("refused") and str(r.get("rule", "")).startswith("managed"):
                refusals.append({"tool": r.get("tool"), "rule": r.get("rule"), "summary": str(r.get("result_summary", ""))[:160]})
    return {"project": project.name, "scope": scope.as_dict(), "components": comps, "changed_files": changed,
            "managed_refusals": refusals}


def provenance_markdown(rep: dict[str, Any]) -> str:
    lines = [f"# Provenance report: {rep['project']}", "", f"Request scope ({rep['scope']['source']}): "
             f"{', '.join(rep['scope']['components']) or 'none'}" + (f" - request: {rep['scope']['request']!r}" if rep["scope"]["request"] else ""),
             "", "| component | ownership | level | theirs/ours | origin | version | licence | trust | in scope |", "|---|---|---|---|---|---|---|---|---|"]
    for c in rep["components"]:
        lines.append(f"| {c['name']} | {c['ownership']} | {c['level']} | {'theirs' if c['theirs'] else 'ours'} | {c['origin'] or ''} | "
                     f"{c['version'] or ''} | {c['licence'] or ''} | {c['trust']} | {'yes' if c['in_scope'] else 'no'} |")
    lines += ["", "## Files by origin", ""]
    for c in rep["components"]:
        lines.append(f"- {c['name']} ({'theirs' if c['theirs'] else 'ours'}, sha256 {c['sha256'][:12]}): " + ", ".join(c["files"][:12]) +
                     (" ..." if len(c["files"]) > 12 else ""))
    lines += ["", "## Changed in this run", "", ", ".join(rep["changed_files"]) or "nothing", "",
              f"## Refusals by the managed policy ({len(rep['managed_refusals'])})", ""]
    lines += [f"- {r['tool']}: {r['rule']}: {r['summary']}" for r in rep["managed_refusals"]] or ["none"]
    return "\n".join(lines) + "\n"


def write_provenance(project: Project, before: dict[str, str] | None = None) -> Path:
    rep = provenance_report(project, before)
    d = project.design / MANAGED_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / "provenance.json").write_text(json.dumps(rep, indent=1) + "\n")
    (d / "provenance.md").write_text(provenance_markdown(rep))
    return d / "provenance.md"


def policy_for(design: Path) -> ManagedPolicy | None:
    """The policy a Session installs on its jail: the manifest plus the scope the CLI wrote (default: every owned component)."""
    proj = load(design)
    if proj is None:
        return None
    pol = ManagedPolicy(proj, load_scope(proj))
    pol.snapshot()
    return pol

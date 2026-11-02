"""Validate the agent's known artefacts when they are written (brief 05c2, fix 4).

Principle: a malformed file is cheapest to fix at the moment it is written, with one clear message that names the
file, the line and column, and the rule broken. The writer refuses the write (the previous good file stays), so a
broken artefact never reaches a gate, and a gate never shows the model a parser traceback.

Known artefacts: ``spec.yaml``, ``verif/testplan.yaml``, ``build.yaml``, ``probes.yaml``, ``ARCHITECTURE.md``; any other ``*.yaml``
is checked for YAML syntax only. Everything else is not checked here.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

PLAN_KEYS = ("schema", "design", "spec", "model", "bench", "checkers", "formal_dir", "thresholds", "requirements")
THRESHOLD_KEYS = ("seeds_min", "functional_bins_pct", "cover_properties_pct", "line_pct", "toggle_pct",
                  "mutation_score_pct")
BUILD_KEYS = ("top", "part", "sources", "constraints")


def yaml_error(rel: str, text: str) -> str | None:
    """``None`` if ``text`` parses as YAML; else one line: file, line, column, the parser's problem."""
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as e:
        mk = getattr(e, "problem_mark", None)
        where = f"line {mk.line + 1}, column {mk.column + 1}" if mk else "unknown position"
        prob = " ".join(str(getattr(e, "problem", None) or e).split())
        ctx = getattr(e, "context", None)
        return f"{rel}: not valid YAML at {where}: {prob}" + (f" ({' '.join(str(ctx).split())})" if ctx else "")
    return None


def _mapping(rel: str, text: str) -> tuple[dict[str, Any] | None, str | None]:
    err = yaml_error(rel, text)
    if err:
        return None, err
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return None, f"{rel}: must be a YAML mapping at the top level, not {type(data).__name__}"
    return data, None


def check_testplan(data: dict[str, Any]) -> list[str]:
    """What flow/verif_gates.py reads from a testplan, as problems (empty list: it can read it)."""
    errs = [f"missing key {k!r}" for k in PLAN_KEYS if k not in data]
    b = data.get("bench")
    if "bench" in data and not (isinstance(b, dict) and isinstance(b.get("modules"), list) and b.get("dir")):
        errs.append("'bench' must be a mapping with 'modules' (a list) and 'dir'")
    th = data.get("thresholds")
    if "thresholds" in data:
        if not isinstance(th, dict):
            errs.append("'thresholds' must be a mapping")
        else:
            errs += [f"thresholds has no {k!r}" for k in THRESHOLD_KEYS if k not in th]
    reqs = data.get("requirements")
    if "requirements" in data:
        if not isinstance(reqs, list) or not reqs:
            errs.append("'requirements' must be a non-empty list")
        else:
            for i, r in enumerate(reqs):
                if not isinstance(r, dict) or not r.get("id") or not isinstance(r.get("spec"), list):
                    errs.append(f"requirements[{i}] must be a mapping with an 'id' and a 'spec' list of spec item ids")
                    break
                for k in ("tests", "assertions", "cover_props", "bins", "formal"):
                    if k in r and not isinstance(r[k], list):
                        errs.append(f"requirements[{i}].{k} must be a list")
    return errs


def check_probes(data: dict[str, Any]) -> list[str]:
    from flow.prepare import check_probes as cp          # one definition, beside the code that reads the file
    return cp(data)


def check_artefact(rel: str, content: str) -> str | None:
    """One clear error for a malformed known artefact, or ``None``. ``rel`` is design-relative."""
    rel = rel.lstrip("/")
    low = rel.lower()
    if low == "spec.yaml":
        data, err = _mapping(rel, content)
        if err:
            return err
        from agent.graph.spec_schema import shape_errors
        errs = shape_errors(data)
        return f"{rel}: {'; '.join(errs)}" if errs else None
    if low == "verif/testplan.yaml":
        data, err = _mapping(rel, content)
        if err:
            return err
        errs = check_testplan(data)
        return f"{rel}: {'; '.join(errs)}" if errs else None
    if low == "build.yaml":
        data, err = _mapping(rel, content)
        if err:
            return err
        errs = [f"missing key {k!r}" for k in BUILD_KEYS if k not in data]
        errs += [f"{k!r} must be a non-empty list" for k in ("sources", "constraints")
                 if k in data and not (isinstance(data[k], list) and data[k])]
        return f"{rel}: {'; '.join(errs)}" if errs else None
    if low == "probes.yaml":
        data, err = _mapping(rel, content)
        if err:
            return err
        errs = check_probes(data)
        return f"{rel}: {'; '.join(errs)}" if errs else None
    if low.endswith((".yaml", ".yml")):
        return yaml_error(rel, content)
    if low == "architecture.md":
        m = re.search(r"^##\s+Block diagram\s*$", content, re.M | re.I)
        if not m:
            return f"{rel}: needs a '## Block diagram' section (with a fenced text diagram), the clock plan and the pin list"
        if "```" not in content[m.end():]:
            return f"{rel}: the '## Block diagram' section needs a fenced (```) text diagram"
    return None

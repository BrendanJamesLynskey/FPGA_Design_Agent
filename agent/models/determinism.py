"""``--deterministic`` (brief 107): which level a run gets, what it pins, and when it refuses.

* **Level 2, replay**: every model call is served from a recorded tape (:mod:`agent.models.tape`). Exact whatever the provider does,
  for the model calls. Chosen when a tape exists for the run.
* **Level 1, temperature 0**: no tape yet, so the calls are live, with ``temperature: 0`` (and a fixed ``seed`` where the endpoint takes
  one) on every purpose, and every call is recorded to a new tape, so the run can be replayed exactly afterwards. Level 1 alone is
  *not* bit-exact: batching and kernel order on the provider's side can still change a reply (``results/107_deterministic`` measures how
  often). It is available only on endpoint kinds that take a temperature: ``openrouter``, ``openai_compatible`` and ``anthropic_api``
  on a model that still accepts it. A ``claude_code`` endpoint has no temperature setting.
* Neither level reachable (no tape, and a purpose that a live call needs sits on an endpoint that cannot take temperature 0): the run
  **fails before its first call** and names the purposes. It never falls back to sampling. A runtime guard in the resolver refuses
  any live call at level 1 whose entry lacks temperature 0, so a purpose that the start-up check did not list still cannot sample.

Not covered by either level: tool results (Vivado, simulators, timestamps), the order of parallel work, and ``claude_code``
sub-agent turns (their tool loop runs inside the CLI; at level 2 they are refused).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from agent.models.tape import DeterminismError, Tape

LEVEL1_KINDS = ("openrouter", "openai_compatible", "anthropic_api")
SEED = 1234
from agent.models.config import ANTHROPIC_TEMPERATURE_OK     # brief 209b: the per-model rule lives in the model config (agent.models.config.BUILTIN_MODELS)
DEFAULT_TAPE_ROOT = Path(os.environ.get("FDA_TAPE_DIR") or Path.home() / ".local" / "share" / "fpga_design_agent" / "tapes")


def level1_capable(e: Any) -> str | None:
    """None when the entry can run at temperature 0, else the reason it cannot."""
    if e.model is None:
        return None
    if e.kind == "claude_code":
        return "claude_code (the `claude -p` CLI) has no temperature or seed setting"
    if e.kind == "replay":
        return None
    if e.kind == "anthropic_api":
        if e.options.get("thinking_budget"):
            return "extended thinking does not accept a temperature"
        if not e.model.startswith(ANTHROPIC_TEMPERATURE_OK):
            return f"{e.model} rejects a temperature (HTTP 400); only older models (Haiku 4.5, Sonnet 4.6, Opus 4.6) take one"
    return None


def level1_patch(table: Any, seed: int = SEED) -> dict[str, Any]:
    """The command-line layer that sets temperature 0 (and the seed, where the kind takes one) on every capable entry."""
    from agent.models.config import SUPPORTS
    purposes: dict[str, Any] = {}
    for e in table.entries():
        if e.model is None or level1_capable(e) is not None or e.kind == "replay":
            continue
        opts = {"temperature": 0, **({"seed": seed} if "seed" in SUPPORTS[e.kind]["options"] else {})}
        purposes[f"{e.purpose}@{e.stage}" if e.stage else e.purpose] = {"options": opts}
    return {"purposes": purposes}


def purposes_in_use(cfg: Any) -> set[str]:
    used = {"interpret", "model", "tests", "rtl", "constraints"}
    if getattr(cfg, "interview", "off") == "oracle" or getattr(cfg, "hidden_spec", None):
        used.add("oracle")
    if getattr(cfg, "spec_tests", False):
        used.add("spectest")
    if getattr(cfg, "docs", "off") != "off":
        used.add("doc")
    if getattr(cfg, "router_model", None):
        used.add("route")
    if getattr(cfg, "closure", "off") != "off":
        used.add("closure")
    return used


def check_level1(table: Any, cfg: Any) -> None:
    """Fail before the first call: every purpose this run uses must be able to run at temperature 0."""
    used = purposes_in_use(cfg)
    bad = []
    for e in table.entries():
        if e.purpose in used and e.model is not None and (why := level1_capable(e)):
            bad.append(f"  {e.purpose}{'@' + e.stage if e.stage else ''}: endpoint {e.endpoint!r} ({e.kind}), model {e.model}: {why}")
    if bad:
        raise DeterminismError("--deterministic cannot run this configuration: there is no recording to replay, and these purposes cannot take "
                               "temperature 0, so the run would sample:\n" + "\n".join(bad) +
                               "\nMove them to an openrouter, openai_compatible or anthropic_api endpoint (a models.yaml or --model-config edit), "
                               "or give --tape a recording of an earlier run to replay.")


def tape_dir_for(cfg: Any, given: str | Path | None) -> Path:
    return Path(given) if given else DEFAULT_TAPE_ROOT / cfg.name


def versions(table: Any) -> dict[str, Any]:
    """Every version the run record pins: the agent, the CLI (when a claude_code endpoint is used), the models and the endpoints."""
    import subprocess
    from urllib.parse import urlparse
    root = Path(__file__).resolve().parents[2]
    git = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    out: dict[str, Any] = {"agent_commit": git, "table_hash": table.hash}
    if any(e.kind == "claude_code" and e.model for e in table.entries()) and shutil.which("claude"):
        from agent.models import claude_cli
        out["claude_code_version"] = claude_cli.version()
    out["endpoints"] = sorted({f"{e.endpoint} ({e.kind}"
                               + (f", {urlparse(e.base_url).hostname}" if e.base_url else "") + f") {e.model}" for e in table.entries() if e.model})
    return out


def describe(mode: str, level: int, tape: Tape | None, table: Any, *, seed: int | None, note: str) -> dict[str, Any]:
    """The ``determinism`` block of ``config.json``: what was asked, the level that actually applies, what it pins and what it does not cover."""
    return {"requested": True, "level": level, "level_meaning": {2: "replay: every model call served from a recorded tape (exact)",
                                                                1: "live calls at temperature 0 (not bit-exact; recorded to a tape for replay)"}[level],
            "mode": mode, "seed": seed, "tape": str(tape.root) if tape else None, "tape_sha256_at_start": tape.sha256() if tape else None,
            "pinned": versions(table), "not_covered": ["tool results (Vivado, simulators, clocks)", "claude_code sub-agent turns (refused at level 2)",
                                                      "provider-side batching at level 1"], "note": note}

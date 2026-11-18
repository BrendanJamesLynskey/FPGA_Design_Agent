"""Open-source synthesis and the equivalence gate as agent tools (brief 101).

- ``oss_synth``: Yosys + ABC (OSS CAD Suite) maps the design's sources for a part, delay-driven, and writes an EDIF and a Verilog
  netlist under ``build/<variant>/oss_netlists/<name>/`` (flow/oss_synth.py). The cell counts it returns are Yosys's, not timing:
  hand the EDIF to Vivado (``read_edif``, out of context) and judge it by Vivado's timing report.
- ``eqy_check``: proves a netlist equivalent to the RTL with ``eqy`` (flow/eqy_gate.py) and records the result bound to the
  netlist's and the RTL's hashes. The post-synthesis gate ``post_synth_oss_netlist_equivalent`` (flow/gates.py) fails any build
  whose ``oss_netlists/`` holds a netlist without that PASS, so a result from a flow outside Vivado's own synthesis (Yosys,
  direct primitives, RapidWright, hand edits) is not reported before this passes.

Neither tool is offered to a stage or role by default (a latency or closure loop opts in; the prompt text is in the private
knowledge base, prompts/oss_synth/). Both run the flow's own Python through the session's runner, so the argv is fixed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from agent.core.registry import tool
from agent.core.session import Session

PY = sys.executable
_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_PART = re.compile(r"^[a-z0-9]{6,24}(-[0-9a-z]{1,4})?$")


def _dest(s: Session, name: str, variant: str) -> Path:
    if not _NAME.match(name):
        return Path()
    return s.design / "build" / variant / "oss_netlists" / name


@tool("oss_synth", "Synthesise the given sources with Yosys + ABC for a part (script abc9 = timing-driven ABC9, abc9_dff = with "
                   "sequential steps, abc_d = classic ABC with a delay target d_ps) and write an EDIF and a Verilog netlist under "
                   "build/<variant>/oss_netlists/<name>/. The LUT/FF counts are Yosys's, not timing: implement the EDIF in Vivado "
                   "(read_edif, out of context) and judge it by Vivado's timing. The netlist must pass eqy_check before any result "
                   "from it is reported (gate post_synth_oss_netlist_equivalent).",
      {"top": {"type": "string", "maxLength": 64}, "sources": {"type": "array", "items": {"type": "string", "maxLength": 300}, "minItems": 1, "maxItems": 40},
       "part": {"type": "string", "maxLength": 40}, "script": {"type": "string", "enum": ["abc9", "abc9_dff", "abc_d"]},
       "d_ps": {"type": "integer", "minimum": 1, "maximum": 100000}, "name": {"type": "string", "maxLength": 40},
       "variant": {"type": "string", "enum": ["base", "ila"]}},
      ["top", "sources", "part"])
def oss_synth(s: Session, top: str, sources: list[str], part: str, script: str = "abc9", d_ps: int = 1, name: str = "oss",
              variant: str = "base") -> dict:
    if not _ID.match(top) or not _PART.match(part) or not _NAME.match(name):
        return {"ok": False, "output": "top, part or name has an illegal form"}
    srcs = [str(s.jail.resolve(p)) for p in sources]
    dest = _dest(s, name, variant)
    argv = [PY, "-m", "flow.oss_synth", "--top", top, "--part", part, "--script", script, "--d-ps", str(d_ps), "--out", str(dest), *srcs]
    r = s.runner.run("oss-synth", argv, s.root, timeout=1800)
    out = (r.stdout + ("\n" + r.stderr if r.stderr.strip() else "")).strip()
    rec = {}
    if r.returncode == 0 and (dest / "synth.json").is_file():
        j = json.loads((dest / "synth.json").read_text())
        rec = {k: j[k] for k in ("script", "family", "lut", "ff", "carry", "seconds", "edif", "netlist")}
        rec["note"] = "cell counts are Yosys's; run eqy_check on the netlist, then Vivado timing on the EDIF"
    return {"ok": r.returncode == 0, "output": out[-4000:], **rec}


@tool("eqy_check", "Prove a netlist (Verilog from Yosys, or Vivado write_verilog -mode funcsim, or RapidWright) equivalent to the RTL "
                   "sources with eqy (OSS CAD Suite). Returns PASS, FAIL (counterexample under the work directory), SKIPPED (suite "
                   "absent: nothing is claimed) or ERROR. strategy auto = register correspondence by name, then a single-partition "
                   "PDR proof if that does not prove. Writes eqy_result.json beside the netlist when it lives under oss_netlists/.",
      {"top": {"type": "string", "maxLength": 64}, "sources": {"type": "array", "items": {"type": "string", "maxLength": 300}, "minItems": 1, "maxItems": 40},
       "netlist": {"type": "string", "maxLength": 300}, "strategy": {"type": "string", "enum": ["auto", "name", "group"]}},
      ["top", "sources", "netlist"])
def eqy_check(s: Session, top: str, sources: list[str], netlist: str, strategy: str = "auto") -> dict:
    if not _ID.match(top):
        return {"ok": False, "output": "top has an illegal form"}
    nl = s.jail.resolve(netlist)
    if not nl.is_file():
        return {"ok": False, "output": f"no such netlist: {netlist}"}
    srcs = [str(s.jail.resolve(p)) for p in sources]
    work = nl.parent / f"eqy_{nl.stem}"
    argv = [PY, "-m", "flow.eqy_gate", "--top", top, "--gold", *srcs, "--gate", str(nl), "--work", str(work), "--strategy", strategy]
    if nl.parent.parent.name == "oss_netlists":
        argv += ["--evidence", str(nl.parent)]
    r = s.runner.run("eqy-gate", argv, s.root, timeout=5200)
    out = (r.stdout + ("\n" + r.stderr if r.stderr.strip() else "")).strip()
    status = "ERROR"
    if (work / "result.json").is_file():
        status = json.loads((work / "result.json").read_text())["status"]
    elif "SKIPPED" in out:
        status = "SKIPPED"
    return {"ok": status == "PASS", "status": status, "output": out[-3000:], "work": str(work)}

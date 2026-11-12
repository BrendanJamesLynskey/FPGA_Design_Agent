#!/usr/bin/env python3
"""Translate a design's SystemVerilog into VHDL-2008 with a model, checked by GHDL lint only (brief 55).

    python3 tools/vhdl_translate.py --sv <files...> --out <dir> [--spec spec.md] [--skill SKILL.md ...]
                                    [--model openai/gpt-6-luna] [--rounds 3] [--max-usd 0.30] [--block]

The model sees the spec (when given), the SystemVerilog sources, the language-boundary notes of flow/vhdl.py and the
skills passed with --skill (the knowledge bank's VHDL units; none for a baseline run). It answers with whole files;
each round's files are linted by GHDL (analysis, then synthesis-elaboration of the top) and the lint messages are the
only feedback. It never sees a bench, a model or a test result: the hidden bench scores the result afterwards
(flow/vhdl_score.py), so the translation stays blind to the tests. ``--block`` is for a module without the test
shell (entity and port names exactly as in the SystemVerilog).

Writes <out>/rtl/*.vhd and <out>/translate.json (rounds, lint output, tokens and provider-reported cost).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow import vhdl  # noqa: E402

SYSTEM = """You are an FPGA engineer who writes synthesisable VHDL-2008 for AMD Vivado. You translate SystemVerilog
designs into VHDL that behaves identically, clock for clock, at every port.

Answer with every VHDL file in full, each in its own fenced block that starts with the file name:
```vhdl file=rtl/<entity>.vhd
...
```
Nothing outside the blocks is used. One entity per file, the file named after the entity."""

BOARD_RULES = vhdl.BOUNDARY_NOTES

BLOCK_RULES = """This is a stand-alone module, not a board top: keep the entity name and every port name exactly as in the
SystemVerilog (same spelling and case), std_logic for 1-bit ports and std_logic_vector(N-1 downto 0) for buses, and
keep the parameters as generics with the same names and defaults. Keep synthesis attributes (for example
(* ASYNC_REG = "TRUE" *) becomes a VHDL `attribute ASYNC_REG : string;` and `attribute ASYNC_REG of <signal> : signal is
"TRUE";`). VHDL-2008, ieee.numeric_std only."""

_BLOCK = re.compile(r"```vhdl\s+file=(\S+)\s*\n(.*?)```", re.S)


def parse_files(text: str) -> dict[str, str]:
    out = {}
    for name, body in _BLOCK.findall(text):
        name = name.strip().lstrip("./")
        if not name.startswith("rtl/"):
            name = "rtl/" + Path(name).name
        if vhdl.is_vhdl(name) and ".." not in name:
            out[name] = body.rstrip() + "\n"
    return out


def build_prompt(sv: list[Path], spec: Path | None, block: bool, skills: list[Path], top: str | None) -> str:
    parts = []
    if spec:
        parts.append("## The specification the design was written to\n\n" + spec.read_text())
    parts.append("## Rules for the VHDL\n\n" + (BLOCK_RULES if block else BOARD_RULES))
    if top:
        parts.append(f"The top-level entity is `{top}`.")
    for s in skills:
        parts.append(f"## Knowledge: {s.parent.name}\n\n" + s.read_text())
    for f in sv:
        parts.append(f"## SystemVerilog source {f.name}\n\n```systemverilog\n{f.read_text()}\n```")
    parts.append("Translate every module above into VHDL-2008 now.")
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sv", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--spec", type=Path)
    ap.add_argument("--top")
    ap.add_argument("--skill", type=Path, action="append", default=[])
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--max-usd", type=float, default=0.30)
    ap.add_argument("--block", action="store_true")
    ap.add_argument("--generics", default="{}", help="JSON generics for the lint's elaboration of the top")
    a = ap.parse_args(argv)
    from agent.graph.llm import OpenRouterClient
    client = OpenRouterClient(a.model)
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(a.sv, a.spec, a.block, a.skill, a.top)}]
    rtl = a.out / "rtl"
    rec = {"model": a.model, "sv": [str(p) for p in a.sv], "spec": str(a.spec) if a.spec else None,
           "skills": [str(s) for s in a.skill], "block": a.block, "ghdl": vhdl.ghdl_version(), "rounds": [],
           "cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    files: dict[str, str] = {}
    ok = False
    for rnd in range(1, a.rounds + 1):
        if rec["cost_usd"] >= a.max_usd:
            rec["stop"] = f"cost cap {a.max_usd} reached"
            break
        r = client(msgs)
        rec["cost_usd"] += r.cost if r.cost is not None else 0.05
        rec["prompt_tokens"] += r.prompt_tokens
        rec["completion_tokens"] += r.completion_tokens
        new = parse_files(r.text)
        if not new:
            rec["rounds"].append({"round": rnd, "files": [], "lint": "no ```vhdl file=...``` blocks in the answer",
                                  "cost": r.cost})
            msgs += [{"role": "assistant", "content": r.text},
                     {"role": "user", "content": "No files were found. Answer with ```vhdl file=rtl/<entity>.vhd blocks."}]
            continue
        files.update(new)
        if rtl.exists():
            for p in rtl.glob("*.vhd*"):
                p.unlink()
        rtl.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (a.out / name).write_text(body)
        vh = sorted(rtl.glob("*.vhd*"))
        try:
            top = vhdl.top_entity(vh, a.top or "")
        except RuntimeError as e:
            top = None
            lint = {"ok": False, "output": str(e)}
        if top:
            lint = vhdl.lint(vh, top, json.loads(a.generics), workdir=ROOT / "build" / "vhdl_translate" / a.out.name)
        rec["rounds"].append({"round": rnd, "files": sorted(files), "lint_ok": lint["ok"], "lint": lint["output"][:3000],
                              "cost": r.cost, "answer_chars": len(r.text)})
        if lint["ok"]:
            ok = True
            break
        msgs += [{"role": "assistant", "content": r.text},
                 {"role": "user", "content": "GHDL rejects the VHDL:\n" + lint["output"][:3000]
                  + "\n\nFix it. Answer with every file that changes, in full, in the same block format."}]
    rec["lint_ok"] = ok
    rec["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "translate.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps({"out": str(a.out), "lint_ok": ok, "rounds": len(rec["rounds"]), "cost_usd": round(rec["cost_usd"], 4)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

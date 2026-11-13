"""Phase 0, the structured spec session (brief 27 Part B, stage P1; docs/design_environment.md section 3).

The session turns the user's words (``system/spec.md``) into the three files the project layer reads, each checked by
:func:`project.schema.check_project`: ``system/requirements.yaml``, ``design.yaml`` and a ``modules/<m>/contract.yaml``
per module (with a ``modules/<m>/spec.md``). It runs in passes; each pass has its own question budget and its own
question log under ``phase0/``.

1. **Requirements** (``phase0/pass1_requirements.json``). The drafter (a model) turns the spec into S-requirements
   with proof methods and lists its own questions, each naming the S-ids it settles. They are put to the user one at a
   time through :class:`agent.graph.interview.Interview`, as the clarify stage does today.
2. **Interface-first decomposition and contracts** (``phase0/pass2_contracts.json``). The drafter proposes the module
   graph, a contract per module and the board binding, with the pass 1 answers in hand. **The questions of this pass
   are not left to the model.** The harness lists every contract and design field (:func:`inventory`). A field counts
   as stated only when the drafter quotes the user's spec for it, and the quote is really there (the oracle's own
   verbatim rule); every other field becomes one question, with the drafter's value as the proposed default and its
   reason. Fields that two ends of a connection must share (``tdata``, ``tuser``, ``tlast``, ``packet_beats``,
   ``backpressure``, ``source_gaps``) are asked once per connection. Interface fields are asked first, each module
   within its own budget share, then data formats, then board pins (:func:`plan_questions`). This generalises ``ensure_register_question``
   (one harness-made question) to every field. The drafter then applies the answers; a field it changes without an
   answer naming it goes back as a repair note, and what is still changed after the repairs is logged
   (``unasked_changes``).
3. **Open questions as assumptions.** A question nobody answers (``not specified``, the budget, ``--interview off``)
   is never silently defaulted: the harness writes it into ``design.yaml`` as ``assumptions: [{id: A-n, ...,
   affects: [<field paths or S-ids>], status: open}]``.

The test-plan pass of the design (section 3, pass 3) is not part of P1.

Who answers: the spec oracle (``--interview oracle``, a hidden full spec; ``agent.graph.interview.SpecOracle``), a
person at the terminal (``on``), or nobody (``off``). The drafter and the oracle are plain callables, so CI runs the
whole session with canned replies and no network.

**spec.yaml (decision, P1):** phase 0 does not write a module's ``spec.yaml``. It stays the stage 1 input, written by
today's stage 0 clarify from ``modules/<m>/spec.md`` and the approved contract; :func:`spec_contract_errors` holds
the two together (the same ports, directions, widths and register offsets). Reason: every role and gate after stage 0
(model, tests, RTL, ``flow/verif_gates.spec_items``, the spec-test role) reads ``spec.yaml``'s behaviour, timing and
M-requirements, which a contract does not hold; replacing it would change every role's request (the eval-1 golden
request test) for no gain. The contract is the authority on the interface; ``spec.yaml`` restates it for the roles.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from agent.graph.interview import NOT_SPECIFIED, Interview, Question, _norm
from agent.graph.spec_schema import propose_proof, requirement_errors
from project.schema import (CONTRACT_SCHEMA, DESIGN_SCHEMA, REQUIREMENTS_SCHEMA, ROOT, board_dir, bus_bits,
                            check_project, iface_ports, load_yaml, params_of, port_map, xdc_ports)
from project.expr import ExprError, evaluate

PASSES = ("requirements", "contracts")
#: question budgets. Pass 1: one budget. Pass 2 (planner review of PR #104, after pilot 1 run 4 lost the median latency
#: past a single 40-question budget): each module has its own share for its interface fields, the design's own interface
#: fields (clocks, resets, design ID, window bases) have one, and data formats and board pins share the rest, asked last.
BUDGET = {"requirements": 12, "contracts_per_module": 12, "contracts_design": 12, "contracts_rest": 12}
#: the order pass 2 asks in: 0 interface fields (latency, stream fields, widths, register map, clocks, resets ...),
#: 1 data formats, 2 board pins
TIERS = ("interface", "data_formats", "board_pins")


def field_tier(path: str) -> int:
    if path.startswith("design.board_ports."):
        return 2
    if ".contract.data_formats." in path:
        return 1
    return 0


def field_group(path: str) -> str:
    """The share a tier-0 field counts against: its module, or ``design``."""
    return "design" if path.startswith("design.") else path.split(".", 1)[0]


def plan_questions(fields: list[Field], budget: dict[str, int]) -> list[tuple[Field, bool]]:
    """The open fields in asking order, each with whether it is inside its budget share: tier 0 module by module (in
    the drafter's module order), then the design's tier 0, then data formats, then board pins. A module's interface
    questions never compete with another module's, or with formats and pins."""
    def key(ix: tuple[int, Field]) -> tuple[int, int, int]:
        i, f = ix
        t, g = field_tier(f.paths[0]), field_group(f.paths[0])
        return (t, 1 if (t == 0 and g == "design") else 0, i)
    used: dict[str, int] = {}
    out = []
    for _, f in sorted(enumerate(fields), key=key):
        t, g = field_tier(f.paths[0]), field_group(f.paths[0])
        share = ("rest", budget["contracts_rest"]) if t else \
            (g, budget["contracts_design"] if g == "design" else budget["contracts_per_module"])
        used[share[0]] = used.get(share[0], 0) + 1
        out.append((f, used[share[0]] <= share[1]))
    return out
MAX_REPAIRS = 3                                         # drafter attempts per step after the first
LINK_FIELDS = ("tdata", "tuser", "tlast", "packet_beats", "backpressure", "source_gaps")
FORMAT_DIR = Path(__file__).with_name("phase0_format")
LOG_DIR = "phase0"


# --- the field inventory ---------------------------------------------------------------------------------------------

@dataclass
class Field:
    """One contract or design field: ``paths[0]`` names it; the other paths are fields it settles too (the far end of a
    connection)."""
    paths: list[str]
    value: Any
    ask: str


def _flow(v: Any) -> str:
    if isinstance(v, str):
        return v
    t = yaml.safe_dump(v, default_flow_style=True, sort_keys=False, width=10_000).strip()
    return t[:-3].strip() if t.endswith("\n...") else t


def contract_fields(module: str, c: dict[str, Any]) -> list[Field]:
    """Every field of one contract the user could have stated, in the contract's order."""
    m, out = module, []
    pre = f"{m}.contract"
    for p in c.get("parameters") or []:
        if isinstance(p, dict) and p.get("name"):
            out.append(Field([f"{pre}.parameters.{p['name']}"], {k: v for k, v in p.items() if k != "name"},
                             f"What value, and what allowed range, should parameter {p['name']} of {m} have?"))
    for k in c.get("clocks") or []:
        if isinstance(k, dict) and k.get("name"):
            out.append(Field([f"{pre}.clocks.{k['name']}.max_mhz"], k.get("max_mhz"),
                             f"At what clock rate (MHz) must {m}'s clock {k['name']} close timing?"))
    for r in c.get("resets") or []:
        if isinstance(r, dict) and r.get("name"):
            out.append(Field([f"{pre}.resets.{r['name']}"], {"polarity": r.get("polarity"), "style": r.get("style")},
                             f"Is {m}'s reset {r['name']} active high or active low, and synchronous or asynchronous?"))
    in_iface: set[str] = set()
    for f in c.get("interfaces") or []:
        try:
            in_iface |= set(iface_ports(f)) if isinstance(f, dict) else set()
        except (TypeError, ValueError, AttributeError):
            pass
    clk_rst = {x.get("port") for x in [*(c.get("clocks") or []), *(c.get("resets") or [])] if isinstance(x, dict)}
    for p in c.get("ports") or []:
        if isinstance(p, dict) and p.get("name") and p["name"] not in in_iface | clk_rst:
            out.append(Field([f"{pre}.ports.{p['name']}"], {k: p.get(k) for k in ("dir", "width", "reset_value")
                                                            if p.get(k) is not None},
                             f"What is {m}'s port {p['name']}: its direction, width and value in reset?"))
    for d in c.get("data_formats") or []:
        if isinstance(d, dict) and d.get("name"):
            out.append(Field([f"{pre}.data_formats.{d['name']}"], {k: d.get(k) for k in ("format", "packing")},
                             f"What number format is {d['name']} in {m} (signed or unsigned, total and fraction bits), "
                             f"and how is it packed?"))
    for f in c.get("interfaces") or []:
        if not isinstance(f, dict) or not f.get("name"):
            continue
        ip = f"{pre}.interfaces.{f['name']}"
        out.append(Field([f"{ip}.protocol"], {"protocol": f.get("protocol"), "role": f.get("role")},
                         f"What protocol does {m}'s interface {f['name']} use, and is {m} its master or slave?"))
        if f.get("protocol") == "axi4-stream":
            asks = {"tdata": f"What does a beat of {m}.{f['name']} carry: the tdata width and its fields with their formats?",
                    "tuser": f"Does {m}.{f['name']} carry sideband bits in tuser, and what does each bit mean?",
                    "tlast": f"What does tlast mark on {m}.{f['name']}, if anything?",
                    "packet_beats": f"How many beats does a packet on {m}.{f['name']} have?",
                    "backpressure": f"May the sink of {m}.{f['name']} stall the stream (drive tready low)?",
                    "source_gaps": f"May the source of {m}.{f['name']} leave gaps (tvalid low) once the stream has started?"}
            for k, a in asks.items():
                out.append(Field([f"{ip}.{k}"], f.get(k), a))
        elif f.get("protocol") == "axi4-lite":
            out.append(Field([f"{ip}.bus"], {"addr_width": f.get("addr_width"), "data_width": f.get("data_width")},
                             f"What address and data widths does the AXI4-Lite interface {m}.{f['name']} have?"))
    regs = c.get("registers")
    if isinstance(regs, dict) and regs.get("map"):
        # worded so that agent.graph.interview.is_register_question matches: the oracle answers with the whole map
        out.append(Field([f"{pre}.registers"], [{k: r.get(k) for k in ("name", "offset", "access", "reset") if k in r}
                                                for r in regs["map"] if isinstance(r, dict)],
                         f"What is the register map of {m}: the offset, width, reset value and access (RW, RO, WO) of "
                         f"every register the host reads or writes?"))
    for x in c.get("latency") or []:
        if isinstance(x, dict):
            out.append(Field([f"{pre}.latency.{x.get('from')}.{x.get('to')}"], x.get("cycles"),
                             f"What latency, in clock cycles, from {m}.{x.get('from')} to {m}.{x.get('to')}?"))
    for x in c.get("throughput") or []:
        if isinstance(x, dict):
            out.append(Field([f"{pre}.throughput.{x.get('interface')}"],
                             {k: v for k, v in x.items() if k != "interface"},
                             f"What throughput must {m}.{x.get('interface')} sustain (beats per clock, and output beats "
                             f"per input beat)?"))
    # fields the drafter left out are asked too (pilot 1 run 1: no latency in the median's contract, so it was never
    # asked): a latency from every stream input to every stream output, a throughput for every stream output
    streams = [f for f in c.get("interfaces") or [] if isinstance(f, dict) and f.get("protocol") == "axi4-stream"]
    have = {p for f in out for p in f.paths}
    for s in (f for f in streams if f.get("role") == "slave"):
        for o in (f for f in streams if f.get("role") == "master"):
            p = f"{pre}.latency.{s.get('name')}.{o.get('name')}"
            if p not in have:
                out.append(Field([p], None, f"What latency, in clock cycles, from {m}.{s.get('name')} to "
                                            f"{m}.{o.get('name')}?"))
    for o in (f for f in streams if f.get("role") == "master"):
        p = f"{pre}.throughput.{o.get('name')}"
        if p not in have:
            out.append(Field([p], None, f"What throughput must {m}.{o.get('name')} sustain (beats per clock, and "
                                        f"output beats per input beat)?"))
    return out


def design_fields(d: dict[str, Any]) -> list[Field]:
    out = []
    for k in d.get("clocks") or []:
        if isinstance(k, dict) and k.get("name"):
            out.append(Field([f"design.clocks.{k['name']}"], {x: k.get(x) for x in ("source", "mhz", "port", "from")
                                                               if k.get(x) is not None},
                             f"Which clock is {k['name']}: its frequency and where it comes from?"))
    for r in d.get("resets") or []:
        if isinstance(r, dict) and r.get("name"):
            out.append(Field([f"design.resets.{r['name']}"], {x: r.get(x) for x in ("from", "polarity", "style")},
                             f"What resets the design's reset {r['name']} (button or other source), and its polarity?"))
    sh = d.get("shell")
    if isinstance(sh, dict):
        out.append(Field(["design.shell.design_id"], sh.get("design_id"), "What design ID does the test shell report?"))
    for m in d.get("modules") or []:
        if isinstance(m, dict) and m.get("window_base") is not None:
            out.append(Field([f"design.modules.{m['name']}.window_base"], m.get("window_base"),
                             f"At which offset of the shell's register window do {m['name']}'s registers start?"))
    for p in d.get("board_ports") or []:
        if isinstance(p, dict) and p.get("name"):
            out.append(Field([f"design.board_ports.{p['name']}"],
                             {x: p.get(x) for x in ("dir", "drive", "from", "to") if p.get(x) is not None},
                             f"What does the board pin {p['name']} connect to, and how is it driven (push-pull, "
                             f"open-drain, pulled up, input)?"))
    return out


def inventory(design: dict[str, Any], contracts: dict[str, dict[str, Any]]) -> list[Field]:
    """Contract fields of every module, then the design's; the shared fields of a connection merged into one Field
    (asked once, at the master end, settling the slave end too)."""
    fs = [f for m, c in contracts.items() for f in contract_fields(m, c)] + design_fields(design)
    by_path = {f.paths[0]: f for f in fs}
    drop: set[str] = set()
    for x in design.get("connections") or []:
        if not isinstance(x, dict):
            continue
        a, b = str(x.get("from", "")), str(x.get("to", ""))
        am, _, ai = a.partition(".")
        bm, _, bi = b.partition(".")
        for k in LINK_FIELDS:
            pa, pb = f"{am}.contract.interfaces.{ai}.{k}", f"{bm}.contract.interfaces.{bi}.{k}"
            if pa in by_path and pb in by_path:
                by_path[pa].paths.append(pb)
                drop.add(pb)
    return [f for f in fs if f.paths[0] not in drop]


def values_by_path(design: dict[str, Any], contracts: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Every field path (also the merged ones) with its value, as text: what the unasked-change check compares."""
    out: dict[str, str] = {}
    for f in [*(f for m, c in contracts.items() for f in contract_fields(m, c)), *design_fields(design)]:
        out[f.paths[0]] = _flow(f.value)
    return out


# --- settled by the user's own words ----------------------------------------------------------------------------------

def quote_ok(quote: Any, spec_text: str) -> bool:
    """The drafter's quote is in the user's spec (whitespace and quote marks normalised, as the oracle checks quotes).
    A quote of fewer than three words does not count (c12 run 1: the bare pin name "AUD_PWM" settled the pin's electrical
    type, and the drafter's type was wrong)."""
    q = _norm(str(quote or ""))
    return len(q.split()) >= 3 and q in _norm(spec_text)


_NUM = re.compile(r"(?<![\w.])(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)(?![\w.])")


def _numbers(text: str) -> set[float]:
    out = set()
    for t in _NUM.findall(text):
        try:
            out.add(float(int(t, 16)) if t.lower().startswith("0x") else float(t))
        except ValueError:
            pass
    return out


def numbers_in_quote(value: Any, quote: str) -> bool:
    """Every number in the field's value is also a number in the quote (pilot 1 run 5: a latency of 1651 cycles was
    "stated" by "The syncs and the picture leave the chip aligned ...", which gives no number, so it was never asked)."""
    return _numbers(_flow(value)) <= _numbers(str(quote))


def settled_by_spec(f: Field, sources: dict[str, Any], spec_text: str) -> str | None:
    """The quote that states the field: in the spec, three words or more, and holding every number of the value."""
    for p in f.paths:
        if quote_ok(sources.get(p), spec_text) and numbers_in_quote(f.value, str(sources[p])):
            return str(sources[p])
    return None


# --- the drafter ----------------------------------------------------------------------------------------------------

@dataclass
class Calls:
    """Every drafter call: tokens, provider-reported cost, seconds (cost is never estimated; ``None`` when not reported)."""
    rows: list[dict[str, Any]] = field(default_factory=list)

    def add(self, who: str, step: str, reply: Any) -> None:
        self.rows.append({"who": who, "step": step, "prompt_tokens": getattr(reply, "prompt_tokens", 0),
                          "completion_tokens": getattr(reply, "completion_tokens", 0),
                          "cost": getattr(reply, "cost", None), "seconds": getattr(reply, "seconds", 0.0)})

    def totals(self) -> dict[str, Any]:
        cost = [r["cost"] for r in self.rows]
        return {"calls": len(self.rows), "prompt_tokens": sum(r["prompt_tokens"] for r in self.rows),
                "completion_tokens": sum(r["completion_tokens"] for r in self.rows),
                "usd_provider_reported": round(sum(c for c in cost if c is not None), 6),
                "unreported_cost_calls": sum(c is None for c in cost)}


class BudgetExceeded(Exception):
    pass


def _yaml_block(text: str) -> Any:
    """The YAML document of a reply: the first fenced block if there is one, else the whole text."""
    m = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.S)
    return yaml.safe_load(m.group(1) if m else text)


def board_port_summary(board: str) -> str:
    """The master XDC's port names, buses shortened (``LED[0..15]``)."""
    names = xdc_ports(next(board_dir(board).glob("*.xdc")))
    buses: dict[str, list[int]] = {}
    singles = []
    for n in sorted(names):
        b = bus_bits(n)
        if b and b[1]:
            buses.setdefault(b[0], []).extend(b[1])
        else:
            singles.append(n)
    return ", ".join([*singles, *(f"{k}[{min(v)}..{max(v)}]" for k, v in sorted(buses.items()))])


def format_example() -> str:
    parts = []
    for p in sorted(FORMAT_DIR.rglob("*.yaml")):
        parts.append(f"--- {p.relative_to(FORMAT_DIR).as_posix()}\n{p.read_text()}")
    return "\n".join(parts)


def _layer_tables() -> str:
    doc = (ROOT / "docs" / "project_layer.md").read_text()
    m = re.search(r"(## `design.yaml`.*?)## Evidence and status", doc, re.S)
    return m.group(1) if m else ""


SYSTEM = """You are the Clarifier of an FPGA design agent, running phase 0 (the spec session) of a multi-module design.
You turn the user's specification into files the project checker reads. Never invent a requirement: when the
specification does not settle something, propose a value and say why, and it will be asked. Reply with ONE fenced
```yaml block and nothing else."""


def pass1_prompt(spec_text: str) -> str:
    return f"""Pass 1: requirements. Turn the user's specification into system requirements with ids S-1, S-2, ...
Each has a text (one testable statement), a proof list (simulation, formal, hardware, analysis) and modules: [] (the
modules are decided in pass 2). Then list your questions: only things a design needs that the specification leaves
open, one per question, each with your proposed default, the reason, and the S-ids it settles. Ask nothing the
specification already answers.

Reply:
```yaml
requirements:
  - {{id: S-1, text: "...", proof: [simulation], modules: []}}
questions:
  - {{question: "...", default: "...", reason: "...", settles: [S-1]}}
```

--- the user's specification (system/spec.md) ---
{spec_text}"""


def pass2_prompt(spec_text: str, board: str, reqs: list[dict[str, Any]], p1: list[Question]) -> str:
    qa = "\n".join(f"- Q: {q.text}\n  A ({q.status}, by {q.by}): {q.answer}" for q in p1) or "(none)"
    return f"""Pass 2: interface-first decomposition. Propose the modules (each a separate RTL block with one job),
the connections between them, a contract per module, and the design file (clock and reset plan, the test shell, the
board pins), before any behaviour. The test shell (shell/rtl/fpga_shell.sv) is always present: it owns the USB-UART
and a register window at 0x80-0xFF; a module's registers on `bus: top` are placed in that window at `window_base`.
Use only board pin names from the board's master XDC: {board_port_summary(board)}.
Pin directions are the FPGA's own (the checker compares them with the board: UART_RXD_OUT is an FPGA output,
UART_TXD_IN an input). Connect the modules point to point through their interfaces: every module must reach a board
pin or the shell's register window, directly or through connections.
The board is {board}.

For EVERY field you fill, either quote the user's specification word for word under `sources` (the exact words that
state it) or give your reason under `reasons` (it will be asked). Field paths:
  <module>.contract.parameters.<P> | .clocks.<clk>.max_mhz | .resets.<rst> | .ports.<port> (ports outside interfaces)
  | .data_formats.<name> | .interfaces.<if>.protocol | .interfaces.<if>.<tdata|tuser|tlast|packet_beats|backpressure|source_gaps>
  | .interfaces.<if>.bus (AXI4-Lite widths) | .registers | .latency.<from>.<to> | .throughput.<if>
  design.clocks.<clk> | design.resets.<rst> | design.shell.design_id | design.modules.<m>.window_base | design.board_ports.<PIN>
Only quote words that really are in the specification; a paraphrase is not a quote.

The requirements from pass 1 (fill in `modules` for each: module names, or `top` for the integrated design):
{yaml.safe_dump(reqs, sort_keys=False, width=200)}
The pass 1 questions and their answers (use the answers; a defaulted answer is an assumption, keep it):
{qa}

The file formats (the checker's own tables):
{_layer_tables()}
A complete, valid example project in these formats (unrelated to this design; copy its form, not its content):
{format_example()}

Reply:
```yaml
design: {{...design.yaml content: schema {DESIGN_SCHEMA}, name, board, clocks, resets, shell, modules, connections, board_ports, owned: []...}}
contracts:
  <module>: {{...contract.yaml content: schema {CONTRACT_SCHEMA}, module, summary, ...}}
module_specs:
  <module>: "a short markdown spec of the module's behaviour"
requirements: [... the S-requirements with modules filled in ...]
sources: {{<field path>: "<exact words of the specification>"}}
reasons: {{<field path>: "<why you chose this value>"}}
```

--- the user's specification (system/spec.md) ---
{spec_text}"""


def apply_prompt(bundle: dict[str, Any], answered: list[tuple[Question, list[str]]]) -> str:
    qa = "\n".join(f"- fields {', '.join(paths)}\n  Q: {q.text}\n  A: {q.answer}" for q, paths in answered)
    return f"""The user answered these questions about your draft. Change exactly the fields each answer names so that
they say what the answer says, and keep every other field as it is. Keep the files consistent with each other (if an
answer changes a width, change the ports and the far end of the connection too). Reply with the whole bundle in the
same form (design, contracts, module_specs, requirements, sources, reasons).

{qa}

--- your draft ---
```yaml
{yaml.safe_dump(bundle, sort_keys=False, width=200)}
```"""


def repair_prompt(errors: list[str]) -> str:
    return ("The project checker rejected the files. Fix every problem and reply with the whole bundle again, in the "
            "same form:\n" + "\n".join(f"- {e}" for e in errors))


class Drafter:
    """The Clarifier: ``client(messages) -> Reply`` (agent.graph.llm), with a USD cap on provider-reported cost."""

    def __init__(self, client: Callable, calls: Calls, usd_cap: float):
        self.client, self.calls, self.usd_cap = client, calls, usd_cap
        self.messages: list[dict[str, str]] = []

    def _spent(self) -> float:
        return sum((r["cost"] if r["cost"] is not None else 0.05) for r in self.calls.rows)

    def ask(self, step: str, prompt: str, fresh: bool = False) -> Any:
        if self._spent() >= self.usd_cap:
            raise BudgetExceeded(f"phase 0 USD cap {self.usd_cap} reached ({self._spent():.4f})")
        if fresh or not self.messages:
            self.messages = [{"role": "system", "content": SYSTEM}]
        self.messages.append({"role": "user", "content": prompt})
        r = self.client(self.messages)
        self.calls.add("drafter", step, r)
        self.messages.append({"role": "assistant", "content": r.text})
        return r.text


def oracle_llm(client: Callable, calls: Calls) -> Callable[[str, str], dict[str, Any]]:
    """The oracle's ``llm(system, user)`` over an OpenRouter client, counted in the same call log."""
    def llm(system: str, user: str) -> dict[str, Any]:
        r = client([{"role": "system", "content": system}, {"role": "user", "content": user}])
        calls.add("oracle", "answer", r)
        try:
            out = json.loads(r.text.strip().removeprefix("```json").removesuffix("```").strip())
            return out if isinstance(out, dict) else {"answer": NOT_SPECIFIED, "quote": None}
        except ValueError:
            return {"answer": NOT_SPECIFIED, "quote": None}
    return llm


class Terminal:
    """``--interview on``: a person answers at the terminal; an empty line means not specified."""
    name = "human"

    def answer(self, q: Question) -> tuple[str, str | None]:
        print(f"\n{q.text}\n  proposed: {q.default}\n  why: {q.reason}")
        a = input("answer (empty: take the proposal as an assumption)> ").strip()
        return (a or NOT_SPECIFIED), None


# --- the session ----------------------------------------------------------------------------------------------------

def _bundle_files(b: Any) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    """design, contracts and the shape problems of a pass 2 bundle."""
    if not isinstance(b, dict):
        return {}, {}, ["the reply must be one YAML mapping with keys design, contracts, module_specs, requirements, "
                        "sources, reasons"]
    errs = []
    d, cs = b.get("design"), b.get("contracts")
    if not isinstance(d, dict):
        errs.append("'design' must be the design.yaml mapping")
        d = {}
    if not isinstance(cs, dict) or not all(isinstance(v, dict) for v in cs.values()):
        errs.append("'contracts' must map each module name to its contract.yaml mapping")
        cs = {}
    for k in ("sources", "reasons", "module_specs"):
        if b.get(k) is not None and not isinstance(b.get(k), dict):
            errs.append(f"'{k}' must be a mapping")
    return d, cs, errs


def _dump(data: Any, header: str) -> str:
    return header + yaml.safe_dump(data, sort_keys=False, width=110, default_flow_style=None, allow_unicode=True)


HEADER = "# Written by phase 0 (python -m project spec; brief 27B P1). Format: docs/project_layer.md.\n"


def write_bundle(root: Path, b: dict[str, Any], assumptions: list[dict[str, Any]]) -> None:
    d = dict(b["design"])
    d.setdefault("schema", DESIGN_SCHEMA)
    d.setdefault("owned", [])
    d["assumptions"] = assumptions     # only the harness writes assumptions: one per question nobody answered
    (root / "design.yaml").write_text(_dump(d, HEADER))
    for m, c in b["contracts"].items():
        md = root / "modules" / str(m)
        md.mkdir(parents=True, exist_ok=True)
        c = dict(c)
        c.setdefault("schema", CONTRACT_SCHEMA)
        c["module"] = m
        (md / "contract.yaml").write_text(_dump(c, HEADER))
        spec = (b.get("module_specs") or {}).get(m)
        if isinstance(spec, str) and spec.strip():
            (md / "spec.md").write_text(spec.rstrip() + "\n")
    rq = {"schema": REQUIREMENTS_SCHEMA, "requirements": b.get("requirements") or []}
    (root / "system").mkdir(exist_ok=True)
    (root / "system" / "requirements.yaml").write_text(_dump(rq, HEADER))


def _fill_proofs(reqs: list[Any]) -> list[str]:
    """A requirement without a proof gets ``propose_proof``'s default; the note says which."""
    notes = []
    for r in reqs:
        if isinstance(r, dict) and r.get("text") and not r.get("proof"):
            r["proof"], why = propose_proof(str(r["text"]))
            notes.append(f"{r.get('id')}: proof {r['proof']} by default ({why})")
    return notes


def _assumption(n: int, q: Question, affects: list[str]) -> dict[str, Any]:
    return {"id": f"A-{n}", "text": q.text, "default": _flow(q.answer), "reason": q.reason, "affects": affects,
            "status": "open", "by": q.by}


@dataclass
class Session:
    root: Path
    drafter: Drafter
    who: Any                                   # an Answerer, or None (interview off)
    board: str = "nexys_a7_100t"
    budget: dict[str, int] = field(default_factory=lambda: dict(BUDGET))
    notes: list[str] = field(default_factory=list)

    def _log(self, name: str, data: dict[str, Any]) -> None:
        d = self.root / LOG_DIR
        d.mkdir(exist_ok=True)
        (d / name).write_text(json.dumps(data, indent=1, default=str) + "\n")

    def _draft(self, step: str, prompt: str, check: Callable[[Any], list[str]], fresh: bool = False) -> tuple[Any, int]:
        """Ask, then repair until ``check`` finds nothing (at most MAX_REPAIRS more calls). Returns (data, repairs)."""
        text = self.drafter.ask(step, prompt, fresh=fresh)
        for n in range(MAX_REPAIRS + 1):
            try:
                data, errs = _yaml_block(text), None
            except yaml.YAMLError as e:
                data, errs = None, [f"the reply is not valid YAML: {' '.join(str(e).split())}"]
            errs = errs if errs is not None else check(data)
            if not errs:
                return data, n
            if n == MAX_REPAIRS:
                raise RuntimeError(f"phase 0 {step}: still invalid after {MAX_REPAIRS} repairs: {errs[:5]}")
            text = self.drafter.ask(f"{step}-repair{n + 1}", repair_prompt(errs))
        raise AssertionError("unreachable")

    # pass 1
    def pass1(self, spec_text: str) -> tuple[list[dict[str, Any]], list[Question], list[dict[str, Any]]]:
        def check(d: Any) -> list[str]:
            if not isinstance(d, dict) or not isinstance(d.get("requirements"), list) or not d["requirements"]:
                return ["reply with a mapping: requirements (a non-empty list) and questions (a list)"]
            e = [x for x in requirement_errors({"requirements": d["requirements"]}, need_proof=False)]
            e += [f"requirement {r.get('id')!r}: ids are S-<n>" for r in d["requirements"]
                  if isinstance(r, dict) and not re.match(r"^S-\d+$", str(r.get("id", "")))]
            if not isinstance(d.get("questions") or [], list):
                e.append("'questions' must be a list")
            return e
        data, repairs = self._draft("pass1", pass1_prompt(spec_text), check, fresh=True)
        reqs = data["requirements"]
        self.notes += _fill_proofs(reqs)
        iv = Interview(max_questions=self.budget["requirements"])
        asked: list[tuple[Question, list[str]]] = []
        for i, q in enumerate(data.get("questions") or [], 1):
            if not isinstance(q, dict) or not str(q.get("question", "")).strip():
                continue
            qq = Question(f"P1-{i}", str(q["question"]), str(q.get("default") or "the drafter's proposal"),
                          str(q.get("reason") or "not given"))
            iv.ask(qq, self.who)
            asked.append((qq, [str(s) for s in q.get("settles") or []]))
        assumptions = [(q, s) for q, s in asked if q.status == "defaulted"]
        self._log("pass1_requirements.json", {
            "pass": "requirements", "budget": self.budget["requirements"], "drafter_repairs": repairs,
            "requirements": len(reqs), **{k: v for k, v in iv.summary().items() if k != "questions"},
            "questions": [{**asdict(q), "settles": s} for q, s in asked]})
        return reqs, [q for q, _ in asked], [{"q": q, "affects": s} for q, s in assumptions]

    # pass 2
    def _check_bundle(self, b: Any) -> list[str]:
        d, cs, errs = _bundle_files(b)
        if errs:
            return errs
        rq = b.get("requirements")
        if not isinstance(rq, list) or not rq:
            return ["'requirements' must be the S-requirement list with modules filled in"]
        self.notes += _fill_proofs(rq)
        names = {m.get("name") for m in d.get("modules") or [] if isinstance(m, dict)}
        missing = [m.get("name") for m in d.get("modules") or [] if isinstance(m, dict) and m.get("kind", "rtl") == "rtl"
                   and m.get("name") not in cs]
        extra = sorted(str(m) for m in cs if m not in names)       # pilot 1 run 1: a contract for the shell itself
        if missing or extra:
            return [*(f"module {m}: no contract under 'contracts'" for m in missing),
                    *(f"contracts.{m}: {m} is not in design.modules (the test shell is not a module; give a contract "
                      f"only for each module you list)" for m in extra)]
        tmp = self.root / LOG_DIR / "check"
        if tmp.exists():
            _rmtree(tmp)
        tmp.mkdir(parents=True)
        write_bundle(tmp, b, [])
        p = check_project(tmp)
        _rmtree(tmp)
        return p.errors

    def pass2(self, spec_text: str, reqs: list[dict[str, Any]], p1: list[Question]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        b, repairs = self._draft("pass2-draft", pass2_prompt(spec_text, self.board, reqs, p1), self._check_bundle,
                                 fresh=True)
        draft_values = values_by_path(b["design"], b["contracts"])
        fields = inventory(b["design"], b["contracts"])
        sources = b.get("sources") or {}
        reasons = b.get("reasons") or {}
        stated, open_fields = [], []
        for f in fields:
            qt = settled_by_spec(f, sources, spec_text)
            (stated if qt else open_fields).append((f, qt))
        bad_quotes = sorted(p for p, v in sources.items() if v and not quote_ok(v, spec_text))
        no_number = sorted(p for f, qt in open_fields for p in f.paths if quote_ok(sources.get(p), spec_text))
        iv = Interview(max_questions=10_000)                 # the shares are applied here, per module
        asked: list[tuple[Question, list[str]]] = []
        for i, (f, inside) in enumerate(plan_questions([f for f, _ in open_fields], self.budget), 1):
            reason = next((str(reasons[p]) for p in f.paths if reasons.get(p)), None) or \
                "the specification does not state it; this is the drafter's proposal"
            q = Question(f"P2-{i}", f.ask, _flow(f.value) if f.value is not None else "(none: leave the field out)",
                         reason)
            if inside:
                iv.ask(q, self.who)
            else:                                            # over its share: the default, recorded as the limit
                q.answer, q.status, q.by = q.default, "defaulted", "limit"
                iv.questions.append(q)
            asked.append((q, f.paths))
        answered = [(q, p) for q, p in asked if q.status == "answered"]
        apply_repairs, unasked, apply_failed = 0, [], None
        if answered:
            ok = {p for _, ps in answered for p in ps}

            def changed(x: dict[str, Any]) -> list[str]:
                after = values_by_path(x["design"], x["contracts"])
                return sorted(p for p in set(draft_values) | set(after) if draft_values.get(p) != after.get(p)
                              and p not in ok)
            tries = [0]

            def check_apply(x: Any) -> list[str]:
                """The bundle check, then (c12 and pilot 1 run 2: the apply step rewrote a register map and every reset
                nobody had asked about) every field changed without an answer naming it goes back as a repair note,
                except on the last attempt, where what is left is only logged."""
                tries[0] += 1
                errs = self._check_bundle(x)
                if errs or tries[0] > MAX_REPAIRS - 1:     # the last repair is kept for checker errors (pilot 1 run 3)
                    return errs
                return [f"{p}: you changed this field, but no answer names it; put back the draft value "
                        f"{draft_values.get(p)!r} (change it only if an answer to another field forces it, and then say "
                        f"so under reasons)" for p in changed(x)]
            try:
                b2, apply_repairs = self._draft("pass2-apply", apply_prompt(b, answered), check_apply)
                unasked = changed(b2)
                b = b2
            except RuntimeError as e:
                # the draft stays (it passed the checker); every answer that could not be applied is kept as an open
                # assumption carrying the answer, so nothing the user said is lost or silently dropped
                apply_failed = str(e)
                apply_repairs = MAX_REPAIRS
                for q, _ in answered:
                    q.status, q.by = "defaulted", f"{q.by}, not applied"
                    q.default, q.answer = q.answer, q.answer
        final_values = values_by_path(b["design"], b["contracts"])
        assumptions = [{"q": q, "affects": p} for q, p in asked if q.status == "defaulted"]
        self._log("pass2_contracts.json", {
            "pass": "contracts", "budget": {k: v for k, v in self.budget.items() if k.startswith("contracts")},
            "drafter_repairs": {"draft": repairs, "apply": apply_repairs}, "apply_failed": apply_failed,
            "modules": sorted(b["contracts"]), "connections": b["design"].get("connections") or [],
            "fields": len(fields), "stated_in_spec": len(stated),
            **{k: v for k, v in iv.summary().items() if k != "questions"},
            "stated": [{"fields": f.paths, "quote": qt} for f, qt in stated],
            "bad_quotes": bad_quotes, "quotes_without_the_value": no_number,
            "questions": [{**asdict(q), "fields": p, "draft_value": draft_values.get(p[0]),
                           "final_value": final_values.get(p[0])} for q, p in asked],
            "unasked_changes": [{"field": p, "draft": draft_values.get(p), "final": final_values.get(p)}
                                for p in unasked]})
        return b, assumptions

    def run(self) -> dict[str, Any]:
        spec_text = (self.root / "system" / "spec.md").read_text()
        reqs, p1, a1 = self.pass1(spec_text)
        b, a2 = self.pass2(spec_text, reqs, p1)
        assumptions = [_assumption(n, x["q"], x["affects"]) for n, x in enumerate([*a1, *a2], 1)]
        write_bundle(self.root, b, assumptions)
        p = check_project(self.root)
        out = {"valid": not p.errors, "errors": p.errors, "warnings": p.warnings, "modules": p.modules(),
               "assumptions": len(assumptions), "notes": self.notes, "llm": self.drafter.calls.totals()}
        self._log("session.json", out)
        self._log("llm_calls.json", {"calls": self.drafter.calls.rows})
        return out


def _rmtree(p: Path) -> None:
    for f in sorted(p.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()
    p.rmdir()


# --- spec.yaml stays the stage 1 input: it must agree with the contract ------------------------------------------------

def spec_contract_errors(spec: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    """A module's ``spec.yaml`` (written by stage 0 clarify) against its approved contract: the same port names,
    directions and widths (parameter defaults applied), and the same register offsets, names and access. Empty list:
    they agree."""
    e: list[str] = []
    params = params_of(contract)
    cports = port_map(contract)
    sports = {p.get("name"): p for p in spec.get("ports") or [] if isinstance(p, dict) and p.get("name")}
    for n, p in cports.items():
        s = sports.get(n)
        if s is None:
            e.append(f"port {n}: in the contract, not in spec.yaml")
            continue
        if str(s.get("dir")) != str(p.get("dir")):
            e.append(f"port {n}: spec.yaml says dir {s.get('dir')}, the contract {p.get('dir')}")
        try:
            want = evaluate(p.get("width", 1), params)
        except ExprError:
            continue
        if int(s.get("width", 1)) != want:
            e.append(f"port {n}: spec.yaml says width {s.get('width', 1)}, the contract {want}")
    e += [f"port {n}: in spec.yaml, not in the contract" for n in sports if n not in cports]
    cregs = {r.get("offset"): r for r in ((contract.get("registers") or {}).get("map") or []) if isinstance(r, dict)}
    sregs = {}
    for r in ((spec.get("registers") or {}).get("map") or []) if isinstance(spec.get("registers"), dict) else []:
        if isinstance(r, dict):
            try:
                sregs[int(str(r.get("offset")), 0)] = r
            except ValueError:
                e.append(f"spec.yaml register {r.get('name')}: offset {r.get('offset')!r} is not a number")
    for off, r in cregs.items():
        s = sregs.get(off)
        if s is None:
            e.append(f"register {r.get('name')} at {off:#04x}: in the contract, not in spec.yaml")
        elif s.get("name") != r.get("name") or str(s.get("access", "")).upper() != str(r.get("access", "")).upper():
            e.append(f"register at {off:#04x}: spec.yaml says {s.get('name')} {s.get('access')}, the contract "
                     f"{r.get('name')} {r.get('access')}")
    e += [f"register {s.get('name')} at {off:#04x}: in spec.yaml, not in the contract" for off, s in sregs.items()
          if off not in cregs]
    return e


__all__ = ["BUDGET", "TIERS", "field_group", "field_tier", "plan_questions", "Calls", "Drafter", "Field", "Session", "Terminal", "contract_fields", "design_fields", "inventory",
           "oracle_llm", "quote_ok", "settled_by_spec", "spec_contract_errors", "values_by_path"]

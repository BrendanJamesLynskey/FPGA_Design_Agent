"""Permission modes of the agent (brief 222): what a run may do without asking.

Twelve named actions are gated. A *mode* is a preset over them (plan, ask, auto, full); *overrides* (allow or deny, one action each) sit on
top of a mode, like the allow and deny rules of a coding agent. Some things are never allowed in any mode (``NEVER``): those are code
checks, run before the mode is looked at, and no setting reaches them.

Where a decision is taken:

* the graph, at the start of every stage (``agent.graph.run``): the stage's actions are looked up, a ``deny`` stops the run with a plain
  reason, an ``ask`` pauses the run on a ``permission`` interrupt (the Navigator's question panel, or a headless stop with a list of what
  is needed); a ``allow`` goes on and is written to the run's decision log;
* every tool call (``agent.core.registry.dispatch`` calls :func:`tool_gate`): the never-list first, then the run's own policy file
  (``permissions.json`` in the run directory, which the graph writes and the Claude Code arm's tool server re-reads at each call), so a
  tool the model calls cannot do what the stage did not ask for;
* the command line (``--max-usd`` above the run's earlier cap on ``resume``): ``raise_budget``.

No model is involved anywhere in this module: it is plain code, so it is the same in every harness.

Records: ``<run>/permissions.json`` (the mode, the overrides, what the run was granted or refused) and ``<run>/permissions.jsonl`` (every
decision: when, which action, allowed, asked or denied, by whom or by which rule). ``summary.json`` and the handover list them.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.core.security import FLASH_WORDS, SecurityError

ALLOW, ASK, DENY = "allow", "ask", "deny"
VALUES = (ALLOW, ASK, DENY)
#: the mode a run has when nothing sets one. It is Auto: before brief 222 a run spent inside its budgets, ran Vivado and edited files without
#: asking, and always stopped for the owner before programming a board, which is what Auto means. The Navigator's picker starts at Ask.
DEFAULT_MODE = "auto"
MODE_ORDER = ("plan", "ask", "auto", "full")
#: the spend above which ``spend_model_money`` is asked (provider-reported or, for a plan run, the Meter's ceiling), in USD
DEFAULT_ASK_ABOVE_USD = 1.0
#: no run is ever given a cap above this (house rule: the FPGA share of the OpenRouter key is $35); a code check, not a setting
HARD_CAP_USD = 35.0
CONFIG_ENV = "FDA_PERMISSIONS_FILE"
STATE_FILE, LOG_FILE = "permissions.json", "permissions.jsonl"


# --- the gated actions --------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    name: str
    label: str
    plain: str                 # what saying yes means, in plain words
    board: bool = False        # touches a board or an instrument: asked at the stage-9 approval, not at the stage start


ACTIONS: tuple[Action, ...] = (
    Action("edit_design_files", "Edit design files",
           "Write or change the design's RTL, tests, constraints and scripts (from the RTL stage on). The spec and the architecture the first "
           "two stages write are the plan and are not gated."),
    Action("run_simulation", "Run simulation and checks",
           "Run the design's simulation, formal proofs, mutation tests and lint, and the open-source synthesis and equivalence checks. These run "
           "on this machine and change nothing outside the run."),
    Action("run_vivado", "Run Vivado synthesis and implementation",
           "Run Vivado builds (synthesis, place and route, bitstream) in a heavy slot. Takes minutes to hours and a large share of this machine's memory."),
    Action("spend_model_money", "Spend model money above the threshold",
           "Keep calling the model after the run has spent more than the threshold (default $1.00). Spending always stops at the run's budget cap."),
    Action("raise_budget", "Raise a budget",
           "Resume a run with a higher cost cap than it started with (--max-usd or --budget-scale). Never above the hard cap."),
    Action("approve_architecture", "Approve the architecture",
           "Accept the architecture of the first two stages as the plan the RTL is written from. Nothing is written before it is approved."),
    Action("approve_stage", "Approve each stage",
           "Pause for a person's decision at the end of every stage (approve, edit or rewind), as --review on does."),
    Action("program_board_sram", "Program the board (SRAM)",
           "Load the bitstream into the attached board's volatile SRAM over JTAG. Never flash. A power-up reverts the board.", board=True),
    Action("write_board_register", "Write a board register",
           "Run the design's bring-up, which writes the design's registers over the JTAG bus or the UART and so changes what the design is doing.", board=True),
    Action("drive_instrument_output", "Drive a lab instrument output",
           "Enable a signal generator, bench supply or other instrument output into the board, inside the lab file's safety limits (brief 221).", board=True),
    Action("read_board", "Read the board (read-only)",
           "The Navigator's read-only board actions: scan the cable, read the status registers and the sensor. Nothing is written or programmed.", board=True),
    Action("use_knowledge_bank", "Use the knowledge bank and IP library",
           "Read the private knowledge bank (skills, documents, IP library) the agent's advice comes from. In this version it is read from a local clone "
           "through the access key; the permission is also the switch for any remote fetch."),
)
ACTION_NAMES = tuple(a.name for a in ACTIONS)
BY_NAME = {a.name: a for a in ACTIONS}
BOARD_ACTIONS = tuple(a.name for a in ACTIONS if a.board)
#: the board actions the stage-9 hardware approval covers: it grants these together
HW_APPROVAL_ACTIONS = ("program_board_sram", "write_board_register")


def _preset(**kw: str) -> dict[str, str]:
    missing = set(ACTION_NAMES) - set(kw)
    assert not missing, missing
    return {k: kw[k] for k in ACTION_NAMES}


MODES: dict[str, dict[str, Any]] = {
    "plan": {"label": "Plan", "plain": "Read and plan only. The interview and the architecture run, with an estimate of time and cost; no files are "
             "changed outside the plan, no simulation or build runs, and the board is not touched. The run stops with the architecture waiting for you.",
             "actions": _preset(edit_design_files=DENY, run_simulation=DENY, run_vivado=DENY, spend_model_money=DENY, raise_budget=DENY, approve_architecture=DENY,
                                approve_stage=ALLOW, program_board_sram=DENY, write_board_register=DENY, drive_instrument_output=DENY, read_board=DENY,
                                use_knowledge_bank=ALLOW)},
    "ask": {"label": "Ask", "plain": "The default for new users. The agent runs simulation and checks itself and asks before every other gated action.",
            "actions": _preset(edit_design_files=ASK, run_simulation=ALLOW, run_vivado=ASK, spend_model_money=ASK, raise_budget=ASK, approve_architecture=ASK,
                               approve_stage=ASK, program_board_sram=ASK, write_board_register=ASK, drive_instrument_output=ASK, read_board=ASK,
                               use_knowledge_bank=ASK)},
    "auto": {"label": "Auto within limits", "plain": "Edits, builds, Vivado and model spend run without asking, inside the run's budgets. The agent still asks "
             "before programming a board, writing registers, driving an instrument or raising a budget.",
             "actions": _preset(edit_design_files=ALLOW, run_simulation=ALLOW, run_vivado=ALLOW, spend_model_money=ALLOW, raise_budget=ASK, approve_architecture=ALLOW,
                                approve_stage=ALLOW, program_board_sram=ASK, write_board_register=ASK, drive_instrument_output=ASK, read_board=ALLOW,
                                use_knowledge_bank=ALLOW)},
    "full": {"label": "Full auto", "plain": "Also programs SRAM, writes registers and drives instruments, inside the lab file's safety limits, and stops at the "
             "budget caps. Only for a board and a bench you are watching: nothing asks you first.",
             "actions": _preset(edit_design_files=ALLOW, run_simulation=ALLOW, run_vivado=ALLOW, spend_model_money=ALLOW, raise_budget=DENY, approve_architecture=ALLOW,
                                approve_stage=ALLOW, program_board_sram=ALLOW, write_board_register=ALLOW, drive_instrument_output=ALLOW, read_board=ALLOW,
                                use_knowledge_bank=ALLOW)},
}
assert tuple(MODES) == MODE_ORDER


# --- what is never allowed ------------------------------------------------------------------------------------------------------

EFUSE_WORDS = re.compile(r"e-?fuse|bbram|program_hw_efuse|write_bbram|\.nky\b|aes[_ ]?key|key[_ ]?(program|load|write)|program[_ ]?(the )?keys?|set_property[^\n]*\b(bbram|efuse|aes)", re.I)
BOOT_WORDS = re.compile(r"boot\.bin|\.bif\b|boot[_ ]?image|\.pof\b|\.jic\b|write_bitstream[^\n]*-(bin|mcs)|emmc|\bmmcblk|\bdd\s+if=", re.I)
LASER_WORDS = re.compile(r"laser", re.I)
LASER_ON = re.compile(r"enable|on\b|true|1\b|emit|tx[_ ]?(enable|disable\s*=\s*0)|disable\s*=\s*0|safe[_ ]?off\s*=\s*0", re.I)
#: Red Pitaya OS (brief 225): the board's SD card, its OS image, its updater and its factory SCPI server are the owner's. A custom bitstream is loaded into the
#: volatile PL configuration only (overlay.sh or fpgautil, which this does not match); nothing that writes the card, the boot files or the OS, or that turns the
#: factory SCPI server on, is ever run by the agent. Matched in a board or instrument tool's arguments and in a script about to run on a board.
REDPITAYA_OS_WORDS = re.compile(
    r"ecosystem[-_ ]?(update|upgrade|install)|\bupdateutil\b|\bupdate[-_ ]?(os|ecosystem)\b|redpitaya[-_ ]?(os|ubuntu)[-_ ]?(image|update)|\bapt(-get)?\s+(dist-)?upgrade"
    r"|(>|>>|\btee\b)\s*/opt/redpitaya/|\b(rm|mv|cp|sed\s+-i)\b[^\n]*/opt/redpitaya/|\bmount\b[^\n]*(mmcblk|/dev/sd)|/media/[^\s/]+/(boot|rootfs)"
    r"|\bfsbl\b[^\n]*(write|copy|flash)|u-boot\.(img|scr)|uImage\b|\bdevicetree\.dtb\b|\bsync;?\s*umount\b"
    r"|scpi[-_ ]?server[^\n]*(start|enable)|(start|enable)[^\n]*scpi[-_ ]?server|systemctl\s+(enable|start|restart)\s+redpitaya_scpi|\bscpi\.sh\s+start",
    re.I)
LAB_TOOLS = frozenset({"drive_instrument", "instrument_output", "lab_output", "set_instrument_output"})     # brief 221 registers its own through register_tool_action; brief 225's addendum: drive_instrument calls check_drive


@dataclass(frozen=True)
class NeverRule:
    id: str
    text: str


NEVER: tuple[NeverRule, ...] = (
    NeverRule("flash", "Write flash, configuration memory (QSPI, .pof, .mcs), an SD card or eMMC."),
    NeverRule("boot_image", "Write a boot image (BOOT.BIN, a .bif image, a .jic file)."),
    NeverRule("efuse_bbram", "Program eFUSE or BBRAM: irreversible."),
    NeverRule("keys", "Program or load a key into a device."),
    NeverRule("laser", "Enable a laser anywhere except the design's own checked bring-up step."),
    NeverRule("lab_limits", "Drive an instrument output beyond the lab file's safety limits, or enable an output the lab file lists as never enabled by a script."),
    NeverRule("redpitaya_os", "Change the Red Pitaya's SD card, boot files or OS image, run its OS updater, or turn on its factory SCPI server (a custom bitstream goes into the volatile PL configuration only)."),
    NeverRule("hard_cap", f"Spend past the hard cap: no run may be given a cost cap above ${HARD_CAP_USD:g}."),
)
NEVER_BY_ID = {r.id: r for r in NEVER}


class NeverRefused(SecurityError):
    """A never-rule fired. It is a SecurityError so every tool path already refuses it without a crash."""

    def __init__(self, rule: str, why: str):
        super().__init__("hardware-flash" if rule == "flash" else f"never-{rule}", f"refused, never allowed in any mode: {why}")     # "hardware-flash" is the rule name the program tool has always used
        self.never = rule


BOARD_TOOLS = frozenset({"program", "bringup", "debug_capture", "axi_board_run", "eye_scan"})


def lab_drive_violation(args: dict[str, Any] | None, design: Any = None) -> str | None:
    """The reason a drive request breaks the lab file's limits, else None. Brief 225's addendum: this is where brief 222's ``lab_limits`` never-rule calls
    :func:`hil.lab.check_drive` (brief 221), over the lab merged for ``design`` (the owner's profile and the design's own lab file). A request that
    names no instrument and output, an instrument the lab does not list, one that is not onboarded, an output that is never enabled by a script, a value
    above a limit, or a value the output needs and the call does not state, is refused: nothing is assumed free."""
    from hil import lab as L
    a = args or {}
    iid, out = str(a.get("instrument") or ""), str(a.get("output") or "")
    if not iid or not out:
        return "a drive request names its instrument and its output; this one does not, so no limit can be checked"
    num = {}
    for k in ("volts", "amps", "dbm", "hz", "attenuator_db", "board_vcco_v"):
        v = a.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            return f"{k} is not a number ({v!r})"
        num[k] = v
    try:
        lab = L.load(Path(design) if design else None)
        L.check_drive(lab, iid, out, **num)
    except L.LabError as e:
        return str(e)
    return None


def never_violation(tool: str, args: dict[str, Any] | None, stage: str | None = None, design: Any = None) -> tuple[str, str] | None:
    """(rule id, reason) when this tool call would break a never-rule, else None. Pure code over the call; it does not read a mode.

    Scanned: the target of ``program``; the path of a file the agent writes (never a boot image, flash image or key file); and, for every tool that
    touches a board or an instrument, the whole argument text for flash, boot-image, eFUSE, BBRAM and key words, and for a laser being enabled by
    anything other than the design's own bring-up step. File contents and the arguments of the simulation tools are not scanned: an AES core's RTL
    may say ``key`` and a test may say ``flash``."""
    a = args or {}
    if tool == "program" and (a.get("target", "sram") != "sram" or FLASH_WORDS.search(str(a.get("target", "")))):
        return "flash", "only the volatile SRAM is programmed; flash and configuration memory are not available to the agent"
    if tool == "write_file":
        path = str(a.get("path", ""))
        if BOOT_WORDS.search(path):
            return "boot_image", f"the agent does not write a boot image ({path!r})"
        if re.search(r"\.(mcs|pof|jic|nky)$", path, re.I):
            return ("keys" if path.lower().endswith(".nky") else "flash"), f"the agent does not write {path!r}"
        if REDPITAYA_OS_WORDS.search(path):
            return "redpitaya_os", f"the agent does not write the Red Pitaya's boot or OS files ({path!r})"
        return None
    if tool in BOARD_TOOLS or tool in LAB_TOOLS or tool in _EXTRA_TOOL_ACTIONS:
        text = json.dumps(a, default=str)
        m = EFUSE_WORDS.search(text)
        if m:
            return ("keys" if re.search(r"key|nky", m.group(0), re.I) else "efuse_bbram"), f"the call names {m.group(0)!r}"
        m = re.search(r"write_cfgmem|program_hw_cfgmem|\bcfgmem\b|\.mcs\b|\.pof\b|\.jic\b|\bqspi\b|\bflash\b", text, re.I)
        if m:
            return "flash", f"the call names {m.group(0)!r} (configuration memory)"
        m = BOOT_WORDS.search(text)
        if m:
            return "boot_image", f"the call names {m.group(0)!r}"
        m = REDPITAYA_OS_WORDS.search(text)
        if m:
            return "redpitaya_os", f"the call names {m.group(0)!r} (the Red Pitaya's SD card, OS or factory SCPI server)"
        if tool != "bringup" and LASER_WORDS.search(text) and LASER_ON.search(text):
            return "laser", "a laser is enabled only inside the design's own checked bring-up step"
        if tool in LAB_TOOLS:                                  # brief 225: the lab file's limits, by hil.lab.check_drive, whatever the mode
            why = lab_drive_violation(a, design)
            if why:
                return "lab_limits", why
    return None


def check_script(text: str) -> tuple[str, str] | None:
    """The same never-rules over a script (a Tcl or Python file about to run on a board): flash, boot images, eFUSE, BBRAM, keys."""
    for rule, rx, why in (("flash", re.compile(r"write_cfgmem|program_hw_cfgmem|\bcfgmem\b|\.mcs\b|\.pof\b|\.jic\b|flash|qspi", re.I), "configuration memory"),
                          ("boot_image", BOOT_WORDS, "a boot image"), ("efuse_bbram", EFUSE_WORDS, "eFUSE, BBRAM or a key"),
                          ("redpitaya_os", REDPITAYA_OS_WORDS, "the Red Pitaya's SD card, OS or factory SCPI server")):
        m = rx.search(text)
        if m:
            return rule, f"the script names {m.group(0)!r} ({why})"
    return None


def lab_limits_violation(request: dict[str, Any], limits: dict[str, Any]) -> str | None:
    """A lab output request against the lab file's limits (brief 221 calls this before any output is enabled).

    ``request``: ``output`` (name), ``voltage_v``, ``current_a``, ``power_w``, ``frequency_hz``, ``dbm``. ``limits``: ``max_voltage_v``,
    ``max_current_a``, ``max_power_w``, ``max_frequency_hz``, ``max_dbm`` and ``never_enable`` (a list of output names). A limit that is
    missing is a limit of zero for that quantity: an output with no stated limit is refused, never assumed free. Returns the reason, or None."""
    out = str(request.get("output", ""))
    if out in (limits.get("never_enable") or []):
        return f"the lab file lists output {out!r} as never enabled by a script"
    for q, lim in (("voltage_v", "max_voltage_v"), ("current_a", "max_current_a"), ("power_w", "max_power_w"), ("frequency_hz", "max_frequency_hz"), ("dbm", "max_dbm")):
        if q in request and request[q] is not None:
            try:
                v, mx = float(request[q]), float(limits.get(lim, 0.0))
            except (TypeError, ValueError):
                return f"{q} is not a number"
            if v > mx:
                return f"{q} {v:g} is above the lab file's {lim} {mx:g}" + ("" if lim in limits else " (the lab file states no limit, so none is assumed)")
    return None


def check_hard_cap(usd: float | None) -> str | None:
    if usd is not None and usd > HARD_CAP_USD:
        return f"a cost cap of ${usd:g} is above the hard cap of ${HARD_CAP_USD:g}; no mode allows it"
    return None


def never_check(tool: str, args: dict[str, Any] | None, stage: str | None = None, design: Any = None) -> None:
    v = never_violation(tool, args, stage, design)
    if v:
        raise NeverRefused(*v)


# --- which tools need which actions -----------------------------------------------------------------------------------------------

SIM_TOOLS = ("simulate", "formal", "mutate", "lint", "axi_simulate", "oss_synth", "eqy_check")
VIVADO_TOOLS = ("build", "rw_route", "rw_place_chain", "rw_relocate_block", "rw_referee")
KNOWLEDGE_TOOLS = ("search_docs", "load_skill", "skill_index", "skill_excerpt", "board_constraints", "ip_lookup")
_EXTRA_TOOL_ACTIONS: dict[str, tuple[str, ...]] = {"drive_instrument": ("drive_instrument_output",)}      # brief 225: the lab tool, gated before its module is imported


def register_tool_action(tool: str, *actions: str) -> None:
    """Brief 221 (and any later tool) names the actions a tool needs here, so a new tool is gated without editing this module."""
    bad = [a for a in actions if a not in BY_NAME]
    if bad:
        raise ValueError(f"unknown permission action(s) {bad}; the names are {', '.join(ACTION_NAMES)}")
    _EXTRA_TOOL_ACTIONS[tool] = tuple(actions)


def stage_index(name: str | None) -> int:
    from agent.core.session import STAGES
    return STAGES.index(name) if name in STAGES else 0


def tool_actions(tool: str, args: dict[str, Any] | None = None, stage: str | None = None) -> tuple[str, ...]:
    """The actions a tool call needs. Reading and listing the design are never gated; writing a file is gated from the RTL stage on."""
    if tool in _EXTRA_TOOL_ACTIONS:
        return _EXTRA_TOOL_ACTIONS[tool]
    if tool == "write_file":
        return ("edit_design_files",) if stage_index(stage) >= 2 else ()
    if tool in SIM_TOOLS:
        return ("run_simulation",)
    if tool in VIVADO_TOOLS:
        return ("run_vivado",)
    if tool == "program":
        return ("program_board_sram",)
    if tool in ("bringup", "axi_board_run"):
        return ("program_board_sram", "write_board_register")
    if tool == "debug_capture":
        return ("program_board_sram", "read_board")
    if tool in KNOWLEDGE_TOOLS:
        return ("use_knowledge_bank",)
    return ()


def stage_actions(n: int, tools: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The actions the graph itself and the stage's agent need at stage ``n``. The graph runs the stage's own gates (simulation in stage 2, Vivado
    from stage 2 on, for the synthesis its gate runs), so those are counted here and not only through the tools the model may call."""
    acts = ["use_knowledge_bank"]
    if n >= 2:
        acts.append("edit_design_files")
    if n == 2:
        acts.append("run_simulation")
    if n >= 2:                                   # stage 2 too: once lint and simulation pass, its gate runs the synthesis (found by the first Ask-mode run, brief 222)
        acts.append("run_vivado")
    if n == 9:
        acts += list(HW_APPROVAL_ACTIONS)
    for t in tools:
        for a in tool_actions(t, None, None if n < 2 else "rtl-design-creation"):
            if a not in acts:
                acts.append(a)
    return tuple(dict.fromkeys(acts))


# --- the policy ---------------------------------------------------------------------------------------------------------------------

def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Decision:
    action: str
    result: str                 # allow | ask | deny
    by: str                     # the mode or rule or person that decided it, in words


class Policy:
    """A run's permissions: a mode, overrides, and what the run has been granted or refused so far. Plain data; ``save`` and ``load`` keep it in the run directory."""

    def __init__(self, mode: str = DEFAULT_MODE, overrides: dict[str, str] | None = None, source: str = f"default ({DEFAULT_MODE}: the behaviour before brief 222)", ask_above_usd: float = DEFAULT_ASK_ABOVE_USD,
                 run_dir: Path | None = None):
        if mode not in MODES:
            raise ValueError(f"unknown permission mode {mode!r}; the modes are {', '.join(MODE_ORDER)}")
        self.mode, self.source = mode, source
        self.overrides: dict[str, str] = {}
        for k, v in (overrides or {}).items():
            self.set_override(k, v)
        self.ask_above_usd = float(ask_above_usd)
        self.run_dir = Path(run_dir) if run_dir else None
        self.granted: dict[str, dict[str, Any]] = {}
        self.refused: dict[str, dict[str, Any]] = {}
        self.history: list[dict[str, Any]] = []        # mode changes on resume

    # -- construction ----------------------------------------------------------------------------------------------------------
    def set_override(self, action: str, value: str) -> None:
        if action not in BY_NAME:
            raise ValueError(f"unknown permission action {action!r}; the actions are {', '.join(ACTION_NAMES)}")
        if value not in VALUES:
            raise ValueError(f"permission value for {action} must be one of {', '.join(VALUES)}, not {value!r}")
        self.overrides[action] = value

    def spec(self) -> dict[str, Any]:
        return {"mode": self.mode, "overrides": dict(self.overrides), "source": self.source, "ask_above_usd": self.ask_above_usd}

    @classmethod
    def from_spec(cls, spec: dict[str, Any] | None, run_dir: Path | None = None) -> "Policy":
        s = dict(spec or {})
        return cls(s.get("mode") or DEFAULT_MODE, s.get("overrides"), s.get("source") or f"default ({DEFAULT_MODE}: the behaviour before brief 222)", s.get("ask_above_usd", DEFAULT_ASK_ABOVE_USD), run_dir)

    # -- deciding -------------------------------------------------------------------------------------------------------------
    def base(self, action: str) -> tuple[str, str]:
        """(value, rule): the override if there is one, else the mode's preset."""
        if action not in BY_NAME:
            raise ValueError(f"unknown permission action {action!r}")
        if action in self.overrides:
            return self.overrides[action], f"override {self.overrides[action]} {action} ({self.source})"
        return MODES[self.mode]["actions"][action], f"mode {self.mode}"

    def decide(self, action: str, stage: int | str | None = None, detail: str = "", log: bool = True) -> Decision:
        """The value now: a refusal the run was given, then a grant the run was given, then the override or preset. An override of ``deny`` is
        never lifted by a grant: a person who denied an action in the settings is not asked about it."""
        value, rule = self.base(action)
        if action in self.refused:
            d = Decision(action, DENY, f"refused by {self.refused[action]['by']} at {self.refused[action]['when']}")
        elif value == DENY:
            d = Decision(action, DENY, rule)
        elif action in self.granted:
            d = Decision(action, ALLOW, f"granted by {self.granted[action]['by']} at {self.granted[action]['when']}")
        else:
            d = Decision(action, value, rule)
        if log:
            self.record(d, stage, detail)
        return d

    def record(self, d: Decision, stage: int | str | None = None, detail: str = "", result: str | None = None) -> None:
        if self.run_dir is None:
            return
        row = {"when": now_text(), "action": d.action, "result": {ALLOW: "allowed", ASK: "asked", DENY: "denied"}[d.result] if result is None else result,
               "by": d.by, "stage": stage, "detail": detail[:200], "mode": self.mode}
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            if row["result"] == "asked":                          # the graph re-runs a node when it resumes from a question: one "asked" row per question
                last = [r for r in self.decisions() if r.get("action") == d.action]
                if last and last[-1].get("result") == "asked" and last[-1].get("stage") == stage:
                    return
            with (self.run_dir / LOG_FILE).open("a") as f:
                f.write(json.dumps(row) + "\n")
        except OSError:
            pass

    def grant(self, actions: list[str] | tuple[str, ...], by: str, stage: int | str | None = None, detail: str = "") -> None:
        for a in actions:
            self.granted[a] = {"by": by, "when": now_text(), "stage": stage}
            self.refused.pop(a, None)
            self.record(Decision(a, ALLOW, f"granted by {by}"), stage, detail, result="granted")
        self.save()

    def refuse(self, actions: list[str] | tuple[str, ...], by: str, stage: int | str | None = None, detail: str = "") -> None:
        for a in actions:
            self.refused[a] = {"by": by, "when": now_text(), "stage": stage}
            self.granted.pop(a, None)
            self.record(Decision(a, DENY, f"refused by {by}"), stage, detail, result="refused")
        self.save()

    def hw_by_rule(self) -> bool:
        """True when the stage-9 hardware approval needs no person: every action it covers is allowed (by the mode, an override or a grant)."""
        return all(self.decide(a, 9, "stage-9 hardware approval", log=False).result == ALLOW for a in HW_APPROVAL_ACTIONS)

    def review_required(self, n: int) -> bool:
        """Does a person decide at the end of stage ``n``? ``approve_stage`` ask (every stage) or ``approve_architecture`` ask (stage 1)."""
        if self.decide("approve_stage", n, log=False).result == ASK:
            return True
        return n == 1 and self.decide("approve_architecture", n, log=False).result == ASK

    # -- keeping it ------------------------------------------------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        return {**self.spec(), "granted": self.granted, "refused": self.refused, "history": self.history}

    def save(self) -> None:
        if self.run_dir is None:
            return
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.run_dir / (STATE_FILE + ".tmp")
            tmp.write_text(json.dumps(self.state(), indent=1))
            tmp.replace(self.run_dir / STATE_FILE)
        except OSError:
            pass

    @classmethod
    def load(cls, run_dir: Path) -> "Policy | None":
        try:
            d = json.loads((Path(run_dir) / STATE_FILE).read_text())
            p = cls.from_spec(d, Path(run_dir))
        except (OSError, ValueError, TypeError, AttributeError):
            return None
        p.granted = {k: v for k, v in (d.get("granted") or {}).items() if k in BY_NAME and isinstance(v, dict)}
        p.refused = {k: v for k, v in (d.get("refused") or {}).items() if k in BY_NAME and isinstance(v, dict)}
        p.history = list(d.get("history") or [])
        return p

    def change_mode(self, spec: dict[str, Any]) -> None:
        """A resume with another mode on the command line: the new mode and overrides replace the old, and what was granted or refused under the old is dropped."""
        new = Policy.from_spec(spec, self.run_dir)
        if (new.mode, new.overrides, new.ask_above_usd) != (self.mode, self.overrides, self.ask_above_usd):
            self.history.append({"when": now_text(), "from": self.mode, "to": new.mode, "overrides": dict(new.overrides), "by": new.source})
            self.mode, self.overrides, self.source, self.ask_above_usd = new.mode, new.overrides, new.source, new.ask_above_usd
            self.granted, self.refused = {}, {}
            self.save()

    def decisions(self) -> list[dict[str, Any]]:
        """Every decision in the log, in order, from the run directory."""
        if self.run_dir is None:
            return []
        try:
            return [json.loads(ln) for ln in (self.run_dir / LOG_FILE).read_text().splitlines() if ln.strip()]
        except (OSError, ValueError):
            return []


def summarise(run_dir: Path, policy: Policy | None) -> dict[str, Any] | None:
    """The block ``summary.json`` and the handover carry: the mode, where it came from, and every distinct decision (first and last time seen)."""
    if policy is None:
        return None
    seen: dict[tuple, dict[str, Any]] = {}
    for d in policy.decisions():
        k = (d.get("action"), d.get("result"), d.get("by"), d.get("stage"))
        if k in seen:
            seen[k]["last"], seen[k]["count"] = d.get("when"), seen[k]["count"] + 1
        else:
            seen[k] = {"action": d.get("action"), "result": d.get("result"), "by": d.get("by"), "stage": d.get("stage"), "first": d.get("when"), "last": d.get("when"), "count": 1}
    return {"mode": policy.mode, "source": policy.source, "overrides": dict(policy.overrides), "ask_above_usd": policy.ask_above_usd, "mode_changes": list(policy.history),
            "granted": {k: v.get("by") for k, v in policy.granted.items()}, "refused": {k: v.get("by") for k, v in policy.refused.items()}, "decisions": list(seen.values())[:60]}


# --- the tool gate ------------------------------------------------------------------------------------------------------------------

def tool_gate(session: Any, name: str, args: dict[str, Any] | None) -> None:
    """Called by ``registry.dispatch`` before every tool runs. The never-rules always; then, when the session belongs to a run with a policy
    file, each action the tool needs. An ``ask`` the run has not been granted refuses the call with the reason (the graph asks at the start of
    the stage, so a tool call that arrives ungranted is the model reaching past it). Raises SecurityError, never crashes."""
    never_check(name, args, getattr(session, "stage", None), getattr(session, "design", None))
    rd = getattr(session, "permissions_run_dir", None)
    if not rd:
        return
    pol = Policy.load(Path(rd))
    if pol is None:
        return
    for a in tool_actions(name, args, getattr(session, "stage", None)):
        d = pol.decide(a, getattr(session, "stage", None), f"tool {name}", log=False)
        if d.result == ALLOW:
            continue
        pol.record(d, getattr(session, "stage", None), f"tool {name} refused", result="refused-at-tool")
        if d.result == DENY:
            raise SecurityError("permission-denied", f"{name} needs the permission {a} ({BY_NAME[a].label}), which is denied ({d.by}); "
                                                     f"the run's mode is {pol.mode}. Do not retry: pick work that does not need it.")
        raise SecurityError("permission-not-granted", f"{name} needs the permission {a} ({BY_NAME[a].label}), which has not been granted in mode {pol.mode}. "
                                                      "The run asks for the permissions a stage needs when the stage starts; do not retry.")


# --- configuration: the command line and the config file ------------------------------------------------------------------------------

def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV) or Path.home() / ".config" / "fpga_design_agent" / "permissions.yaml")


def load_config(path: Path | None = None) -> dict[str, Any]:
    import yaml
    p = Path(path) if path else config_path()
    try:
        d = yaml.safe_load(p.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return d if isinstance(d, dict) else {}


def _clean(entry: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(entry, dict):
        return out
    if entry.get("mode") in MODES:
        out["mode"] = entry["mode"]
    ov = entry.get("overrides")
    if isinstance(ov, dict):
        out["overrides"] = {k: v for k, v in ov.items() if k in BY_NAME and v in VALUES}
    if isinstance(entry.get("ask_above_usd"), (int, float)) and not isinstance(entry.get("ask_above_usd"), bool) and entry["ask_above_usd"] >= 0:
        out["ask_above_usd"] = float(entry["ask_above_usd"])
    return out


def resolve(cli_mode: str | None = None, cli_allow: list[str] | None = None, cli_deny: list[str] | None = None, cli_ask_above: float | None = None,
            project: str | None = None, config: dict[str, Any] | None = None, config_file: Path | None = None, cli_ask: list[str] | None = None) -> dict[str, Any]:
    """The spec of a run's policy: the command line wins over the config file's project entry, which wins over its default entry, which wins over
    the built-in default. Raises ValueError for a name that is not an action or a mode."""
    cfg = load_config(config_file) if config is None else config
    where = str(config_file or config_path())
    mode, src, ov, ask_above = DEFAULT_MODE, f"default ({DEFAULT_MODE}: the behaviour before brief 222)", {}, DEFAULT_ASK_ABOVE_USD
    base = _clean(cfg)
    if base.get("mode"):
        mode, src = base["mode"], f"config file {where}"
    ov.update(base.get("overrides") or {})
    ask_above = base.get("ask_above_usd", ask_above)
    proj = _clean((cfg.get("projects") or {}).get(project)) if project and isinstance(cfg.get("projects"), dict) else {}
    if proj.get("mode"):
        mode, src = proj["mode"], f"config file {where}, project {project}"
    ov.update(proj.get("overrides") or {})
    ask_above = proj.get("ask_above_usd", ask_above)
    if cli_mode:
        if cli_mode not in MODES:
            raise ValueError(f"unknown permission mode {cli_mode!r}; the modes are {', '.join(MODE_ORDER)}")
        mode, src = cli_mode, "command line"
    for names, val in ((cli_ask or [], ASK), (cli_allow or [], ALLOW), (cli_deny or [], DENY)):
        for n in names:
            if n not in BY_NAME:
                raise ValueError(f"unknown permission action {n!r}; the actions are {', '.join(ACTION_NAMES)}")
            ov[n] = val
    if cli_ask_above is not None:
        if cli_ask_above < 0:
            raise ValueError("--ask-above-usd must be zero or more")
        ask_above = float(cli_ask_above)
    if (cli_allow or cli_deny or cli_ask) and not cli_mode:
        src += " + command-line overrides"
    return {"mode": mode, "overrides": ov, "source": src, "ask_above_usd": ask_above}


def save_config(project: str | None, mode: str, overrides: dict[str, str], ask_above_usd: float | None = None, path: Path | None = None) -> Path:
    """Write one entry of the config file (the project's, or the default when ``project`` is None), keeping the others. The Navigator's settings panel calls this."""
    import yaml
    if mode not in MODES:
        raise ValueError(f"unknown permission mode {mode!r}")
    ov = {}
    for k, v in (overrides or {}).items():
        if k not in BY_NAME or v not in VALUES:
            raise ValueError(f"bad override {k}={v}")
        if v != MODES[mode]["actions"][k]:                     # only a real difference from the mode is kept
            ov[k] = v
    entry: dict[str, Any] = {"mode": mode, **({"overrides": ov} if ov else {}), **({"ask_above_usd": float(ask_above_usd)} if ask_above_usd is not None else {})}
    p = Path(path) if path else config_path()
    cfg = load_config(p)
    if project:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", project):
            raise ValueError("a project name is letters, digits, dot, dash and underscore")
        cfg.setdefault("projects", {})
        cfg["projects"][project] = entry
    else:
        cfg.update(entry)
        if not ov:
            cfg.pop("overrides", None)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False))
    tmp.replace(p)
    return p


def plan_estimate(run_limits: dict[str, float], stages: Any, stop_after: int | None = None) -> dict[str, Any]:
    """An upper bound on the time and cost of a full run, from the stage limits (turns, seconds, USD per visit) and the run's own caps. These are
    the limits the Meter enforces, not a prediction: a stage ends early when its gates pass, and a repair visit can run a stage again (up to
    ``visits_per_stage`` times). Nothing here is measured, and it is labelled so."""
    rows, tot_s, tot_usd = [], 0.0, 0.0
    for st in stages:
        if stop_after is not None and st.n > stop_after:
            break
        s, u = float(st.limits.get("seconds", 0)), float(st.limits.get("usd", 0))
        rows.append({"stage": st.n, "name": st.name, "seconds_per_visit": s, "usd_per_visit": u})
        tot_s, tot_usd = tot_s + s, tot_usd + u
    visits = int(run_limits.get("visits_per_stage", 1))
    cap_s, cap_usd = float(run_limits.get("seconds", tot_s)), float(run_limits.get("usd", tot_usd))
    return {"stages": rows, "one_visit_each": {"hours": round(tot_s / 3600, 2), "usd": round(tot_usd, 2)},
            "run_caps": {"hours": round(cap_s / 3600, 2), "usd": round(cap_usd, 2), "visits_per_stage": visits},
            "upper_bound": {"hours": round(min(cap_s, tot_s * visits) / 3600, 2), "usd": round(min(cap_usd, tot_usd * visits), 2)},
            "note": "limits the run enforces, not a prediction: stages normally end well inside them (see the measured runs in docs/agent.md), and Claude Code runs on the plan report no bill"}


def view(policy: Policy | None = None) -> dict[str, Any]:
    """Everything the Navigator's panel shows: the actions, each mode's value for each, the never-list, and (with a policy) the effective values."""
    return {"actions": [{"name": a.name, "label": a.label, "plain": a.plain, "board": a.board,
                         "modes": {m: MODES[m]["actions"][a.name] for m in MODE_ORDER}} for a in ACTIONS],
            "modes": [{"name": m, "label": MODES[m]["label"], "plain": MODES[m]["plain"]} for m in MODE_ORDER],
            "never": [{"id": r.id, "rule": r.text} for r in NEVER], "default_mode": DEFAULT_MODE, "navigator_default_mode": "ask",
            "ask_above_usd": DEFAULT_ASK_ABOVE_USD, "hard_cap_usd": HARD_CAP_USD}

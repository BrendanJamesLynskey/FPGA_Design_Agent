"""How strict the spec interview is about unanswered questions (brief 210).

``--interview`` says **who answers** a question (a person, the oracle, nobody). ``--requirements`` says **what may be left
unanswered**:

- ``loose``: every gap is filled with the proposed default and recorded (the behaviour before brief 210);
- ``standard``: ``low`` and ``medium`` questions may be defaulted; a ``high`` question must be answered or explicitly waived,
  else the run stops at the clarify stage with a list of what is needed (exit status 3, not a crash);
- ``strict``: every question must be answered or explicitly waived. A waiver is a recorded user decision (the question, the
  chosen value, who, when, why). There are no silent defaults.

Each question has a **risk class**:

- ``high``: it changes behaviour, board safety or an interface someone else builds against (clocks, pins and I/O standards,
  resets, protocols and handshakes, number formats, rates and latency, register maps, anything an external device sees);
- ``medium``: it changes quality of result or cost, not function (resource budget, pipeline depth, buffer depth);
- ``low``: cosmetic or easily changed (names, comments, ordering) or a choice of verification method.

The class comes from the Clarifier when it sets one (``risk`` and ``risk_reason`` on an open question) and from the code rules
below; the **higher** of the two counts, so the Clarifier can raise a class and a rule can never be talked down. The Clarifier's
prompt does not yet ask for a class (prompts are pinned in the private knowledge repository), so today the rules decide.

No model is called here: the rules, the levels, the waivers and the stop are tested without one.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

LEVELS = ("loose", "standard", "strict")
RISKS = ("low", "medium", "high")
RANK = {r: i for i, r in enumerate(RISKS)}
EXIT_REQUIREMENTS = 3                 # exit status of a run that stopped because requirements are unresolved (not a crash: 1; usage: 2)
STOP_PREFIX = "requirements:"
NEEDED_FILE = "REQUIREMENTS_NEEDED.md"
WAIVERS_FILE = "requirements_waivers.yaml"
#: verification profiles (brief 194) that imply at least ``standard``; production_secure (brief 196) does too
DEFAULT_LEVEL = "loose"            # for a run nobody answers; see default_level and docs/agent.md
STANDARD_PROFILES = ("thorough", "ip_release", "high_dependability")
MIN_WHY = 8                           # characters: "ok" is not a reason


# ---- the risk class -------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    id: str
    risk: str
    rx: re.Pattern
    why: str


def _r(i: str, risk: str, rx: str, why: str) -> Rule:
    return Rule(i, risk, re.compile(rx, re.I), why)


#: ordered: the first rule that matches decides, so the lower classes come first only where they are exact (a proof-method question)
RULES: tuple[Rule, ...] = (
    _r("verification-method", "low", r"\bproof method|\bwhich (?:verification|test) method", "a choice of verification method, not of behaviour"),
    _r("clock", "high", r"\bclocks?\b|\bclk\w*|\bMHz\b|\bGHz\b|\bPLL\b|\bMMCM\b|\boscillator\b|\bfrequenc\w+|\bclock source",
       "a clock frequency or source changes timing and every rate derived from it"),
    _r("pins-and-io", "high", r"\bpins?\b|\bI/?O standards?\b|\bIOSTANDARD\b|\bLVCMOS\w*|\bLVDS\b|\bdrive strength|\bconnect to\b|\bpull(?:ed)?[- ]?(?:up|down)\b|"
       r"\bpush-pull\b|\bopen-drain\b|\bvoltage\b|\bVadj\b|\btermination\b|\bseries (?:resistor|R)\b|\bpinout\b",
       "a pin or I/O standard decides what the board sees; a wrong one can damage a part"),
    _r("reset", "high", r"\bresets?\b|\bactive[- ](?:high|low)\b|\bpolarity\b", "reset polarity and style decide the start-up state and the interface"),
    _r("external-device", "high", r"\btransceivers?\b|\bGT[HYXP]\b|\blaser\b|\boptical\b|\bmotor\b|\brelay\b|\bDAC\b|\bADC\b|\bexternal device\b|\bPHY\b|"
       r"\bMAC address\b|\bIP address\b|\bARP\b|\bEthernet\b|\bsensor\b", "it drives or answers a device outside the FPGA"),
    _r("cosmetic", "low", r"^(?!.*\b(?:offsets?|address\w*|widths?|map|protocol|pins?)\b).*\b(?:nam(?:e|es|ed|ing)|comments?|labels?|titles?|cosmetic|prefix|register order|order of)\b",
       "a name, comment or ordering that is easy to change later"),
    _r("interface", "high", r"\bprotocols?\b|\bhandshake\b|\btvalid\b|\btready\b|\btlast\b|\bstall\b|\bbeats?\b|\bAXI\w*|\bAPB\b|\bwishbone\b|\bframing\b|"
       r"\bregisters?\b|\boffsets?\b|\baddress(?:es|ing)?\b|\bendian\w*|\bbyte[- ]order\b|\bbaud\b|\bpackets?\b|\bmessages?\b|\bstreams?\b|"
       r"\bmaster or slave\b|\bdirection\b|\bport\b|\bwidths?\b|\bcommand syntax\b|\bUART\b|\bSPI\b|\bI2C\b|\bsession\b|\bsequence",
       "an interface or register map is what other code is written against"),
    _r("number-format", "high", r"\bsigned\b|\bunsigned\b|\bfixed[- ]point\b|\bQ\d+\.\d+\b|\bround(?:ing)?\b|\boverflow\b|\bsaturat\w+|\bwrap(?:s|ping)?\b|"
       r"\bbit-exact\b|\bscale\b|\bprecision\b|\bencod\w+|\bresolution\b|\bnumber format",
       "a number format decides every value the design produces"),
    _r("rate-and-latency", "high", r"\blatency\b|\bthroughput\b|\bcycles?\b|\bgiven as\b|\binterval\b|\bperiod\b|\brate\b|\bdebounce\b|\brefresh\b|"
       r"\btimeout\b|\bduration\b|\bdeadline\b|\bbandwidth\b|\btransfer function\b",
       "a rate, delay or latency target is a requirement the tests check"),
    _r("cost", "medium", r"\bresources?\b|\bbudget\b|\bdepth\b|\bpipelin\w+|\boptimi[sz]\w+|\barea\b|\butili[sz]ation\b|\bLUTs?\b|\bDSPs?\b|\bBRAM\b|\bFIFO\b|"
       r"\bbuffer\w*|\bpower\b|\bmargin\b|\bparallel\b|\bfolded?\b", "it changes size, speed or power, not what the design does"),
    _r("behaviour", "high", r"\bshould\b|\bmust\b|\bmay\b|\bwhat happens\b|\bhow should\b|\bdoes (?:it|the)\b|\bsimultaneous\b|\bwins?\b|\bpriority\b",
       "it settles what the design does in a case the request left open"),
)
DEFAULT_RULE = Rule("unmatched", "medium", re.compile(""), "no rule names it a behaviour, an interface or a cosmetic choice: treated as a cost choice")


@dataclass(frozen=True)
class Risk:
    cls: str          # low | medium | high
    rule: str         # the rule id, or "clarifier", or "clarifier+<rule>"
    why: str

    def as_dict(self) -> dict[str, str]:
        return {"risk": self.cls, "risk_rule": self.rule, "risk_reason": self.why}


def classify(text: str, default: str = "", reason: str = "", clarifier: str | None = None, clarifier_reason: str = "") -> Risk:
    """The risk class of a question. The question text decides (the default and its reason are the Clarifier's guess and never lower
    a class). ``clarifier`` is the class the Clarifier set, if any; the higher of that and the rule's class is used."""
    rule = next((r for r in RULES if r.rx.search(text or "")), DEFAULT_RULE)
    got = Risk(rule.risk, rule.id, rule.why)
    c = (clarifier or "").strip().lower()
    if c in RANK:
        if RANK[c] > RANK[got.cls]:
            return Risk(c, "clarifier", clarifier_reason or "the Clarifier set this class")
        if RANK[c] == RANK[got.cls]:
            return Risk(c, f"clarifier+{rule.id}", clarifier_reason or rule.why)
    return got


# ---- the level ------------------------------------------------------------------------------------------------------------------------
_LINE = re.compile(r"(?im)^\s*[-*]?\s*requirements(?:[ _-]strictness)?\s*:\s*(loose|standard|strict)\s*\.?\s*$")


def _higher(a: str, b: str) -> str:
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


def floor_level(*, production_secure: bool = False, verif_profile: str | None = None) -> str | None:
    """The level a setting implies: ``production_secure`` (brief 196) and the higher verification profiles (brief 194) imply
    at least ``standard``."""
    if production_secure or (verif_profile or "") in STANDARD_PROFILES:
        return "standard"
    return None


def resolve_level(*, cli: str | None, spec_md: str = "", spec: dict[str, Any] | None = None, package: dict[str, Any] | None = None,
                  default: str = "loose", production_secure: bool = False, verif_profile: str | None = None) -> tuple[str, str]:
    """(level, where it came from). Precedence: the command line, then the request's own line ``Requirements: strict``
    (or ``requirements_strictness`` in spec.yaml), then the design package's ``requirements`` field, then ``default``. A floor
    from ``production_secure`` or a high-assurance profile then raises the result to at least ``standard``; the source says so."""
    got, src = None, ""
    if cli:
        got, src = cli, "command line"
    else:
        m = _LINE.search(spec_md or "")
        v = (spec or {}).get("requirements_strictness")
        if m:
            got, src = m.group(1).lower(), "the request (spec.md)"
        elif isinstance(v, str) and v.lower() in LEVELS:
            got, src = v.lower(), "spec.yaml"
        elif isinstance((package or {}).get("requirements"), str) and package["requirements"].lower() in LEVELS:
            got, src = package["requirements"].lower(), "design package"
    if got is None:
        got, src = default, "default"
    if got not in LEVELS:
        raise ValueError(f"--requirements must be one of {', '.join(LEVELS)}, not {got!r}")
    fl = floor_level(production_secure=production_secure, verif_profile=verif_profile)
    if fl and _higher(got, fl) != got:
        return fl, f"{src}, raised to {fl} by production_secure or the verification profile"
    return got, src


def default_level(has_hidden_spec: bool = False, interview: str = "off") -> str:
    """The level when nothing sets one. ``standard`` when a person answers the interview (``--interview on``: a high-risk question is
    put to them, and "accept default" is one reply away); ``loose`` otherwise. A run with nobody to answer (``--interview off`` or the
    oracle, which is every benchmark run) stays ``loose``: the re-scoring of recorded runs (``results/210_requirements/rescore.json``)
    found a high-risk default in 38 of 39 runs, so ``standard`` would stop nearly every unattended run at clarify. A benchmark run (it has
    a hidden spec) also stays ``loose`` so that earlier numbers stay comparable (brief 210)."""
    if has_hidden_spec:
        return "loose"
    return "standard" if interview == "on" else DEFAULT_LEVEL


STATE_DIR = ("build", "requirements")


def state_path(design: Path) -> Path:
    return Path(design).joinpath(*STATE_DIR, "state.json")


def read_state(design: Path) -> dict[str, Any]:
    import json
    try:
        return json.loads(state_path(design).read_text())
    except (OSError, ValueError):
        return {}


def write_state(design: Path, **kw: Any) -> dict[str, Any]:
    """``build/requirements/state.json``: the level this run used, its source, the waivers in force and the conflicts met. Updated key by key."""
    import json
    st = {**read_state(design), **kw}
    p = state_path(design)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1) + "\n")
    return st


def load_package(design: Path) -> dict[str, Any]:
    """The design package's ``package.yaml`` (in the design directory or ``package/``); {} when there is none or it cannot be read."""
    for f in (Path(design) / "package.yaml", Path(design) / "package" / "package.yaml"):
        if f.is_file():
            try:
                doc = yaml.safe_load(f.read_text())
            except yaml.YAMLError:
                return {}
            return doc if isinstance(doc, dict) else {}
    return {}


# ---- waivers --------------------------------------------------------------------------------------------------------------------------
@dataclass
class Waiver:
    match: str            # a question id (q3), text that the question contains, or "*" (every question of the class in ``risk``)
    value: str            # the value chosen, or "agent's default accepted"
    who: str
    when: str             # YYYY-MM-DD
    why: str
    risk: str | None = None            # for a "*" waiver: the class it covers (required; a waiver of everything is not allowed)
    requirement: str | None = None     # a waiver of a conflict with this requirement id (see ``conflicts``)

    def covers(self, q: Any) -> bool:
        if self.requirement:
            return False
        m = self.match.strip()
        if m == "*":
            return self.risk == getattr(q, "risk", None)
        return m.lower() == q.id.lower() or m.lower() in q.text.lower()

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in (("match", self.match), ("value", self.value), ("who", self.who), ("when", self.when),
                                  ("why", self.why), ("risk", self.risk), ("requirement", self.requirement)) if v}


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def waiver_problems(w: dict[str, Any]) -> list[str]:
    p = []
    for k in ("who", "when", "why"):
        if not str(w.get(k) or "").strip():
            p.append(f"no {k}")
    if w.get("when") and not _DATE.match(str(w["when"])):
        p.append("when is not YYYY-MM-DD")
    if w.get("why") and len(str(w["why"]).strip()) < MIN_WHY:
        p.append(f"why is under {MIN_WHY} characters")
    if not w.get("requirement"):
        if not str(w.get("match") or w.get("question") or "").strip():
            p.append("no match (a question id, words of the question, or *)")
        if str(w.get("match") or w.get("question") or "").strip() == "*" and w.get("risk") not in RISKS:
            p.append("a * waiver names the risk class it covers (low, medium or high)")
        if not str(w.get("value") or "").strip():
            p.append("no value (the value chosen, or \"agent's default accepted\")")
    return p


def load_waivers(*dirs: Path) -> tuple[list[Waiver], list[str]]:
    """The waivers of ``requirements_waivers.yaml`` in the first of ``dirs`` that has the file (the design directory, then the
    request's directory). A waiver with a missing field is not used; the problems are returned, never silently dropped."""
    for d in dirs:
        f = Path(d) / WAIVERS_FILE
        if not f.is_file():
            continue
        try:
            doc = yaml.safe_load(f.read_text()) or {}
        except yaml.YAMLError as e:
            return [], [f"{WAIVERS_FILE} is not valid YAML: {' '.join(str(e).split())[:200]}"]
        rows = doc.get("waivers") if isinstance(doc, dict) else None
        out, probs = [], []
        for i, w in enumerate(rows or []):
            if not isinstance(w, dict):
                probs.append(f"waivers[{i}]: not a mapping")
                continue
            bad = waiver_problems(w)
            if bad:
                probs.append(f"waivers[{i}]: " + "; ".join(bad))
                continue
            out.append(Waiver(match=str(w.get("match") or w.get("question") or ""), value=str(w.get("value") or ""), who=str(w["who"]),
                              when=str(w["when"]), why=str(w["why"]).strip(), risk=w.get("risk"), requirement=w.get("requirement")))
        return out, probs
    return [], []


def today() -> str:
    return _dt.date.today().isoformat()


# ---- the policy -----------------------------------------------------------------------------------------------------------------------
def must_resolve(level: str, risk: str) -> bool:
    """Whether a question of this class has to be answered or waived at this level (otherwise a default is allowed)."""
    return level == "strict" or (level == "standard" and risk == "high")


def apply_policy(q: Any, level: str, waivers: list[Waiver]) -> Any:
    """The question as the level sees it. ``q`` has been asked: ``status`` is ``answered`` or ``defaulted``. A defaulted question
    that the level lets through stays ``defaulted`` (an assumption). One it does not let through is ``waived`` when a waiver
    covers it, else ``unresolved``. An answered question is untouched."""
    if q.status != "defaulted" or not must_resolve(level, q.risk):
        return q
    w = next((w for w in waivers if w.covers(q)), None)
    if w is not None:
        chosen = w.value if w.value.strip().lower() not in ("agent's default accepted", "default accepted", "accepted") else q.default
        q.waiver, q.answer, q.status = w.as_dict(), chosen, "waived"
        return q
    q.status, q.answer = "unresolved", None
    return q


def unresolved(questions: list[Any]) -> list[Any]:
    return [q for q in questions if q.status == "unresolved"]


def waiver_from_human(reply: Any, q: Any, who: str = "human") -> Waiver | None:
    """A person's reply that waives a question: a mapping ``{waive: true, value?, why}`` or the plain words "accept default" /
    "waive". The record needs a reason; a bare waiver gets the reason "accepted at the interview" and says so."""
    if isinstance(reply, dict):
        if not reply.get("waive"):
            return None
        why = str(reply.get("why") or "").strip() or "accepted at the interview, no reason given"
        return Waiver(match=q.id, value=str(reply.get("value") or reply.get("answer") or "agent's default accepted"), who=str(reply.get("by") or who),
                      when=today(), why=why)
    t = str(reply or "").strip().lower()
    if t in ("accept default", "accept the default", "waive", "waived", "default accepted"):
        return Waiver(match=q.id, value="agent's default accepted", who=who, when=today(), why="accepted at the interview, no reason given")
    return None


# ---- what a stopped run shows ---------------------------------------------------------------------------------------------------------
def needed_markdown(level: str, source: str, qs: list[Any], conflicts: list[dict[str, Any]] | None = None, problems: list[str] | None = None) -> str:
    out = [f"# Requirements needed before this design can proceed", "",
           f"Requirements level: **{level}** (from {source}). The run stopped at the clarify stage; nothing was built.", ""]
    if qs:
        out += [f"{len(qs)} question(s) need an answer or an explicit waiver. For each, either put the answer in the request (spec.md) and run again, "
                f"answer it with `--interview on`, or record a waiver in `{WAIVERS_FILE}` (question or id, value, who, when, why).", "",
                "| Id | Risk | Question | The agent would have used | Why it matters |", "|---|---|---|---|---|"]
        for q in qs:
            out.append(f"| {q.id} | {q.risk} | {_c(q.text)} | {_c(q.default)} | {_c(q.risk_reason)} |")
        out.append("")
    if conflicts:
        out += ["A fix asked for by a gate conflicts with a stated requirement:", ""]
        out += [f"- {c['requirement']} ({c['requirement_text']}) against the fix for {c['code']} ({c['fix_kind']}): {c['why']}" for c in conflicts]
        out += ["", "Decide which gives way: change the requirement in the request, change the clock or the interface so the fix is not needed, or record a waiver "
                f"in `{WAIVERS_FILE}` with `requirement: <id>`.", ""]
    if problems:
        out += ["Waivers that were not used:", ""] + [f"- {p}" for p in problems] + [""]
    out += [f"Example waiver (`{WAIVERS_FILE}`):", "", "```yaml", "waivers:", "  - match: <question id or words of the question>",
            "    value: agent's default accepted", "    who: <your name>", "    when: <YYYY-MM-DD>", "    why: <the reason, at least a sentence>", "```", ""]
    return "\n".join(out)


def _c(s: Any) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def stop_text(qs: list[Any], conflicts: list[dict[str, Any]] | None = None) -> str:
    bits = []
    if qs:
        bits.append(f"{len(qs)} unanswered question(s), {sum(q.risk == 'high' for q in qs)} high risk: " + "; ".join(f"{q.id} [{q.risk}] {q.text[:70]}" for q in qs[:4]))
    if conflicts:
        bits.append("; ".join(f"the fix for {c['code']} ({c['fix_kind']}) conflicts with {c['requirement']}" for c in conflicts[:3]))
    return f"{STOP_PREFIX} " + " | ".join(bits) + f" (see {NEEDED_FILE})"


def is_requirements_stop(stop: str | None) -> bool:
    return bool(stop) and str(stop).startswith(STOP_PREFIX)


# ---- the handover: assumptions ---------------------------------------------------------------------------------------------------------
def assumptions_of(spec: dict[str, Any]) -> list[dict[str, str]]:
    """"Assumptions you did not confirm": every question of spec.yaml's ``resolved_questions`` whose answer is the agent's default (status
    ``defaulted``, or ``waived`` with the default accepted), with its risk class. Questions answered by a person, the oracle or a design
    package fact are not listed. A record from before brief 210 has no class: it is classified now by the same rules."""
    out = []
    for q in spec.get("resolved_questions") or []:
        if not isinstance(q, dict) or q.get("status") not in ("defaulted", "waived"):
            continue
        rk = q.get("risk") if q.get("risk") in RANK else classify(str(q.get("question", "")), "", str(q.get("default_reason", ""))).cls
        out.append({"question": str(q.get("question", "")), "risk": rk, "used": str(q.get("answer", "")),
                    "how": ("waived by " + str((q.get("waiver") or {}).get("who", "?")) + ": " + str((q.get("waiver") or {}).get("why", "")))
                    if q.get("status") == "waived" else {"limit": "defaulted: the question limit was reached", "oracle": "defaulted: the oracle did not know"
                                                         }.get(str(q.get("by")), "defaulted: nobody answered"),
                    "reason": str(q.get("default_reason", ""))})
    return sorted(out, key=lambda a: -RANK[a["risk"]])


# ---- a fix against a stated requirement (brief 210, item 7) -----------------------------------------------------------------------------
#: fix kind -> (what the fix does, a pattern for requirement text that the fix would break)
FIX_KINDS: dict[str, tuple[str, re.Pattern]] = {
    "pipeline": ("adds registers inside a path", re.compile(
        r"\bno (?:registers?|flip-?flops?|pipelin\w+|latches?)\b|\bnot pipelined\b|\bwithout (?:any )?(?:registers?|pipelin\w+)\b|"
        r"\bcombinational\b|\bsingle[- ]cycle\b|\bone clock(?: cycle)?\b|\bzero[- ]latency\b|\bunregistered\b|\bnot folded\b", re.I)),
    "fewer-resets": ("removes resets from registers", re.compile(r"\ball registers? (?:are|is|have|has) (?:a )?(?:reset|reset)\b|\bevery register is reset\b", re.I)),
}


def fix_kind_of(finding: dict[str, Any]) -> str | None:
    """What a blocking report-gate finding asks the Designer to do. RPT-LL-02 (a setup path that cannot close at this clock) is
    answered by pipelining or retiming; RPT-CS-02 (control sets) by fewer distinct resets, enables and clocks; RPT-LOG-03 by none."""
    code = str(finding.get("code", ""))
    fix = str(finding.get("fix", "")) + " " + str(finding.get("message", ""))
    if code == "RPT-LL-02" or re.search(r"\bpipelin|\bretim|\badd (?:a )?register", fix, re.I):
        return "pipeline"
    if code == "RPT-CS-02":
        return "fewer-resets"
    return None


def fix_conflicts(findings: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The stated requirements (spec.yaml ``requirements``) that the fix a blocking finding asks for would break."""
    out, seen = [], set()
    for f in findings:
        kind = fix_kind_of(f)
        if kind is None:
            continue
        what, rx = FIX_KINDS[kind]
        for r in spec.get("requirements") or []:
            if isinstance(r, dict) and rx.search(str(r.get("text", ""))) and (str(r["id"]), f.get("code")) not in seen:
                seen.add((str(r["id"]), f.get("code")))
                out.append({"requirement": str(r["id"]), "requirement_text": str(r.get("text", "")), "code": f.get("code"), "fix_kind": kind,
                            "why": f"the fix {what}, and the requirement says otherwise"})
    return out

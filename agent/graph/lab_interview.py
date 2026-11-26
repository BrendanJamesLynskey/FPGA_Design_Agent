"""The lab questions of the spec interview (brief 221).

The interview reads the lab (``hil/lab.py``) and asks only about gaps:

* ``[lab:connect:<instrument>:<requirement>]``: an onboarded instrument could check a requirement that states a frequency or a level, and nothing
  records that it is connected for this design. One question per instrument and requirement; it offers the measurement ("the 25 MHz clock on pin C3:
  the m2k on DIO0 to DIO3 as an independent check beside the design's own count, or the on-chip count alone?") and asks which channel is wired to
  which pin. Default: not connected, on-chip measurement only.
* ``[lab:record]``: there is no lab file at all and the spec has a requirement an instrument could check. Asked once, and only to a person
  (``--interview on``). Default: no, on-chip measurement only. A "no" is written to the design's ``lab.yaml`` (``no_instruments: true``) so it is not asked again.

Answers are recorded like every interview answer (who, default, reason). A connect answer has one form, ``<instrument>: <CHANNEL> -> <pin or probe point>``
(several joined by ``;``), or ``not connected``; :func:`record_answers` writes the connections into the design's ``lab.yaml`` with their provenance. An
answer in any other form is not guessed at: it is recorded in ``build/lab/answer_problems.json``, the instrument stays "not connected for this design",
and the stage-9 plan says so. An instrument that is not onboarded is never asked about: the plan lists it as "available after onboarding".

The question text carries the ``[lab:...]`` tag, which the requirement-risk rules (``agent.graph.requirements``) read as a low-risk verification-method
choice, so a default never stops a run at ``standard``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from hil import lab as L

TAG = re.compile(r"\[lab:(connect|record)(?::([a-z0-9_]+))?(?::([A-Za-z0-9_.-]+))?\]")
ANSWER = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*:\s*([A-Za-z0-9_+-]+)\s*->\s*(.+?)\s*$")
NOT_CONNECTED = "not connected"


def questions(lab: L.Lab, needs: list[L.Need], *, asked: str = "", person: bool = False) -> list[dict[str, str]]:
    """Open questions (``question``, ``default``, ``reason``) for the gaps. ``asked`` is the text of questions already in the spec (open or resolved):
    a tag found there is not asked again. ``person``: a human answers (``--interview on``)."""
    out: list[dict[str, str]] = []
    if not needs or lab.declined:
        return out
    if not lab.present and not lab.problems:
        if person and "[lab:record]" not in asked:
            out.append({"question": "[lab:record] Which instruments on your bench can the agent use to check this design on the board (scope, counter, logic analyser, supply)? "
                                    "Recording them in a lab file lets the bring-up add an independent instrument check beside the design's own. Record a lab file now?",
                        "default": "No: on-chip measurement only for this design.",
                        "reason": "Nothing is assumed about your bench: without a lab file the bring-up uses only what the design measures itself and the JTAG or UART link. "
                                  "To record one, copy hil/lab.example.yaml to ~/.config/fpga-force/lab.yaml, edit it, and re-run stage 9."})
        return out
    for iid, inst in sorted(lab.instruments.items()):
        if inst.get("kind") == "on_chip" or not inst.get("onboarded"):
            continue                                          # not onboarded: offered in the plan only ("available after onboarding")
        for n in needs:
            caps = [c for c in inst.get("capabilities") or [] if isinstance(c, dict) and c.get("measure") == n.quantity and L._covers(c, n) is None]
            if not caps or lab.connected(iid):
                continue
            tag = f"[lab:connect:{iid}:{n.requirement}]"
            if tag in asked:
                continue
            chans = ", ".join(caps[0].get("channels") or [c["name"] for c in inst.get("channels") or []])
            what = (f"{n.value / 1e6:g} MHz" if n.value and n.quantity == "frequency" and n.value >= 1e6 else
                    (f"{n.value:g} Hz" if n.value and n.quantity == "frequency" else (f"{n.value:g} V" if n.value else "")))
            out.append({"question": f"{tag} {n.requirement} ({n.text.rstrip('.')}): {n.target}{' at ' + what if what else ''} could be checked by the {inst.get('model') or iid} "
                                    f"(channels {chans}) as an independent check beside {n.onchip or 'the design' + chr(39) + 's own measurement'}. Is it connected for this design, "
                                    f"and which channel probes which pin? Answer '{iid}: <CHANNEL> -> <pin>' or 'not connected'.",
                        "default": f"{NOT_CONNECTED}: on-chip measurement only for {n.requirement}.",
                        "reason": f"A scope, counter or logic analyser settles this in seconds, but only if it is wired to the right pin and you confirm the channel. "
                                  f"Without an answer the bring-up measures {n.requirement} on-chip only. Check the probe is on the pin you name: a probe on the wrong pin "
                                  f"is not detectable here and shows up as a reading nowhere near the expected value."})
    return out


def ensure_lab_questions(design: Path, spec: dict[str, Any], *, person: bool = False, lab: L.Lab | None = None) -> tuple[dict[str, Any], list[str]]:
    """Add the gap questions to ``open_questions`` (the way ``interview.ensure_protocol_questions`` does). Returns (spec, question tags added). A design
    with no lab at all and no person to ask gets nothing: a run behaves exactly as before."""
    lab = lab if lab is not None else L.load(design)
    asked = " \n ".join(str(q.get("question", "")) for q in [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])] if isinstance(q, dict))
    add = questions(lab, L.needs_from_spec(spec), asked=asked, person=person)
    if not add:
        return spec, []
    spec = dict(spec)
    spec["open_questions"] = [*(spec.get("open_questions") or []), *add]
    return spec, [TAG.search(q["question"]).group(0) for q in add if TAG.search(q["question"])]


def parse_answer(text: str) -> list[tuple[str, str, str]] | None:
    """(instrument, channel, probes) triples of a connect answer, ``[]`` for "not connected", None when the form is not understood."""
    t = str(text or "").strip()
    if re.match(r"(?i)^(no|none|not connected|not\b)", t):
        return []
    rows = []
    for part in re.split(r"[;\n]", t):
        if not part.strip():
            continue
        m = ANSWER.match(part)
        if not m:
            return None
        rows.append((m.group(1), m.group(2), m.group(3)))
    return rows or None


def record_answers(design: Path, resolved: list[dict[str, Any]], lab: L.Lab | None = None) -> dict[str, Any]:
    """Write the answers of the lab questions into the design's ``lab.yaml`` (``connections`` with provenance; ``no_instruments`` for a declined
    record question). A connection to an instrument or channel the lab does not have, or an answer in another form, is a problem recorded in
    ``build/lab/answer_problems.json`` and nothing is written for it. Returns ``{connections, problems, declined}``."""
    design = Path(design)
    lab = lab if lab is not None else L.load(design)
    f = design / L.FILE
    doc = (yaml.safe_load(f.read_text()) or {}) if f.is_file() else {}
    conns = [c for c in doc.get("connections") or [] if isinstance(c, dict)]
    problems: list[str] = []
    declined = False
    for q in resolved:
        m = TAG.search(str(q.get("question", "")))
        if not m or q.get("status") not in ("answered", "defaulted", "waived"):
            continue
        ans = str(q.get("answer", ""))
        prov = {"source": "interview", "by": q.get("by"), "status": q.get("status"), "answer": ans, "reason": q.get("default_reason")}
        if m.group(1) == "record":
            if re.match(r"(?i)^\s*(no\b|default|none)", ans):
                doc["no_instruments"], declined = True, True
            continue
        rows = parse_answer(ans)
        if rows is None:
            problems.append(f"{m.group(0)}: the answer {ans!r} is not '<instrument>: <CHANNEL> -> <pin>' or 'not connected'; nothing recorded")
            continue
        for iid, ch, probes in rows:
            inst = lab.instruments.get(iid)
            chans = {c.get("name") for c in (inst or {}).get("channels") or []}
            if inst is None:
                problems.append(f"{m.group(0)}: no instrument {iid!r} in the lab; nothing recorded")
            elif chans and ch not in chans:
                problems.append(f"{m.group(0)}: {iid} has no channel {ch!r} (channels: {', '.join(sorted(chans))}); nothing recorded")
            elif not any(c.get("instrument") == iid and c.get("channel") == ch for c in conns):
                conns.append({"instrument": iid, "channel": ch, "probes": probes, "provenance": prov})
    if conns:
        doc["connections"] = conns
    if conns or declined:
        doc.setdefault("schema", L.SCHEMA)
        f.write_text(yaml.safe_dump(doc, sort_keys=False))
    out = {"connections": conns, "problems": problems, "declined": declined}
    p = design / "build" / "lab" / "answer_problems.json"
    if problems:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(problems, indent=1) + "\n")
    return out

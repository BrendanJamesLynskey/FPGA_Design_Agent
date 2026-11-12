"""Data for the home page's feedback loop (brief 47): site/data/loop.json, from committed records only.

    from loop import build; build(agent_graph)    # called by site/export.py

- ``stations``: the loop drawn on the bench (spec and interview, role agents, simulators and formal, Vivado, the board,
  the instruments). Each label of what comes back is read from a run record or result file named beside it; a station
  with no committed measurement says "being measured".
- ``legs``: site/data/loop_legs.yaml, checked (status, evidence paths) and counted: "legs automated: N of M".
- ``tour``: the frames of the hero animation, from one recorded Deep Agents run on the T1 design that went from the
  interview to a bitstream (its visit order, as recorded), and the board run made on its files as written.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent

PASS_RUN = "results/course/c14_int8_dot_requant/run_5.json"      # the development run whose numbers label the arrows
REBUILDS = "results/vivado_2026_1_remeasure/dev_rebuilds.json"                # brief 49: that run's design rebuilt on Vivado 2026.1
HIL_RUN = "results/b30/hil_runs/b30_hil_audio.hil.json"
TOUR_RUN = "results/f2/agent_luna_05c2_run7.json"                  # interview to bitstream, visit order recorded
TOUR_BOARD = "results/f2/agent_luna_05c2_run7_bringup.json"        # the board run on that run's files, as written
STATUS = ("automated", "building", "person")
STATION_OF = {0: "spec", 1: "agents", 2: "sim"}                    # every later stage measures with Vivado (3-9)
ACT_PATH = {"spec": [["f-spec", 1]], "agents": [], "sim": [["f-sim", 0]], "vivado": [["f-sim", 0], ["f-viv", 0]],
            "board": [["f-board", 0]]}
ACTS = {"spec": "the clarify role's questions go to the person who asked, or in a development run to an oracle model.",
        "sim": "they run lint and their own tests on the simulators{verif}.",
        "vivado": "they run Vivado on the design."}
OBSERVES = {"spec": "the answers come back, and code checks that no question is left open.",
            "sim": "lint and test results come back; code reads them, and no model judges them.",
            "vivado": "Vivado's reports come back (timing, design rules, clock crossings, methodology, exceptions); code reads them."}
WORKS = {0: "the clarify role turns the request into a spec and asks about what it leaves open",
         1: "the RTL writer plans the architecture, clocks and resources",
         9: "the RTL writer and the test writer prepare the bring-up files"}


def jload(rel):
    return json.loads((ROOT / rel).read_text())


def legs():
    y = yaml.safe_load((HERE / "data" / "loop_legs.yaml").read_text())["legs"]
    out = []
    for x in y:
        assert x["status"] in STATUS, x
        assert not re.search(r"\d", x["leg"] + x["note"]), ("no typed numbers in loop_legs.yaml", x["id"])
        ev = x.get("evidence") or []
        assert ev or x["status"] != "automated", ("an automated leg needs evidence", x["id"])
        for p in ev:
            assert (ROOT / p).exists(), ("evidence path missing", x["id"], p)
        out.append({"id": x["id"], "leg": x["leg"], "status": x["status"], "note": x["note"], "evidence": ev})
    ids = [x["id"] for x in out]
    assert len(ids) == len(set(ids))
    return out


def stations(A):
    """The bench, with what each station feeds back. Values read from the named records."""
    r = jload(PASS_RUN)
    b = jload(TOUR_BOARD)["run_as_written"]["steps"]
    q, g = r["questions"], r["gates"]
    # brief 49: the Vivado figures are the run's saved design rebuilt on 2026.1, not the run record's own (earlier release)
    qo = jload(REBUILDS)["runs"][f'{r["task"]}/run_{r["run"]}']
    v3 = g["V3"]
    bins = re.search(r"functional bins [\d.]+% (\d+)/(\d+)", v3)
    mut = re.search(r"mutation score ([\d.]+)%", v3)
    ut = b["uart_tests"]
    ila_fit = "Unable to fit compare values" in b["ila_captures"]["why"]
    vivado = A["vivado"]
    hil = jload(HIL_RUN)
    jack = hil["checks"]["tone_at_the_jack"]["measured"]
    pass_src = {"record": PASS_RUN, "what": f'{r["task"]}, attempt {r["run"]} ({r["date"]}), a development run with Claude Code {r["claude_code_version"]} and {r["model"]}'}
    tour = jload(TOUR_RUN)
    board_src = {"record": TOUR_BOARD, "what": f'the board run on the files of the replayed run (the LED-dimmer design, Deep Agents harness, '
                                               f'{tour["model"]}), as written; bitstream built before the move to Vivado 2026.1'}
    return [
        {"id": "spec", "title": "Spec and interview", "desc": "the request in plain English, and questions on what it leaves open",
         "fb": {"kind": "answers to its questions", "values": [f'{q["asked"]} questions asked', f'{q["answered"]} answered, {q["defaulted"]} defaulted'],
                "src": pass_src, "leg": "interview"},
         "gate": {"title": "spec signed off", "line": "no question left open", "leg": "interview"}},
        {"id": "agents", "title": "Role agents", "desc": "Deep Agents or Claude Code; four roles, each in its own jail",
         "fb": None, "gate": None},
        {"id": "sim", "title": "Simulators and formal", "desc": "cocotb on Icarus or Verilator; SymbiYosys for proofs",
         "fb": {"kind": "test results, coverage, mutation score",
                "values": [f"functional bins {bins.group(1)} of {bins.group(2)}", f"mutation score {mut.group(1)}%"],
                "src": pass_src, "leg": "simulate"},
         "gate": {"title": "V0 to V3", "line": "test plan to mutation", "leg": "gates"}},
        {"id": "vivado", "title": f"Vivado {vivado}", "desc": "synthesis, place and route, and the bitstream",
         "fb": {"kind": "timing, DRC, CDC, methodology and exception reports",
                "values": [f'WNS {qo["wns_ns_at_100MHz_post_route"]:+.3f} ns', f'power {qo["power_w"]:.3f} W'],
                "src": {"record": REBUILDS, "what": f'{r["task"]}, development run {r["run"]} ({r["model"]}): its saved design rebuilt on Vivado {qo["vivado"]}'},
                "leg": "gates"},
         "gate": {"title": "stage gates", "line": "UltraFast stages", "leg": "gates"}},
        {"id": "board", "title": "Nexys A7 board", "desc": "Artix-7, programmed over JTAG into SRAM; UART shell, ILA, XADC",
         "fb": {"kind": "UART tests, ILA captures, XADC temperature and voltage",
                "values": [f'UART {ut["tests"] - ut["failures"]} of {ut["tests"]} passed',
                           "ILA trigger did not fit" if ila_fit else ("ILA captures passed" if b["ila_captures"]["pass"] else "ILA captures failed"),
                           "XADC matches JTAG"],
                "src": board_src, "leg": "uart"},
         "gate": {"title": "board tests", "line": "registers, captures", "leg": "uart"}},
        {"id": "instr", "title": "Instruments", "desc": "ADALM2000, Red Pitaya, HDMI and audio capture, Pluto and RTL-SDR",
         "fb": {"kind": "waveforms, spectra, frames, audio",
                "values": [f'audio {jack["freq_hz"]} Hz', f'THD {jack["thd_percent"]} %',
                           "caught a pin fault", "scope, SDR, video: next"],
                "src": {"record": HIL_RUN, "what": f'the hardware-in-the-loop run on {hil["design"].split("/")[-1]} ({hil["started"][:10]}); bitstream built before the move to Vivado 2026.1'},
                "leg": "audio_capture"},
         "gate": {"title": "instrument tests", "line": "scripted, not in loop yet", "leg": "hil_gate"}},
    ]


def tour(A):
    """Frames of the hero animation: TOUR_RUN's visits in recorded order, then the board run on its files."""
    r = jload(TOUR_RUN)
    br = jload(TOUR_BOARD)
    steps = br["run_as_written"]["steps"]
    S = {s["n"]: s for s in A["stages"]}
    roles = {x["id"]: x["label"] for x in A["roles"]}
    order = r["stages_visited"]
    F, count = [], {}

    def low(s):
        return s if s[:3].isupper() else s[0].lower() + s[1:]
    for i, n in enumerate(order):
        count[n] = count.get(n, 0) + 1
        k, K = count[n], order.count(n)
        st = STATION_OF.get(n, "vivado")
        head = f"Stage {n}, {S[n]['label']}, visit {k} of {K}. "
        names = ["the " + low(roles[x]) for x in S[n]["roles"]]
        who = WORKS.get(n) or ((", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]) +
                               (" write" if len(S[n]["roles"]) > 1 else " writes") +
                               (" again, to repair what failed" if k > 1 else ""))
        base = {"stage": n, "visit": k, "visits": K, "station": st}
        F.append({**base, "ph": "work", "at": "agents", "path": [], "cap": head + "Plan and write: " + who + "."})
        if st != "agents":
            F.append({**base, "ph": "act", "at": st, "path": ACT_PATH[st], "cap": head + "Act: " + ACTS[st].format(verif=f" (this run asked for verification to level {r['verif_level']})")})
            F.append({**base, "ph": "observe", "at": st, "path": [["o-" + st, 0]], "fb": st,
                      "cap": head + "Observe: " + OBSERVES[st]})
        nxt = order[i + 1] if i + 1 < len(order) else None
        if nxt is None:                                   # stage 9: every build gate passed, then the pause for a yes
            F.append({**base, "ph": "decide", "at": st, "path": [["r-" + st, 0]], "gate": "pass", "rail": "pass",
                      "cap": head + "Decide: both bitstreams built and every gate passed (" + r["gates_last"]["base_build"].split(",")[0] + ")."})
        elif nxt > n:
            F.append({**base, "ph": "decide", "at": st, "path": [] if st == "agents" else [["r-" + st, 0]], "gate": "pass", "rail": "pass",
                      "cap": head + f"Decide: the stage's gates pass, so the controller moves on to stage {nxt}, {S[nxt]['label']}."})
        else:
            F.append({**base, "ph": "decide", "at": st, "path": [] if st == "agents" else [["r-" + st, 0]], "gate": "fail", "rail": "fail",
                      "cap": head + f"Decide: not passed on this visit, so the controller sends the work back to stage {nxt}, "
                                    f"{S[nxt]['label']}, for a repair. The record keeps the order of visits, not each failure's text."})
    ms = steps["program_base"]["program_ms"]
    ut = steps["uart_tests"]
    base = {"stage": 9, "visit": 1, "visits": 1, "station": "board"}
    F.append({**base, "ph": "approve", "at": "agents", "path": [], "person": "approve",
              "cap": "The run pauses for a yes before anything is programmed, as it always does. With the owner's yes, "
                     "the board tests then ran on the agent's files as written."})
    F.append({**base, "ph": "act", "at": "board", "path": [["f-sim", 0], ["f-viv", 0], ["f-board", 0]],
              "cap": f"Act: the bitstream is programmed over JTAG into the board's SRAM, selected by the cable's serial number "
                     f"({round(ms / 1000, 1)} s)."})
    F.append({**base, "ph": "observe", "at": "board", "path": [["o-board", 0]], "fb": "board",
              "cap": f"Observe: {ut['tests'] - ut['failures']} of {ut['tests']} tests over the UART shell pass. The ILA trigger the agent "
                     "wrote needs more comparators than the core has, so Vivado never arms it and the captures fail."})
    F.append({**base, "ph": "decide", "at": "board", "path": [["r-board", 0]], "gate": "fail", "rail": "fail",
              "cap": "Decide: the board tests fail. Since this run, such a failure goes back to stage 9 with Vivado's error "
                     "lines, and a dry check before programming catches this kind of trigger."})
    F.append({**base, "ph": "end", "at": "instr", "path": [], "station": "instr",
              "cap": "The instruments were not used in this run: their captures are being measured, and a stage that feeds "
                     "them to the repair loop is being built."})
    info = {"record": TOUR_RUN, "board_record": TOUR_BOARD, "harness": r["harness"], "model": r["model"], "design": "t1_dimmer_counter",
            "run": r["run"], "date": br["run_as_written"]["started"][:10], "wall_h": round(r["wall_s"] / 3600, 2),
            "usd": round(r["key_usage_usd"]["delta"], 2), "visits": len(order), "program_s": round(ms / 1000, 1),
            "repairs": sum(1 for a, b in zip(order, order[1:]) if b <= a)}
    return F, info


def build(A):
    L = legs()
    c = {s: sum(1 for x in L if x["status"] == s) for s in STATUS}
    frames, info = tour(A)
    return {"stations": stations(A), "legs": L, "counts": {**c, "total": len(L)}, "tour": frames, "tour_info": info}

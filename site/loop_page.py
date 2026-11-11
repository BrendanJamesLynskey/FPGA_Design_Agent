"""The home page's hero figure (brief 47): the agent's feedback loop drawn on the bench, from site/data/loop.json.

Two hand-tuned layouts on fixed grids, like agent_page.py: wide (940, shown from 820 px) and narrow (360, phones).
Forward along the top (or down the column): spec and interview, role agents, simulators and formal, Vivado, the board,
the instruments. Down from each station: what it returns, labelled with a recorded value. Into a gate per station; from
every gate a rail back to the role agents (the controller: the next stage, or a repair by the role that owns the
failure). Each arrow carries data-leg; its line style comes from the leg's status in loop_legs.yaml (solid: runs with no
person; dashed: being built), and a tag marks a leg that needs a person. Path ids (f-*, o-*, r-*) are what app.js moves
the token along. Type: the site's sans at 15, 13 and 11 px. No glow.
"""
from __future__ import annotations

from agent_page import E, box, defs, lines, text, wrap

ORDER = ["spec", "agents", "sim", "vivado", "board", "instr"]
FWD = {"spec": ("f-spec", "interview"), "sim": ("f-sim", "simulate"), "vivado": ("f-viv", "build"),
       "board": ("f-board", "program"), "instr": ("f-instr", "instruments")}     # the arrow INTO each station
OBS = {"spec": "interview", "sim": "simulate", "vivado": "build", "board": "uart", "instr": "instruments"}
PERSON = {"board": "approve", "instr": "wiring"}                                   # person tags on the arrow into


def _st(L, leg):
    return {x["id"]: x["status"] for x in L["legs"]}[leg]


def _path(pid, d, leg, L, p, cls="ed"):
    st = _st(L, leg)
    dash = ' stroke-dasharray="5 4"' if st == "building" else ""
    return f'<path class="{cls} lg-{st}" id="{p}-{pid}" data-p="{pid}" data-leg="{leg}" d="{d}"{dash} marker-end="url(#{p}-ah)"/>'


def _person(x, y, leg, words, L, p, anchor="middle"):
    assert _st(L, leg) == "person", leg
    w = len(words) * 5.8 + 14
    x0 = x - w / 2 if anchor == "middle" else x
    return (f'<g class="person" data-person="{leg}" data-leg="{leg}">{box(x0, y - 13, w, 18, "ptag", 9)}'
            f'{text(x0 + w / 2, y, words, "s", "middle")}</g>')


def _fb_rows(fb, width):
    kind = wrap("returns " + fb["kind"], width)
    return kind, fb["values"]


def hero(L, lay):
    wide = lay == "wide"
    p = f"lp{lay[0]}"
    S = {s["id"]: s for s in L["stations"]}
    out = []
    if wide:
        W, cw, gap = 940, 141, 18
        X = {sid: i * (cw + gap) for i, sid in enumerate(ORDER)}
        TL = {sid: wrap(S[sid]["title"], cw - 22, 15) for sid in ORDER}
        DL = {sid: wrap(S[sid]["desc"], cw - 22) for sid in ORDER}
        sy = 44
        sh = max(30 + 18 * len(TL[s]) + 15 * len(DL[s]) for s in ORDER)
        gy = sy + sh + 140                     # gates
        gh = 52
        ry = gy + gh + 30                      # the rail
        rx = X["agents"] + 16                  # the rail rises in the agents column
        ay = sy + 34                           # forward arrows
        out.append(text(X["agents"], 14, "plan and write", "s ph"))
        out.append(text(X["sim"], 14, "act: the design goes through the tools on the bench", "s ph"))
        for sid in ORDER:
            s, x = S[sid], X[sid]
            cls = "stn"
            body = [lines(x + 12, sy + 24, TL[sid], "t", 18)]
            body.append(lines(x + 12, sy + 26 + 18 * len(TL[sid]), DL[sid], "s", 15))
            out.append(f'<g class="{cls}" data-s="{sid}" data-ax="{x + cw / 2:g}" data-ay="{sy + sh / 2:g}">{box(x, sy, cw, sh, "nd")}{"".join(body)}</g>')
            if sid in FWD:
                pid, leg = FWD[sid]
                if sid == "spec":               # the interview: from the role agents' clarify role back to the person
                    d = f"M{X['agents'] - 1} {ay} L{x + cw + 2} {ay}"
                    out.append(_path(pid, f"M{x + cw + 1} {ay} L{X['agents'] - 2} {ay}", leg, L, p))
                else:
                    prev = ORDER[ORDER.index(sid) - 1]
                    out.append(_path(pid, f"M{X[prev] + cw + 1} {ay} L{x - 2} {ay}", leg, L, p))
                if sid in PERSON:
                    mx = x - gap / 2
                    words = {"approve": "a person's yes", "wiring": "wired by hand"}[PERSON[sid]]
                    out.append(f'<path class="tick" d="M{mx} 31 L{mx} {ay - 6}"/>')
                    out.append(_person(mx, 30, PERSON[sid], words, L, p))
            fb = s["fb"]
            if fb:
                fx = x + 12
                out.append(_path("o-" + sid, f"M{fx} {sy + sh + 1} L{fx} {gy - 2}", OBS[sid], L, p))
                kind, vals = _fb_rows(fb, cw + gap - 30)
                rows = [text(fx + 12, sy + sh + 26 + 14 * k, r, "s") for k, r in enumerate(kind)]
                rows += [text(fx + 12, sy + sh + 32 + 14 * (len(kind) + k), v, "s v") for k, v in enumerate(vals)]
                out.append(f'<g class="fb" data-fb="{sid}" data-leg="{fb["leg"]}">{"".join(rows)}</g>')
                g = s["gate"]
                gst = _st(L, g["leg"])
                dash = ' stroke-dasharray="5 4"' if gst == "building" else ""
                out.append(f'<g class="gate" data-g="{sid}" data-leg="{g["leg"]}">'
                           f'<rect class="gbx lg-{gst}" x="{x}" y="{gy}" width="{cw}" height="{gh}" rx="4"{dash}/>'
                           f'{text(x + 12, gy + 21, g["title"])}{text(x + 12, gy + 38, g["line"], "s")}</g>')
                gx = x + cw / 2
                out.append(_path("r-" + sid, f"M{gx} {gy + gh + 1} L{gx} {ry} L{rx} {ry} L{rx} {sy + sh + 3}", "repair", L, p, "ed rail"))
        rl = wrap("decide: the controller sends a pass on to the next stage, and a failure back to the role that owns it, for a repair", cw - 30)
        out.append(lines(rx + 12, sy + sh + 26, rl, "s", 14))
        H = ry + 50
        ly = ry + 34
    else:
        W, sw, gx0, gw, rx = 360, 206, 228, 104, 350
        y = 26
        out.append(text(0, 12, "station, and what it returns", "s ph"))
        out.append(text(gx0, 12, "gate", "s ph"))
        rows, ys = [], {}
        for sid in ORDER:
            s = S[sid]
            dl = wrap(s["desc"], sw - 24)
            body = lines(12, y + 42, dl, "s", 15)
            h = 30 + 15 * len(dl) + 8
            fbh = 0
            fbs = ""
            if s["fb"]:
                kind, vals = _fb_rows(s["fb"], sw - 24)
                fy = y + h + 16
                fbs = (f'<g class="fb" data-fb="{sid}" data-leg="{s["fb"]["leg"]}">'
                       + "".join(text(12, fy + 14 * k, r, "s") for k, r in enumerate(kind))
                       + "".join(text(12, fy + 4 + 14 * (len(kind) + k), v, "s v") for k, v in enumerate(vals)) + "</g>")
                fbh = 14 * (len(kind) + len(vals)) + 22
            H0 = h + fbh
            out.append(f'<g class="stn" data-s="{sid}" data-ax="{sw / 2:g}" data-ay="{y + H0 / 2:g}">{box(0, y, sw, H0, "nd")}'
                       f'{text(12, y + 22, s["title"], "t")}{body}</g>')
            if s["fb"]:
                out.append(f'<path class="sep" d="M12 {y + h} L{sw - 12} {y + h}"/>')
                out.append(fbs)
                g = s["gate"]
                gst = _st(L, g["leg"])
                dash = ' stroke-dasharray="5 4"' if gst == "building" else ""
                gt, gl = wrap(g["title"], gw - 20, 13), wrap(g["line"], gw - 20)
                ghh = 14 + 16 * len(gt) + 14 * len(gl) + 6
                gyy = y + H0 - ghh
                out.append(f'<g class="gate" data-g="{sid}" data-leg="{g["leg"]}">'
                           f'<rect class="gbx lg-{gst}" x="{gx0}" y="{gyy:g}" width="{gw}" height="{ghh}" rx="4"{dash}/>'
                           + lines(gx0 + 10, gyy + 20, gt, "", 16) + lines(gx0 + 10, gyy + 20 + 16 * len(gt), gl, "s", 14) + "</g>")
                oy = gyy + ghh / 2
                out.append(_path("o-" + sid, f"M{sw + 1} {oy:g} L{gx0 - 2} {oy:g}", OBS[sid], L, p))
                rows.append((sid, gx0 + gw, oy))
            ys[sid] = (y, H0)
            y += H0 + (30 if sid != ORDER[-1] else 0)
        H = y + 8
        for k, sid in enumerate(ORDER[1:], 1):           # forward arrows down the column
            prev = ORDER[k - 1]
            y1, y2 = ys[prev][0] + ys[prev][1], ys[sid][0]
            pid, leg = FWD["spec" if sid == "agents" else sid]
            out.append(_path(pid, f"M24 {y1 + 1:g} L24 {y2 - 2:g}", leg, L, p))
            if sid in PERSON:
                words = {"approve": "a person's yes", "wiring": "wired by hand"}[PERSON[sid]]
                out.append(_person(40, (y1 + y2) / 2 + 4, PERSON[sid], words, L, p, "start"))
        ay0, ah = ys["agents"]
        am = ay0 + ah / 2
        for sid, x1, oy in rows:
            out.append(_path("r-" + sid, f"M{x1 + 1} {oy:g} L{rx} {oy:g} L{rx} {am:g} L{sw + 3} {am:g}", "repair", L, p, "ed rail"))
        rl = wrap("decide: a pass goes on to the next stage, a failure back to its owner", gw + 6)
        out.append(lines(gx0, am + 18, rl, "s", 14))
        ly = H + 18
        H = ly + 16
    # legend: what the line styles mean (from the leg statuses)
    lg = [("solid", "runs with no person"), ("dash", "being built"), ("tag", "needs a person")]
    if wide:
        lx, out2 = 0, []
        for kind, words in lg:
            out2.append(_legend(lx, ly, kind, words))
            lx += 34 + len(words) * 5.8 + 30
        out.append("".join(out2))
    else:
        out.append(_legend(0, ly - 6, "solid", lg[0][1]) + _legend(170, ly - 6, "dash", lg[1][1]) + _legend(0, ly + 14, "tag", lg[2][1]))
        H += 20
    out.append(f'<circle class="tok idle" r="6" cx="0" cy="0" data-tok="1"/>')
    body = "".join(out)
    return (f'<svg class="ag loop" viewBox="0 0 {W} {H:g}" role="img" aria-labelledby="{p}-t"><title id="{p}-t">'
            f'{E("The agent feedback loop on the bench: spec and interview, role agents, simulators and formal, Vivado, the Nexys A7 board and the instruments, what each returns, the gate it enters, and the path back to the role agents")}'
            f'</title>{defs(p)}{body}</svg>')


def _legend(x, y, kind, words):
    if kind == "tag":
        w = 30
        g = box(x, y - 9, w, 14, "ptag", 7)
    else:
        dash = ' stroke-dasharray="5 4"' if kind == "dash" else ""
        g = f'<path class="ed" d="M{x} {y - 2} L{x + 30} {y - 2}"{dash}/>'
    return g + text(x + 38, y + 2, words, "s")


def legs_table(L, repo):
    """The legs, grouped by status, each with its evidence links (repository paths)."""
    names = {"automated": "Runs with no person today", "building": "Being built or measured", "person": "Needs a person today"}
    out = []
    for st in ("automated", "building", "person"):
        rows = [x for x in L["legs"] if x["status"] == st]
        items = []
        for x in rows:
            ev = " ".join(f'<a class="evsrc" href="{repo}/blob/main/{E(pth)}">{E(pth.split("/")[-1])}</a>' for pth in x["evidence"])
            items.append(f'<li data-leg="{E(x["id"])}"><b>{E(x["leg"])}</b> <span class="muted">{E(x["note"])}</span>'
                         + (f' <span class="evl">Evidence: {ev}</span>' if ev else "") + "</li>")
        out.append(f'<div class="legs lg-{st}"><h3>{E(names[st])} <span class="tag">{len(rows)}</span></h3><ul>{"".join(items)}</ul></div>')
    return '<div class="legcols">' + "".join(out) + "</div>"


def sources_table(L):
    rows = []
    for s in L["stations"]:
        if not s["fb"]:
            continue
        src = s["fb"]["src"]
        rows.append([s["title"], "; ".join(s["fb"]["values"]), (src["what"] + " (" + src["record"] + ")") if src else "no committed measurement yet"])
    return rows

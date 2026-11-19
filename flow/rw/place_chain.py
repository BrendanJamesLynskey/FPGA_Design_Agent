"""Capability 2 of brief 100: latency-aware placement of a chain of cells, with RapidWright. Run with the venv python. Usage:
  place_chain.py <in_placed.dcp> <out.dcp> <chain.json> [--seed N] [--iters N] [--crit file]
chain.json: {"cells": ["u_pcs/*", "u_mac/x_d_reg[*]", ...] (fnmatch on full cell names), "anchor": "GTHE4_CHANNEL_X0Y6",
             "window": {"cols": 60, "rows": 40}  (tile columns/rows around the anchor that the chain may use),
             "anchor_weight": 4.0 (weight of the nets that touch the anchor),
             "protect": {"cells": ["u_blk/*", "u_blk"], "regions": ["SLICE_X26Y70:SLICE_X37Y89"]}  (brief 102: a locked placed-and-routed block;
             optional: no chain cell may match a protected pattern (the run fails), no slice holding a protected cell moves, and no site inside a
             protected region is a target, free or not)}
The units that move are whole slices (a SiteInst with its LUT/FF assignment, so Vivado's packing stays legal), only slices with no
carry chain, no LUT-RAM and no shift-register cell, only to a free site of the same type. Simulated annealing on a weighted half-perimeter
wire length in tile units. That cost is RapidWright's estimate of nothing physical: it is never reported as a result. The output checkpoint
has the moved slices' nets unrouted (the rest keep their routing); Vivado's route_design routes it and Vivado's report_timing judges it.
One JSON line on stdout: moved slices, the estimate before and after (for the log only), the time."""
import fnmatch
import json
import math
import random
import sys
import time

import rapidwright  # noqa: F401
from com.xilinx.rapidwright.design import Design, DesignTools
from com.xilinx.rapidwright.device import SiteTypeEnum

src, dst, cfgfile = sys.argv[1], sys.argv[2], sys.argv[3]
opts = sys.argv[4:]
seed = int(opts[opts.index("--seed") + 1]) if "--seed" in opts else 1
iters = int(opts[opts.index("--iters") + 1]) if "--iters" in opts else 200000
cfg = json.load(open(cfgfile))
rnd = random.Random(seed)
t_start = time.time()

d = Design.readCheckpoint(src)
DesignTools.createMissingSitePinInsts(d)       # a placed, unrouted checkpoint has no site pins on its nets yet
dev = d.getDevice()
anchor = dev.getSite(cfg["anchor"])
acol, arow = int(anchor.getTile().getColumn()), int(anchor.getTile().getRow())
win_c, win_r = cfg["window"]["cols"], cfg["window"]["rows"]
aw = float(cfg.get("anchor_weight", 4.0))
pats = cfg["cells"]
SLICE_TYPES = (SiteTypeEnum.SLICEL, SiteTypeEnum.SLICEM)
BAD_PREFIX = ("CARRY", "RAM", "SRL", "LUTRAM")


def is_chain(name):
    return any(fnmatch.fnmatchcase(name, p) for p in pats)


import re  # noqa: E402
prot_cells = (cfg.get("protect") or {}).get("cells", [])
prot_rects = []
for r in (cfg.get("protect") or {}).get("regions", []):
    m = re.match(r"SLICE_X(\d+)Y(\d+):SLICE_X(\d+)Y(\d+)$", r)
    x0, y0, x1, y1 = (int(v) for v in m.groups())
    prot_rects.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))


def is_protected(name):
    return any(fnmatch.fnmatchcase(name, p) for p in prot_cells)


def in_protected_region(site_name):
    m = re.match(r"SLICE_X(\d+)Y(\d+)$", site_name)
    return bool(m) and any(r[0] <= int(m.group(1)) <= r[2] and r[1] <= int(m.group(2)) <= r[3] for r in prot_rects)


bad = [str(c.getName()) for c in d.getCells() if is_chain(str(c.getName())) and is_protected(str(c.getName()))]
if bad:
    print(json.dumps({"ok": False, "error": "chain patterns select cells inside a protected (locked, placed-and-routed) block", "cells": bad[:5]}))
    sys.exit(2)


# --- units: slices that hold at least one chain cell and nothing that must stay put ---------------------------------
units, fixed_units = {}, 0
for si in d.getSiteInsts():
    if si.getSiteTypeEnum() not in SLICE_TYPES:
        continue
    cells = list(si.getCells())
    if not any(is_chain(str(c.getName())) for c in cells):
        continue
    if any(is_protected(str(c.getName())) for c in cells):
        fixed_units += 1                            # a slice shared with a protected cell never moves
        continue
    if any(str(c.getType()).startswith(BAD_PREFIX) for c in cells):
        fixed_units += 1
        continue
    units[str(si.getName())] = si
site_xy = {}


def xy(site):
    k = str(site.getName())
    if k not in site_xy:
        t = site.getTile()
        site_xy[k] = (int(t.getColumn()), int(t.getRow()))
    return site_xy[k]


pos = {n: xy(si.getSite()) for n, si in units.items()}
start_pos = dict(pos)
# --- free sites of each type in the window --------------------------------------------------------------------------
occupied = {str(si.getSite().getName()) for si in d.getSiteInsts()}
mine = {str(units[n].getSite().getName()) for n in units}
free = {SiteTypeEnum.SLICEL: [], SiteTypeEnum.SLICEM: []}
for st in SLICE_TYPES:
    for s in dev.getAllSitesOfType(st):
        c, r = xy(s)
        if abs(c - acol) <= win_c and abs(r - arow) <= win_r:
            n = str(s.getName())
            if (n not in occupied or n in mine) and not in_protected_region(n):
                free[st].append(s)
site_of = {n: units[n].getSite() for n in units}
unit_type = {n: units[n].getSiteTypeEnum() for n in units}
by_xy = {st: {} for st in SLICE_TYPES}
for st in SLICE_TYPES:
    for s in free[st]:
        by_xy[st][xy(s)] = s
taken = {str(site_of[n].getName()) for n in units}

# --- nets: movable pins by unit, fixed pins as a bounding box -----------------------------------------------------
nets = []     # (weight, {unit: npins}, fixed_bbox or None)
unit_nets = {n: [] for n in units}
crit = {}
if "--crit" in opts:
    for l in open(opts[opts.index("--crit") + 1]):
        p = l.split()
        if len(p) == 2:
            crit[p[0]] = float(p[1])
for net in d.getNets():
    if net.isClockNet() or net.isStaticNet():
        continue
    pins = list(net.getPins())
    if len(pins) < 2 or len(pins) > 64:
        continue
    mov, fx = {}, []
    touches_anchor = False
    for p in pins:
        sn = str(p.getSiteInst().getName())
        if sn in units:
            mov[sn] = mov.get(sn, 0) + 1
        else:
            t = p.getTile()
            fx.append((int(t.getColumn()), int(t.getRow())))
            if str(p.getSite().getName()) == cfg["anchor"]:
                touches_anchor = True
    if not mov:
        continue
    w = crit.get(str(net.getName()), 1.0) * (aw if touches_anchor else 1.0)
    bb = None
    if fx:
        bb = (min(c for c, _ in fx), max(c for c, _ in fx), min(r for _, r in fx), max(r for _, r in fx))
    k = len(nets)
    nets.append((w, mov, bb))
    for u in mov:
        unit_nets[u].append(k)


def net_cost(k, over=None):
    w, mov, bb = nets[k]
    c0, c1, r0, r1 = bb if bb else (10**9, -10**9, 10**9, -10**9)
    for u in mov:
        c, r = (over[u] if over and u in over else pos[u])
        c0, c1, r0, r1 = min(c0, c), max(c1, c), min(r0, r), max(r1, r)
    return w * ((c1 - c0) * 0.5 + (r1 - r0))      # a tile row is one CLB row; a CLB column is two tile columns (CLB and INT)


def total():
    return sum(net_cost(k) for k in range(len(nets)))


cost0 = total()
names = list(units)
T0 = max(cost0 / max(len(nets), 1) * 0.5, 0.5)
accepted = 0
if names:
    for it in range(iters):
        T = T0 * (1 - it / iters) ** 3 + 1e-3
        u = names[rnd.randrange(len(names))]
        st = unit_type[u]
        c, r = pos[u]
        rad = max(2, int(10 * (1 - it / iters)) + 2)
        cand = by_xy[st].get((c + rnd.randint(-2 * rad, 2 * rad), r + rnd.randint(-rad, rad)))
        if cand is None:
            continue
        cn = str(cand.getName())
        if cn in taken and cn != str(site_of[u].getName()):
            continue
        new = xy(cand)
        if new == pos[u]:
            continue
        old = sum(net_cost(k) for k in unit_nets[u])
        newc = sum(net_cost(k, {u: new}) for k in unit_nets[u])
        dlt = newc - old
        if dlt <= 0 or rnd.random() < math.exp(-dlt / T):
            taken.discard(str(site_of[u].getName()))
            taken.add(cn)
            site_of[u] = cand
            pos[u] = new
            accepted += 1
cost1 = total()
# --- apply: unplace every moved slice first, then place, so a swap into a vacated site is legal ----------------------
moved = [n for n in units if str(site_of[n].getName()) != str(units[n].getSite().getName())]
unrouted = set()
for n in moved:                      # a moved slice's nets lose their routing; Vivado's route_design routes them and keeps the rest
    for p in units[n].getSitePinInsts():   # clock and static nets too: their trees reached the old site
        net = p.getNet()
        if net is not None and str(net.getName()) not in unrouted:
            net.unroute()
            unrouted.add(str(net.getName()))
for n in moved:
    units[n].unPlace()
for n in moved:
    units[n].place(site_of[n])
d.writeCheckpoint(dst)
print(json.dumps({"units": len(units), "units_fixed_by_rule": fixed_units, "moved": len(moved), "nets_unrouted": len(unrouted), "nets": len(nets), "accepted_moves": accepted,
                  "estimate_before": round(cost0, 1), "estimate_after": round(cost1, 1), "seed": seed, "iters": iters,
                  "seconds": round(time.time() - t_start, 1), "estimate_note": "RapidWright's own weighted HPWL; not a result"}))

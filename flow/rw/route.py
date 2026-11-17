"""Capability 3 of brief 100: route with RWRoute (RapidWright's router) instead of Vivado's. Run with the venv python. Usage:
  route.py full  <in.dcp> <out.dcp> [timing|nontiming]   route every net of a placed (or partly routed) checkpoint with RWRoute
  route.py complete <in.dcp> <out.dcp>                  route only the pins left unrouted, with soft preserve: routes already in the checkpoint
                                                         (locked blocks) stay unless a pin cannot be reached without ripping one up
  route.py nets  <in.dcp> <out.dcp> <netfile>            route only the nets named in <netfile> (one full net name per line), then
                                                         lock them (fixed routes); Vivado's route_design completes the rest
One JSON line on stdout: the mode, RWRoute's wall time, nets routed. RWRoute is timing-driven by its own estimate of delay (it reads the
clock period from the checkpoint's constraints); that estimate is not a result: Vivado's report_timing on the written checkpoint is."""
import json
import sys
import time

import rapidwright  # noqa: F401
from com.xilinx.rapidwright.design import Design
from com.xilinx.rapidwright.rwroute import PartialRouter, RWRoute

mode, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
d = Design.readCheckpoint(src)
t0 = time.time()
out = {"mode": mode}
if mode == "full":
    timing = (sys.argv[4] if len(sys.argv) > 4 else "timing") == "timing"
    d = RWRoute.routeDesignFullTimingDriven(d) if timing else RWRoute.routeDesignFullNonTimingDriven(d)
    out["timing_driven"] = timing
elif mode == "complete":
    pins = PartialRouter.getUnroutedPins(d)
    out["unrouted_pins_before"] = int(pins.size())
    d = PartialRouter.routeDesignPartialTimingDriven(d, pins, True)
    out["unrouted_pins_after"] = int(PartialRouter.getUnroutedPins(d).size())
elif mode == "nets":
    names = [l.strip() for l in open(sys.argv[4]) if l.strip()]
    from java.util import ArrayList
    pins = ArrayList()
    missing = []
    for n in names:
        net = d.getNet(n)
        if net is None:
            missing.append(n)
            continue
        net.unroute()
        for p in net.getSinkPins():
            pins.add(p)
    d = PartialRouter.routeDesignPartialTimingDriven(d, pins, True)
    locked = 0
    for n in names:
        net = d.getNet(n)
        if net is not None and net.hasPIPs():
            net.lockRouting()
            locked += 1
    out.update({"nets_requested": len(names), "nets_locked": locked, "missing": missing})
out["route_s"] = round(time.time() - t0, 2)
t1 = time.time()
d.writeCheckpoint(dst)
out["write_s"] = round(time.time() - t1, 2)
out["nets_with_pips"] = sum(1 for n in d.getNets() if n.hasPIPs())
print(json.dumps(out))

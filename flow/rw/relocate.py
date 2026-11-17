"""Capability 1 of brief 100: move a pre-implemented block (placement and routing) by a tile offset and write the checkpoint.
Run with the venv python (designs/b100_rapidwright/scripts/rw.sh). Usage:
  relocate.py options <in.dcp>                    print RapidWright's valid relocation options for the block
  relocate.py move <in.dcp> <out.dcp> <dx> <dy>   relocate by dx tile columns and dy tile rows; one JSON line on stdout
  relocate.py moveto <in.dcp> <out.dcp> <SITE>    relocate so that the block's anchor slice lands on SITE (for example SLICE_X41Y70)
The block keeps its routing: only the tiles change, so the delays inside it are the delays Vivado routed, moved (they differ only where
the device differs: tile types, clock-region crossings). Vivado's report_timing on the stamped design is the referee."""
import json
import sys

import rapidwright  # noqa: F401
from com.xilinx.rapidwright.design import Design
from com.xilinx.rapidwright.design.tools import RelocationTools
from java.lang import System

mode = sys.argv[1]
d = Design.readCheckpoint(sys.argv[2])


def bbox(design):
    xs, ys = [], []
    for si in design.getSiteInsts():
        t = si.getTile()
        xs.append(int(t.getColumn()))
        ys.append(int(t.getRow()))
    return {"col": [min(xs), max(xs)], "row": [min(ys), max(ys)], "site_insts": len(xs)}


if mode == "options":
    opts = RelocationTools.getValidRelocationOptions(d)
    RelocationTools.printValidRelocationOptions(opts, 40, System.out)
    print(json.dumps({"bbox": bbox(d)}))
else:
    a = RelocationTools.getValidRelocationOptions(d).getFirst()
    if mode == "moveto":
        t = d.getDevice().getSite(sys.argv[4]).getTile()
        dx, dy = int(t.getTileXCoordinate()) - int(a.getTile().getTileXCoordinate()), int(t.getTileYCoordinate()) - int(a.getTile().getTileYCoordinate())
    else:
        dx, dy = int(sys.argv[4]), int(sys.argv[5])
    before = bbox(d)
    nets_before = sum(1 for n in d.getNets() if n.hasPIPs())
    ok = bool(RelocationTools.relocate(d, d.getSiteInsts(), dx, dy))
    out = {"ok": ok, "dx": dx, "dy": dy, "nets_with_pips_before": nets_before, "before": before, "target": sys.argv[4] if mode == "moveto" else None}
    if ok:
        out["after"] = bbox(d)
        out["nets_with_pips_after"] = sum(1 for n in d.getNets() if n.hasPIPs())
        out["anchor_before"] = str(a.getName())
        t = a.getTile()
        out["anchor_after"] = str(d.getDevice().getSite(sys.argv[4]).getName()) if mode == "moveto" else None
        d.writeCheckpoint(sys.argv[3])
    print(json.dumps(out))

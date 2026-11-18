"""Stage 0 of brief 100: read a Vivado checkpoint with RapidWright and write it back (run with the venv python, see
flow/rapidwright_pin.py). Prints one JSON line: the part, cell and net counts, whether the design is placed and routed, and the
read and write times. Usage: roundtrip.py <in.dcp> <out.dcp>"""
import json
import sys
import time

import rapidwright  # noqa: F401  (starts the JVM)
from com.xilinx.rapidwright.design import Design

t0 = time.time()
d = Design.readCheckpoint(sys.argv[1])
t1 = time.time()
routed = sum(1 for n in d.getNets() if n.hasPIPs())
placed = sum(1 for c in d.getCells() if c.isPlaced())
d.writeCheckpoint(sys.argv[2])
t2 = time.time()
print(json.dumps({"part": str(d.getPartName()), "cells": len(d.getCells()), "placed_cells": placed, "nets": len(d.getNets()),
                  "nets_with_pips": routed, "read_s": round(t1 - t0, 2), "write_s": round(t2 - t1, 2),
                  "rapidwright": rapidwright.version}))

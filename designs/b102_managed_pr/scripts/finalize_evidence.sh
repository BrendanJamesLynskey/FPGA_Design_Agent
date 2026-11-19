#!/usr/bin/env bash
# finalize_evidence.sh: the records of stage 2 after run_placements.sh and run_dumps.sh and the flow build (flow/run_vivado.sh designs/b102_managed_pr base):
# the import check with simulation (and its planted fault), the placement evidence for all placements and for the adopted ones, the build's gates
# recorded as 'built' evidence, the boundary budgets on the routed build, and the computed trust labels. Needs the heavy slot (one short Vivado run),
# the OSS CAD Suite (FDA_OSS_CAD) and Icarus Verilog.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$HERE/../.."; cd "$ROOT"
R=results/102_managed_pr; W=designs/b102_managed_pr/build/pr; D=designs/b102_managed_pr
ADOPTED="${ADOPTED:-p0,p0x,p0y,p1}"
[ -n "${FDA_OSS_CAD:-}" ] && export PATH="$FDA_OSS_CAD/bin:$PATH"
python3 flow/managed_placed.py check $D --sim --out $R/import_check.json >/dev/null
python3 - <<'PY'
import json, re, sys
from pathlib import Path
sys.path.insert(0, ".")
from flow import managed_placed as MP
w = Path("designs/b102_managed_pr/build/managed/import/blk")
src = (w / "funcsim.v").read_text()
m = re.search(r"\.INIT\(64'h([0-9A-Fa-f]{16})\)", src)
bad = src[:m.start()] + f".INIT(64'h{int(m.group(1), 16) ^ 1:016X})" + src[m.end():]
(w / "funcsim_fault.v").write_text(bad)
refs = [Path("designs/b102_managed_pr/ext/reference") / f for f in ("b96_pkg.sv", "pcs_tx.sv", "pcs_unit.sv")]
r = MP.simulate_vs_reference(w / "funcsim_fault.v", refs, "pcs_unit", w / "sim_fault")
Path("results/102_managed_pr/import_fault.json").write_text(json.dumps({"planted": "one INIT bit flipped in the first LUT of the functional netlist: " + m.group(0), "simulation": r}, indent=1) + "\n")
assert r["passed"] is False
PY
python3 flow/managed_placed.py compare $D $W --out $R/placements/placement_evidence_all.json >/dev/null || true
python3 flow/managed_placed.py compare $D $W --only "$ADOPTED" --out $R/placements/placement_evidence.json >/dev/null
python3 flow/managed_import.py record-build $D $D/build/base >/dev/null
mkdir -p $R/build_base
for f in gates.json timing_summary.rpt utilization.rpt; do [ -f $D/build/base/$f ] && cp $D/build/base/$f $R/build_base/; done
python3 - <<'PY'
import json
g = json.load(open("designs/b102_managed_pr/build/base/gates.json"))
t, u, p = g["timing"], g["utilization"], g["power"]
json.dump({"vivado": g["vivado_version"], "part": "xck26-sfvc784-2LV-c", "clock_ns": 4.0,
           "builds": {"baseline": {"gates_pass": g["pass"], "lut": u["lut"], "ff": u["ff"], "wns_ns": t["wns_ns"], "whs_ns": t["whs_ns"],
                                   "build_stamp": g["build_stamp"], "power_w": p["total_w"]}}},
          open("results/102_managed_pr/builds.json", "w"), indent=1)
open("results/102_managed_pr/builds.json", "a").write("\n")
PY
python3 flow/managed_import.py budget-tcl $D "$ROOT/$D/build/base/post_route.dcp" $W/budget_route.tcl >/dev/null
designs/b100_rapidwright/scripts/viv.sh "$ROOT/$W/budget_route.tcl" "$ROOT/$W/budget_route.log" || true
grep '^BUDGET|' $W/budget_route.log > $R/budgets_baseline.txt || true
python3 flow/managed_import.py boundary $D $D/build/base --budgets $R/budgets_baseline.txt --out $R/boundary.json >/dev/null || true
python3 - <<'PY'
import json, sys
sys.path.insert(0, ".")
from pathlib import Path
from agent.core import managed as M
p = M.load(Path("designs/b102_managed_pr"))
out = {c.name: {"ownership": c.ownership, "trust": M.trust(p, c)[0], "why_not_higher": M.trust(p, c)[1]} for c in p.components}
Path("results/102_managed_pr/trust.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
PY

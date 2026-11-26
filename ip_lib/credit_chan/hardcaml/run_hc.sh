#!/usr/bin/env bash
# Build the Hardcaml credit_chan and drive the existing cocotb benches and formal wrapper on its generated Verilog (brief 171).
# usage: ip_lib/credit_chan/hardcaml/run_hc.sh {gen|sim|formal}   (run from anywhere)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"
export OPAMROOT="${OPAMROOT:-$HOME/.local/opt/opam}" PATH="$HOME/.local/opt/opam-bin:$PATH"
eval "$(opam env --switch=hardcaml-5.3.0)"
mkdir -p "$HERE/build/rtl"
# the parameter points of the existing bench (tb/test_credit_chan_rtl.py: POINTS, and SIDEBAND with tlast, tkeep, tuser 5) plus the default
POINTS=$(python3 - <<PY
import re
src=open("$ROOT/ip_lib/credit_chan/tb/test_credit_chan_rtl.py").read()
ns={}
exec(re.search(r"^POINTS = .*?\]\n", src, re.S|re.M).group(0), ns)
exec(re.search(r"^SIDEBAND = \[.*?\]", src, re.M).group(0), ns)
pts=[p+(0,0,0) for p in ns["POINTS"]]+[p+(1,1,5) for p in ns["SIDEBAND"]]+[(32,8,1,1,0,0,0)]
print(" ".join(",".join(map(str,p)) for p in pts))
PY
)
case "${1:-gen}" in
gen)
  (cd "$HERE" && dune build 2>&1)
  (cd "$HERE" && dune exec src/gen.exe -- build/rtl/credit_chan.sv $POINTS)
  (cd "$HERE" && dune exec src/gen.exe -- formal/credit_chan_formal.sv -formal 4,1,0,0,0,0,0 4,2,0,0,0,0,0 4,1,1,1,0,0,0 4,2,1,1,0,0,0 4,3,1,1,0,0,0 4,4,1,1,0,0,0 4,2,2,1,0,0,0 4,3,0,2,0,0,0 4,5,2,2,0,0,0 4,4,3,0,0,0,0) ;;
sim)  "$0" gen
  cd "$ROOT" && NET_RTL_CREDIT_CHAN="$HERE/build/rtl" python3 -m pytest -q ip_lib/credit_chan/tb/test_credit_chan_rtl.py -p no:cacheprovider ;;
formal) "$0" gen
  export PATH="$HOME/.local/opt/oss-cad-suite/bin:$PATH"
  cd "$HERE/formal" && for t in $(grep -E '^[a-z0-9]+_(prove|bmc) (prove|bmc) ' credit_hc.sby | cut -d' ' -f1); do
    sby -f -d "$HERE/build/sby_$t" credit_hc.sby "$t" >/dev/null 2>&1 || true
    echo "$t $(head -1 "$HERE/build/sby_$t/status" 2>/dev/null | cut -d' ' -f1)"
  done ;;
esac

#!/usr/bin/env bash
# Build the Hardcaml pipe_reg and drive the existing cocotb benches, formal wrapper and lint on its generated Verilog
# (brief 171).  usage: ip_lib/pipe_reg/hardcaml/run_hc.sh {gen|sim|formal|lint}   (run from anywhere)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"
export OPAMROOT="${OPAMROOT:-$HOME/.local/opt/opam}" PATH="$HOME/.local/opt/opam-bin:$PATH"
eval "$(opam env --switch=hardcaml-5.3.0)"
mkdir -p "$HERE/build/rtl"
# the parameter points the existing bench (ip_lib/pipe_reg/tb/test_pipe_reg_rtl.py POINTS) uses, plus the formal points
POINTS=$(python3 - <<PY
import re,sys
src=open("$ROOT/ip_lib/pipe_reg/tb/test_pipe_reg_rtl.py").read()
ns={}
exec(re.search(r"^POINTS = .*?\n\n", src, re.S|re.M).group(0), ns)
print(" ".join(",".join(map(str,p)) for p in ns["POINTS"]))
PY
)
POINTS="$POINTS 32,1,1,0,0,0"   # the default point: tools that elaborate the top with its defaults (slang, Vivado) need it
case "${1:-gen}" in
gen)
  (cd "$HERE" && dune build 2>&1)
  (cd "$HERE" && dune exec src/gen.exe -- build/rtl/pipe_reg.sv $POINTS)
  (cd "$HERE" && dune exec src/gen.exe -- formal/pipe_reg_formal.sv -formal 4,1,0,0,0,0 4,3,0,0,0,0 4,1,1,0,0,0 4,2,1,0,0,0 4,3,1,0,0,0 4,1,2,0,0,0 4,2,2,0,0,0 4,3,2,0,0,0 4,1,3,0,0,0 4,2,3,0,0,0 4,1,4,0,0,0 4,2,4,0,0,0 4,3,4,0,0,0 4,0,1,0,0,0) ;;
sim)  "$0" gen
  cd "$ROOT" && NET_RTL_PIPE_REG="$HERE/build/rtl" python3 -m pytest -q ip_lib/pipe_reg/tb/test_pipe_reg_rtl.py -p no:cacheprovider ;;
formal) "$0" gen
  export PATH="$HOME/.local/opt/oss-cad-suite/bin:$PATH"
  cd "$HERE/formal" && for t in $(grep -E '^[a-z0-9]+_(prove|bmc) (prove|bmc) ' pipe_hc.sby | cut -d' ' -f1); do
    sby -f -d "$HERE/build/sby_$t" pipe_hc.sby "$t" >/dev/null 2>&1 || true
    echo "$t $(head -1 "$HERE/build/sby_$t/status" 2>/dev/null | cut -d' ' -f1)"
  done ;;
esac

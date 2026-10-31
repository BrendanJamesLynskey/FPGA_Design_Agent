#!/usr/bin/env bash
# lint.sh: Verilator --lint-only -Wall on the shell and on every design's board top.
# A design may keep lint-only stand-ins for vendor primitives (e.g. STARTUPE2) in designs/<name>/lint/.
# CI installs Verilator from apt; locally: source ~/.local/opt/verilator-deb/env.sh first.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
verilator --version
echo "lint: shell (fpga_shell)"
verilator --lint-only -Wall --top-module fpga_shell shell/rtl/*.sv
for d in designs/*/; do
  [ -f "$d/build.yaml" ] || continue
  top="$(python3 -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['top'])" "$d/build.yaml")"
  echo "lint: $d ($top)"
  stubs=(); [ -d "$d/lint" ] && stubs=("$d"lint/*.sv)    # lint-only stand-ins for vendor primitives
  verilator --lint-only -Wall --top-module "$top" shell/rtl/*.sv "$d"rtl/*.sv "${stubs[@]}"
done
echo "lint: clean"

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
# the block-design crossbar on its own at a many-to-many point (a design's top lints it only at that design's point),
# and the block-design support RTL at its default parameters; the generated tops are linted below with each design
echo "lint: ip_lib/axil_xbar (3 masters, 4 slaves)"
verilator --lint-only -Wall --top-module axil_xbar -GN_M=3 -GN_S=4 -GADDR_W=32 \
  "-GS_BASE=128'h00008000_00002000_00001000_00000000" "-GS_BITS=32'h0f0c0c0c" ip_lib/axil_xbar/rtl/axil_xbar.sv
for t in bd_axil_regs bd_axil_win bd_win_axil_master; do
  echo "lint: flow/blockdesign/rtl/$t"; verilator --lint-only -Wall --top-module "$t" "flow/blockdesign/rtl/$t.sv"
done
for d in designs/*/; do
  [ -f "$d/build.yaml" ] || continue
  top="$(python3 -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['top'])" "$d/build.yaml")"
  echo "lint: $d ($top)"
  stubs=(); for s in "$d"lint/*.sv; do [ -f "$s" ] && stubs+=("$s"); done    # lint-only stand-ins (lint/ may hold only waivers.yaml)
  cfgs=(); for s in "$d"lint/*.vlt; do [ -f "$s" ] && cfgs+=("$s"); done     # brief 58A: Verilator configuration (waivers), read first
  # the sources are the ones the build uses (build.yaml): brief 30's designs also read ip_lib blocks and share RTL
  mapfile -t srcs < <(python3 -c "import yaml,sys,glob; [print(f) for g in yaml.safe_load(open(sys.argv[1]))['sources'] for f in sorted(glob.glob(g))]" "$d/build.yaml")
  verilator --lint-only -Wall --top-module "$top" "${cfgs[@]}" "${stubs[@]}" "${srcs[@]}"
done
echo "lint: clean"

#!/usr/bin/env bash
# Brief 156: does GHDL give code coverage? Try every spelling GHDL's documentation or NVC-style tools suggest, on both local builds.
# Output (stdout) is committed as ghdl_coverage_probe.txt.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../55_vhdl/translations/A/t1_sync_fifo_regs/rtl/sync_fifo_regs.vhd"
W="$(mktemp -d)"
cd "$W"
for G in "$HOME/.local/bin/ghdl" "$HOME/.local/opt/oss-cad-suite/bin/ghdl"; do
  echo "=== $($G --version | head -1) ($G)"
  for opt in -fprofile-arcs -ftest-coverage --coverage --cover; do
    echo "--- analysis with $opt"; "$G" -a --std=08 $opt "$SRC" 2>&1 | head -2
  done
  "$G" -a --std=08 "$SRC" >/dev/null 2>&1
  for opt in "-fprofile-arcs -ftest-coverage -Wl,-lgcov" "-Wc,-fprofile-arcs -Wl,-lgcov"; do
    echo "--- elaboration with $opt"; "$G" -e --std=08 $opt sync_fifo_regs 2>&1 | head -2
  done
  echo "--- analysis, elaboration and run with --coverage (the option analysis accepted)"
  rm -rf cov && mkdir cov && (cd cov && "$G" -a --std=08 --coverage "$SRC" >/dev/null 2>&1 && "$G" -e --std=08 --coverage sync_fifo_regs 2>&1 | head -2; \
    "$G" -r --std=08 --coverage sync_fifo_regs --stop-time=100ns 2>&1 | grep -v '^\*\*\*\*' | head -3; echo "files written: $(ls | tr '\n' ' ')")
  echo "--- ghdl coverage"; "$G" coverage 2>&1 | head -2
done
echo "=== what GHDL does report: PSL cover/assert counts (--psl-report), not statement/branch/toggle coverage"

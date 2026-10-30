#!/usr/bin/env bash
# run_mutants.sh: show that T1's tests catch broken RTL. Each mutant is one
# deliberate bug applied with sed to a copy of rtl/ under build/mutants/; the
# same pytest entry runs against the copy and must FAIL. The real RTL is never
# touched. Exit 0 only if every mutant is caught (and the sed changed the file).
#
#   designs/t1_dimmer_counter/tests/run_mutants.sh          (from the repo root)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DESIGN="$ROOT/designs/t1_dimmer_counter"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY=python3

# name | file | sed expression | the bug
MUTANTS=(
  "debounce_short|debounce.sv|s/CW'(CYCLES - 1)/CW'(CYCLES - 2)/|debounce accepts a level one clock early"
  "pwm_le|dimmer_counter.sv|s/(phase < duty_eff)/(phase <= duty_eff)/|PWM on for one phase step too many"
  "glyph_b|sevenseg_scan.sv|s/4'hB: glyph = 7'b1111100/4'hB: glyph = 7'b1111110/|digit b shows an extra segment"
  "down_saturates|dimmer_counter.sv|s/else if (p_down)                   count <= count - 1'b1;/else if (p_down \&\& count != 0) count <= count - 1'b1;/|down stops at 0 instead of wrapping"
  "press_wins|dimmer_counter.sv|s/if (win_wr \&\& win_addr == R_COUNT) count/if (win_wr \&\& win_addr == R_COUNT \&\& !p_up \&\& !p_down \&\& !p_clear) count/|a press on the clock of a COUNT write beats the write"
)

caught=0
for row in "${MUTANTS[@]}"; do
  IFS='|' read -r name file expr why <<<"$row"
  dir="$ROOT/build/mutants/$name"
  rm -rf "$dir" && mkdir -p "$dir" && cp "$DESIGN"/rtl/*.sv "$dir/"
  sed -i "$expr" "$dir/$file"
  if cmp -s "$DESIGN/rtl/$file" "$dir/$file"; then
    echo "MUTANT $name: sed did not change $file (fix the expression)"; exit 2
  fi
  if (cd "$ROOT" && T1_RTL_DIR="$dir" T1_SIM_NAME="mutant_$name" "$PY" -m pytest -q -x \
        designs/t1_dimmer_counter/tests/test_t1_rtl.py >"$dir/pytest.log" 2>&1); then
    echo "MUTANT $name: NOT caught ($why)"
  else
    failed=$(grep -o 't1_cocotb\.[a-z_]* *FAIL' "$ROOT/build/sim/mutant_$name/sim.log" | awk '{print $1}' | sed 's/t1_cocotb\.//' | paste -sd, -)
    echo "MUTANT $name: caught by [$failed] ($why)"
    caught=$((caught + 1))
  fi
done
echo "caught $caught of ${#MUTANTS[@]}"
[ "$caught" -eq "${#MUTANTS[@]}" ]

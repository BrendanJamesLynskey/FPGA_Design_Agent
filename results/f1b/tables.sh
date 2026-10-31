#!/usr/bin/env bash
# Remake every F1B table from the committed CSVs, with the CVDP RTL Agent's own tools at the commit the runs used.
#
#   CVDP_DIR=<a clone of BrendanJamesLynskey/CVDP_RTL_Agent> bash results/f1b/tables.sh
#
# Writes results/f1b/paired_eval86.md, drift_eval86.md, vs_luna_old_eval86.md, reliability.md (and
# claude_code_eval86.md if the Claude Code run is in runs/). Nothing here calls an LLM; the numbers come only from
# runs/*.csv (collect.py rows, provider-reported cost) and reliability_rows.csv (counts from the uploaded traces).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
: "${CVDP_DIR:?set CVDP_DIR to a clone of CVDP_RTL_Agent}"
COMMIT=aa7404cbd98ac97cb55ad8caea68cd4c4915badd  # the runs' commit; its tools/ are the analysis tools
tools=$(mktemp -d)
trap 'rm -rf "$tools"' EXIT
git -C "$CVDP_DIR" fetch -q origin f1b-model-screen 2>/dev/null || true
git -C "$CVDP_DIR" archive "$COMMIT" tools | tar -x -C "$tools"
T="$tools/tools"
ids="$T/m3b_eval_ids.txt"
echo "de88c76a626e93c80288eacf08036e6ce460049a10cceec464ccbcced1af54bf  $ids" | sha256sum -c --quiet -
r="$here/runs"
arm() { ls "$r"/"$1"[0-9]_*.csv | paste -sd,; }
# the candidate arms with scored runs (G had none valid and X was dropped: PREREG deviations 2 and 3)
cands=""; for a in D G X; do ls "$r"/"$a"[0-9]_*.csv >/dev/null 2>&1 && cands="$cands --arm $a=$(arm $a)"; done
old="$here/luna_old"

# shellcheck disable=SC2086
python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base L --arm "L=$(arm L)" $cands > "$here/paired_eval86.md"
python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base luna_old --arm "luna_old=$(ls "$old"/*.csv | paste -sd,)" \
  --arm "L=$(arm L)" > "$here/drift_eval86.md"
# shellcheck disable=SC2086
python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base luna_old --arm "luna_old=$(ls "$old"/*.csv | paste -sd,)" \
  $cands > "$here/vs_luna_old_eval86.md"
if ls "$r"/C1_*.csv >/dev/null 2>&1; then
  pick=$(cat "$here/pick.txt")
  python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base "$pick" --arm "$pick=$(arm "$pick")" --arm "C=$(arm C)" \
    > "$here/claude_code_eval86.md"
fi
python3 "$T/reliability.py" --from-csv "$here/reliability_rows.csv" --ids "$ids" > "$here/reliability.md"
python3 "$T/reliability.py" --from-csv "$here/reliability_rows_void.csv" --ids "$ids" > "$here/reliability_void.md"
echo "tables written to $here"
# Sensitivity (not pre-registered): D without D3, whose 8 llm_error stops were the account's 402s (REPORT.md)
python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base L --arm "L=$(arm L)" \
  --arm "D12=$(ls "$r"/D1_*.csv "$r"/D2_*.csv | paste -sd,)" > "$here/sensitivity_D1D2_eval86.md"

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
COMMIT=aa7404cbd98ac97cb55ad8caea68cd4c4915badd
tools=$(mktemp -d)
trap 'rm -rf "$tools"' EXIT
git -C "$CVDP_DIR" fetch -q origin f1b-model-screen 2>/dev/null || true
git -C "$CVDP_DIR" archive "$COMMIT" tools | tar -x -C "$tools"
T="$tools/tools"
ids="$T/m3b_eval_ids.txt"
echo "de88c76a626e93c80288eacf08036e6ce460049a10cceec464ccbcced1af54bf  $ids" | sha256sum -c --quiet -
r="$here/runs"
arm() { ls "$r"/"$1"[0-9]_*.csv | paste -sd,; }
old="$here/luna_old"

python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base L --arm "L=$(arm L)" --arm "D=$(arm D)" --arm "G=$(arm G)" \
  --arm "X=$(arm X)" > "$here/paired_eval86.md"
python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base luna_old --arm "luna_old=$(ls "$old"/*.csv | paste -sd,)" \
  --arm "L=$(arm L)" > "$here/drift_eval86.md"
python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base luna_old --arm "luna_old=$(ls "$old"/*.csv | paste -sd,)" \
  --arm "D=$(arm D)" --arm "G=$(arm G)" --arm "X=$(arm X)" > "$here/vs_luna_old_eval86.md"
if ls "$r"/C1_*.csv >/dev/null 2>&1; then
  pick=$(cat "$here/pick.txt")
  python3 "$T/ablate.py" --ids "$ids" --level 0.975 --base "$pick" --arm "$pick=$(arm "$pick")" --arm "C=$(arm C)" \
    > "$here/claude_code_eval86.md"
fi
python3 "$T/reliability.py" --from-csv "$here/reliability_rows.csv" --ids "$ids" > "$here/reliability.md"
echo "tables written to $here"

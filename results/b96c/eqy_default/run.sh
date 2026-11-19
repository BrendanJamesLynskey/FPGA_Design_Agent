#!/bin/bash
# Brief 96C addendum 2: formal equivalence (eqy, OSS CAD Suite, slang front end) of the RATE_MATCH = 0 core against main 6909e43f's core.
#   run.sh [default|all3|mutant]     default: base core against main's base core. all3: lat_all3's files with GO_REG = 0 against main's lat_all3 files.
#                                    mutant: the default gate with one planted change (the MAC's error counter counts by 2): must FAIL (the proof is not vacuous).
# Work directory: $WORK (default <repo>/build/eqy_<mode>, git-ignored). No Vivado, no board. About 5 minutes; result in result_<mode>.txt and partitions_<mode>.txt beside this script (the PASS or FAIL line and every partition).
set -uo pipefail
MODE="${1:-default}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; D=designs/b96_kr260_10g
WORK="${WORK:-$ROOT/build/eqy_$MODE}"; MAIN=6909e43f
export PATH="$HOME/.local/opt/oss-cad-suite/bin:$PATH"
rm -rf "$WORK"; mkdir -p "$WORK/gold" "$WORK/gate_rtl"; cd "$ROOT"
git archive $MAIN $D/rtl $D/lint $D/lat_all3/rtl | tar -x -C "$WORK/gold"          # gold: main's files, as committed
GR="$WORK/gold/$D"; N="$ROOT/$D/rtl"
python3 - "$GR/lint/gth_wiz_stub.sv" "$ROOT/$D/lint/gth_wiz_stub.sv" "$WORK" <<'PY'
import re, sys
def bb(src, dst):       # the lint stub's port list as an empty black box (its outputs are free signals, the same on both sides)
    s = open(src).read(); m = re.search(r"^\);", s, re.M)
    body = re.sub(r"^//.*\n", "", s[:m.end()], flags=re.M).replace("output logic", "output").replace("input  logic", "input")
    open(dst, "w").write("(* blackbox *) " + body + "\nendmodule\n")
bb(sys.argv[1], sys.argv[3] + "/gth_old_bb.sv"); bb(sys.argv[2], sys.argv[3] + "/gth_new_bb.sv")
PY
# the gate's core: the worktree's b96_core.sv with FOUR stated edits (the diff is printed and kept in gate_edits.diff)
cp "$N/b96_core.sv" "$WORK/gate_rtl/b96_core.sv"
sed -i "/12'h01C: begin ppm_step/d; /12'h01C: rd = /d; /12'h020: rd = /d" "$WORK/gate_rtl/b96_core.sv"          # TXPPM write, TXPPM read, GT_BUF read: registers 96C added
sed -i "s/h_addr < 12'h100 + 12'(4 \* NRXW)/h_addr < 12'h100 + 12'(4 * 18)/" "$WORK/gate_rtl/b96_core.sv"          # RXV read window: the 97C's 18 words (the 96C words read 0 by construction; bench checks it)
diff "$N/b96_core.sv" "$WORK/gate_rtl/b96_core.sv" > "$WORK/gate_edits.diff" || true; cat "$WORK/gate_edits.diff"
if [ "$MODE" = all3 ]; then
  GT="$GR/lat_all3/rtl/trade64.sv"; GX="$GR/lat_all3/rtl/tx_path.sv"; GC="$GR/lat_all3/rtl/b96_core.sv"; NT="$ROOT/$D/lat_all3/rtl/trade64.sv"; NX="$ROOT/$D/lat_all3/rtl/tx_path.sv"; EXTRA="-G GO_REG=0"
else
  GT="$GR/rtl/trade64.sv"; GX="$GR/rtl/tx_path.sv"; GC="$GR/rtl/b96_core.sv"; NT="$N/trade64.sv"; NX="$N/tx_path.sv"; EXTRA=""
fi
LEG="$N/rx_path_legacy.sv"
if [ "$MODE" = mutant ]; then
  cp "$LEG" "$WORK/rx_path_legacy.sv"; sed -i "s/if (m_err) c_err <= c_err + 32'd1;/if (m_err) c_err <= c_err + 32'd2;/" "$WORK/rx_path_legacy.sv"; LEG="$WORK/rx_path_legacy.sv"
fi
GS="$GR/rtl/b96_pkg.sv $GR/rtl/pcs_tx.sv $GR/rtl/pcs_rx.sv $GR/rtl/mac64_tx.sv $GR/rtl/mac64_rx.sv $GR/rtl/hs_vec.sv $GR/rtl/frame_src.sv $GT $GX $GR/rtl/rx_path.sv $GC"
NS="$N/b96_pkg.sv $N/pcs_tx.sv $N/pcs_rx.sv $N/mac64_tx.sv $N/mac64_rx.sv $N/hs_vec.sv $N/frame_src.sv $NT $N/rate_match.sv $N/rate_match_gp.sv $NX $N/rx_path.sv $LEG $WORK/gate_rtl/b96_core.sv"
GATE_READ="read_slang $HERE/xpm_wire.sv $WORK/gth_new_bb.sv $NS --top b96_core --allow-use-before-declare -G RATE_MATCH=0 $EXTRA"
HIDE="opt_clean -purge
select -set keep t:\$*dff* %co:+[Q] w:* %i
rename -hide w:* @keep %d i:* %d o:* %d"
# the gate's registers sit under the generate block g_old (the old receive path): drop that prefix so they match main's names
cat > "$WORK/names.ys" <<YS
plugin -i slang
$GATE_READ
hierarchy -top b96_core
flatten
prep -top b96_core
memory_map
tee -o $WORK/names_w.txt select -list w:g_old.*
tee -o $WORK/names_all.txt select -list w:*
YS
yosys -q "$WORK/names.ys" > "$WORK/names.log" 2>&1
python3 - "$WORK" <<'PY'
import sys
w = sys.argv[1]
allw = {l.strip().split('/', 1)[1] for l in open(w + '/names_all.txt') if '/' in l}
out = ["cd b96_core"]
for l in open(w + '/names_w.txt'):
    n = l.strip().split('/', 1)[1]; t = n.replace('g_old.', '')
    if t in allw: print("name collision, not renamed:", n); continue
    out.append("rename \\%s \\%s" % (n, t))
out.append("cd ..")
open(w + '/rename_gen.ys', 'w').write("\n".join(out) + "\n")
PY
cat > "$WORK/$MODE.eqy" <<EQY
[gold]
plugin -i slang
read_slang $HERE/xpm_wire.sv $WORK/gth_old_bb.sv $GS --top b96_core --allow-use-before-declare
hierarchy -top b96_core
flatten
prep -top b96_core
memory_map
$HIDE

[gate]
plugin -i slang
$GATE_READ
hierarchy -top b96_core
flatten
prep -top b96_core
memory_map
script $WORK/rename_gen.ys
$HIDE

[script]
hierarchy -top b96_core

[strategy sby]
use sby
depth 2
engine smtbmc bitwuzla
EQY
cd "$WORK"; eqy -f -j 2 "$MODE.eqy" > "$MODE.log" 2>&1; rc=$?
{ echo "mode $MODE; eqy exit $rc"; grep -E "Successfully proved designs equivalent|Failed to prove|DONE \(" "$MODE.log" | sed 's/^EQY *[0-9:]* //'; grep -c "Proved equivalence of partition" "$MODE.log" | sed 's/^/partitions proved: /'; } | tee result.txt
cp result.txt "$HERE/result_$MODE.txt"; cp gate_edits.diff "$HERE/gate_edits.diff"
grep -E "Successfully proved|Failed to prove|DONE|Elapsed clock" "$MODE.log" | sed 's/^EQY *[0-9:]* //' > "$HERE/partitions_$MODE.txt"

#!/usr/bin/env bash
# run_probe.sh: what each free simulator does with FSM coverage constructs (brief 24). Writes survey.txt beside it.
#   results/24_fsm/simprobe/run_probe.sh <scratch dir>
# Needs iverilog, Verilator 5.020 (~/.local/opt/verilator-deb) and 5.048 (~/.local/opt/verilator-5048), and xsim 2026.1 (brief 49 re-run).
set -u
S="$(cd "$(dirname "$0")" && pwd)"; W="${1:?scratch dir}"; mkdir -p "$W"; cd "$W"
OUT="$S/survey.txt"; : > "$OUT"
say() { echo "$*" | tee -a "$OUT"; }
cnt() { python3 - "$1" <<'PY'
import re, sys
kinds, arms, user = {}, [], []
for l in open(sys.argv[1], errors="replace"):
    if not l.startswith("C "): continue
    n = int(l.rsplit(" ", 1)[1]); f = dict(re.findall(r"\x01(\w+)\x02([^\x01]*)", l)); pg = f.get("page", "").split("/")[0]
    kinds[pg] = kinds.get(pg, 0) + 1
    if pg == "v_line" and f.get("o") == "case": arms.append((f["l"], n))
    if pg == "v_user": user.append((f.get("o"), n))
print("  point kinds:", dict(sorted(kinds.items())))
print("  case-arm line hits (line, hits):", sorted(arms, key=lambda x: int(x[0])))
print("  user cover points (name, hits):", user)
PY
}
say "== Icarus Verilog $(iverilog -V 2>&1 | head -1 | sed 's/ (.*//')"
for D in WITH_COVERGROUP WITH_COVERPROP; do
  r=$(iverilog -g2012 -D$D -o i.vvp "$S/probe_fsm.sv" "$S/tb_probe.sv" 2>&1 | head -1 | sed "s#$S/##"); say "  $D: ${r:-accepted}"
done
say "  code coverage: none (vvp has no coverage option)"
for V in deb 5048; do
  ( source ~/.local/opt/verilator-$V/env.sh; say "== Verilator $(verilator --version | cut -c1-24)"
    for D in WITH_COVERGROUP WITH_COVERPROP WITH_COVERPROP_IMPL; do
      rm -rf "obj_$V$D"
      r=$(verilator --binary --timing --assert --coverage --coverage-user -Wno-fatal -Wno-lint -Wno-style -D$D --top-module tb_probe -Mdir "obj_$V$D" "$S/probe_fsm.sv" "$S/tb_probe.sv" 2>&1 | grep -E "%Error|COVERIGN" | head -1 | sed "s#$S/##")
      say "  $D: ${r:-accepted}"
      if [ -x "obj_$V$D/Vtb_probe" ]; then ( cd "obj_$V$D"; { ./Vtb_probe +verilator+coverage+file+cov.dat; } >/dev/null 2>&1; [ -f cov.dat ] && cnt cov.dat | tee -a "$OUT" || say "  (this --binary main writes no coverage file in this version)" ); fi
    done )
done
say "== xsim $(/opt/Xilinx/2026.1/Vivado/bin/xsim -version 2>&1 | head -1)"
( set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; mkdir -p xs && cd xs   # set +u: the 2026.1 settings64.sh reads unset variables
  xvlog -sv -d WITH_COVERGROUP -d WITH_COVERPROP "$S/probe_fsm.sv" "$S/tb_probe.sv" >/dev/null 2>&1 && say "  covergroup and ##1 cover property: accepted by xvlog"
  xelab -debug off -cc_type sbct -cc_db cc1 tb_probe -s s1 >/dev/null 2>&1; xsim s1 -runall -cc_db cc1 >/dev/null 2>&1
  xcrg -cov_db_name cc1 -report_format all -report_dir rep -nolog > xcrg.out 2>&1; [ -d rep ] || say "  xcrg (coverage report): $(grep -v '^$' xcrg.out | tail -1)"
  [ -d rep ] && python3 - <<'PY' | tee -a "$OUT"
import glob, html, re
def txt(f):
    t = open(f).read(); t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S); return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))
g = txt(glob.glob("rep/functionalCoverageReport/grp0.html")[0]); m = re.search(r"cp_state (\d+) (\d+) (\d+) (\d+)", g)
print("  functional coverage (covergroup on state_q): expected %s, uncovered %s, covered %s, score %s%%" % m.groups() if m else "  functional: not parsed")
c = txt("rep/codeCoverageReport/dashboard.html"); m = re.search(r"Toggle Coverage Score (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+)", c)
print("  code coverage (statement, branch, condition, toggle %%): %s" % ", ".join(m.groups()[3:]) if m else "  code: not parsed")
PY
  [ -d rep ] && say "  no FSM coverage kind in xcrg; cover property hit counts are not in the xcrg reports"; true )

#!/bin/bash
# Brief 208 Quartus arms: <out root>. Each arm: project, compile, Timing Analyzer reports.
Q=/home/brendan/altera_lite/25.1std/quartus/bin
H=$(cd "$(dirname "$0")" && pwd)
root=$1; mkdir -p "$root"
arm() { # name family device top rtl generic(GF or -) sdc
  n=$1; fam=$2; dev=$3; top=$4; rtl=$5; gf=$6; sdc=$7
  d=$root/$n; mkdir -p "$d"; cd "$d" || return
  cat > mk.tcl <<EOT
project_new $n -overwrite
set_global_assignment -name FAMILY "$fam"
set_global_assignment -name DEVICE $dev
set_global_assignment -name TOP_LEVEL_ENTITY $top
set_global_assignment -name VERILOG_FILE $rtl
set_global_assignment -name SDC_FILE $sdc
set_global_assignment -name NUM_PARALLEL_PROCESSORS 1
EOT
  [ "$gf" != "-" ] && echo "set_parameter -name GF $gf" >> mk.tcl
  echo "project_close" >> mk.tcl
  echo "=== $n $(date +%H:%M:%S)"
  $Q/quartus_sh -t mk.tcl > mk.log 2>&1
  $Q/quartus_sh --flow compile $n > compile.log 2>&1; echo "compile rc=$?"
  $Q/quartus_sta -t $H/sta.tcl $n "$d" > sta.log 2>&1; echo "sta rc=$?"
  cd "$root"
}
ARMS=${ARMS:-all}
for fam in "Cyclone V:5CEBA4F23C7:cv" "MAX 10:10M50DAF484C7G:m10"; do
  IFS=: read -r F D S <<< "$fam"
  if [ "$ARMS" = gen ]; then arm ${S}_ctrl_gfoff_gen "$F" $D q_clkctrl $H/q_clkctrl.v '"OFF"' $H/gen.sdc; continue; fi
  arm ${S}_ctrl_gfoff "$F" $D q_clkctrl $H/q_clkctrl.v '"OFF"' $H/base.sdc
  arm ${S}_ctrl_gfoff_groups "$F" $D q_clkctrl $H/q_clkctrl.v '"OFF"' $H/groups.sdc
  arm ${S}_ctrl_gfon "$F" $D q_clkctrl $H/q_clkctrl.v '"ON"' $H/base.sdc
  arm ${S}_lut "$F" $D mux_lut $H/../designs/mux_lut.v - $H/base_lut.sdc
done

#!/bin/bash
# Equivalence of the draft CARRY8 mapping (drafts/pr_1/arith_map_carry8.v, run as the patched synth_xilinx would: techmap with -D HAS_CARRY8)
# against the RTL, with the CARRY8 model of +/xilinx/cells_sim.v. Usage: carry8_equiv.sh   (needs the OSS CAD Suite on PATH)
set -u
HERE=$(cd "$(dirname "$0")" && pwd); PATCHED=$HERE/../arith_map_carry8.v
cat > $HERE/c8.ys <<S
synth_xilinx -family xcup -noiopad -noclkbuf -run begin:fine
opt -full
xilinx_srl -variable -minlen 3
techmap -map +/techmap.v -D LUT_SIZE=6 -D HAS_CARRY8 -map $PATCHED
opt -fast
synth_xilinx -family xcup -noiopad -noclkbuf -run map_cells:
S
for w in 3 8 9 17 32 33; do   # widths around the CARRY8 boundary (8, 16, 24, 32)
cat > $HERE/t_w$w.v <<S
module t(input [$((w-1)):0] a, b, input s, c, output [$w:0] y, output lt, eq, output [$((w-1)):0] d);
  assign y = s ? {1'b0,a} - {1'b0,b} - c : {1'b0,a} + {1'b0,b} + c;
  assign lt = a < b;  assign eq = a == b;  assign d = a - b;
endmodule
S
r=$(yosys -p "read_verilog $HERE/t_w$w.v; hierarchy -top t; proc; equiv_opt -assert -map +/xilinx/cells_sim.v script $HERE/c8.ys; design -load postopt; stat -tech xilinx" 2>&1)
echo "width $w: $(echo "$r" | grep -c 'Equivalence successfully proven') proven; $(echo "$r" | grep -E '^ +[0-9]+ +CARRY' | tr -s ' ' | tr '\n' ' ')"
done
# registered designs of the brief 142 micro set (equiv_opt: both sides get the same registers, proved by induction)
for t in m01_add32 m03_add3 m04_addsub32 m05_cmp32 m06_counter32 m32_cmpchain; do
  r=$(timeout 300 yosys -p "plugin -i slang; read_slang --top $t $HERE/../../../rtl/micro/$t.sv; proc; equiv_opt -assert -map +/xilinx/cells_sim.v script $HERE/c8.ys; design -load postopt; stat -tech xilinx" 2>&1)
  echo "$t: $(echo "$r" | grep -c 'Equivalence successfully proven') proven; $(echo "$r" | grep -E '^ +[0-9]+ +CARRY' | tr -s ' ' | sort -u | tr '\n' ' ')"
done

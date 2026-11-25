foreach {top part} {t_tmpl xc7a100tcsg324-1 t_tmpl12 xc7a100tcsg324-1 t_ours xc7a100tcsg324-1 t_ours_mod xc7a100tcsg324-1 t_tmpl xck26-sfvc784-2LV-c t_tmpl12 xck26-sfvc784-2LV-c t_ours xck26-sfvc784-2LV-c t_ours_mod xck26-sfvc784-2LV-c} {
  read_verilog -sv [list t_tmpl.sv t_tmpl12.sv t_ours.sv t_ours_mod.sv]
  synth_design -top $top -part $part -mode out_of_context
  set n [llength [get_cells -hier -filter {PRIMITIVE_TYPE =~ MULT.DSP.*}]]
  set dsp [llength [get_cells -hier -filter {REF_NAME =~ DSP48*}]]
  puts "RESULT $top $part dsp_macro_cells=$n dsp48=$dsp"
  foreach c [get_cells -hier -filter {REF_NAME =~ DSP48*}] { puts "RESULT   $c USE_SIMD=[get_property USE_SIMD $c] AREG=[get_property AREG $c] PREG=[get_property PREG $c]" }
  report_utilization -file util_${top}_${part}.txt
  close_design
}

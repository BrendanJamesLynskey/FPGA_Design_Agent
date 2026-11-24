# Brief 208: run a list of jobs in one Vivado session (one heavy job; jobs run one after another).
#   vivado -mode batch -source run_jobs.tcl -tclargs <jobs file> <out root>
# A jobs file line: <name> <part> <rtl file> <top> <generics, k=v comma list or -> <xdc files, comma list> <stage: synth|route>
set_param general.maxThreads 1
set_param synth.maxThreads 1
set here [file dirname [file normalize [info script]]]
source [file join $here clock_mux_dump.tcl]
lassign $argv jobs_file out_root
set fh [open $jobs_file r]; set lines [split [read $fh] "\n"]; close $fh

proc reports {d tag} {
  catch {check_timing -verbose -file $d/check_timing_$tag.rpt}
  catch {report_clocks -file $d/clocks_$tag.rpt}
  catch {report_clock_interaction -delay_type min_max -file $d/clock_interaction_$tag.rpt}
  catch {report_methodology -file $d/methodology_$tag.rpt}
  catch {report_cdc -details -file $d/cdc_$tag.rpt}
  catch {report_timing_summary -max_paths 5 -report_unconstrained -file $d/timing_summary_$tag.rpt}
  catch {report_exceptions -file $d/exceptions_$tag.rpt}
  catch {report_exceptions -ignored -file $d/exceptions_ignored_$tag.rpt}
  # report_clock_networks is not run: it segfaulted (Vivado 2026.1, HASTClockSniffer::isForwardedClock) on the post-synthesis
  # MMCM design a7_r_none with the renamed MMCM clocks (r_base.xdc); see README "Gotchas"
  # f2: timing paths that end on a clock-buffer control pin (select or enable)
  set ctl [get_pins -quiet -of_objects [get_cells -quiet -hier -filter {IS_PRIMITIVE && (REF_NAME =~ BUFG* )}] -filter {DIRECTION == IN && (REF_PIN_NAME =~ S* || REF_PIN_NAME =~ CE*)}]
  if {[llength $ctl] > 0} { catch {report_timing -to $ctl -max_paths 8 -nworst 2 -file $d/timing_to_bufctl_$tag.rpt} }
  catch {clock_mux_dump $d/clock_mux_dump_$tag.txt}
}

foreach line $lines {
  set line [string trim $line]
  if {$line eq "" || [string index $line 0] eq "#"} continue
  lassign $line name part rtl top generics xdcs stage
  set d [file join $out_root $name]
  file mkdir $d
  puts "=== JOB $name $part $top $generics $xdcs $stage [clock format [clock seconds] -format %H:%M:%S]"
  set gopt {}
  if {$generics ne "-"} { foreach kv [split $generics ","] { lappend gopt -generic $kv } }
  if {[catch {
    read_verilog $rtl
    synth_design -top $top -part $part {*}$gopt
    foreach x [split $xdcs ","] { read_xdc $x }
    # read_xdc on an open design applies the constraints now
    reports $d synth
    write_checkpoint -force $d/post_synth.dcp
    catch {report_utilization -file $d/utilization_synth.rpt}
    if {$stage eq "route"} {
      opt_design
      place_design
      route_design
      reports $d route
      catch {report_utilization -file $d/utilization_route.rpt}
      catch {report_power -file $d/power_route.rpt}
      catch {report_clock_utilization -file $d/clock_utilization_route.rpt}
      if {$top eq "pwr"} {
        # f1: vectorless power with the enable's static probability set; toggle rate 2 % of the clock
        foreach p {0.1 0.5 0.9} {
          set_switching_activity -static_probability $p -toggle_rate 2 [get_nets -hier -filter {NAME =~ *en_r}]
          report_power -file $d/power_en$p.rpt
        }
      }
      catch {write_checkpoint -force $d/post_route.dcp}
    }
  } err]} {
    puts "JOBERROR $name: $err"
    set ef [open $d/JOBERROR.txt w]; puts $ef $err; close $ef
  }
  close_project -quiet
  catch {close_design -quiet}
  puts "=== END $name [clock format [clock seconds] -format %H:%M:%S]"
}

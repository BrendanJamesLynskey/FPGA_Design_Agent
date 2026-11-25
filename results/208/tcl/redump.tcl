# Brief 208 review fix: rerun the (changed) clock_mux_dump.tcl on every arm's checkpoint, so the check's fixtures and
# measured.json come from the dump the check now reads.
#   vivado -mode batch -source redump.tcl -tclargs <build root>
# For each arm folder: the checkpoint of the latest stage it reached (post_route, post_place, else post_synth); the
# constraints are inside the checkpoint (run_jobs.tcl wrote it after read_xdc). Writes clock_mux_dump_<stage>.txt in place.
set_param general.maxThreads 1
set here [file dirname [file normalize [info script]]]
source [file join $here clock_mux_dump.tcl]
set root [lindex $argv 0]
foreach dir [lsort [glob -type d $root/a7/* $root/k26/*]] {
  foreach {f tag} {post_route.dcp route post_place.dcp place post_synth.dcp synth} {
    if {[file exists $dir/$f]} {
      puts "=== REDUMP [file tail $dir] $tag [clock format [clock seconds] -format %H:%M:%S]"
      if {[catch {open_checkpoint $dir/$f; clock_mux_dump $dir/clock_mux_dump_$tag.txt} err]} { puts "REDUMPERROR [file tail $dir]: $err" }
      catch {close_design}
      break
    }
  }
}

# board_licence_probe.tcl: does the installed Vivado licence let a part go through synthesis, placement and routing? (brief 95)
#   vivado -mode batch -source tools/board_licence_probe.tcl -tclargs <out.json> <part> [<part> ...]
# For each part: a one-flop in-memory design with an unplaced clock and one LED output goes through synth_design, opt_design,
# place_design and route_design; each step is caught, and the first error message (a licence error names the feature and the device)
# is written to the JSON. No bitstream is written. Nothing here is board-specific: the point is the part.
set out [lindex $argv 0]
set parts [lrange $argv 1 end]
set v [file join [file dirname [file normalize $out]] probe_[pid].v]
set vh [open $v w]; puts $vh "module probe(input clk, input d, output reg q); always @(posedge clk) q <= d; endmodule"; close $vh
set fh [open $out w]
puts $fh "\["
set first 1
foreach part $parts {
    set res "ok"; set stage "route"; set msg ""
    catch {read_verilog $v}
    foreach {step cmd} [list synth "synth_design -top probe -part $part -mode out_of_context" opt "opt_design" place "place_design" route "route_design"] {
        if {[catch {eval $cmd} err]} {
            set res "failed"; set stage $step; set msg [string map [list "\n" " " "\"" "'" "\\" "/"] $err]
            break
        }
    }
    catch {close_project}
    catch {close_design}
    if {!$first} {puts $fh ","}
    set first 0
    puts -nonewline $fh "{\"part\": \"$part\", \"result\": \"$res\", \"stage\": \"$stage\", \"message\": \"[string range $msg 0 400]\"}"
}
puts $fh "\n\]"
close $fh
file delete $v

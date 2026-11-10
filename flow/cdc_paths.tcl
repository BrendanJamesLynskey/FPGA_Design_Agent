# cdc_paths.tcl: every register-to-register path whose launch and capture clocks are asynchronous, from the synthesised
# netlist (brief 16, V-level CDC gate, part 1). flow/cdc_structure.py classifies the rows; flow/gates.py reads the result.
#
#   source flow/cdc_paths.tcl ; cdc_dump_paths <file>        (a synthesised or implemented design must be open)
#
# One line per capture pin of a flip-flop whose startpoints include a flip-flop or RAM on an asynchronous clock:
#   PATH|<capture cell>|<ref>|<pin>|<capture clock>|<ASYNC_REG>|<source cell>|<source ref>|<source clock>|<n startpoints>
#       |<chain>|<q loads>|<sinks>
# chain = flip-flops in a row on the same clock with ASYNC_REG, each driving only the next one, from the capture cell
# (>= 2 is a synchroniser); q loads = loads of the capture cell's Q; sinks = capture endpoints (flip-flop D pins) the last
# stage of the chain reaches through combinational logic, at most 24. Two clocks are asynchronous when their primary clocks
# differ (a generated clock follows its master). Costs one all_fanin per capture pin: a design with one clock writes only
# its header.

proc cdc_root_clock {c} {
    set c [get_clocks -quiet $c]
    set n 0
    while {[get_property IS_GENERATED $c] && $n < 20} {
        set m [get_property MASTER_CLOCK $c]
        if {$m eq ""} { break }
        set c [get_clocks -quiet $m]
        if {$c eq ""} { break }
        incr n
    }
    return [get_property NAME $c]
}

proc cdc_cell_clock {cell} {
    set cp [get_pins -quiet -of_objects $cell -filter {REF_PIN_NAME == C || REF_PIN_NAME == CLK || REF_PIN_NAME == WCLK}]
    if {$cp eq ""} { return "" }
    set c [get_clocks -quiet -of_objects [lindex $cp 0]]
    if {$c eq ""} { return "" }
    return [lindex $c 0]
}

proc cdc_q_loads {cell} {
    set q [get_pins -quiet -of_objects $cell -filter {REF_PIN_NAME == Q}]
    if {$q eq ""} { return {} }
    set net [get_nets -quiet -of_objects $q]
    if {$net eq ""} { return {} }
    return [get_pins -quiet -of_objects $net -leaf -filter {DIRECTION == IN}]
}

proc cdc_dump_paths {file} {
    set f [open $file w]
    puts $f "# cdc_paths v1"
    set clocks [get_clocks -quiet]
    foreach c $clocks {
        puts $f "CLOCK|[get_property NAME $c]|[get_property PERIOD $c]|[cdc_root_clock $c]"
    }
    set roots [lsort -unique [lmap c $clocks { cdc_root_clock $c }]]
    if {[llength $roots] < 2} { puts $f "# one primary clock: no asynchronous crossing"; puts $f "# end"; close $f; return }
    set flops [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE && IS_SEQUENTIAL && REF_NAME =~ FD*}]
    foreach c $flops {
        set dclk [cdc_cell_clock $c]
        if {$dclk eq ""} { continue }
        set droot [cdc_root_clock $dclk]
        set ar [get_property ASYNC_REG $c]
        foreach pn {D CE R S CLR PRE} {
            set rc [catch {
            set p [get_pins -quiet -of_objects $c -filter "REF_PIN_NAME == $pn"]
            if {$p eq ""} { continue }
            set sps [all_fanin -quiet -startpoints_only -flat $p]
            if {$sps eq ""} { continue }
            set scells [get_cells -quiet -of_objects $sps]
            set cross {}
            foreach sc $scells {
                set sclk [cdc_cell_clock $sc]
                if {$sclk eq ""} { continue }
                if {[cdc_root_clock $sclk] ne $droot} { lappend cross [list $sc $sclk] }
            }
            if {$cross eq ""} { continue }
            # the synchroniser chain behind this capture cell
            set chain 0
            set cur $c
            set loads [cdc_q_loads $c]
            set nloads [llength $loads]
            while {$chain < 8} {
                if {[get_property REF_NAME $cur] ni {FDRE FDSE FDCE FDPE}} { break }
                if {[get_property ASYNC_REG $cur] ne "1" && [get_property ASYNC_REG $cur] ne "TRUE"} { break }
                incr chain
                set ld [cdc_q_loads $cur]
                if {[llength $ld] != 1} { break }
                set nx [get_cells -quiet -of_objects [lindex $ld 0]]
                if {$nx eq "" || [get_property REF_NAME $nx] ni {FDRE FDSE FDCE FDPE} || [lindex [get_pins -of_objects $nx -filter {REF_PIN_NAME == D}] 0] ne [lindex $ld 0]} { break }
                if {[cdc_cell_clock $nx] ne $dclk} { break }
                set cur $nx
            }
            set sinks {}
            set lq [get_pins -quiet -of_objects $cur -filter {REF_PIN_NAME == Q}]
            if {$lq ne ""} {
                foreach e [lrange [all_fanout -quiet -endpoints_only -flat $lq] 0 23] {
                    set ec [get_cells -quiet -of_objects $e]
                    if {$ec ne ""} { lappend sinks [get_property NAME $ec] }
                }
            }
            lassign [lindex $cross 0] sc sclk
            puts $f "PATH|[get_property NAME $c]|[get_property REF_NAME $c]|$pn|$dclk|$ar|[get_property NAME $sc]|[get_property REF_NAME $sc]|$sclk|[llength $scells]|$chain|$nloads|[join $sinks ,]"
            } err]
            if {$rc == 1} { puts $f "ERROR|[get_property NAME $c]|$pn|[string map {\n { }} $err]" }
        }
    }
    puts $f "# end"
    close $f
}

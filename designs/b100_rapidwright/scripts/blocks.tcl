# blocks.tcl: the block-internal paths of reloc_top's four copies (brief 100, capability 1), written as <out>_blocks.csv.
proc block_paths {out} {
    set n 4
    # The block-internal paths: the worst setup path to each endpoint register inside each copy, with the path's data delay, slack and
    # logic levels. Endpoint names are relative to the copy so that copies compare endpoint by endpoint.
    set f [open ${out}_blocks.csv w]
    puts $f "copy,endpoint,data_path_delay_ns,slack_ns,logic_levels"
    for {set i 0} {$i < $n} {incr i} {
        set cells [get_cells -hier -filter "IS_SEQUENTIAL && NAME =~ c$i/*"]
        set prefix "c$i/"
        foreach p [get_timing_paths -setup -from $cells -to $cells -max_paths 2000 -nworst 1 -unique_pins] {
            set e [string map [list $prefix ""] [get_property ENDPOINT_PIN $p]]
            puts $f "$i,$e,[get_property DATAPATH_DELAY $p],[get_property SLACK $p],[get_property LOGIC_LEVELS $p]"
        }
    }
    close $f
}

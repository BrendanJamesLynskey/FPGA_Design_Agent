# rig_map.tcl: copy counts and the copy -> (variant, k, direction, class, domains) map, the same arithmetic as
# rtl/rig_pkg.sv and rtl/rig_core.sv (copies numbered in variant order; dir = k mod 3, class = (k + k/3) mod 3).

set rig_variants {C1 C2 C3A C3B C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 M1 M1B M2 M3 M4 M5 M6A M6B M6C M7 M8 M9 M10 M11}

# small build: one copy of each variant (28)
set rig_counts_small {}
foreach v $rig_variants { dict set rig_counts_small $v 1 }

# full build (design section 3): 312 correct + 14 x 16 mutants = 536
set rig_counts_full [dict create \
    C1 48 C2 40 C3A 20 C3B 20 C4 24 C5 24 C6 24 C7 24 C8 16 C9 16 C10 16 C11 8 C12 16 C13 16 \
    M1 16 M1B 16 M2 16 M3 16 M4 16 M5 16 M6A 16 M6B 16 M6C 16 M7 16 M8 16 M9 16 M10 16 M11 16]

proc rig_generics {counts} {
    set g {}
    dict for {v n} $counts { lappend g -generic N_${v}=$n }
    return $g
}

# rig_copies counts -> list of {g variant k dir cls sdom ddom}
proc rig_copies {counts} {
    global rig_variants
    set out {}
    set g 0
    foreach v $rig_variants {
        set n [dict get $counts $v]
        for {set k 0} {$k < $n} {incr k} {
            set dir [expr {$k % 3}]
            set cls [expr {($k + $k / 3) % 3}]
            if {$v eq "M6B" || $v eq "M6C"} {
                set sd f; set dd b
            } else {
                set sd [lindex {a b a} $dir]
                set dd [lindex {b a c} $dir]
            }
            lappend out [list $g $v $k [lindex {a->b b->a a->c} $dir] [lindex {far near boundary} $cls] $sd $dd]
            incr g
        }
    }
    return $out
}

# copy index from a cell name (.../g_copy[17].u_copy/...), or -1
proc rig_copy_of {name} {
    if {[regexp {g_copy\[(\d+)\]\.u_copy} $name -> g]} { return $g }
    return -1
}

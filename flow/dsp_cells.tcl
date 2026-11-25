# dsp_cells.tcl (brief 185): write the register properties of every DSP48 cell of the open design, one line per cell:
#   source flow/dsp_cells.tcl; fda_dsp_cells <file>
# The same format as results/185_dsp_slices/raw/*/*/dsp_cells.txt; flow/dsp_regs_check.py reads it.
proc fda_dsp_cells {file} {
    set f [open $file w]
    foreach c [lsort [get_cells -hier -filter {REF_NAME =~ DSP48*}]] {
        set line "$c [get_property REF_NAME $c]"
        foreach p {AREG BREG CREG DREG ADREG MREG PREG USE_MULT USE_SIMD USE_PATTERN_DETECT} {
            if {![catch {set v [get_property $p $c]}]} { append line " $p=$v" }
        }
        puts $f $line
    }
    close $f
}

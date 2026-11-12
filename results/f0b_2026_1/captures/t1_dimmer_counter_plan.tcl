set fda_depth 1024
set fda_captures {}
lappend fda_captures [list count_write AND 64 [list [list 1 1 4 1] [list 0 128 24 8]]]
lappend fda_captures [list pwm_08 AND 0 [list [list 0 0 48 8]]]
lappend fda_captures [list pwm_40 AND 0 [list [list 0 0 48 8]]]
lappend fda_captures [list pwm_a0 AND 0 [list [list 0 0 48 8]]]

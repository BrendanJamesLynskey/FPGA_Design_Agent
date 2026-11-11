set fda_depth 1024
set fda_captures {}
lappend fda_captures [list count_write AND 64 [list [list 6 1] [list 8 128]]]
lappend fda_captures [list pwm_08 AND 0 [list [list 10 0]]]
lappend fda_captures [list pwm_40 AND 0 [list [list 10 0]]]
lappend fda_captures [list pwm_a0 AND 0 [list [list 10 0]]]

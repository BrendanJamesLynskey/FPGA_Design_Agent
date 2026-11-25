// book_bind.sv (brief 188): attaches book_props to every book_core instance; the port names of book_props are the names of book_core's own signals.
bind book_core book_props #(.N_INST(N_INST), .LEVELS(LEVELS), .ORD_AW(ORD_AW)) u_props (.*);

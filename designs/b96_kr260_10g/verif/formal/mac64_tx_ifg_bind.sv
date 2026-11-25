// mac64_tx_ifg_bind.sv (brief 158): attaches mac64_tx_ifg_props to every mac64_tx instance. The state is passed as its bits (the enum state_t is local to mac64_tx).
bind mac64_tx mac64_tx_ifg_props u_props (.clk, .rst, .adv, .s_valid, .s_last, .s_nb1, .st(2'(st)), .n);

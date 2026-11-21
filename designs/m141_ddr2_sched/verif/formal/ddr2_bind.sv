// ddr2_bind.sv (brief 141): attaches ddr2_props to every ddr2_sched; the port names of ddr2_props are the names of ddr2_sched's own signals (ports and internal nets).
`ifndef FV_BOUND
`define FV_BOUND 100
`endif
bind ddr2_sched ddr2_props #(.NB_(NB), .QD(QD), .BW(BW), .RW(RW), .CB(CB), .TW(TW), .T_RCD(T_RCD), .T_RP(T_RP), .T_RPA(T_RPA), .T_RAS(T_RAS), .T_RC(T_RC), .T_RRD(T_RRD), .T_FAW(T_FAW),
    .T_WR(T_WR), .T_WTR(T_WTR), .T_RTP(T_RTP), .T_RFC(T_RFC), .T_REFI(T_REFI), .RL(RL), .WL(WL), .BL2(BL2), .AGE_LIM(AGE_LIM), .REF_POST(REF_POST), .BOUND(`FV_BOUND)) u_props (.*);

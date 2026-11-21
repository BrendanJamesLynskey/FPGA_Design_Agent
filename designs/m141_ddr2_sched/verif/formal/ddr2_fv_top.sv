// ddr2_fv_top.sv (brief 141): the proof harness: ddr2_sched with free inputs every step (requests of any kind and address, any ref_defer, any en timing within the assumptions in ddr2_props.sv).
module ddr2_fv_top #(
    parameter int POLICY = 0, parameter int QD = 4, parameter int BW = 3, parameter int RW = 2, parameter int CB = 2, parameter int TW = 2,
    parameter int T_RCD = 6, parameter int T_RP = 6, parameter int T_RPA = 7, parameter int T_RAS = 16, parameter int T_RC = 22, parameter int T_RRD = 4, parameter int T_FAW = 20,
    parameter int T_WR = 6, parameter int T_WTR = 3, parameter int T_RTP = 3, parameter int T_RFC = 51, parameter int T_REFI = 3120,
    parameter int RL = 6, parameter int WL = 5, parameter int BL2 = 4, parameter int AGE_LIM = 64, parameter int WR_HI = 3, parameter int WR_LO = 1, parameter int RUN_MAX = 4,
    parameter int REF_POST = 4
) (
    input logic clk, rst, en,
    input logic req_v, req_wr, ref_defer,
    input logic [RW+BW+CB-1:0] req_addr,
    input logic [TW-1:0] req_tag
);
    logic req_rdy, cmd_v;
    logic [2:0] cmd_op;
    logic [BW-1:0] cmd_bank;
    logic [RW-1:0] cmd_row;
    logic [CB-1:0] cmd_col;
    logic [TW-1:0] cmd_tag;
    ddr2_sched #(.POLICY(POLICY), .QD(QD), .BW(BW), .RW(RW), .CB(CB), .TW(TW), .MAP(0), .T_RCD(T_RCD), .T_RP(T_RP), .T_RPA(T_RPA), .T_RAS(T_RAS), .T_RC(T_RC), .T_RRD(T_RRD), .T_FAW(T_FAW),
                 .T_WR(T_WR), .T_WTR(T_WTR), .T_RTP(T_RTP), .T_RFC(T_RFC), .T_REFI(T_REFI), .RL(RL), .WL(WL), .BL2(BL2), .AGE_LIM(AGE_LIM), .WR_HI(WR_HI), .WR_LO(WR_LO), .RUN_MAX(RUN_MAX),
                 .REF_POST(REF_POST)) dut (.*);
endmodule

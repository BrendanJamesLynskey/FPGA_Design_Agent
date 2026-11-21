`timescale 1ns/1ps
// itch_unit.sv (brief 127): the new blocks with the REAL mac64_rx and mac64_tx and nothing else of the core: XGMII words in -> mac64_rx -> itch_path -> tx_mux -> mac64_tx -> XGMII words out.
// One clock; the transmit MAC's `adv` pause (one clock in 33, as the PCS gearbox gives it) is generated here. Used by tests/b127_unit_cocotb.py (Icarus) to compare the strip,
// the Mold/ITCH path, the order frames on the wire and the counters with brief 110's model, and to measure the clocks of the chain.
module itch_unit #(
    parameter bit PAUSE = 1'b1
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        x_v,
    input  logic [63:0] x_d,
    input  logic [7:0]  x_c,
    input  logic [b96_pkg::CFGW-1:0] cfg,
    input  logic [32*itch_pkg2::NCW-1:0] cfg2,
    output logic [32*itch_pkg2::NSW-1:0] stat2,
    output logic [63:0] t_d,
    output logic [7:0]  t_c,
    output logic        t_sop, t_eop,
    output logic [31:0] ts
);
    import b96_pkg::*;
    import itch_pkg2::*;
    logic        m_v, m_sof, m_end, m_fcs_ok, m_err, rx_sop;
    logic [63:0] m_d;
    logic [3:0]  m_nb;
    logic [15:0] m_len;
    mac64_rx u_mr (.clk, .rst, .lock_i(1'b1), .x_v, .x_d, .x_c, .m_v, .m_d, .m_sof, .m_nb, .m_end, .m_fcs_ok, .m_len, .m_err, .rx_sop);
    always_ff @(posedge clk) ts <= rst ? 32'd0 : ts + 32'd1;
    logic        o_v, o_sof, o_eof, o_poison, o_unres, fcs_poison, rp_start, rp_stop, wr_we;
    logic [15:0] rp_loops;
    logic [63:0] o_d, wr_data;
    logic [7:0]  o_keep, wr_addr;
    logic        ord_start, ord_drop, ord_end, ord_end_seg, ord_end_unres, ord_end_fcs, ord_end_ofl, ord_sop, ord_busy, own_a, rp_busy;
    logic [31:0] rp_frames, rp_err, n_ofl;
    itch_path u_ip (.clk, .rst, .ts, .cfg, .rx_sop, .m_v, .m_d, .m_sof, .m_end, .m_fcs_ok, .m_len, .m_err, .cfg2, .stat2, .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_poison, .o_unres,
        .fcs_poison, .rp_start, .rp_stop, .rp_loops, .wr_we, .wr_addr, .wr_data, .ord_start, .ord_drop, .ord_end, .ord_end_seg, .ord_end_unres, .ord_end_fcs, .ord_end_ofl, .ord_sop,
        .ord_busy, .rp_frames, .rp_err, .n_ofl, .rp_busy);
    logic        s_valid, s_last, s_poison, s_ready, sop, eop, underrun;
    logic        adv;
    logic [63:0] s_data;
    logic [2:0]  s_nb1;
    tx_mux u_mx (.clk, .rst, .s_valid, .s_data, .s_last, .s_nb1, .s_poison, .s_ready, .mac_sop(sop), .a_valid(1'b0), .a_data(64'd0), .a_last(1'b0), .a_nb1(3'd0), .a_poison(1'b0), .a_ready(),
        .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_poison, .o_unres, .fcs_poison, .ord_start, .ord_drop, .ord_end, .ord_end_seg, .ord_end_unres, .ord_end_fcs, .ord_end_ofl, .ord_sop, .ord_busy, .own_a,
        .rp_start, .rp_stop, .rp_loops, .wr_we, .wr_addr, .wr_data, .rp_frames, .rp_err, .rp_busy, .n_ofl);
    logic [5:0] pc;
    always_ff @(posedge clk) pc <= (rst || pc == 6'd32) ? 6'd0 : pc + 6'd1;
    assign adv = PAUSE ? (pc != 6'd32) : 1'b1;
    mac64_tx u_mt (.clk, .rst, .adv, .s_valid, .s_data, .s_last, .s_nb1, .s_poison, .s_ready, .x_d(t_d), .x_c(t_c), .sop, .eop, .underrun);
    assign t_sop = sop; assign t_eop = eop;
endmodule

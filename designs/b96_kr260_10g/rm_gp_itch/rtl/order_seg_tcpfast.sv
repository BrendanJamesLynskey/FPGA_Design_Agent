// order_seg_tcpfast.sv: the same module and ports as order_seg.sv, with brief 119's tcp_fast (PR #245, designs/b119_tcp_fast) in place of the stand-in header builder (brief 127).
// NOT IN build.yaml: to use it, merge #245 and replace `designs/b96_kr260_10g/rm_gp_itch/rtl/order_seg.sv` by this file in build.yaml (and in tests/test_b127_unit.py's file list). docs/itch_integration.md
// section 8 says what changes. tcp_fast contains its own ouch_enter (the same one of brief 110), builds the whole 113-byte frame from the template and the connection state software wrote through its
// register bus (the host's TCPF_ADDR and TCPF_WDATA registers reach `sw_*`), finishes both checksums per order, and poisons an aborted or unresolved speculative frame itself (`o_poison`), so `o_unres`
// is 0 here (the poison policy of itch_path still ORs in the verdict of the trigger frame's FCS). A refused order (not armed, stale state, closed window, MSS) makes no words at all: `refuse_v`.
// The template inputs of the stand-in (tpl_*) are unused: the addressing, sequence and acknowledgement numbers are tcp_fast's registers, written by software.
module order_seg (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    input  logic        go_spec,
    input  logic [63:0] f_sym,
    input  logic [31:0] f_px,
    input  logic [31:0] f_qty,
    input  logic [31:0] f_ref,
    input  logic        commit,
    input  logic        abort,
    input  logic        tx_unsent,       // brief 176, one clock: the transmit side poisoned the frame that just ended (the trigger frame's bad FCS, STRICT without a verdict, FIFO overflow): its sequence number is given back
    input  logic        tx_drop,         // brief 176, one clock, in the clock of the frame's first word: the multiplexer drops this frame whole (the MAC is owned): it consumes no sequence number
    input  logic [7:0]  cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic [31:0] cfg_minqty,
    input  logic [47:0] tpl_my_mac, tpl_venue_mac,
    input  logic [31:0] tpl_my_ip, tpl_venue_ip,
    input  logic [15:0] tpl_sport, tpl_dport,
    input  logic [31:0] tpl_seq0, tpl_ack,
    input  logic        tpl_load,
    input  logic        sw_we,
    input  logic [4:0]  sw_waddr,
    input  logic [31:0] sw_wdata,
    input  logic [4:0]  sw_raddr,
    output logic [31:0] sw_rdata,
    output logic        busy,
    output logic        late,
    output logic        spec_pend,
    output logic        refuse_v,
    output logic        o_v,
    output logic [63:0] o_d,
    output logic        o_sof,
    output logic        o_eof,
    output logic [7:0]  o_keep,
    output logic        o_poison,
    output logic        o_unres
);
    logic [2:0]   refuse_code;
    logic         rec_v;
    logic [31:0]  rec_seq;
    logic [15:0]  rec_len, rec_id;
    logic [511:0] rec_pay;
    tcp_fast u_tf (.clk, .rst, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .tx_unsent, .tx_drop, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross, .cfg_custtype, .cfg_minqty,
                   .busy, .late, .refuse_v, .refuse_code, .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_poison, .rec_v, .rec_seq, .rec_len, .rec_id, .rec_pay,
                   .sw_we, .sw_waddr, .sw_wdata, .sw_raddr, .sw_rdata);
    assign o_unres = 1'b0;
    // tcp_fast has no spec_pend output: itch_top does not use it (it is a stand-in observation)
    assign spec_pend = 1'b0;
    logic _unused;
    assign _unused = &{1'b0, refuse_code, rec_v, rec_seq, rec_len, rec_id, rec_pay, tpl_my_mac, tpl_venue_mac, tpl_my_ip, tpl_venue_ip, tpl_sport, tpl_dport, tpl_seq0, tpl_ack, tpl_load};
endmodule

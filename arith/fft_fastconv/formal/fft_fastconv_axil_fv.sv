// fft_fastconv_axil_fv: the AXI4-Lite register file of fft_fastconv_os obeys the protocol and its own register contract (arith brief 161). Bounded model check from reset (the master is
// constrained to the AXI4-Lite master rules: a request valid stays high with its address, data and strobes until accepted; reset is asserted in the first clock); busy, sat_pulse and blocks are free.
// Shadow state tracks which requests were accepted and what the register map says, sharing no code with the module:
//   HB   once bvalid is high and bready low, bvalid and bresp hold;   HR   the same for rvalid, rdata, rresp;
//   ONE  a write response only after an address and a data beat were both accepted, at most one outstanding on each channel (so exactly one response per accepted pair);
//   ONER a read response only after an address beat, at most one outstanding;
//   RESP the response of an executed write is SLVERR for a write to a read-only or unmapped register, with partial strobes, or a refused commit, else OKAY (the contract's table);
//   RID  a read of the ID register returns 0x46435631 with OKAY and a read of an unmapped address returns 0 with SLVERR;
//   COMMIT the commit strobe fires only for a COEF_IM write with all strobes while busy is low; a refused commit sets DROPPED; SAT stays set once the datapath's pulse arrived.
// Run by tools/run_formal.py (SymbiYosys, slang front end).
module fft_fastconv_axil_fv #(
    parameter int LOGN = 4,
    parameter int L    = 9,
    parameter int W    = 8,
    parameter int WH   = 12,
    parameter int FH   = 8,
    parameter int GB   = 1
) (
    input logic          clk,
    input logic          aresetn,
    input logic          awvalid,
    input logic [5:0]    awaddr,
    input logic          wvalid,
    input logic [31:0]   wdata,
    input logic [3:0]    wstrb,
    input logic          bready,
    input logic          arvalid,
    input logic [5:0]    araddr,
    input logic          rready,
    input logic          busy,
    input logic          sat_pulse,
    input logic [31:0]   blocks
);
    logic        awready, wready, bvalid, arready, rvalid, coef_we;
    logic [1:0]  bresp, rresp;
    logic [31:0] rdata;
    logic [LOGN-1:0] coef_addr;
    logic [WH-1:0]   coef_re, coef_im;
    fft_fastconv_axil #(.LOGN(LOGN), .L(L), .W(W), .WH(WH), .FH(FH), .GB(GB)) u (
        .clk(clk), .aresetn(aresetn), .s_axil_awvalid(awvalid), .s_axil_awready(awready), .s_axil_awaddr(awaddr), .s_axil_wvalid(wvalid), .s_axil_wready(wready),
        .s_axil_wdata(wdata), .s_axil_wstrb(wstrb), .s_axil_bvalid(bvalid), .s_axil_bready(bready), .s_axil_bresp(bresp), .s_axil_arvalid(arvalid), .s_axil_arready(arready),
        .s_axil_araddr(araddr), .s_axil_rvalid(rvalid), .s_axil_rready(rready), .s_axil_rdata(rdata), .s_axil_rresp(rresp), .busy(busy), .sat_pulse(sat_pulse), .blocks(blocks),
        .coef_we(coef_we), .coef_addr(coef_addr), .coef_re(coef_re), .coef_im(coef_im));

    logic first = 1'b1;
    logic p_aw = 1'b0, p_awr = 1'b0, p_w = 1'b0, p_wr = 1'b0, p_ar = 1'b0, p_arr = 1'b0, p_b = 1'b0, p_br = 1'b0, p_r = 1'b0, p_rr = 1'b0;
    logic [5:0] p_awa, p_ara;
    logic [31:0] p_wd, p_rd;
    logic [3:0] p_ws;
    logic [1:0] p_bresp, p_rresp;
    logic pend_aw = 1'b0, pend_w = 1'b0, pend_b = 1'b0, pend_r = 1'b0;
    logic exec_q = 1'b0, exp_ok_q = 1'b0, drop_q = 1'b0, pulse_q = 1'b0, commit_q = 1'b0;
    logic [3:0] cur_awa;
    logic [3:0] awa_s = 4'd0;                                   // the address the master presented, decoded here from the raw address bits
    logic [3:0] strb_s = 4'd0;
    logic [5:0] last_ar;
    logic exp_ok;
    always_comb begin
        // the master's obligations (assumed) and the reset
        if (first) assume (!aresetn);
        if (p_aw && !p_awr && aresetn) assume (awvalid && awaddr == p_awa);
        if (p_w && !p_wr && aresetn) assume (wvalid && wdata == p_wd && wstrb == p_ws);
        if (p_ar && !p_arr && aresetn) assume (arvalid && araddr == p_ara);
        // what the contract says an executed write answers
        cur_awa = awa_s;
        exp_ok  = (strb_s == 4'hF) && (cur_awa == 4'd3 || cur_awa == 4'd5 || cur_awa == 4'd6 || (cur_awa == 4'd7 && !busy));
    end
    always_ff @(posedge clk) begin
        first   <= 1'b0;
        if (!aresetn) begin
            p_aw <= 1'b0; p_awr <= 1'b0; p_w <= 1'b0; p_wr <= 1'b0; p_ar <= 1'b0; p_arr <= 1'b0; p_b <= 1'b0; p_br <= 1'b0; p_r <= 1'b0; p_rr <= 1'b0;
        end else begin
            p_aw <= awvalid; p_awr <= awready; p_awa <= awaddr;
            p_w <= wvalid; p_wr <= wready; p_wd <= wdata; p_ws <= wstrb;
            p_ar <= arvalid; p_arr <= arready; p_ara <= araddr;
            p_b <= bvalid; p_br <= bready; p_bresp <= bresp;
            p_r <= rvalid; p_rr <= rready; p_rd <= rdata; p_rresp <= rresp;
        end
        if (!aresetn) begin
            pend_aw <= 1'b0; pend_w <= 1'b0; pend_b <= 1'b0; pend_r <= 1'b0; exec_q <= 1'b0; drop_q <= 1'b0; commit_q <= 1'b0; pulse_q <= 1'b0;
        end else begin
            if (awvalid && awready) begin pend_aw <= 1'b1; awa_s <= awaddr[5:2]; end
            if (wvalid && wready) begin pend_w <= 1'b1; strb_s <= wstrb; end
            if (u.do_wr) begin pend_aw <= 1'b0; pend_w <= 1'b0; pend_b <= 1'b1; end
            if (bvalid && bready) pend_b <= 1'b0;
            if (arvalid && arready) begin pend_r <= 1'b1; last_ar <= araddr; end
            if (rvalid && rready) pend_r <= 1'b0;
            exec_q   <= u.do_wr;
            exp_ok_q <= exp_ok;
            drop_q   <= u.do_wr && (strb_s == 4'hF) && (cur_awa == 4'd7) && busy;
            commit_q <= coef_we;
            pulse_q  <= sat_pulse;
        end
    end
    always_comb begin
        if (!first && aresetn) begin
            HB_B:   assert (!(p_b && !p_br && aresetn) || (bvalid && bresp == p_bresp));
            HB_R:   assert (!(p_r && !p_rr && aresetn) || (rvalid && rdata == p_rd && rresp == p_rresp));
            ONE_B:  assert (!bvalid || pend_b);
            AW_RDY: assert (!(pend_aw || pend_b) || !awready);
            W_RDY:  assert (!(pend_w || pend_b) || !wready);
            ONE_R:  assert (!rvalid || pend_r);
            AR_RDY: assert (!rvalid || !arready);
            RESP_W: assert (!exec_q || !bvalid || bresp == (exp_ok_q ? 2'b00 : 2'b10));
            RID:    assert (!(rvalid && pend_r && last_ar[5:2] == 4'd0) || (rdata == 32'h46435631 && rresp == 2'b00));
            RUNM:   assert (!(rvalid && pend_r && last_ar[5:2] >= 4'd8) || (rdata == 32'd0 && rresp == 2'b10));
            COMMIT: assert (!coef_we || (!busy && awa_s == 4'd7 && strb_s == 4'hF));
            DROP:   assert (!drop_q || u.dropped);
            SATP:   assert (!pulse_q || u.sat);
            CRESP:  assert (!(commit_q && exec_q) || (!bvalid || bresp == 2'b00));
        end
    end
endmodule

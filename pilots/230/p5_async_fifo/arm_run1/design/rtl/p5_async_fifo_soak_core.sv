// Register core of the asynchronous FIFO soak: registers, PRBS-31 writer (clk_wr), 512x32 asynchronous FIFO,
// reader/checker (clk_rd, p5_rd_side), snapshot of the reader counters by handshake.
module p5_async_fifo_soak_core #(
    parameter int          COUNTER_WIDTH_BITS      = 32,
    parameter logic [30:0] PRBS_SEED               = 31'h7FFFFFFF,
    parameter int          SLOW_READ_PERIOD_CYCLES = 8,
    parameter logic [31:0] DESIGN_ID               = 32'h20950001
) (
    input  logic        clk_wr,
    input  logic        clk_rd,
    input  logic        rst,          // active high, asynchronous to both clocks
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam int W = COUNTER_WIDTH_BITS;

    assign sfp_tx_disable = 1'b1;

    // ---------------- reset synchronisers ----------------
    logic rst_wr, rst_rd;
    reset_gen u_rstgen (.rst(rst), .clk_wr(clk_wr), .clk_rd(clk_rd), .rst_wr(rst_wr), .rst_rd(rst_rd));

    // ---------------- build stamp ----------------
    logic [31:0] build_word;
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.DATA(build_word), .CFGCLK(), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */

    // ---------------- control registers (clk_wr) ----------------
    logic        run, slow_rd, inj_pend, snap_t;
    logic [31:0] scratch;
    logic [3:0]  clr_cnt;
    logic        clr_lvl;
    wire         clr_act = (clr_cnt != 4'd0);

    // crossing results
    logic        inj_ack_s, err_s;
    logic [9:0]  rgray_s;
    logic [9:0]  rbin;

    always_comb begin
        for (int i = 0; i < 10; i++) rbin[i] = ^(rgray_s >> i);
    end

    // ---------------- writer ----------------
    logic [9:0]  wptr, wgray;
    logic [30:0] wprbs;
    logic [31:0] wword;
    logic [30:0] wprbs_n;
    p5_prbs31 u_wprbs (.s(wprbs), .word(wword), .s_next(wprbs_n));

    wire [9:0] occ    = wptr - rbin;
    wire       full   = occ[9];
    wire       we_mem = run & ~full & ~clr_act;
    wire [9:0] wptr_n = wptr + 10'd1;

    logic [W-1:0] words_w, ovf, stall;
    logic [9:0]   occ_max;

    // ---------------- snapshot ----------------
    logic [W-1:0] s_words_w, s_words_r, s_errs, s_ovf, s_unf, s_stall;
    logic [9:0]   s_occ;

    // ---------------- reader and crossings ----------------
    logic [8:0]    raddr;
    logic [9:0]    rgray;
    logic [31:0]   dout;
    logic          inj_done, err_flag;
    logic          hs_send, hs_rcv, hs_req;
    logic [3*W-1:0] hs_in, hs_out;

    logic [2:0] ctl_rd;       // {clr, inj, slow} in clk_rd
    logic [9:0] wgray_rd;
    logic       snap_rd;

    logic [1:0] back_s;
    top #(.W(W)) u_xing (
        .clk_wr(clk_wr), .clk_rd(clk_rd),
        .ctl_wr({clr_lvl, inj_pend, slow_rd}), .ctl_rd(ctl_rd),
        .snap_t(snap_t), .snap_rd(snap_rd),
        .back_rd({inj_done, err_flag}), .back_wr(back_s),
        .hs_in(hs_in), .hs_send(hs_send), .hs_rcv(hs_rcv), .hs_req(hs_req), .hs_out(hs_out));
    assign inj_ack_s = back_s[1];
    assign err_s     = back_s[0];

    async_fifo u_fifo (
        .clk_wr(clk_wr), .clk_rd(clk_rd), .we(we_mem), .waddr(wptr[8:0]), .wdata(wword),
        .wgray(wgray), .raddr(raddr), .rgray(rgray), .dout(dout),
        .wgray_rd(wgray_rd), .rgray_s(rgray_s));

    p5_rd_side #(.W(W), .SEED(PRBS_SEED), .SLOW_PERIOD(SLOW_READ_PERIOD_CYCLES)) u_rd (
        .clk(clk_rd), .rst(rst_rd), .clr(ctl_rd[2]), .slow(ctl_rd[0]), .inj_lvl(ctl_rd[1]),
        .snap_req(snap_rd), .wgray(wgray_rd), .dout(dout), .raddr(raddr), .rgray(rgray),
        .inj_done(inj_done), .err_flag(err_flag), .hs_send(hs_send), .hs_data(hs_in), .hs_rcv(hs_rcv));

    // ---------------- clk_wr sequential logic ----------------
    wire ctrl_wr = h_we && (h_addr == 12'h010);
    wire snap_wr = h_we && (h_addr == 12'h030);

    always_ff @(posedge clk_wr) begin
        clr_lvl <= clr_act;

        if (rst_wr) begin
            run      <= 1'b0;
            slow_rd  <= 1'b0;
            inj_pend <= 1'b0;
            snap_t   <= 1'b0;
            scratch  <= '0;
            clr_cnt  <= 4'd0;
            h_rdata  <= '0;
        end else begin
            if (clr_cnt != 4'd0) clr_cnt <= clr_cnt - 4'd1;
            if (inj_ack_s && inj_pend) inj_pend <= 1'b0;
            if (h_we && h_addr == 12'h008) scratch <= h_wdata;
            if (ctrl_wr) begin
                run     <= h_wdata[0];
                slow_rd <= h_wdata[1];
                if (h_wdata[2] && !run) clr_cnt <= 4'd10;
                if (h_wdata[3] && !inj_ack_s) inj_pend <= 1'b1;
            end
            if (snap_wr) snap_t <= ~snap_t;
            if (h_re) begin
                case (h_addr)
                    12'h000: h_rdata <= DESIGN_ID;
                    12'h004: h_rdata <= build_word;
                    12'h008: h_rdata <= scratch;
                    12'h010: h_rdata <= {28'd0, inj_pend, 1'b0, slow_rd, run};
                    12'h014: h_rdata <= 32'(s_words_w);
                    12'h018: h_rdata <= 32'(s_words_r);
                    12'h01C: h_rdata <= 32'(s_errs);
                    12'h020: h_rdata <= 32'(s_ovf);
                    12'h024: h_rdata <= 32'(s_unf);
                    12'h028: h_rdata <= 32'(s_stall);
                    12'h02C: h_rdata <= {22'd0, s_occ};
                    default: h_rdata <= '0;
                endcase
            end
        end

        // writer, FIFO write pointer and counters
        if (rst_wr || clr_act) begin
            wptr    <= '0;
            wgray   <= '0;
            wprbs   <= PRBS_SEED;
            words_w <= '0;
            ovf     <= '0;
            stall   <= '0;
            occ_max <= '0;
        end else begin
            if (we_mem) begin
                wptr    <= wptr_n;
                wgray   <= wptr_n ^ (wptr_n >> 1);
                wprbs   <= wprbs_n;
                words_w <= words_w + W'(1);
            end
            if (we_mem && full) ovf <= ovf + W'(1);
            if (run && full)    stall <= stall + W'(1);
            if (occ > occ_max)  occ_max <= occ;
        end

        // snapshot of the clk_wr counters at the SNAPSHOT write
        if (rst_wr) begin
            s_words_w <= '0; s_ovf <= '0; s_stall <= '0; s_occ <= '0;
            s_words_r <= '0; s_errs <= '0; s_unf <= '0;
        end else begin
            if (snap_wr) begin
                s_words_w <= words_w;
                s_ovf     <= ovf;
                s_stall   <= stall;
                s_occ     <= occ_max;
            end
            if (hs_req) {s_unf, s_errs, s_words_r} <= hs_out;
        end

        led <= {err_s | (ovf != '0), run};
    end

endmodule

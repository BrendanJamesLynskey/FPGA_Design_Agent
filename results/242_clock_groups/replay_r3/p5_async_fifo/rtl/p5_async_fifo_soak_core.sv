// p5_async_fifo_soak_core: register core of the asynchronous FIFO soak test.
// This module's registers are all in clk_wr (25 MHz): register bus, PRBS-31 writer, writer counters, snapshot.
// The reader domain is prbs_rd (clk_rd), the FIFO is fifo, and every crossing is in fifo or cdc_ctrl.
// Reset model "reprogram": no reset input; every register starts from its initial value, and a power-up
// clear sequence (same as CLEAR) resets the FIFO and both generators before RUN is honoured.
module p5_async_fifo_soak_core #(
    parameter logic [31:0] DESIGN_ID            = 32'h20950001,
    parameter logic [30:0] PRBS_SEED            = 31'h7FFFFFFF,
    parameter int          FIFO_DEPTH_WORDS     = 512,
    parameter int          SLOW_READ_DIV_CYCLES = 8
) (
    input  logic        clk_wr,
    input  logic        clk_rd,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam int CW = $clog2(FIFO_DEPTH_WORDS) + 1;
    localparam logic [5:0] CLR_HOLD = 6'd40;   // clear sequence length in clk_wr clocks
    localparam logic [5:0] RST_PART = 6'd32;   // FIFO reset is asserted while clr_cnt is above this

    assign sfp_tx_disable = 1'b1;

    // ---------------------------------------------------------------- build stamp
    logic [31:0] build_word;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        usr_cfgclk;
    logic        usr_valid;
    /* verilator lint_on UNUSEDSIGNAL */
    USR_ACCESSE2 u_usr (.CFGCLK(usr_cfgclk), .DATA(build_word), .DATAVALID(usr_valid));

    // ---------------------------------------------------------------- writer domain
    logic [31:0] scratch  = '0;
    logic        run      = 1'b0;
    logic        slow     = 1'b0;
    logic        inj_tgl  = 1'b0;
    logic        snap_tgl = 1'b0;
    logic [5:0]  clr_cnt  = CLR_HOLD;
    logic        fifo_rst_q = 1'b1;
    logic        clr_lvl_q  = 1'b1;

    logic [31:0] ww = '0, ofl = '0, stall = '0, occ_max = '0;
    logic [31:0] hold_ww = '0, hold_of = '0, hold_st = '0, hold_occ = '0;
    logic [31:0] hold_wr = '0, hold_de = '0, hold_uf = '0;

    logic [30:0] prbs_w = PRBS_SEED;
    logic [30:0] prbs_w_next;
    logic [31:0] prbs_w_word;
    prbs31_next u_prbs_w (.state(prbs_w), .next_state(prbs_w_next), .word(prbs_w_word));

    logic            fifo_full;
    logic            wr_rst_busy;
    logic [CW-1:0]   wr_count;
    logic            err_rd_s;
    logic            wr_go;
    logic            wr_en;
    logic [CW-1:0]   occ_now;

    assign wr_go   = run && (clr_cnt == 6'd0) && !wr_rst_busy;
    assign wr_en   = wr_go && !fifo_full;
    assign occ_now = fifo_full ? CW'(FIFO_DEPTH_WORDS) : wr_count;

    // reader results arrive by handshake
    logic [95:0] hs_dest;
    logic        hs_req;

    // register bus, control, snapshot request
    always_ff @(posedge clk_wr) begin
        fifo_rst_q <= (clr_cnt > RST_PART);
        clr_lvl_q  <= (clr_cnt != 6'd0);
        if (clr_cnt != 6'd0) clr_cnt <= clr_cnt - 6'd1;
        if (h_we) begin
            case (h_addr)
                12'h008: scratch <= h_wdata;
                12'h010: begin
                    run  <= h_wdata[0];
                    slow <= h_wdata[1];
                    if (h_wdata[2] && !run) clr_cnt <= CLR_HOLD;
                    if (h_wdata[3]) inj_tgl <= ~inj_tgl;
                end
                12'h030: begin
                    snap_tgl <= ~snap_tgl;
                    hold_ww  <= ww;
                    hold_of  <= ofl;
                    hold_st  <= stall;
                    hold_occ <= occ_max;
                end
                default: ;
            endcase
        end
        if (hs_req) {hold_wr, hold_de, hold_uf} <= hs_dest;
    end

    // writer: PRBS, counters
    always_ff @(posedge clk_wr) begin
        if (clr_cnt != 6'd0) begin
            prbs_w  <= PRBS_SEED;
            ww      <= '0;
            ofl     <= '0;
            stall   <= '0;
            occ_max <= '0;
        end else begin
            if (wr_en) begin
                prbs_w <= prbs_w_next;
                ww     <= ww + 32'd1;
            end
            if (wr_go && fifo_full)  stall <= stall + 32'd1;
            if (wr_en && fifo_full)  ofl   <= ofl + 32'd1;   // never: the writer is gated by full
            if (!wr_rst_busy && (32'(occ_now) > occ_max)) occ_max <= 32'(occ_now);
        end
    end

    // read data: shown within 2 clocks of h_re and held until the next h_re
    initial h_rdata = 32'd0;
    always_ff @(posedge clk_wr) begin
        if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {30'd0, slow, run};
                12'h014: h_rdata <= hold_ww;
                12'h018: h_rdata <= hold_wr;
                12'h01C: h_rdata <= hold_de;
                12'h020: h_rdata <= hold_of;
                12'h024: h_rdata <= hold_uf;
                12'h028: h_rdata <= hold_st;
                12'h02C: h_rdata <= hold_occ;
                default: h_rdata <= 32'd0;
            endcase
        end
    end

    assign led = {err_rd_s || (ofl != 32'd0), run};

    // ---------------------------------------------------------------- crossings and reader domain
    logic [3:0]  ctl_rd;
    logic        slow_r, clr_r, inj_r, snap_r;
    logic        err_r;
    logic [95:0] stage;
    logic        hs_send, hs_rcv;
    assign {snap_r, inj_r, clr_r, slow_r} = ctl_rd;

    cdc_ctrl u_cdc (
        .clk_wr(clk_wr), .clk_rd(clk_rd),
        .ctl_wr({snap_tgl, inj_tgl, clr_lvl_q, slow}), .ctl_rd(ctl_rd),
        .err_rd(err_r), .err_wr(err_rd_s),
        .res_rd(stage), .res_send(hs_send), .res_rcv(hs_rcv), .res_wr(hs_dest), .res_req(hs_req));

    logic        fifo_empty;
    logic        rd_rst_busy;
    logic        rd_en;
    logic [31:0] fifo_dout;
    fifo #(.DEPTH(FIFO_DEPTH_WORDS), .CW(CW)) u_fifo (
        .rst(fifo_rst_q),
        .wr_clk(clk_wr), .wr_en(wr_en), .din(prbs_w_word), .full(fifo_full),
        .wr_rst_busy(wr_rst_busy), .wr_data_count(wr_count),
        .rd_clk(clk_rd), .rd_en(rd_en), .dout(fifo_dout), .empty(fifo_empty), .rd_rst_busy(rd_rst_busy));

    prbs_rd #(.PRBS_SEED(PRBS_SEED), .SLOW_READ_DIV_CYCLES(SLOW_READ_DIV_CYCLES)) u_rd (
        .clk_rd(clk_rd), .slow_r(slow_r), .clr_r(clr_r), .inj_r(inj_r), .snap_r(snap_r),
        .fifo_dout(fifo_dout), .fifo_empty(fifo_empty), .rd_rst_busy(rd_rst_busy),
        .rd_en(rd_en), .err_r(err_r), .stage(stage), .hs_send(hs_send), .hs_rcv(hs_rcv));
endmodule

// Register core of the asynchronous FIFO soak: PRBS-31 writer on clk_wr, checker on clk_rd.
// Reset model: reprogram (no reset input); every register starts from its initial value.
/* verilator lint_off DECLFILENAME */
module soak_core #(
    parameter int FIFO_DEPTH = 512,
    parameter int DATA_WIDTH = 32,
    parameter int ADDR_WIDTH = 9,
    parameter int PRBS_SEED = 2147483647,
    parameter int DESIGN_ID = 546635777,
    parameter int SLOW_READ_DIV_CYCLES = 8,
    parameter int SYNC_STAGES = 2
) (
    input  logic        clk_wr,
    input  logic        clk_rd,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata = '0,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam int PW = ADDR_WIDTH + 1;
    localparam logic [30:0] SEED = PRBS_SEED[30:0];

    assign sfp_tx_disable = 1'b1;

    // ---------------- build stamp ----------------
    logic [31:0] build_word;
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.DATA(build_word), .DATAVALID(), .CFGCLK());
    /* verilator lint_on PINCONNECTEMPTY */

    // ---------------- clk_wr domain ----------------
    logic [31:0] scratch = '0;
    logic        run = 1'b0;
    logic        slow = 1'b0;
    logic        inj_p = 1'b0;
    logic        snap_p = 1'b0;
    logic        clr_p = 1'b0;

    logic [PW-1:0]   wptr = '0;
    logic [PW-1:0]   rptr_s;
    logic [30:0]     wprbs = SEED;
    logic [31:0]     wword;
    logic [30:0]     wprbs_n;
    logic [31:0]     words_w = '0;
    logic [31:0]     stall_w = '0;
    logic [31:0]     ovf_w = '0;
    logic [31:0]     occ_max = '0;

    logic [31:0] snap_ww = '0, snap_wr = '0, snap_de = '0, snap_ov = '0;
    logic [31:0] snap_un = '0, snap_st = '0, snap_occ = '0;

    prbs31_step u_wprbs (.s(wprbs), .w(wword), .s_n(wprbs_n));

    wire [PW-1:0] fill_w = wptr - rptr_s;
    wire          full   = (fill_w == PW'(FIFO_DEPTH));
    wire          wr_en  = run && !full;
    wire [PW-1:0] occ_new = fill_w + PW'(1);

    // reader-side results seen in this domain
    logic         err_s;
    logic         hs_req;
    logic [95:0]  hs_out;

    always_ff @(posedge clk_wr) begin
        inj_p  <= 1'b0;
        snap_p <= 1'b0;
        clr_p  <= 1'b0;

        if (wr_en) begin
            wptr    <= wptr + PW'(1);
            wprbs   <= wprbs_n;
            words_w <= words_w + 32'd1;
            if ({22'b0, occ_new} > occ_max) occ_max <= {22'b0, occ_new};
        end else if (run) begin
            stall_w <= stall_w + 32'd1;
        end

        if (snap_p) begin
            snap_ww  <= words_w;
            snap_st  <= stall_w;
            snap_ov  <= ovf_w;
            snap_occ <= occ_max;
        end
        if (hs_req) begin
            snap_wr  <= hs_out[95:64];
            snap_de  <= hs_out[63:32];
            snap_un  <= hs_out[31:0];
        end

        if (h_we) begin
            case (h_addr)
                12'h008: scratch <= h_wdata;
                12'h010: begin
                    run    <= h_wdata[0];
                    slow   <= h_wdata[1];
                    inj_p  <= h_wdata[3];
                    if (h_wdata[2] && !run) begin
                        clr_p   <= 1'b1;
                        wprbs   <= SEED;
                        words_w <= '0;
                        stall_w <= '0;
                        ovf_w   <= '0;
                        occ_max <= '0;
                    end
                end
                12'h030: snap_p <= 1'b1;
                default: ;
            endcase
        end

        if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= 32'(DESIGN_ID);
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {28'b0, 1'b0, 1'b0, slow, run};
                12'h014: h_rdata <= snap_ww;
                12'h018: h_rdata <= snap_wr;
                12'h01C: h_rdata <= snap_de;
                12'h020: h_rdata <= snap_ov;
                12'h024: h_rdata <= snap_un;
                12'h028: h_rdata <= snap_st;
                12'h02C: h_rdata <= snap_occ;
                default: h_rdata <= 32'd0;
            endcase
        end
    end

    assign led = {err_s || (ovf_w != 32'd0), run};

    // ---------------- FIFO memory ----------------
    logic [DATA_WIDTH-1:0] ram_q;
    logic [ADDR_WIDTH-1:0] ram_raddr;
    (* ram_style = "block" *) logic [DATA_WIDTH-1:0] mem [0:(1<<ADDR_WIDTH)-1];
    always_ff @(posedge clk_wr) if (wr_en) mem[wptr[ADDR_WIDTH-1:0]] <= wword;
    always_ff @(posedge clk_rd) ram_q <= mem[ram_raddr];

    // ---------------- crossings ----------------
    logic [PW-1:0] wptr_s;
    logic [PW-1:0] rptr = '0;

    xpm_cdc_gray #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(PW)) u_w2r (
        .src_clk(clk_wr), .src_in_bin(wptr), .dest_clk(clk_rd), .dest_out_bin(wptr_s));
    xpm_cdc_gray #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(PW)) u_r2w (
        .src_clk(clk_rd), .src_in_bin(rptr), .dest_clk(clk_wr), .dest_out_bin(rptr_s));

    logic slow_s;
    xpm_cdc_array_single #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                           .SRC_INPUT_REG(1), .WIDTH(1)) u_slow (
        .src_clk(clk_wr), .src_in(slow), .dest_clk(clk_rd), .dest_out(slow_s));

    logic err_r = 1'b0;
    xpm_cdc_array_single #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                           .SRC_INPUT_REG(1), .WIDTH(1)) u_err (
        .src_clk(clk_rd), .src_in(err_r), .dest_clk(clk_wr), .dest_out(err_s));

    logic inj_rd, clr_rd, snap_rd;
    xpm_cdc_pulse #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_inj (
        .src_clk(clk_wr), .src_pulse(inj_p), .src_rst(1'b0), .dest_clk(clk_rd), .dest_pulse(inj_rd), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_clr (
        .src_clk(clk_wr), .src_pulse(clr_p), .src_rst(1'b0), .dest_clk(clk_rd), .dest_pulse(clr_rd), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_snp (
        .src_clk(clk_wr), .src_pulse(snap_p), .src_rst(1'b0), .dest_clk(clk_rd), .dest_pulse(snap_rd), .dest_rst(1'b0));

    // ---------------- clk_rd domain: reader and checker ----------------
    logic [30:0] rprbs = SEED;
    logic [31:0] rexp;
    logic [30:0] rprbs_n;
    prbs31_step u_rprbs (.s(rprbs), .w(rexp), .s_n(rprbs_n));

    logic [31:0] words_r = '0, data_errs = '0, under_r = '0;
    logic [3:0]  slow_cnt = '0;
    logic        flush = 1'b0;
    logic        dvalid = 1'b0;
    logic        inj_pend = 1'b0;

    wire empty   = (wptr_s == rptr);
    wire can_pop = !empty && (flush || slow_cnt == 4'd0);
    wire pop_bad = can_pop && empty;   // a pop while empty cannot happen: counted for the record
    assign ram_raddr = rptr[ADDR_WIDTH-1:0];

    // snapshot hand-over
    logic [95:0] hold = '0;
    logic        hs_send = 1'b0;
    logic [1:0]  hs_state = 2'd0;
    logic        hs_rcv;

    always_ff @(posedge clk_rd) begin
        dvalid <= 1'b0;
        if (slow_cnt != 4'd0) slow_cnt <= slow_cnt - 4'd1;
        if (can_pop) begin
            rptr   <= rptr + PW'(1);
            dvalid <= !flush;
            if (slow_s && !flush) slow_cnt <= 4'(SLOW_READ_DIV_CYCLES - 1);
        end
        if (pop_bad) under_r <= under_r + 32'd1;
        if (flush && empty) begin
            flush <= 1'b0;
            rprbs <= SEED;
        end
        if (dvalid) begin
            rprbs   <= rprbs_n;
            words_r <= words_r + 32'd1;
            if ((ram_q ^ {31'b0, inj_pend}) != rexp) begin
                data_errs <= data_errs + 32'd1;
                err_r     <= 1'b1;
            end
        end
        if (dvalid) inj_pend <= inj_rd;
        else if (inj_rd) inj_pend <= 1'b1;
        if (under_r != 32'd0) err_r <= 1'b1;

        // snapshot handshake
        case (hs_state)
            2'd0: if (snap_rd) begin
                hold     <= {words_r, data_errs, under_r};
                hs_send  <= 1'b1;
                hs_state <= 2'd1;
            end
            2'd1: if (hs_rcv) begin
                hs_send  <= 1'b0;
                hs_state <= 2'd2;
            end
            default: if (!hs_rcv) hs_state <= 2'd0;
        endcase

        if (clr_rd) begin
            flush     <= 1'b1;
            dvalid    <= 1'b0;
            slow_cnt  <= 4'd0;
            rprbs     <= SEED;
            words_r   <= '0;
            data_errs <= '0;
            under_r   <= '0;
            err_r     <= 1'b0;
        end
    end

    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(SYNC_STAGES), .WIDTH(96)) u_snap (
        .src_clk(clk_rd), .src_in(hold), .src_send(hs_send), .src_rcv(hs_rcv),
        .dest_clk(clk_wr), .dest_out(hs_out), .dest_req(hs_req), .dest_ack(1'b0));
endmodule

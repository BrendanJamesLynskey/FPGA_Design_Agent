// FIR register core: host register port (clk), FIFOs, run/clear control, datapath on clk_dp.
// Reset model: reprogram (initial values) plus the synchronous host reset rst (clk domain).
/* verilator lint_off PINMISSING */
/* verilator lint_off PINCONNECTEMPTY */
module fir_core #(
    parameter [31:0] DESIGN_ID = 32'h20940001
) (
    input  logic        clk,        // 25 MHz register-bus clock
    input  logic        clk_dp,     // 250 MHz datapath clock
    input  logic        rst,        // active high, synchronous to clk
    input  logic        dp_locked,  // MMCM locked (clk_dp valid)
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // ---------------- build stamp ----------------
    logic [31:0] build_word;
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());

    // ---------------- datapath reset (clk_dp) ----------------
    logic dp_rst;
    logic arst_r = 1'b1;
    logic locked25;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_dprst (
        .dest_arst(dp_rst), .dest_clk(clk_dp), .src_arst(arst_dp));

    // bring the clk25-domain reset request into clk_dp before the reset synchroniser
    logic arst_s;
    logic arst_dp = 1'b1;
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_arst_x (
        .src_clk(clk), .src_in(arst_r), .dest_clk(clk_dp), .dest_out(arst_s));
    always_ff @(posedge clk_dp) arst_dp <= arst_s;

    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_lk (
        .src_clk(clk_dp), .src_in(dp_locked), .dest_clk(clk), .dest_out(locked25));

    // registered (glitch-free) source of the asynchronous datapath reset
    always_ff @(posedge clk) arst_r <= rst | ~locked25;

    // ---------------- clk domain: registers ----------------
    localparam [11:0] A_ID = 12'h000, A_BUILD = 12'h004, A_SCR = 12'h008, A_CTRL = 12'h010, A_PUSH = 12'h014,
                      A_POP = 12'h018, A_STAT = 12'h01C, A_SAT = 12'h020, A_DONE = 12'h024;

    logic [31:0] scratch = 32'd0;
    logic        busy25 = 1'b0;
    logic [2:0]  clr_hold = 3'd0;
    logic [2:0]  run_wait = 3'd0;
    logic        clr_p25 = 1'b0, run_p25 = 1'b0;
    logic [10:0] pop_cnt = 11'd0;

    wire         done_p25;
    wire [10:0]  in_cnt, out_cnt;
    wire         in_wbusy;
    wire         out_empty;
    wire [15:0]  out_dout;
    wire [31:0]  sat_s, done_s;

    wire wr_ctrl = h_we && (h_addr == A_CTRL);
    wire push_req = h_we && (h_addr == A_PUSH);
    // Pushes made while the input FIFO is held in reset (after CLEAR) wait in a small queue.
    logic [15:0] pq [0:63];
    logic [5:0]  pq_w = 6'd0, pq_r = 6'd0;
    logic [6:0]  pq_n = 7'd0;
    wire         pq_flush = wr_ctrl && h_wdata[0];
    wire         push_en = (pq_n != 7'd0) && !in_wbusy && !in_rst;
    wire [15:0]  push_d  = pq[pq_r];
    always_ff @(posedge clk) begin
        if (pq_flush || rst) begin
            pq_w <= 6'd0; pq_r <= 6'd0; pq_n <= 7'd0;
        end else begin
            if (push_req && pq_n != 7'd64) begin
                pq[pq_w] <= h_wdata[15:0];
                pq_w <= pq_w + 6'd1;
            end
            if (push_en) pq_r <= pq_r + 6'd1;
            pq_n <= pq_n + {6'd0, (push_req && pq_n != 7'd64)} - {6'd0, push_en};
        end
    end
    wire pop_en  = h_re && (h_addr == A_POP) && !out_empty;
    wire in_rst  = rst | (clr_hold != 3'd0);

    always_ff @(posedge clk) begin
        clr_p25 <= 1'b0;
        run_p25 <= 1'b0;
        if (clr_hold != 3'd0) clr_hold <= clr_hold - 3'd1;
        if (run_wait != 3'd0) begin
            run_wait <= run_wait - 3'd1;
            if (run_wait == 3'd1) begin
                if (in_cnt != 11'd0) run_p25 <= 1'b1;
                else busy25 <= 1'b0;
            end
        end
        if (done_p25) busy25 <= 1'b0;
        if (pop_en) pop_cnt <= pop_cnt + 11'd1;
        if (h_we && h_addr == A_SCR) scratch <= h_wdata;
        if (wr_ctrl) begin
            if (h_wdata[0]) begin
                clr_p25  <= 1'b1;
                clr_hold <= 3'd4;
                busy25   <= 1'b0;
                run_wait <= 3'd0;
                pop_cnt  <= 11'd0;
            end else if (h_wdata[1] && !busy25) begin
                busy25   <= 1'b1;
                run_wait <= 3'd4;
            end
        end
        if (rst) begin
            scratch <= 32'd0; busy25 <= 1'b0; clr_hold <= 3'd0; run_wait <= 3'd0;
            clr_p25 <= 1'b0; run_p25 <= 1'b0; pop_cnt <= 11'd0;
        end
    end

    always_ff @(posedge clk) begin
        if (h_re) begin
            case (h_addr)
                A_ID:    h_rdata <= DESIGN_ID;
                A_BUILD: h_rdata <= build_word;
                A_SCR:   h_rdata <= scratch;
                A_POP:   h_rdata <= out_empty ? 32'd0 : {1'b1, 15'd0, out_dout};
                A_STAT:  h_rdata <= {1'b0, out_cnt, 4'd0, 1'b0, in_cnt, 3'd0, busy25};
                A_SAT:   h_rdata <= sat_s;
                A_DONE:  h_rdata <= done_s;
                default: h_rdata <= 32'd0;
            endcase
        end
    end
    initial h_rdata = 32'd0;

    assign led = {locked25, busy25};

    // ---------------- crossings clk -> clk_dp ----------------
    wire clr_p_dp, run_p_dp;
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_clr (
        .dest_pulse(clr_p_dp), .dest_clk(clk_dp), .dest_rst(1'b0),
        .src_clk(clk), .src_pulse(clr_p25), .src_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_run (
        .dest_pulse(run_p_dp), .dest_clk(clk_dp), .dest_rst(1'b0),
        .src_clk(clk), .src_pulse(run_p25), .src_rst(1'b0));

    wire [10:0] pop_sync;
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(11)) u_pop (
        .src_clk(clk), .src_in_bin(pop_cnt), .dest_clk(clk_dp), .dest_out_bin(pop_sync));

    // ---------------- clk_dp domain ----------------
    logic [4:0]  clr_cnt = 5'd0;
    logic        run_act = 1'b0;
    logic [2:0]  dwait = 3'd0;
    logic [10:0] wr_cnt = 11'd0;
    logic        room_r = 1'b0;
    logic        v_r = 1'b0;
    logic [15:0] x_r;
    logic [31:0] sat_cnt = 32'd0, done_cnt = 32'd0;

    wire        in_empty;
    wire [15:0] in_dout;
    wire        out_wbusy;
    wire        dp_out_valid, dp_sat, dp_pipe_busy;
    wire [15:0] dp_y;

    wire clr_act = (clr_cnt != 5'd0);
    wire rst_any = dp_rst | clr_act;
    wire out_rst = dp_rst | clr_act;

    wire issue = run_act & ~in_empty & room_r & ~out_wbusy & ~rst_any;
    wire [10:0] wr_cnt_n = rst_any ? 11'd0 : (wr_cnt + {10'd0, issue});
    /* verilator lint_off UNUSEDSIGNAL */
    wire [10:0] occ_n = wr_cnt_n - pop_sync;
    /* verilator lint_on UNUSEDSIGNAL */
    wire done_cond = run_act & in_empty & ~issue & ~v_r & ~dp_pipe_busy;

    always_ff @(posedge clk_dp) begin
        wr_cnt <= wr_cnt_n;
        room_r <= ~occ_n[10];
        x_r    <= in_dout;
        v_r    <= issue;
        if (clr_p_dp) clr_cnt <= 5'd31;
        else if (clr_cnt != 5'd0) clr_cnt <= clr_cnt - 5'd1;
        if (run_p_dp && !clr_act) run_act <= 1'b1;
        if (done_cond) begin run_act <= 1'b0; dwait <= 3'd5; end
        else if (dwait != 3'd0) dwait <= dwait - 3'd1;
        if (dp_out_valid) begin
            done_cnt <= done_cnt + 32'd1;
            sat_cnt  <= sat_cnt + {31'd0, dp_sat};
        end
        if (rst_any) begin
            run_act <= 1'b0; dwait <= 3'd0; done_cnt <= 32'd0; sat_cnt <= 32'd0; v_r <= 1'b0;
        end
        if (dp_rst) clr_cnt <= 5'd0;
    end

    wire done_src = (dwait == 3'd1);

    fir_datapath u_dp (
        .clk(clk_dp), .rst(rst_any), .in_valid(v_r), .x(x_r),
        .out_valid(dp_out_valid), .y(dp_y), .sat(dp_sat), .pipe_busy(dp_pipe_busy));

    // ---------------- crossings clk_dp -> clk ----------------
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_done (
        .dest_pulse(done_p25), .dest_clk(clk), .dest_rst(1'b0),
        .src_clk(clk_dp), .src_pulse(done_src), .src_rst(1'b0));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_sat (
        .src_clk(clk_dp), .src_in_bin(sat_cnt), .dest_clk(clk), .dest_out_bin(sat_s));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_done_c (
        .src_clk(clk_dp), .src_in_bin(done_cnt), .dest_clk(clk), .dest_out_bin(done_s));

    // ---------------- FIFOs ----------------
    // input FIFO: write clk (host push), read clk_dp
    xpm_fifo_async #(.CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"),
        .FIFO_MEMORY_TYPE("block"), .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(1024), .FULL_RESET_VALUE(0),
        .RD_DATA_COUNT_WIDTH(11), .READ_DATA_WIDTH(16), .READ_MODE("fwft"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(0), .USE_ADV_FEATURES("0004"), .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(16),
        .WR_DATA_COUNT_WIDTH(11)) u_fin (
        .dout(in_dout), .empty(in_empty), .wr_data_count(in_cnt), .wr_rst_busy(in_wbusy),
        .din(push_d), .injectdbiterr(1'b0), .injectsbiterr(1'b0),
        .rd_clk(clk_dp), .rd_en(issue), .rst(in_rst), .sleep(1'b0), .wr_clk(clk), .wr_en(push_en));

    // output FIFO: write clk_dp (results), read clk (host pop)
    xpm_fifo_async #(.CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"),
        .FIFO_MEMORY_TYPE("block"), .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(1024), .FULL_RESET_VALUE(0),
        .RD_DATA_COUNT_WIDTH(11), .READ_DATA_WIDTH(16), .READ_MODE("fwft"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(0), .USE_ADV_FEATURES("0400"), .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(16),
        .WR_DATA_COUNT_WIDTH(11)) u_fout (
        .dout(out_dout), .empty(out_empty), .rd_data_count(out_cnt), .wr_rst_busy(out_wbusy),
        .din(dp_y), .injectdbiterr(1'b0), .injectsbiterr(1'b0),
        .rd_clk(clk), .rd_en(pop_en), .rst(out_rst), .sleep(1'b0), .wr_clk(clk_dp), .wr_en(dp_out_valid));
endmodule

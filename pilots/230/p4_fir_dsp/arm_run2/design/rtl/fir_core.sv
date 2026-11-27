// Register core of the 32-tap symmetric FIR: host register port (clk25), FIFOs, LEDs, CDC to the datapath (clk_dp).
/* verilator lint_off PINCONNECTEMPTY */
module fir_core (
    input  logic        clk25,
    input  logic        clk_dp,
    input  logic        rst,            // active high, clk25 domain
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam logic [11:0] A_ID = 12'h000, A_BUILD = 12'h004, A_SCR = 12'h008, A_CTRL = 12'h010,
                            A_PUSH = 12'h014, A_POP = 12'h018, A_STAT = 12'h01C, A_SAT = 12'h020,
                            A_DONE = 12'h024;

    assign sfp_tx_disable = 1'b1;

    // ---- reset into clk_dp ----
    logic rst_dp;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_dp (
        .dest_clk(clk_dp), .src_arst(rst), .dest_arst(rst_dp));

    // ---- build stamp ----
    logic [31:0] build_word;
    /* verilator lint_off PINMISSING */
    USR_ACCESSE2 u_usr (.DATA(build_word), .CFGCLK(), .DATAVALID());
    /* verilator lint_on PINMISSING */

    // ---- FIFOs ----
    logic        in_full, in_empty_dp, in_rd_en_dp;
    logic [15:0] in_dout;
    logic [11:0] in_cnt;
    logic        in_wr_en;
    logic        in_rst_r = 1'b1;
    logic [3:0]  in_rst_cnt = 4'd15;
    logic        in_wr_busy, in_rd_busy;

    logic        out_empty, out_rd_en, out_wr_en, out_rst_dp, out_wr_busy, out_rd_busy;
    logic [15:0] out_dout, out_din;
    logic [11:0] out_cnt, out_wr_cnt;

    xpm_fifo_async #(
        .CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"),
        .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(2048), .FULL_RESET_VALUE(0),
        .PROG_EMPTY_THRESH(10), .PROG_FULL_THRESH(10), .RD_DATA_COUNT_WIDTH(12), .READ_DATA_WIDTH(16),
        .READ_MODE("fwft"), .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0), .USE_ADV_FEATURES("0404"),
        .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(16), .WR_DATA_COUNT_WIDTH(12)) u_in_fifo (
        .rst(in_rst_r), .wr_clk(clk25), .wr_en(in_wr_en), .din(h_wdata[15:0]), .full(in_full),
        .rd_clk(clk_dp), .rd_en(in_rd_en_dp), .dout(in_dout), .empty(in_empty_dp),
        .wr_data_count(in_cnt), .rd_data_count(), .wr_rst_busy(in_wr_busy), .rd_rst_busy(in_rd_busy),
        .sleep(1'b0), .injectsbiterr(1'b0), .injectdbiterr(1'b0),
        .almost_empty(), .almost_full(), .data_valid(), .overflow(), .underflow(), .prog_empty(),
        .prog_full(), .sbiterr(), .dbiterr(), .wr_ack());

    xpm_fifo_async #(
        .CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"),
        .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(2048), .FULL_RESET_VALUE(0),
        .PROG_EMPTY_THRESH(10), .PROG_FULL_THRESH(10), .RD_DATA_COUNT_WIDTH(12), .READ_DATA_WIDTH(16),
        .READ_MODE("fwft"), .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0), .USE_ADV_FEATURES("0404"),
        .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(16), .WR_DATA_COUNT_WIDTH(12)) u_out_fifo (
        .rst(out_rst_dp), .wr_clk(clk_dp), .wr_en(out_wr_en), .din(out_din), .full(),
        .rd_clk(clk25), .rd_en(out_rd_en), .dout(out_dout), .empty(out_empty),
        .wr_data_count(out_wr_cnt), .rd_data_count(out_cnt), .wr_rst_busy(out_wr_busy), .rd_rst_busy(out_rd_busy),
        .sleep(1'b0), .injectsbiterr(1'b0), .injectdbiterr(1'b0),
        .almost_empty(), .almost_full(), .data_valid(), .overflow(), .underflow(), .prog_empty(),
        .prog_full(), .sbiterr(), .dbiterr(), .wr_ack());

    // ---- host-side registers ----
    logic [31:0] scratch = 32'd0;
    logic        clr_p = 1'b0, run_p = 1'b0;
    logic        pop_v = 1'b0;
    logic        busy_loc = 1'b0;
    logic        busy_dp, busy_s;
    logic [63:0] snap;
    logic [23:0] hb = 24'd0;

    logic busy_o;
    assign busy_o = busy_loc | busy_s;

    assign in_wr_en  = h_we && (h_addr == A_PUSH) && (in_cnt < 12'd1024) && !in_wr_busy;
    assign out_rd_en = pop_v;

    always_ff @(posedge clk25) begin
        clr_p <= 1'b0; run_p <= 1'b0; pop_v <= 1'b0;
        hb <= hb + 24'd1;
        if (rst) begin
            scratch <= 32'd0; busy_loc <= 1'b0; in_rst_cnt <= 4'd15; in_rst_r <= 1'b1;
        end else begin
            if (in_rst_cnt != 4'd0) in_rst_cnt <= in_rst_cnt - 4'd1;
            in_rst_r <= (in_rst_cnt > 4'd1);
            if (busy_s) busy_loc <= 1'b0;
            if (h_we && h_addr == A_SCR) scratch <= h_wdata;
            if (h_we && h_addr == A_CTRL) begin
                if (h_wdata[0]) begin
                    clr_p <= 1'b1; busy_loc <= 1'b0; in_rst_cnt <= 4'd15; in_rst_r <= 1'b1;
                end else if (h_wdata[1] && !busy_o && (in_cnt != 12'd0) && !in_rst_r) begin
                    run_p <= 1'b1; busy_loc <= 1'b1;
                end
            end
            if (h_re) begin
                pop_v <= (h_addr == A_POP) && !out_empty;
                case (h_addr)
                    A_ID:    h_rdata <= 32'd546570241;
                    A_BUILD: h_rdata <= build_word;
                    A_SCR:   h_rdata <= scratch;
                    A_POP:   h_rdata <= out_empty ? 32'd0 : {1'b1, 15'd0, out_dout};
                    A_STAT:  h_rdata <= {out_cnt, 4'd0, in_cnt, 3'd0, busy_o};
                    A_SAT:   h_rdata <= snap[63:32];
                    A_DONE:  h_rdata <= snap[31:0];
                    default: h_rdata <= 32'd0;
                endcase
            end
        end
    end
    initial h_rdata = 32'd0;

    assign led = {hb[23], busy_o};

    // ---- CDC ----
    logic clr_dp_p, run_dp_p;
    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_clr (
        .src_clk(clk25), .src_pulse(clr_p), .src_rst(1'b0), .dest_clk(clk_dp), .dest_rst(1'b0),
        .dest_pulse(clr_dp_p));
    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_run (
        .src_clk(clk25), .src_pulse(run_p), .src_rst(1'b0), .dest_clk(clk_dp), .dest_rst(1'b0),
        .dest_pulse(run_dp_p));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_busy (
        .src_clk(clk_dp), .src_in(busy_dp), .dest_clk(clk25), .dest_out(busy_s));

    // SAT_COUNT / SAMPLES_DONE snapshot through xpm_cdc_handshake, refreshed continuously
    logic [31:0] sat_dp, done_dp;
    logic        hs_send = 1'b0, hs_rcv, hs_dreq;
    logic [63:0] hs_sin = '0, hs_dout;
    always_ff @(posedge clk_dp) begin
        if (rst_dp) hs_send <= 1'b0;
        else if (!hs_send && !hs_rcv) begin hs_send <= 1'b1; hs_sin <= {sat_dp, done_dp}; end
        else if (hs_send && hs_rcv)   hs_send <= 1'b0;
    end
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(64)) u_hs (
        .src_clk(clk_dp), .src_in(hs_sin), .src_send(hs_send), .src_rcv(hs_rcv),
        .dest_clk(clk25), .dest_out(hs_dout), .dest_req(hs_dreq), .dest_ack(1'b0));
    initial snap = '0;
    always_ff @(posedge clk25) if (hs_dreq) snap <= hs_dout;

    // ---- datapath ----
    fir_engine u_engine (
        .clk(clk_dp), .rst(rst_dp), .clr_p(clr_dp_p), .run_p(run_dp_p),
        .in_empty(in_empty_dp), .in_dout(in_dout), .in_rd_en(in_rd_en_dp),
        .out_wr_cnt(out_wr_cnt), .out_wr_en(out_wr_en), .out_din(out_din), .out_rst(out_rst_dp),
        .busy(busy_dp), .sat_cnt(sat_dp), .done_cnt(done_dp));

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = &{1'b0, in_full, in_rd_busy, out_wr_busy, out_rd_busy, h_wdata[31:16]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

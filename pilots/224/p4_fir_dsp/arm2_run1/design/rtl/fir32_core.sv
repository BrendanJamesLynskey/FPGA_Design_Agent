// Register core of the 32-tap FIR: JTAG register port (clk_bus), FIFOs, datapath (clk_dp), LEDs.
/* verilator lint_off DECLFILENAME */
module fir_core (
    input  logic        clk_bus,
    input  logic        clk_dp,
    input  logic        rst_bus,      // active high, synchronous to clk_bus
    input  logic        rst_dp,       // active high, synchronous to clk_dp
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam logic [31:0] DESIGN_ID = 32'h20940001;

    assign sfp_tx_disable = 1'b1;

    // ---------------- build stamp ----------------
    logic [31:0] usr_data;
    logic usr_cfgclk, usr_valid;
    USR_ACCESSE2 u_usr (.DATA(usr_data), .CFGCLK(usr_cfgclk), .DATAVALID(usr_valid));
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_usr;
    assign unused_usr = usr_cfgclk ^ usr_valid;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] build_r;
    // USR_ACCESS data is static after configuration, launched by the config clock
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                           .SRC_INPUT_REG(0), .WIDTH(32)) u_build_cdc (
        .src_clk(1'b0), .src_in(usr_data), .dest_clk(clk_bus), .dest_out(build_r));

    // ---------------- decode ----------------
    wire a_scr  = (h_addr == 12'h008);
    wire a_ctrl = (h_addr == 12'h010);
    wire a_push = (h_addr == 12'h014);
    wire a_pop  = (h_addr == 12'h018);

    // ---------------- FIFOs ----------------
    logic [11:0] in_wcount, in_rcount, out_wcount, out_rcount;
    logic        in_wbusy, out_empty, in_empty_dp;
    logic [15:0] out_dout, in_dout;
    logic        in_rd_en, out_wr_en, out_rst_dp;
    logic [15:0] out_din;

    // recent accepted pushes: the write-side count lags by a few clocks
    logic [3:0]  push_hist;
    logic [2:0]  pend;
    assign pend = 3'(push_hist[0]) + 3'(push_hist[1]) + 3'(push_hist[2]) + 3'(push_hist[3]);
    wire [12:0] in_level = 13'(in_wcount) + 13'(pend);
    logic [4:0] in_rst_cnt;
    logic       in_rst;
    wire push_ok = h_we && a_push && (in_level < 13'd1024) && !in_wbusy && !in_rst;
    always_ff @(posedge clk_bus) begin
        push_hist <= {push_hist[2:0], push_ok};
        if (rst_bus) begin push_hist <= '0; end
    end

    in_fifo u_in (
        .rst(in_rst), .wr_clk(clk_bus), .wr_en(push_ok), .din(h_wdata[15:0]),
        .wr_count(in_wcount), .wr_busy(in_wbusy),
        .rd_clk(clk_dp), .rd_en(in_rd_en), .dout(in_dout), .empty(in_empty_dp),
        .rd_count(in_rcount)
    );

    wire pop_en = h_re && a_pop && !out_empty;
    out_fifo u_out (
        .rst(out_rst_dp), .wr_clk(clk_dp), .wr_en(out_wr_en), .din(out_din),
        .wr_count(out_wcount),
        .rd_clk(clk_bus), .rd_en(pop_en), .dout(out_dout), .empty(out_empty),
        .rd_count(out_rcount)
    );

    // ---------------- commands ----------------
    logic clr_b, run_b, clr_dp, run_dp;
    logic [31:0] scratch;
    always_ff @(posedge clk_bus) begin
        clr_b <= 1'b0; run_b <= 1'b0;
        if (rst_bus) begin
            scratch <= '0; in_rst_cnt <= 5'd16; in_rst <= 1'b1;
        end else begin
            if (in_rst_cnt != 5'd0) in_rst_cnt <= in_rst_cnt - 5'd1;
            in_rst <= (in_rst_cnt != 5'd0);
            if (h_we && a_scr) scratch <= h_wdata;
            if (h_we && a_ctrl) begin
                if (h_wdata[0]) begin clr_b <= 1'b1; in_rst_cnt <= 5'd16; end
                else if (h_wdata[1]) run_b <= 1'b1;
            end
        end
    end

    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(1), .SIM_ASSERT_CHK(0)) u_clr_cdc (
        .src_clk(clk_bus), .src_rst(rst_bus), .src_pulse(clr_b),
        .dest_clk(clk_dp), .dest_rst(rst_dp), .dest_pulse(clr_dp));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(1), .SIM_ASSERT_CHK(0)) u_run_cdc (
        .src_clk(clk_bus), .src_rst(rst_bus), .src_pulse(run_b),
        .dest_clk(clk_dp), .dest_rst(rst_dp), .dest_pulse(run_dp));

    // ---------------- datapath ----------------
    logic        busy_dp, busy_b;
    logic [31:0] sat_dp, done_dp, sat_b, done_b;
    fir_datapath u_dp (
        .clk(clk_dp), .rst(rst_dp), .run(run_dp), .clr(clr_dp),
        .in_rd_en(in_rd_en), .in_dout(in_dout), .in_empty(in_empty_dp), .in_count(in_rcount),
        .out_wr_en(out_wr_en), .out_din(out_din), .out_count(out_wcount), .out_rst(out_rst_dp),
        .busy(busy_dp), .sat_cnt(sat_dp), .done_cnt(done_dp)
    );

    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_busy_cdc (
        .src_clk(clk_dp), .src_in(busy_dp), .dest_clk(clk_bus), .dest_out(busy_b));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_sat_cdc (
        .src_clk(clk_dp), .src_in_bin(sat_dp), .dest_clk(clk_bus), .dest_out_bin(sat_b));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_done_cdc (
        .src_clk(clk_dp), .src_in_bin(done_dp), .dest_clk(clk_bus), .dest_out_bin(done_b));

    // ---------------- read port ----------------
    always_ff @(posedge clk_bus) begin
        if (rst_bus) h_rdata <= '0;
        else if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build_r;
                12'h008: h_rdata <= scratch;
                12'h018: h_rdata <= out_empty ? 32'd0 : {16'h8000, out_dout};
                12'h01C: h_rdata <= {out_rcount, 4'd0, in_wcount, 3'd0, busy_b};
                12'h020: h_rdata <= sat_b;
                12'h024: h_rdata <= done_b;
                default: h_rdata <= '0;
            endcase
        end
    end

    // LED0 follows BUSY three clocks late, so it never reads low while a status read just saw BUSY high
    logic [2:0] busy_d;
    always_ff @(posedge clk_bus) busy_d <= {busy_d[1:0], busy_b};
    assign led = {~out_empty, busy_d[2]};
endmodule

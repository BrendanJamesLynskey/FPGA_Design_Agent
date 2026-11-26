// fir32_core: register map, FIFOs, control and LEDs of the 32-tap symmetric FIR.
//
// clk (25 MHz): host register port, input-FIFO write side, output-FIFO read side.
// clk_dsp (250 MHz): FIR datapath, input-FIFO read side, output-FIFO write side.
//
// Crossings: run/clear pulses (xpm_cdc_pulse); FIFO pointers and the done/sat counters (xpm_cdc_gray);
// reset into clk_dsp (xpm_cdc_async_rst).
// Datapath latency: 11 clk_dsp cycles from issue to out_valid (see fir_dsp), plus one for the input RAM read.
module fir32_core #(
    parameter logic [31:0] DESIGN_ID = 32'h20940001
) (
    input  logic        clk,
    input  logic        clk_dsp,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led
);
    localparam logic [11:0] A_ID = 12'h000, A_BUILD = 12'h004, A_SCRATCH = 12'h008, A_CTRL = 12'h010,
                            A_PUSH = 12'h014, A_POP = 12'h018, A_STATUS = 12'h01C, A_SAT = 12'h020,
                            A_DONE = 12'h024;

    // ------------------------------------------------------------------ clk_dsp reset
    logic rst_dsp;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_dsp (
        .dest_clk(clk_dsp), .src_arst(rst), .dest_arst(rst_dsp));

    // ------------------------------------------------------------------ build stamp
    logic [31:0] build_word;
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.DATA(build_word), .DATAVALID(), .CFGCLK());
    /* verilator lint_on PINCONNECTEMPTY */

    // ------------------------------------------------------------------ host (clk) state
    logic [31:0] scratch;
    logic [10:0] in_wptr, out_rptr, tgt;
    logic        busy, clr_pulse, run_pulse;
    logic [3:0]  run_dly;
    logic [3:0]  pend_cnt;        // CLEAR in flight to clk_dsp and back: counts read as 0 meanwhile
    logic [10:0] in_rptr_s;       // from clk_dsp
    logic [31:0] done_s, sat_s;   // from clk_dsp

    wire        clr_pend   = (pend_cnt != 4'd0);
    wire [10:0] in_rptr_e  = clr_pend ? 11'd0 : in_rptr_s;
    wire [10:0] in_cnt     = in_wptr - in_rptr_e;
    wire [10:0] out_cnt    = clr_pend ? 11'd0 : (done_s[10:0] - out_rptr);
    wire        in_full    = in_cnt[10];
    wire        out_nonempty = (out_cnt != 11'd0);
    /* verilator lint_off UNUSEDSIGNAL */
    wire [10:0] lag        = done_s[10:0] - tgt;
    /* verilator lint_on UNUSEDSIGNAL */
    wire        reached_ok = !clr_pend && !lag[10];

    wire wr_push = h_we && (h_addr == A_PUSH) && !in_full;
    wire wr_ctrl = h_we && (h_addr == A_CTRL);
    wire do_clear = wr_ctrl && h_wdata[0];
    wire do_run   = wr_ctrl && h_wdata[1] && !h_wdata[0] && !busy && (in_cnt != 11'd0);
    wire do_pop   = h_re && (h_addr == A_POP) && out_nonempty;

    logic [15:0] out_head;
    logic [9:0]  out_raddr;
    assign out_raddr = do_pop ? out_rptr[9:0] + 10'd1 : out_rptr[9:0];

    always_ff @(posedge clk) begin
        clr_pulse <= 1'b0;
        run_pulse <= 1'b0;
        if (rst) begin
            scratch <= '0; in_wptr <= '0; out_rptr <= '0; tgt <= '0; busy <= 1'b0;
            pend_cnt <= '0; run_dly <= '0; h_rdata <= '0;
        end else begin
            if (h_we && h_addr == A_SCRATCH) scratch <= h_wdata;
            if (wr_push) in_wptr <= in_wptr + 11'd1;
            if (do_pop)  out_rptr <= out_rptr + 11'd1;
            if (pend_cnt != 4'd0) pend_cnt <= pend_cnt - 4'd1;
            // RUN reaches clk_dsp after the input write pointer has (8 clk cycles of delay)
            if (run_dly != 4'd0) begin
                run_dly <= run_dly - 4'd1;
                if (run_dly == 4'd1) run_pulse <= 1'b1;
            end

            if (do_clear) begin
                in_wptr <= '0; out_rptr <= '0; busy <= 1'b0; pend_cnt <= 4'd10; clr_pulse <= 1'b1;
                run_dly <= '0;
            end else begin
                if (do_run) begin
                    busy <= 1'b1; tgt <= in_wptr; run_dly <= 4'd8;
                end else if (busy && reached_ok && run_dly == 4'd0 && !run_pulse) busy <= 1'b0;
            end

            if (h_re) begin
                case (h_addr)
                    A_ID:      h_rdata <= DESIGN_ID;
                    A_BUILD:   h_rdata <= build_word;
                    A_SCRATCH: h_rdata <= scratch;
                    A_POP:     h_rdata <= out_nonempty ? {1'b1, 15'd0, out_head} : 32'd0;
                    A_STATUS:  h_rdata <= {1'b0, out_cnt, 4'd0, 1'b0, in_cnt, 3'd0, busy};
                    A_SAT:     h_rdata <= clr_pend ? 32'd0 : sat_s;
                    A_DONE:    h_rdata <= clr_pend ? 32'd0 : done_s;
                    default:   h_rdata <= 32'd0;
                endcase
            end
        end
    end

    assign led = {1'b0, busy};

    // ------------------------------------------------------------------ pulses to clk_dsp
    logic run_d, clr_d;
    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(1), .SIM_ASSERT_CHK(0)) u_run (
        .src_clk(clk), .src_rst(rst), .src_pulse(run_pulse),
        .dest_clk(clk_dsp), .dest_rst(rst_dsp), .dest_pulse(run_d));
    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(1), .SIM_ASSERT_CHK(0)) u_clr (
        .src_clk(clk), .src_rst(rst), .src_pulse(clr_pulse),
        .dest_clk(clk_dsp), .dest_rst(rst_dsp), .dest_pulse(clr_d));

    // ------------------------------------------------------------------ pointers across
    logic [10:0] in_wp_d, out_rp_d;
    logic [10:0] in_rptr;
    logic [31:0] done, sat;
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(11)) u_wp (
        .src_clk(clk), .src_in_bin(in_wptr), .dest_clk(clk_dsp), .dest_out_bin(in_wp_d));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(11)) u_orp (
        .src_clk(clk), .src_in_bin(out_rptr), .dest_clk(clk_dsp), .dest_out_bin(out_rp_d));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(11)) u_irp (
        .src_clk(clk_dsp), .src_in_bin(in_rptr), .dest_clk(clk), .dest_out_bin(in_rptr_s));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_done (
        .src_clk(clk_dsp), .src_in_bin(done), .dest_clk(clk), .dest_out_bin(done_s));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_sat (
        .src_clk(clk_dsp), .src_in_bin(sat), .dest_clk(clk), .dest_out_bin(sat_s));

    // ------------------------------------------------------------------ input FIFO RAM
    logic [15:0] in_data;
    /* verilator lint_off PINCONNECTEMPTY */
    xpm_memory_sdpram #(.ADDR_WIDTH_A(10), .ADDR_WIDTH_B(10), .BYTE_WRITE_WIDTH_A(16),
        .CLOCKING_MODE("independent_clock"), .MEMORY_PRIMITIVE("block"), .MEMORY_SIZE(16384),
        .READ_DATA_WIDTH_B(16), .READ_LATENCY_B(1), .WRITE_DATA_WIDTH_A(16)) u_inram (
        .sleep(1'b0), .clka(clk), .ena(1'b1), .wea(wr_push), .addra(in_wptr[9:0]), .dina(h_wdata[15:0]),
        .injectsbiterra(1'b0), .injectdbiterra(1'b0),
        .clkb(clk_dsp), .rstb(1'b0), .enb(1'b1), .regceb(1'b1), .addrb(in_rptr[9:0]), .doutb(in_data),
        .sbiterrb(), .dbiterrb());

    // ------------------------------------------------------------------ clk_dsp control
    logic        run_active, issue_d;
    logic [10:0] issued;
    wire         rst_c    = rst_dsp | clr_d;
    wire         in_empty = (in_rptr == in_wp_d);
    /* verilator lint_off UNUSEDSIGNAL */
    wire [10:0]  committed = issued - out_rp_d;
    /* verilator lint_on UNUSEDSIGNAL */
    wire         issue    = run_active && !in_empty && !committed[10];

    logic        out_valid, out_sat;
    logic [15:0] out_data;

    always_ff @(posedge clk_dsp) begin
        if (rst_c) begin
            in_rptr <= '0; issued <= '0; run_active <= 1'b0; issue_d <= 1'b0;
            done <= '0; sat <= '0;
        end else begin
            if (run_d) run_active <= 1'b1;
            else if (run_active && in_empty) run_active <= 1'b0;
            issue_d <= issue;
            if (issue) begin in_rptr <= in_rptr + 11'd1; issued <= issued + 11'd1; end
            if (out_valid) begin
                done <= done + 32'd1;
                if (out_sat) sat <= sat + 32'd1;
            end
        end
    end

    fir_dsp u_fir (
        .clk(clk_dsp), .clr(rst_c), .in_valid(issue_d), .in_data(in_data),
        .out_valid(out_valid), .out_data(out_data), .out_sat(out_sat));

    // ------------------------------------------------------------------ output FIFO RAM
    xpm_memory_sdpram #(.ADDR_WIDTH_A(10), .ADDR_WIDTH_B(10), .BYTE_WRITE_WIDTH_A(16),
        .CLOCKING_MODE("independent_clock"), .MEMORY_PRIMITIVE("block"), .MEMORY_SIZE(16384),
        .READ_DATA_WIDTH_B(16), .READ_LATENCY_B(1), .WRITE_DATA_WIDTH_A(16)) u_outram (
        .sleep(1'b0), .clka(clk_dsp), .ena(1'b1), .wea(out_valid), .addra(done[9:0]), .dina(out_data),
        .injectsbiterra(1'b0), .injectdbiterra(1'b0),
        .clkb(clk), .rstb(1'b0), .enb(1'b1), .regceb(1'b1), .addrb(out_raddr), .doutb(out_head),
        .sbiterrb(), .dbiterrb());

    /* verilator lint_on PINCONNECTEMPTY */
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = |h_wdata[31:16];
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

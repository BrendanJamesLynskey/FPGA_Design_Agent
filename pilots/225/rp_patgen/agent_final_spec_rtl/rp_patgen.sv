// rp_patgen: P2 programmable pulse and pattern generator (block inside the Red Pitaya
// STEMlab 125-14 shell). One clock domain (clk, 125 MHz). rstn is the shell's active-low
// synchronous reset, inverted once here; the design uses active-high rst internally.
// dac_b is tied to 0. adc_a and adc_b are not used.
module rp_patgen (
    input  logic               clk,
    input  logic               rstn,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0]        sys_addr,      // only bits 19 to 0 are used
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic [31:0]        sys_wdata,
    input  logic               sys_wen,
    input  logic               sys_ren,
    output logic [31:0]        sys_rdata,
    output logic               sys_err,
    output logic               sys_ack,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic signed [13:0] adc_a,         // not used by this block
    input  logic signed [13:0] adc_b,         // not used by this block
    /* verilator lint_on UNUSEDSIGNAL */
    output logic signed [13:0] dac_a,
    output logic signed [13:0] dac_b
);
    wire rst = ~rstn;

    wire         running, done, clamped, emit_valid;
    wire         start_req, stop_req, start_go;
    wire  [31:0] periods, period_v, width_start_v;
    wire         mode_v;
    wire  [15:0] count_v, sdiv_v;
    wire   [4:0] patlen_v;
    wire  [13:0] lvl_hi_v, lvl_lo_v, raw;
    wire  [12:0] limit_v;
    wire [223:0] pat_v;

    // a START is accepted only when the block is stopped (and STOP is not in the same write)
    assign start_go = start_req & ~running & ~rst;

    bus_regs u_bus (
        .clk          (clk),
        .rst          (rst),
        .addr         (sys_addr[19:0]),
        .wdata        (sys_wdata),
        .wen          (sys_wen),
        .ren          (sys_ren),
        .running_i    (running),
        .done_i       (done),
        .clamped_i    (clamped),
        .periods_i    (periods),
        .start_go     (start_go),
        .rdata_q      (sys_rdata),
        .ack_q        (sys_ack),
        .err_q        (sys_err),
        .start_req    (start_req),
        .stop_req     (stop_req),
        .period_o     (period_v),
        .width_start_o(width_start_v),
        .mode_o       (mode_v),
        .count_o      (count_v),
        .patlen_o     (patlen_v),
        .sdiv_o       (sdiv_v),
        .lvl_hi_o     (lvl_hi_v),
        .lvl_lo_o     (lvl_lo_v),
        .limit_o      (limit_v),
        .pat_o        (pat_v)
    );

    sequencer u_seq (
        .clk          (clk),
        .rst          (rst),
        .start_go     (start_go),
        .stop_req     (stop_req),
        .cont_new     (sys_wdata[2]),
        .period_i     (period_v),
        .width_i      (width_start_v),
        .mode_i       (mode_v),
        .count_i      (count_v),
        .patlen_i     (patlen_v),
        .sdiv_i       (sdiv_v),
        .lvl_hi_i     (lvl_hi_v),
        .lvl_lo_i     (lvl_lo_v),
        .pat_i        (pat_v),
        .running_o    (running),
        .done_o       (done),
        .periods_o    (periods),
        .emit_valid_o (emit_valid),
        .raw_o        (raw)
    );

    output_clamp u_clamp (
        .clk          (clk),
        .rst          (rst),
        .start_go     (start_go),
        .running_i    (running),
        .emit_valid   (emit_valid),
        .raw_i        (raw),
        .limit_i      (limit_v),
        .dac_a        (dac_a),
        .clamped_q    (clamped)
    );

    assign dac_b = 14'sd0;
endmodule

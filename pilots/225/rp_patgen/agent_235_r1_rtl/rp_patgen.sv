// rp_patgen: programmable pulse and pattern generator for OUT1 of the Red Pitaya STEMlab
// 125-14. Built inside the vendor shell: clk is the shell's 125 MHz ADC clock and owns every
// pin and clock; the block has no board pins. Single clock domain, no CDC, no RAM, no DSP.
// rstn is the shell's active-low synchronous reset, inverted once here into rst.
module rp_patgen (
    input  logic               clk,        // 125 MHz shell ADC clock
    input  logic               rstn,       // shell adc_rstn, active low, synchronous
    input  logic        [31:0] sys_addr,   // shell register bus, byte address, bits 19:0 used
    input  logic        [31:0] sys_wdata,
    input  logic               sys_wen,    // one-cycle pulse
    input  logic               sys_ren,    // one-cycle pulse
    output logic        [31:0] sys_rdata,  // valid with sys_ack
    output logic               sys_err,    // high with sys_ack: the access failed
    output logic               sys_ack,    // one clock after sys_wen or sys_ren
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic signed [13:0] adc_a,      // IN1: not used by this block
    input  logic signed [13:0] adc_b,      // IN2: not used by this block
    /* verilator lint_on UNUSEDSIGNAL */
    output logic signed [13:0] dac_a,      // OUT1 sample, registered
    output logic signed [13:0] dac_b       // OUT2: tied to 0
);
    wire rst = ~rstn;

    assign dac_b = 14'sd0;

    wire               running;
    wire               done;
    wire               clamped;
    wire        [31:0] periods;
    wire               width_set;
    wire        [31:0] width_set_val;
    wire               start_req;
    wire               stop_req;
    wire               cont;
    wire               mode;
    wire        [31:0] period;
    wire        [31:0] width;
    wire signed [13:0] lvl_hi;
    wire signed [13:0] lvl_lo;
    wire        [15:0] count;
    wire        [12:0] limit;
    wire        [4:0]  pat_len;
    wire        [15:0] sample_div;
    wire        [223:0] pat;
    wire               load;
    wire               zero;
    wire               clr;
    wire signed [13:0] lvl;

    rp_reg_bus u_reg (
        .clk            (clk),
        .rst            (rst),
        .sys_addr       (sys_addr),
        .sys_wdata      (sys_wdata),
        .sys_wen        (sys_wen),
        .sys_ren        (sys_ren),
        .sys_rdata      (sys_rdata),
        .sys_err        (sys_err),
        .sys_ack        (sys_ack),
        .running        (running),
        .done           (done),
        .clamped        (clamped),
        .periods        (periods),
        .width_set      (width_set),
        .width_set_val  (width_set_val),
        .start_req      (start_req),
        .stop_req       (stop_req),
        .cont           (cont),
        .mode           (mode),
        .period         (period),
        .width          (width),
        .lvl_hi         (lvl_hi),
        .lvl_lo         (lvl_lo),
        .count          (count),
        .limit          (limit),
        .pat_len        (pat_len),
        .sample_div     (sample_div),
        .pat            (pat)
    );

    rp_seq u_seq (
        .clk            (clk),
        .rst            (rst),
        .start_req      (start_req),
        .stop_req       (stop_req),
        .cont           (cont),
        .mode           (mode),
        .period         (period),
        .width          (width),
        .lvl_hi         (lvl_hi),
        .lvl_lo         (lvl_lo),
        .count          (count),
        .pat_len        (pat_len),
        .sample_div     (sample_div),
        .pat            (pat),
        .running        (running),
        .done           (done),
        .periods        (periods),
        .width_set      (width_set),
        .width_set_val  (width_set_val),
        .load           (load),
        .zero           (zero),
        .clr            (clr),
        .lvl            (lvl)
    );

    rp_out_limit u_lim (
        .clk            (clk),
        .rst            (rst),
        .load           (load),
        .zero           (zero),
        .clr            (clr),
        .lvl            (lvl),
        .limit          (limit),
        .dac            (dac_a),
        .clamped        (clamped)
    );
endmodule

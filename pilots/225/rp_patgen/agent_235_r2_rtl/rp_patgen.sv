// rp_patgen: P2 programmable pulse and pattern generator on OUT1.
// Top of the block: wires the bus front end, register file, sequencer and
// output stage. rstn is the shell's active-low synchronous reset, inverted
// once here. dac_b is tied to 0. adc_a and adc_b are not used.
module rp_patgen (
    input  logic        clk,
    input  logic        rstn,
    input  logic [31:0] sys_addr,
    input  logic [31:0] sys_wdata,
    input  logic        sys_wen,
    input  logic        sys_ren,
    output logic [31:0] sys_rdata,
    output logic        sys_err,
    output logic        sys_ack,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [13:0] adc_a,
    input  logic [13:0] adc_b,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [13:0] dac_a,
    output logic [13:0] dac_b
);
    wire rst = ~rstn;

    wire [4:0]  idx;
    wire        wr_en;
    wire [31:0] rd_val;
    wire        running;
    wire        done;
    wire        clamped;
    wire [31:0] pdone;
    wire        start_eff;
    wire        stop_req;
    wire [12:0] limit;
    wire [3:0]  pat_idx;
    wire [13:0] pat_val;
    wire        run_mode;
    wire [31:0] run_period;
    wire [31:0] run_width;
    wire [13:0] run_hi;
    wire [13:0] run_lo;
    wire [15:0] run_count;
    wire        run_cont;
    wire [4:0]  run_pat_len;
    wire [15:0] run_div;
    wire        sv;
    wire [13:0] sval;

    rp_patgen_bus u_bus (
        .clk       (clk),
        .rst       (rst),
        .sys_addr  (sys_addr),
        .sys_wen   (sys_wen),
        .sys_ren   (sys_ren),
        .rd_val    (rd_val),
        .idx       (idx),
        .wr_en     (wr_en),
        .sys_rdata (sys_rdata),
        .sys_err   (sys_err),
        .sys_ack   (sys_ack)
    );

    rp_patgen_regs u_regs (
        .clk        (clk),
        .rst        (rst),
        .idx        (idx),
        .wr_en      (wr_en),
        .wdata      (sys_wdata),
        .rd_val     (rd_val),
        .running    (running),
        .done       (done),
        .clamped    (clamped),
        .pdone      (pdone),
        .start_eff  (start_eff),
        .stop_req   (stop_req),
        .limit      (limit),
        .pat_idx    (pat_idx),
        .pat_val    (pat_val),
        .run_mode   (run_mode),
        .run_period (run_period),
        .run_width  (run_width),
        .run_hi     (run_hi),
        .run_lo     (run_lo),
        .run_count  (run_count),
        .run_cont   (run_cont),
        .run_pat_len(run_pat_len),
        .run_div    (run_div)
    );

    rp_patgen_seq u_seq (
        .clk        (clk),
        .rst        (rst),
        .start_eff  (start_eff),
        .stop_req   (stop_req),
        .run_mode   (run_mode),
        .run_period (run_period),
        .run_width  (run_width),
        .run_hi     (run_hi),
        .run_lo     (run_lo),
        .run_count  (run_count),
        .run_cont   (run_cont),
        .run_pat_len(run_pat_len),
        .run_div    (run_div),
        .pat_idx    (pat_idx),
        .pat_val    (pat_val),
        .running    (running),
        .done       (done),
        .pdone      (pdone),
        .sv         (sv),
        .sval       (sval)
    );

    rp_patgen_out u_out (
        .clk       (clk),
        .rst       (rst),
        .running   (running),
        .stop_req  (stop_req),
        .start_eff (start_eff),
        .sv        (sv),
        .sval      (sval),
        .limit     (limit),
        .dac       (dac_a),
        .clamped   (clamped)
    );

    assign dac_b = 14'd0;
endmodule

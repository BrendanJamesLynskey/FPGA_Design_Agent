// rp_freqcount: frequency and period meter block inside the STEMlab 125-14 shell.
// Single clock (clk, 125 MHz, 8.000 ns). rstn is the shell's active-low synchronous
// reset, inverted once here into rst (active high). The shell system bus is the only
// register path: one access per cycle, sys_ack one cycle after sys_wen or sys_ren,
// sys_err for misaligned, unmapped, read-only and ID writes. dac_a and dac_b are 0.
// adc_b is not used by this block.
/* verilator lint_off UNUSEDSIGNAL */
module rp_freqcount #(
    parameter integer GATE_MIN_CYCLES   = 1000,
    parameter integer GATE_RESET_CYCLES = 125000000,
    parameter integer THR_HIGH_RESET    = 256,
    parameter integer THR_LOW_RESET     = -256,
    parameter logic [31:0] ID_VALUE     = 32'hFDA10101,
    parameter integer ADC_WIDTH         = 14,
    parameter integer SYS_ADDR_USED_BITS = 20
) (
    input  logic                       clk,
    input  logic                       rstn,
    input  logic [31:0]                sys_addr,
    input  logic [31:0]                sys_wdata,
    input  logic                       sys_wen,
    input  logic                       sys_ren,
    output logic [31:0]                sys_rdata,
    output logic                       sys_err,
    output logic                       sys_ack,
    input  logic signed [ADC_WIDTH-1:0] adc_a,
    input  logic signed [ADC_WIDTH-1:0] adc_b,
    output logic [ADC_WIDTH-1:0]       dac_a,
    output logic [ADC_WIDTH-1:0]       dac_b
);
/* verilator lint_on UNUSEDSIGNAL */

    localparam logic [31:0] GMIN       = GATE_MIN_CYCLES;
    localparam logic [31:0] GRESET     = GATE_RESET_CYCLES;

    // register indices for the decoder
    localparam logic [3:0] R_NONE  = 4'd0;
    localparam logic [3:0] R_ID    = 4'd1;
    localparam logic [3:0] R_SCR   = 4'd2;
    localparam logic [3:0] R_CTRL  = 4'd3;
    localparam logic [3:0] R_GLEN  = 4'd4;
    localparam logic [3:0] R_THRH  = 4'd5;
    localparam logic [3:0] R_THRL  = 4'd6;
    localparam logic [3:0] R_STAT  = 4'd7;
    localparam logic [3:0] R_EDGES = 4'd8;
    localparam logic [3:0] R_GACT  = 4'd9;
    localparam logic [3:0] R_SPAN  = 4'd10;
    localparam logic [3:0] R_MDONE = 4'd11;

    wire rst = ~rstn;

    logic [SYS_ADDR_USED_BITS-1:0] a;
    logic [3:0]  which;
    logic        is_ro;
    logic        wr_ok;
    logic        wr_err;
    logic        rd_err;
    logic        start_strobe;
    logic [31:0] rd_val;

    // registers
    logic [31:0]                 scratch;
    logic                        cont;
    logic [31:0]                 gate_len;
    logic signed [ADC_WIDTH-1:0] thr_h;
    logic signed [ADC_WIDTH-1:0] thr_l;

    // gate and schmitt status
    logic        busy;
    logic        done;
    logic        few;
    logic        bad;
    logic        good;
    logic        edge_p;
    logic [31:0] edges;
    logic [31:0] gate_actual;
    logic [31:0] span;
    logic [31:0] meas_done;

    assign a = sys_addr[SYS_ADDR_USED_BITS-1:0];

    // address decode: only aligned offsets match a constant, so a[1:0] nonzero falls to R_NONE
    always_comb begin
        case (a)
            20'h00000: which = R_ID;
            20'h00004: which = R_SCR;
            20'h00008: which = R_CTRL;
            20'h0000C: which = R_GLEN;
            20'h00010: which = R_THRH;
            20'h00014: which = R_THRL;
            20'h00018: which = R_STAT;
            20'h0001C: which = R_EDGES;
            20'h00020: which = R_GACT;
            20'h00024: which = R_SPAN;
            20'h00028: which = R_MDONE;
            default:   which = R_NONE;
        endcase
    end

    assign is_ro  = (which == R_ID) || (which == R_STAT) || (which == R_EDGES) ||
                    (which == R_GACT) || (which == R_SPAN) || (which == R_MDONE);
    assign wr_ok  = sys_wen & ~is_ro & (which != R_NONE);
    assign wr_err = sys_wen & (is_ro | (which == R_NONE));
    assign rd_err = sys_ren & (which == R_NONE);
    assign start_strobe = sys_wen & (which == R_CTRL) & sys_wdata[0];

    // read mux (registers as they are before this edge)
    always_comb begin
        case (which)
            R_ID:    rd_val = ID_VALUE;
            R_SCR:   rd_val = scratch;
            R_CTRL:  rd_val = {30'd0, cont, 1'b0};
            R_GLEN:  rd_val = gate_len;
            R_THRH:  rd_val = {{(32-ADC_WIDTH){thr_h[ADC_WIDTH-1]}}, thr_h};
            R_THRL:  rd_val = {{(32-ADC_WIDTH){thr_l[ADC_WIDTH-1]}}, thr_l};
            R_STAT:  rd_val = {28'd0, bad, few, done, busy};
            R_EDGES: rd_val = edges;
            R_GACT:  rd_val = gate_actual;
            R_SPAN:  rd_val = span;
            R_MDONE: rd_val = meas_done;
            default: rd_val = 32'd0;
        endcase
    end

    // bus response and register file: control state takes the synchronous reset
    always_ff @(posedge clk) begin
        if (rst) begin
            sys_ack  <= 1'b0;
            sys_err  <= 1'b0;
            scratch  <= 32'd0;
            cont     <= 1'b0;
            gate_len <= GRESET;
            thr_h    <= THR_HIGH_RESET[ADC_WIDTH-1:0];
            thr_l    <= THR_LOW_RESET[ADC_WIDTH-1:0];
        end else begin
            sys_ack <= sys_wen | sys_ren;
            sys_err <= wr_err | rd_err;
            if (wr_ok && which == R_SCR)  scratch  <= sys_wdata;
            if (wr_ok && which == R_CTRL) cont     <= sys_wdata[1];
            if (wr_ok && which == R_GLEN) gate_len <= (sys_wdata < GMIN) ? GMIN : sys_wdata;
            if (wr_ok && which == R_THRH) thr_h   <= sys_wdata[ADC_WIDTH-1:0];
            if (wr_ok && which == R_THRL) thr_l   <= sys_wdata[ADC_WIDTH-1:0];
        end
    end

    // read data: no side effects, zero when no read strobe
    always_ff @(posedge clk) begin
        sys_rdata <= sys_ren ? rd_val : 32'd0;
    end

    assign good = (thr_h > thr_l);

    schmitt_edge #(
        .ADC_WIDTH(ADC_WIDTH)
    ) u_schmitt (
        .clk   (clk),
        .rst   (rst),
        .adc_a (adc_a),
        .thr_h (thr_h),
        .thr_l (thr_l),
        .edge_p(edge_p)
    );

    gate_ctrl u_gate (
        .clk        (clk),
        .rst        (rst),
        .start      (start_strobe),
        .cont       (cont),
        .gate_len   (gate_len),
        .good       (good),
        .edge_p     (edge_p),
        .busy       (busy),
        .done       (done),
        .few        (few),
        .bad        (bad),
        .edges      (edges),
        .gate_actual(gate_actual),
        .span       (span),
        .meas_done  (meas_done)
    );

    assign dac_a = '0;
    assign dac_b = '0;

endmodule

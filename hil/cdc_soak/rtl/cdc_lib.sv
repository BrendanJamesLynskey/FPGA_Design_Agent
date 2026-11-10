`timescale 1ns / 1ps
// cdc_lib.sv: the small building blocks of the CDC soak rig.
//
// cff         one flip-flop (a bus of W). INJ=1 marks it as the first flop to sample an asynchronous input. In
//             simulation (+define+CDC_SIM) a bit that changed less than CDC_WIN_NS before the clock edge keeps its old
//             value with probability 1/2: the flop may resolve either way, which looks like one extra cycle of
//             latency (metastability injection, artix7-cdc-verification-without-hardware). INJREL=1 does the same for
//             the release of the asynchronous reset (a recovery or removal violation). ASYNC=1 sets ASYNC_REG.
//             Every cff is DONT_TOUCH in hardware, so duplicated test flops (M2, C12/M10) are not merged.
//             Plusarg +CDC_NOINJECT turns injection off.
// rst_bridge  asynchronous assert, synchronous release (2 flops, ASYNC_REG); optional synchronous second source.
// rt_delay    N route-through LUT1s (DONT_TOUCH) in hardware; a transport delay of N x SIM_NS in simulation.
//             SIM_NS defaults to CDC_LUT_NS = 0.5 ns a stage (brief 11c): the routed delay tables put one padded stage
//             at about 0.3 ns (fast corner) to 0.93 ns (slow corner); the first model used 1.0 ns, which is the slow
//             corner and made M6c tear in simulation where the board's silicon did not.
// lfsr16      PRBS-16 (x^16 + x^14 + x^13 + x^11 + 1), one step when en.

`ifndef CDC_LUT_NS
`define CDC_LUT_NS 0.5
`endif
`ifndef CDC_WIN_NS
`define CDC_WIN_NS 1.0
`endif

module cff #(
    parameter int           W      = 1,
    parameter logic [W-1:0] INIT   = '0,
    parameter bit           ASYNC  = 1'b0,
    parameter bit           INJ    = 1'b0,
    parameter bit           INJREL = 1'b0
) (
    input  logic         clk,
    input  logic         arst,
    input  logic [W-1:0] d,
    output logic [W-1:0] q
);
`ifdef CDC_SIM
    logic [W-1:0] r = INIT;
    integer seed;
    bit inj_on;
    initial begin
        if (!$value$plusargs("CDC_SEED=%d", seed)) seed = 1;
        seed = seed ^ $urandom;
    end
    initial inj_on = !$test$plusargs("CDC_NOINJECT");
    for (genvar i = 0; i < W; i++) begin : b
        realtime tc = -1.0e6;
        realtime tr = -1.0e6;
        always @(d[i]) tc = $realtime;
        always @(negedge arst) tr = $realtime;
        always @(posedge clk or posedge arst)
            if (arst)                                                              r[i] <= INIT[i];
            else if (INJREL && inj_on && ($realtime - tr) < `CDC_WIN_NS && $random(seed) % 2 == 0) r[i] <= INIT[i];
            else if (INJ && inj_on && ($realtime - tc) < `CDC_WIN_NS && $random(seed) % 2 == 0)    r[i] <= r[i];
            else                                                                   r[i] <= d[i];
    end
    assign q = r;
`else
    if (ASYNC) begin : g
        (* ASYNC_REG = "TRUE", DONT_TOUCH = "TRUE" *) logic [W-1:0] r = INIT;
        always_ff @(posedge clk or posedge arst)
            if (arst) r <= INIT;
            else      r <= d;
        assign q = r;
    end else begin : g
        (* DONT_TOUCH = "TRUE" *) logic [W-1:0] r = INIT;
        always_ff @(posedge clk or posedge arst)
            if (arst) r <= INIT;
            else      r <= d;
        assign q = r;
    end
`endif
endmodule

// STAGES-flop synchroniser built from cff (first flop injected). STAGES >= 2.
module sync_n #(
    parameter int W      = 1,
    parameter int STAGES = 2,
    parameter bit ASYNC  = 1'b1
) (
    input  logic         clk,
    input  logic [W-1:0] d,
    output logic [W-1:0] q
);
    // syn_s1 is the crossing's endpoint (the constraints and the delay table find it by name); ss are the rest
    logic [W-1:0] s [STAGES];
    cff #(.W(W), .ASYNC(ASYNC), .INJ(1'b1)) syn_s1 (.clk(clk), .arst(1'b0), .d(d), .q(s[0]));
    for (genvar i = 1; i < STAGES; i++) begin : st
        cff #(.W(W), .ASYNC(ASYNC)) ss (.clk(clk), .arst(1'b0), .d(s[i-1]), .q(s[i]));
    end
    assign q = s[STAGES-1];
endmodule

// sync_in (optional) is a reset already synchronous to clk (for example the domain's power-on reset): it holds
// the bridge in reset through its D input, so two reset sources combine without a LUT on an asynchronous pin.
module rst_bridge (
    input  logic clk,
    input  logic arst_in,
    input  logic sync_in,
    output logic rst_out
);
    logic s1;
    cff #(.INIT(1'b1), .ASYNC(1'b1), .INJREL(1'b1)) brg_s1 (.clk(clk), .arst(arst_in), .d(sync_in), .q(s1));
    cff #(.INIT(1'b1), .ASYNC(1'b1))                brg_s2 (.clk(clk), .arst(arst_in), .d(s1),   .q(rst_out));
endmodule

module rt_delay #(
    parameter int  N      = 4,
    parameter real SIM_NS = `CDC_LUT_NS
) (
    input  logic a,
    output logic y
);
`ifdef CDC_SIM
    assign #(N * SIM_NS) y = a;
`else
    logic [N:0] c;
    assign c[0] = a;
    for (genvar i = 0; i < N; i++) begin : lut
        (* DONT_TOUCH = "TRUE" *) LUT1 #(.INIT(2'b10)) rt (.I0(c[i]), .O(c[i+1]));
    end
    assign y = c[N];
`endif
endmodule

module lfsr16 #(
    parameter logic [15:0] SEED = 16'hACE1
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        en,
    output logic [15:0] q
);
    logic [15:0] r = SEED;
    always_ff @(posedge clk)
        if (rst)     r <= SEED;
        else if (en) r <= rig_pkg::prbs16_next(r);
    assign q = r;
endmodule

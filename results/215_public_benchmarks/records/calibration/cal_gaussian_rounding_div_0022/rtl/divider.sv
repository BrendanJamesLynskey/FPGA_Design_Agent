/* verilator lint_off DECLFILENAME */
//////////////////////////////////////////////
// Latency-optimised Goldschmidt divider, Q9.9, 10 iterations, 1-clock latency
//////////////////////////////////////////////
module divider (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start,
    input  logic [17:0]  dividend,  // unsigned Q9.9
    input  logic [17:0]  divisor,   // unsigned Q9.9
    output logic [17:0]  dv_out,
    output logic         valid
);

    localparam int ITERATIONS = 10;
    // 2.0 in Q9.9 is 1<<10 (model.py: two = 2 << FRAC_BITS)
    localparam logic [17:0] TWO = 18'h400;

    logic [17:0] D_0, N_0;
    logic [17:0] pd, pn;

    // The two reg18 instances: input registers
    reg18 reg_dividend_pre (.clk(clk), .reset(~rst_n), .data_in(dividend), .data_out(N_0));
    reg18 reg_divisor_pre  (.clk(clk), .reset(~rst_n), .data_in(divisor),  .data_out(D_0));

    dff1 ff0 (.clk(clk), .reset(~rst_n), .d(start), .q(valid));

    pre_scaler prescaler_inst (.a(D_0), .c(N_0), .b(pd), .d(pn));

    // Combinational iteration chain (no registers between iterations)
    /* verilator lint_off UNUSEDSIGNAL */
    always_comb begin : iter_chain
        logic [17:0] d_v, n_v, f_v;
        logic [35:0] dfull, nfull;
        d_v = pd;
        n_v = pn;
        for (int i = 0; i < ITERATIONS; i++) begin
            f_v   = TWO - d_v;
            dfull = f_v * d_v;
            nfull = f_v * n_v;
            d_v   = dfull[26:9];
            n_v   = nfull[26:9];
        end
        dv_out = n_v;
    end
    /* verilator lint_on UNUSEDSIGNAL */

endmodule

////////////////////////////////////////////////
// Pre-scaling Module: shift both right so divisor[17:9] == 0
////////////////////////////////////////////////
module pre_scaler (
    input  logic [17:0] a,  // unsigned divisor
    input  logic [17:0] c,  // unsigned dividend
    output logic [17:0] b,  // prescaled divisor
    output logic [17:0] d   // prescaled dividend
);
    always_comb begin : SHIFT_LOGIC
        if (a[17])      begin b = a >> 9; d = c >> 9; end
        else if (a[16]) begin b = a >> 8; d = c >> 8; end
        else if (a[15]) begin b = a >> 7; d = c >> 7; end
        else if (a[14]) begin b = a >> 6; d = c >> 6; end
        else if (a[13]) begin b = a >> 5; d = c >> 5; end
        else if (a[12]) begin b = a >> 4; d = c >> 4; end
        else if (a[11]) begin b = a >> 3; d = c >> 3; end
        else if (a[10]) begin b = a >> 2; d = c >> 2; end
        else            begin b = a;      d = c;      end
    end
endmodule

////////////////////////////////////////////////
// Single-bit DFF
////////////////////////////////////////////////
module dff1 (
    input  logic clk,
    input  logic reset,
    input  logic d,
    output logic q
);
    always_ff @(posedge clk) begin
        if (reset) q <= 1'b0;
        else       q <= d;
    end
endmodule

////////////////////////////////////////////////
// 18-bit register (parallel load)
////////////////////////////////////////////////
module reg18 (
    input  logic        clk,
    input  logic        reset,
    input  logic [17:0] data_in,
    output logic [17:0] data_out
);
    always_ff @(posedge clk) begin
        if (reset) data_out <= 18'd0;
        else       data_out <= data_in;
    end
endmodule

// adder_checker: the specification of arith/adder/spec.md as a passive checker (arith brief 139a). Instantiate it beside your adder instance with the
// same signals; `errors` counts the clock edges where the instance disagrees with the specification, and each one prints a line. The expected value is
// computed with plain wide arithmetic (not the RTL's a + (b ^ sub) + (cin ^ sub) formula) and delayed by LAT clocks, the instance's latency. Nothing is
// checked until LAT clocks have passed. Sampling is at the rising clock edge, before the instance's registers update; inputs must be stable then.
module adder_checker #(
    parameter int WIDTH = 32,
    parameter int LAT   = 0
) (
    input  logic             clk,
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    input  logic             cin,
    input  logic             sub,
    input  logic [WIDTH-1:0] s,
    input  logic             co,
    input  logic             ovf,
    output logic [31:0]      errors
);
    logic [WIDTH:0]   x;
    logic signed [WIDTH+1:0] sa, sb, r;
    logic [WIDTH+1:0] expv;                       // {ovf, co, s}
    always_comb begin
        sa = {{2{a[WIDTH-1]}}, a};
        sb = {{2{b[WIDTH-1]}}, b};
        if (sub) begin
            x = {1'b0, a} - {1'b0, b} - {{WIDTH{1'b0}}, cin};
            r = sa - sb - $signed({{(WIDTH+1){1'b0}}, cin});
            expv[WIDTH]   = ~x[WIDTH];             // carry out of the subtraction: 1 when there is no borrow
        end else begin
            x = {1'b0, a} + {1'b0, b} + {{WIDTH{1'b0}}, cin};
            r = sa + sb + $signed({{(WIDTH+1){1'b0}}, cin});
            expv[WIDTH]   = x[WIDTH];
        end
        expv[WIDTH-1:0] = x[WIDTH-1:0];
        expv[WIDTH+1]   = (r > $signed({2'b00, {(WIDTH-1){1'b1}}})) || (r < -$signed({2'b00, 1'b1, {(WIDTH-1){1'b0}}}));
    end

    logic [WIDTH+1:0] dly [LAT+1];
    logic [31:0]      warm;
    initial begin
        errors = 32'd0;
        warm   = 32'd0;
    end
    always_ff @(posedge clk) begin
        dly[0] <= expv;
        for (int j = 1; j <= LAT; j++) dly[j] <= dly[j-1];
        if (warm != 32'hFFFFFFFF) warm <= warm + 32'd1;
        if (warm >= LAT && !$isunknown(LAT == 0 ? expv : dly[LAT > 0 ? LAT-1 : 0])) begin   // nothing is expected until the inputs have been driven
            if ({ovf, co, s} !== (LAT == 0 ? expv : dly[LAT > 0 ? LAT-1 : 0])) begin
                errors <= errors + 32'd1;
                $display("adder_checker: mismatch at %0t: s=%h co=%b ovf=%b expected %h", $time, s, co, ovf, (LAT == 0 ? expv : dly[LAT > 0 ? LAT-1 : 0]));
            end
        end
    end
endmodule

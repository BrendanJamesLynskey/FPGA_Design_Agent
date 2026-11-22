// mult_checker: the specification of arith/multiplier/spec.md as a passive checker (arith brief 139a). Instantiate it beside your multiplier instance with the
// same signals; `errors` counts the clock edges where the instance disagrees with a plain signed or unsigned `*`, delayed by LAT clocks (the instance's
// latency); each one prints a line. Nothing is checked until LAT clocks have passed. Sampling is at the rising clock edge, before the instance's registers update.
module mult_checker #(
    parameter int WA     = 18,
    parameter int WB     = 18,
    parameter int SIGNED = 1,
    parameter int LAT    = 0
) (
    input  logic                clk,
    input  logic [WA-1:0]       a,
    input  logic [WB-1:0]       b,
    input  logic [WA+WB-1:0]    p,
    output logic [31:0]         errors
);
    logic signed [WA:0]       ea;
    logic signed [WB:0]       eb;
    logic signed [WA+WB+1:0]  full;
    logic [WA+WB-1:0]         expv;
    always_comb begin
        ea   = SIGNED != 0 ? {a[WA-1], a} : {1'b0, a};
        eb   = SIGNED != 0 ? {b[WB-1], b} : {1'b0, b};
        full = ea * eb;
        expv = full[WA+WB-1:0];
    end
    logic [WA+WB-1:0] dly [LAT+1];
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
            if (p !== (LAT == 0 ? expv : dly[LAT > 0 ? LAT-1 : 0])) begin
                errors <= errors + 32'd1;
                $display("mult_checker: mismatch at %0t: p=%h expected %h", $time, p, (LAT == 0 ? expv : dly[LAT > 0 ? LAT-1 : 0]));
            end
        end
    end
endmodule

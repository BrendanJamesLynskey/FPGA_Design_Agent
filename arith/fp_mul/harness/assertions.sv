// fp_mul_checker: the specification of arith/fp_mul/spec.md as a passive checker (arith brief 139e). Instantiate it beside your fp_mul instance with the same signals; `errors` counts the clock
// edges where the instance disagrees with the exact result (a * b) rounded once to nearest even, delayed by LAT clocks (the instance's latency); each one prints a
// line. The expected value comes from fpx_ref (fpx_ref.sv, in this folder), a plain wide-integer formulation. Nothing is checked until LAT clocks have passed. Sampling is at the rising
// clock edge, before the instance's registers update. The checker is for simulation (initial values, a display); it is not synthesisable RTL.
module fp_mul_checker #(
    parameter int EXP     = 8,
    parameter int MAN     = 23,
    parameter int SUBNORM = 1,
    parameter int LAT     = 0
) (
    input  logic                clk,
    input  logic [EXP+MAN:0]    a,
    input  logic [EXP+MAN:0]    b,
    input  logic [EXP+MAN:0]    y,
    output logic [31:0]         errors
);
    localparam int W = EXP + MAN + 1;
    logic [W-1:0] expv;
    fpx_ref #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .OP(1)) u_ref (.a(a), .b(b), .c('0), .y(expv));
    logic [W-1:0] dly [LAT+1];
    logic [LAT:0] okd;                                  // the inputs of each delayed expected value were known (not X or Z)
    logic         ok_now;
    assign ok_now = !$isunknown({a, b});
    logic [31:0]  warm;
    initial begin
        errors = 32'd0;
        warm   = 32'd0;
    end
    always_ff @(posedge clk) begin
        dly[0] <= expv;
        okd[0] <= ok_now;
        for (int j = 1; j <= LAT; j++) begin
            dly[j] <= dly[j-1];
            okd[j] <= okd[j-1];
        end
        if (warm != 32'hFFFFFFFF) warm <= warm + 32'd1;
        if (warm >= LAT && (LAT == 0 ? ok_now : okd[LAT > 0 ? LAT-1 : 0])) begin   // nothing is expected until the inputs have been driven
            if (y !== (LAT == 0 ? expv : dly[LAT > 0 ? LAT-1 : 0])) begin
                errors <= errors + 32'd1;
                $display("fp_mul_checker: mismatch at %0t: y=%h expected %h", $time, y, (LAT == 0 ? expv : dly[LAT > 0 ? LAT-1 : 0]));
            end
        end
    end
endmodule

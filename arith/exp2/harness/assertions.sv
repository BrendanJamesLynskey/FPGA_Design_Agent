// exp2_checker: the specification of arith/exp2/spec.md as a passive checker (arith brief 139d). Instantiate it beside your exp2 instance with the same signals; `errors`
// counts the clock edges where the instance is further than ERR_MILLI / 1000 last places from the exact function (2**x - 1 for x = x / 2**IW, in real arithmetic, not rounded), computed from
// the input delayed by LAT clocks (the instance's latency); each one prints a line. Nothing is checked until LAT clocks have passed. Sampling is at the rising clock edge,
// before the instance's registers update. A SIMULATION checker (real-number system functions, an initial value, a display): it elaborates in Verilator and runs in Icarus,
// and is not meant for synthesis. It checks the error bound, not the exact bits: the exact bits are the cocotb bench's job (run_harness.py compares with the variant's model).
module exp2_checker #(
    parameter int IW        = 12,
    parameter int OW        = 12,
    parameter int LAT       = 2,
    parameter int ERR_MILLI = 1000
) (
    input  logic            clk,
    input  logic [IW-1:0]   x,
    input  logic [OW-1:0]   y,
    output logic [31:0]     errors
);
    logic [IW-1:0] dly [LAT+1];
    logic [31:0]   warm;
    logic [IW-1:0] xs;
    real           u, ideal, diff;
    always_comb xs = (LAT == 0) ? x : dly[LAT > 0 ? LAT-1 : 0];
    initial begin
        errors = 32'd0;
        warm   = 32'd0;
    end
    always_ff @(posedge clk) begin
        dly[0] <= x;
        for (int j = 1; j <= LAT; j++) dly[j] <= dly[j-1];
        if (warm != 32'hFFFFFFFF) warm <= warm + 32'd1;
        if (warm >= LAT && !$isunknown(xs) && !$isunknown(y)) begin
            u     = $itor(xs) / (2.0 ** IW);
            ideal = ($pow(2.0, u) - 1.0) * (2.0 ** OW);
            diff  = $itor(y) - ideal;
            if (diff < 0.0) diff = -diff;
            if (diff * 1000.0 > $itor(ERR_MILLI)) begin
                errors <= errors + 32'd1;
                $display("exp2_checker: error bound exceeded at %0t: x=%0d y=%0d, exact %f, error %f last places", $time, xs, y, ideal, diff);
            end
        end
    end
endmodule

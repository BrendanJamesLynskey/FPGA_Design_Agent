// sincos_checker: the specification of arith/sincos/spec.md as a passive checker (arith brief 139d). Instantiate it beside your sincos instance with the same signals;
// `errors` counts the clock edges where s or c is further than ERR_MILLI / 1000 last places (2**-(OW-1)) from the exact sine or cosine of the phase (real arithmetic, not
// rounded), computed from the phase delayed by LAT clocks (the instance's latency); each one prints a line. Nothing is checked until LAT clocks have passed. Sampling is at
// the rising clock edge, before the instance's registers update. A SIMULATION checker (real-number system functions, an initial value, a display): it elaborates in
// the lint tool and runs in Icarus, and is not meant for synthesis. It checks the error bound, not the exact bits: the exact bits are the cocotb bench's job.
module sincos_checker #(
    parameter int PH        = 14,
    parameter int OW        = 14,
    parameter int LAT       = 2,
    parameter int ERR_MILLI = 3000
) (
    input  logic                  clk,
    input  logic [PH-1:0]         phase,
    input  logic signed [OW-1:0]  s,
    input  logic signed [OW-1:0]  c,
    output logic [31:0]           errors
);
    localparam real TWO_PI = 6.283185307179586;
    logic [PH-1:0] dly [LAT+1];
    logic [31:0]   warm;
    logic [PH-1:0] ps;
    real           a, es, ec, ds, dc;
    always_comb ps = (LAT == 0) ? phase : dly[LAT > 0 ? LAT-1 : 0];
    initial begin
        errors = 32'd0;
        warm   = 32'd0;
    end
    always_ff @(posedge clk) begin
        dly[0] <= phase;
        for (int j = 1; j <= LAT; j++) dly[j] <= dly[j-1];
        if (warm != 32'hFFFFFFFF) warm <= warm + 32'd1;
        if (warm >= LAT && !$isunknown(ps) && !$isunknown(s) && !$isunknown(c)) begin
            a  = TWO_PI * $itor(ps) / (2.0 ** PH);
            es = $sin(a) * (2.0 ** (OW - 1));
            ec = $cos(a) * (2.0 ** (OW - 1));
            ds = $itor(s) - es;
            dc = $itor(c) - ec;
            if (ds < 0.0) ds = -ds;
            if (dc < 0.0) dc = -dc;
            if (ds * 1000.0 > $itor(ERR_MILLI) || dc * 1000.0 > $itor(ERR_MILLI)) begin
                errors <= errors + 32'd1;
                $display("sincos_checker: error bound exceeded at %0t: phase=%0d s=%0d c=%0d, exact %f %f", $time, ps, s, c, es, ec);
            end
        end
    end
endmodule

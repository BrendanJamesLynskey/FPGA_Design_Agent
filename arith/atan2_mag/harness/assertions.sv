// atan2_checker: the specification of arith/atan2_mag/spec.md as a passive checker (arith brief 139d). Instantiate it beside your instance with the same signals;
// `errors` counts the clock edges where ang is further than ERR_MILLI / 1000 last places (2**-PH turns, measured round the circle) from the exact atan2(y, x) / 2 pi, or mag
// further than ERR_MAG_MILLI / 1000 counts from the exact length (real arithmetic, not rounded), computed from x and y delayed by LAT clocks (the instance's latency). At the
// origin only mag is checked (its angle is undefined). Each error prints a line. Nothing is checked until LAT clocks have passed. Sampling is at the rising clock edge,
// before the instance's registers update. A SIMULATION checker (real-number system functions, an initial value, a display): it elaborates in Verilator and runs in Icarus,
// and is not meant for synthesis. It checks the error bounds, not the exact bits: the exact bits are the cocotb bench's job.
module atan2_checker #(
    parameter int W             = 12,
    parameter int PH            = 12,
    parameter int LAT           = 16,
    parameter int ERR_MILLI     = 1000,
    parameter int ERR_MAG_MILLI = 1000
) (
    input  logic          clk,
    input  logic [W-1:0]  x,
    input  logic [W-1:0]  y,
    input  logic [PH-1:0] ang,
    input  logic [W-1:0]  mag,
    output logic [31:0]   errors
);
    localparam real TWO_PI = 6.283185307179586;
    logic [W-1:0] dx [LAT+1];
    logic [W-1:0] dy [LAT+1];
    logic [31:0]  warm;
    logic [W-1:0] xs, ys;
    real          rx, ry, ia, da, im, dm, full;
    always_comb begin
        xs = (LAT == 0) ? x : dx[LAT > 0 ? LAT-1 : 0];
        ys = (LAT == 0) ? y : dy[LAT > 0 ? LAT-1 : 0];
    end
    initial begin
        errors = 32'd0;
        warm   = 32'd0;
    end
    always_ff @(posedge clk) begin
        dx[0] <= x;
        dy[0] <= y;
        for (int j = 1; j <= LAT; j++) begin
            dx[j] <= dx[j-1];
            dy[j] <= dy[j-1];
        end
        if (warm != 32'hFFFFFFFF) warm <= warm + 32'd1;
        if (warm >= LAT && !$isunknown(xs) && !$isunknown(ys) && !$isunknown(ang) && !$isunknown(mag)) begin
            rx   = $itor($signed(xs));
            ry   = $itor($signed(ys));
            im   = $hypot(rx, ry);
            dm   = $itor(mag) - im;
            if (dm < 0.0) dm = -dm;
            full = 2.0 ** PH;
            ia   = $atan2(ry, rx) / TWO_PI;
            if (ia < 0.0) ia = ia + 1.0;
            ia   = ia * full;
            da   = $itor(ang) - ia;
            if (da < 0.0) da = -da;
            if (da > full / 2.0) da = full - da;
            if (dm * 1000.0 > $itor(ERR_MAG_MILLI) || ((rx != 0.0 || ry != 0.0) && da * 1000.0 > $itor(ERR_MILLI))) begin
                errors <= errors + 32'd1;
                $display("atan2_checker: error bound exceeded at %0t: x=%0d y=%0d ang=%0d mag=%0d, exact %f %f", $time, $signed(xs), $signed(ys), ang, mag, ia, im);
            end
        end
    end
endmodule

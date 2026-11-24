// mac_checker: the specification of arith/mac/spec.md as a passive checker (arith brief 139a). Instantiate it beside your MAC instance with the same signals;
// `errors` counts the clock edges where acc disagrees with mac_ref (mac_ref.sv in this folder: the specification written as plainly as it reads, with the
// instance's latency LAT) fed the same inputs; each one prints a line. The first clock with rst high starts the comparison (every register of the reference
// is then cleared; the instance is expected to be too). Sampling is at the rising clock edge, before the instance's registers update.
module mac_checker #(
    parameter int WA     = 16,
    parameter int WB     = 16,
    parameter int LANES  = 1,
    parameter int ACCW   = 40,
    parameter int SIGNED = 1,
    parameter int LAT    = 1
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                en,
    input  logic                clr,
    input  logic [LANES*WA-1:0] a,
    input  logic [LANES*WB-1:0] b,
    input  logic [ACCW-1:0]     acc,
    output logic [31:0]         errors
);
    logic [ACCW-1:0] ref_acc;
    mac_ref #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED), .LAT(LAT)) u_ref (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(ref_acc));
    logic started;
    initial begin
        errors  = 32'd0;
        started = 1'b0;
    end
    always_ff @(posedge clk) begin
        if (rst) started <= 1'b1;
        if (started && acc !== ref_acc) begin
            errors <= errors + 32'd1;
            $display("mac_checker: mismatch at %0t: acc=%h expected %h", $time, acc, ref_acc);
        end
    end
endmodule

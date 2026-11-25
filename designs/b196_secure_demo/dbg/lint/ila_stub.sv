// lint-only stand-in for the ILA IP ila_dbg (ip/amd_ip_ila.tcl creates the real one in the build); never part of a build.
module ila_dbg (input logic clk, input logic [15:0] probe0);
    logic [15:0] last;
    always_ff @(posedge clk) last <= probe0;
endmodule

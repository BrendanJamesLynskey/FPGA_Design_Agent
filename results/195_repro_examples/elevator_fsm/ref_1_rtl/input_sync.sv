// input_sync: STAGES-flop synchroniser per bit plus rising-edge detect.
// rise is high for one clock when the last synchroniser stage went 0 -> 1.
module input_sync #(
    parameter int W      = 4,
    parameter int STAGES = 2
) (
    input  logic         clk,
    input  logic         rst,     // synchronous, active high
    input  logic [W-1:0] din,     // asynchronous
    output logic [W-1:0] rise
);
    (* ASYNC_REG = "TRUE" *) logic [W*STAGES-1:0] sync;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [W*STAGES+W-1:0] ext;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [W-1:0] last, prev;

    assign ext  = {sync, din};
    assign last = sync[W*STAGES-1 -: W];
    assign rise = last & ~prev;

    always_ff @(posedge clk) begin
        if (rst) begin
            sync <= '0;
            prev <= '0;
        end else begin
            sync <= ext[W*STAGES-1:0];
            prev <= last;
        end
    end
endmodule

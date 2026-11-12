// fir_ram: simple dual-port RAM for the folded FIR variants (brief 63A). One write port, one read port, read latency 2
// (address to q1, q1 to q). The second register lets synthesis use the block RAM output register (or a fabric register
// after LUT RAM), which keeps the RAM clock-to-out off the multiply path. STYLE picks the memory resource by inference
// attribute (KB inference template: simple dual-port RAM, synchronous read): 0 leaves it to synthesis, 1 block RAM,
// 2 distributed (LUT) RAM. No vendor primitive is instantiated.
module fir_ram #(
    parameter int WIDTH = 16,
    parameter int DEPTH = 16,
    parameter int STYLE = 0,
    localparam int AW = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
    input  logic             clk,
    input  logic             we,
    input  logic [AW-1:0]    wa,
    input  logic [WIDTH-1:0] wd,
    input  logic [AW-1:0]    ra,
    output logic [WIDTH-1:0] q
);
    logic [WIDTH-1:0] q1;
    generate
        if (STYLE == 1) begin : g_block
            (* ram_style = "block" *) logic [WIDTH-1:0] mem [0:DEPTH-1];
            always_ff @(posedge clk) begin
                if (we) mem[wa] <= wd;
                q1 <= mem[ra];
            end
        end else if (STYLE == 2) begin : g_dist
            (* ram_style = "distributed" *) logic [WIDTH-1:0] mem [0:DEPTH-1];
            always_ff @(posedge clk) begin
                if (we) mem[wa] <= wd;
                q1 <= mem[ra];
            end
        end else begin : g_auto
            logic [WIDTH-1:0] mem [0:DEPTH-1];
            always_ff @(posedge clk) begin
                if (we) mem[wa] <= wd;
                q1 <= mem[ra];
            end
        end
    endgenerate
    always_ff @(posedge clk) q <= q1;
endmodule

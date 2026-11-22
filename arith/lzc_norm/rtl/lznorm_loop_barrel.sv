// lznorm_loop_barrel: leading-zero count by a priority loop, then a barrel shifter, in one clock (brief 139b). Latency 1.
// Same function and interface as lznorm_tree_barrel; the count is written as the textbook "first set bit from the top" for loop, which
// synthesis may or may not turn into the same logic as the tree (the Vivado runs decide; the simulation cannot).
// Primitive use (intended, not yet measured): a priority chain of W terms (LUT6 levels, possibly a carry chain if the tool infers one
// for the found flag) feeding the same barrel shifter.
module lznorm_loop_barrel #(
    parameter int W = 16
) (
    input  logic                    clk,
    input  logic                    rst,
    input  logic                    in_valid,
    output logic                    in_ready,
    input  logic [W-1:0]            x,
    output logic                    out_valid,
    output logic [$clog2(W+1)-1:0]  lz,
    output logic [W-1:0]            y
);
    localparam int LW = $clog2(W + 1);

    logic [LW-1:0] lz_c;

    assign in_ready = 1'b1;
    always_comb begin : count
        logic found;
        lz_c  = LW'(W);
        found = 1'b0;
        for (int i = W - 1; i >= 0; i--) begin
            if (!found && x[i]) begin
                lz_c  = LW'(W - 1 - i);
                found = 1'b1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) out_valid <= 1'b0;
        else     out_valid <= in_valid;
    end
    always_ff @(posedge clk) begin
        lz <= lz_c;
        y  <= x << lz_c;
    end
endmodule

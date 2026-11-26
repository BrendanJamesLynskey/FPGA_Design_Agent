module generic_counter #(
    parameter int N = 8,
    parameter logic [2:0] BINARY_UP   = 3'd0,
    parameter logic [2:0] BINARY_DOWN = 3'd1,
    parameter logic [2:0] MODULO_256  = 3'd2,
    parameter logic [2:0] JOHNSON     = 3'd3,
    parameter logic [2:0] GRAY        = 3'd4,
    parameter logic [2:0] RING        = 3'd5
) (
    input  logic          clk_in,
    input  logic          rst_in,
    input  logic [2:0]    mode_in,
    input  logic          enable_in,
    input  logic [N-1:0]  ref_modulo,
    output logic [N-1:0]  o_count
);

    logic [N-1:0] count;
    logic [N-1:0] next_count;
    logic [N-1:0] view;

    always_comb begin
        if (mode_in == BINARY_UP) begin
            next_count = count + 1'b1;
        end else if (mode_in == BINARY_DOWN) begin
            next_count = count - 1'b1;
        end else if (mode_in == MODULO_256) begin
            next_count = (count == ref_modulo) ? '0 : count + 1'b1;
        end else if (mode_in == JOHNSON) begin
            next_count = {~count[0], count[N-1:1]};
        end else if (mode_in == GRAY) begin
            next_count = count + 1'b1;
        end else if (mode_in == RING) begin
            next_count = (count == '0) ? {{(N-1){1'b0}}, 1'b1}
                                       : {count[N-2:0], count[N-1]};
        end else begin
            next_count = '0;
        end
    end

    // Synchronous reset (STD-RST-01). o_count is additionally forced to 0
    // combinationally while rst_in is high, so it clears without a clock edge.
    always_ff @(posedge clk_in) begin
        if (rst_in)          count <= '0;
        else if (enable_in)  count <= next_count;
    end

    assign view    = (mode_in == GRAY) ? (count ^ (count >> 1)) : count;
    assign o_count = rst_in ? '0 : view;

endmodule

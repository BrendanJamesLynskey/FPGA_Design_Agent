// Elastic buffer approximate pattern matcher: o_match <= popcount(i_data ^ i_pattern) < ERR_TOLERANCE
module elastic_buffer_pattern_matcher #(
    parameter int WIDTH         = 16,
    parameter int ERR_TOLERANCE = 2
) (
    input  logic             clk,
    input  logic             rst,
    input  logic [WIDTH-1:0] i_data,
    input  logic [WIDTH-1:0] i_pattern,
    output logic             o_match
);

    function automatic logic [$clog2(WIDTH):0] ones_count(input logic [WIDTH-1:0] v);
        logic [$clog2(WIDTH):0] c;
        c = '0;
        for (int i = 0; i < WIDTH; i++) c = c + {{$clog2(WIDTH){1'b0}}, v[i]};
        return c;
    endfunction

    logic [$clog2(WIDTH):0] err_count;
    assign err_count = ones_count(i_data ^ i_pattern);

    always_ff @(posedge clk) begin
        if (rst) o_match <= 1'b0;
        else     o_match <= (32'(err_count) < 32'(ERR_TOLERANCE));
    end

endmodule

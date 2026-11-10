// Part 9 lesson 6 reference solution: the 19-compare-exchange median-of-nine network.
module median3x3 (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        in_valid,
    input  logic [71:0] win,
    output logic        out_valid,
    output logic [7:0]  med
);
    logic [7:0] v [0:8];
    function automatic logic [15:0] ce(input logic [7:0] a, input logic [7:0] b);      // {smaller, larger}
        ce = (a < b) ? {a, b} : {b, a};
    endfunction
    always_comb begin
        for (int k = 0; k < 9; k++) v[k] = win[k*8 +: 8];
        {v[1], v[2]} = ce(v[1], v[2]); {v[4], v[5]} = ce(v[4], v[5]); {v[7], v[8]} = ce(v[7], v[8]);
        {v[0], v[1]} = ce(v[0], v[1]); {v[3], v[4]} = ce(v[3], v[4]); {v[6], v[7]} = ce(v[6], v[7]);
        {v[1], v[2]} = ce(v[1], v[2]); {v[4], v[5]} = ce(v[4], v[5]); {v[7], v[8]} = ce(v[7], v[8]);
        {v[0], v[3]} = ce(v[0], v[3]); {v[5], v[8]} = ce(v[5], v[8]); {v[4], v[7]} = ce(v[4], v[7]);
        {v[3], v[6]} = ce(v[3], v[6]); {v[1], v[4]} = ce(v[1], v[4]); {v[2], v[5]} = ce(v[2], v[5]);
        {v[4], v[7]} = ce(v[4], v[7]); {v[4], v[2]} = ce(v[4], v[2]); {v[6], v[4]} = ce(v[6], v[4]);
        {v[4], v[2]} = ce(v[4], v[2]);
    end
    always_ff @(posedge clk) begin
        med <= v[4];
        if (!rst_n) out_valid <= 1'b0;
        else        out_valid <= in_valid;
    end
endmodule

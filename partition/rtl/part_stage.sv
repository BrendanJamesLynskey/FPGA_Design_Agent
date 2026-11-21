// part_stage.sv: one sub-module of the synthetic large system (brief 151): purely combinational logic of a stated depth between
// the registers of the boundaries around it. D rounds of add, rotate and xor on a W-bit word: each round is a W-bit carry chain
// plus a LUT level, so D sets the logic depth of the path through the sub-module. No state, no reset, no handshake: the boundaries
// (pipe_reg or credit_chan) hold all the flow control.
module part_stage #(
    parameter int W = 64,
    parameter int D = 2,
    parameter int ID = 0
) (
    input  logic [W-1:0] x,
    output logic [W-1:0] y
);
    function automatic logic [W-1:0] rnd(input logic [W-1:0] a, input int r);
        logic [W-1:0] rot;
        begin
            rot = {a[W-8:0], a[W-1:W-7]};
            rnd = (a + rot) ^ (a >> 3) ^ (W'(64'h9E3779B97F4A7C15) + W'(r * 64'h632BE59BD9B4E019));
        end
    endfunction
    function automatic logic [W-1:0] mix(input logic [W-1:0] a);
        logic [W-1:0] v;
        begin
            v = a;
            for (int r = 0; r < D; r++) v = rnd(v, ID * 16 + r);
            mix = v;
        end
    endfunction
    assign y = mix(x);
endmodule

// wrap_lg_small_comb: the brief 87 ooc_wrap (an input register for the features); the network has its own output register.
module ooc_wrap (input wire logic clk, input wire logic rst, input wire logic in_v, input wire logic [37:0] in_f,
                 output logic out_v, output logic [1:0] out_cls);
    logic v_q;
    logic [37:0] f_q;
    always_ff @(posedge clk) begin
        f_q <= in_f;
        v_q <= in_v;
    end
    lg_small_comb u_blk (.clk, .rst, .in_v(v_q), .in_f(f_q), .out_v, .out_cls);
endmodule

// 8x3 priority encoder, purely combinational. Bit 7 has highest priority; in==0 gives 0.
/* verilator lint_off DECLFILENAME */
module priority_encoder_8x3 (
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [7:0] in,  // in[0] only distinguishes from in==0, both give 0
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [2:0] out
);
    always_comb begin
        if (in[7])      out = 3'd7;
        else if (in[6]) out = 3'd6;
        else if (in[5]) out = 3'd5;
        else if (in[4]) out = 3'd4;
        else if (in[3]) out = 3'd3;
        else if (in[2]) out = 3'd2;
        else if (in[1]) out = 3'd1;
        else            out = 3'd0;
    end
endmodule
/* verilator lint_on DECLFILENAME */

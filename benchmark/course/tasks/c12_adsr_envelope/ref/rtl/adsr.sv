// Part 12 lesson 5 solution: a linear ADSR.
module adsr (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        en,
    input  logic        gate,
    input  logic [15:0] atk_inc,
    input  logic [15:0] dec_dec,
    input  logic [15:0] sus_lvl,
    input  logic [15:0] rel_dec,
    output logic [15:0] level,
    output logic [2:0]  state
);
    logic gate_d;
    logic [16:0] sum;
    always_comb sum = {1'b0, level} + {1'b0, atk_inc};
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            level <= '0; state <= 3'd0; gate_d <= 1'b0;
        end else if (en) begin
            gate_d <= gate;
            if (gate && !gate_d) state <= 3'd1;
            else if (!gate && gate_d && state != 3'd0) state <= 3'd4;
            else case (state)
                3'd1: if (sum >= 17'd65535) begin level <= 16'd65535; state <= 3'd2; end else level <= sum[15:0];
                3'd2: if (level <= sus_lvl) state <= 3'd3;
                      else if (level - sus_lvl <= dec_dec) begin level <= sus_lvl; state <= 3'd3; end
                      else level <= level - dec_dec;
                3'd4: if (level <= rel_dec) begin level <= '0; state <= 3'd0; end else level <= level - rel_dec;
                default: ;
            endcase
        end
    end
endmodule

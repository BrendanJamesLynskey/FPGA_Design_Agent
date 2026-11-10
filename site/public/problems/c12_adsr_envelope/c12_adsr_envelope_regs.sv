// c12_adsr_envelope_regs.sv: the shell window of course task c12_adsr_envelope (gate, four values, tick command, level and state).
module c12_adsr_envelope_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic        gate_r;
    logic [15:0] atk_r, dec_r, sus_r, rel_r, level;
    logic [4:0]  tleft;
    logic [2:0]  state;
    wire         en = (tleft != 5'd0);

    assign led = 16'd0;

    adsr u_core (.clk(clk), .rst_n(!rst), .en(en), .gate(gate_r), .atk_inc(atk_r), .dec_dec(dec_r), .sus_lvl(sus_r), .rel_dec(rel_r),
                 .level(level), .state(state));

    always_ff @(posedge clk) begin
        if (en) tleft <= tleft - 1'b1;
        if (win_wr) begin
            case (win_addr)
                7'h00: gate_r <= win_wdata[0];
                7'h01: atk_r  <= win_wdata[15:0];
                7'h02: dec_r  <= win_wdata[15:0];
                7'h03: sus_r  <= win_wdata[15:0];
                7'h04: rel_r  <= win_wdata[15:0];
                7'h05: tleft  <= win_wdata[4:0];
                default: ;
            endcase
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            case (win_addr)
                7'h00: win_rdata <= {31'd0, gate_r};
                7'h01: win_rdata <= {16'd0, atk_r};
                7'h02: win_rdata <= {16'd0, dec_r};
                7'h03: win_rdata <= {16'd0, sus_r};
                7'h04: win_rdata <= {16'd0, rel_r};
                7'h06: win_rdata <= {16'd0, level};
                7'h07: win_rdata <= {29'd0, state};
                7'h08: win_rdata <= {13'd0, state, level};
                default: ;
            endcase
        end
        if (rst) begin
            gate_r <= 1'b0; atk_r <= '0; dec_r <= '0; sus_r <= '0; rel_r <= '0; tleft <= '0; win_rdata <= 32'd0;
        end
    end
endmodule

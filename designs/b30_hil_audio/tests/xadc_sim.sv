// Simulation stand-in for the XADC primitive: the DRP answers three clocks after DEN with fixed codes.
// Status registers (UG480): 0x00 temperature, 0x01 VCCINT, 0x02 VCCAUX, 0x06 VCCBRAM.
module XADC #(
    parameter [15:0] INIT_40 = 0, INIT_41 = 0, INIT_42 = 0, INIT_48 = 0, INIT_49 = 0, INIT_4A = 0, INIT_4B = 0,
    parameter [15:0] INIT_4C = 0, INIT_4D = 0, INIT_4E = 0, INIT_4F = 0, INIT_50 = 0, INIT_51 = 0, INIT_52 = 0,
    parameter [15:0] INIT_53 = 0, INIT_54 = 0, INIT_55 = 0, INIT_56 = 0, INIT_57 = 0, INIT_58 = 0, INIT_5C = 0,
    parameter SIM_DEVICE = "7SERIES"
) (
    input DCLK, DEN, DWE, input [6:0] DADDR, input [15:0] DI, output reg [15:0] DO, output reg DRDY,
    input RESET, CONVST, CONVSTCLK, VP, VN, input [15:0] VAUXP, VAUXN,
    output ALM, OT, BUSY, output [4:0] CHANNEL, output EOC, EOS, JTAGBUSY, JTAGLOCKED, JTAGMODIFIED, output [4:0] MUXADDR
);
    reg [2:0] cnt = 0;
    reg [6:0] a;
    assign {ALM, OT, BUSY, CHANNEL, EOC, EOS, JTAGBUSY, JTAGLOCKED, JTAGMODIFIED, MUXADDR} = '0;
    always @(posedge DCLK) begin
        DRDY <= 1'b0;
        if (DEN) begin cnt <= 3'd3; a <= DADDR; end
        else if (cnt != 0) begin
            cnt <= cnt - 1'b1;
            if (cnt == 3'd1) begin
                DRDY <= 1'b1;
                case (a)
                    7'h00: DO <= 16'h9A50;      // 0x9A5 -> 0.4 + ... about 35 C
                    7'h01: DO <= 16'h5560;      // 0x556 -> 1.000 V
                    7'h02: DO <= 16'hB200;      // 0xB20 -> 2.0 V (illustrative)
                    7'h06: DO <= 16'h5570;
                    default: DO <= 16'h0000;
                endcase
            end
        end
    end
endmodule

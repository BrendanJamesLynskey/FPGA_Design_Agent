// divider_hr_digit: radix-4 SRT quotient digit selection (brief 139c).
//   i = the three divisor bits below the leading one (b[W-2:W-4]), k = the 7-bit signed estimate of 32 * (4w) (the top bits of the partial
//   remainder, summed when it is carry-save). q = the digit in {-2,-1,0,1,2} as 3-bit two's complement: the largest digit whose threshold k reaches.
//   The thresholds are model.THR, found by exhaustive search over exact fractions (a=2 digit set, redundancy 2/3, estimate error 0 or 1 unit of 1/8).
module divider_hr_digit (
    input  logic [2:0]        i,
    input  logic signed [6:0] k,
    output logic [2:0]        q
);
    logic signed [6:0] m_n1, m_0, m_1, m_2;
    always_comb begin
        case (i)
            3'd0:    begin m_n1 = -7'sd13; m_0 = -7'sd5;  m_1 = 7'sd3; m_2 = 7'sd12; end
            3'd1:    begin m_n1 = -7'sd15; m_0 = -7'sd6;  m_1 = 7'sd4; m_2 = 7'sd14; end
            3'd2:    begin m_n1 = -7'sd16; m_0 = -7'sd6;  m_1 = 7'sd4; m_2 = 7'sd15; end
            3'd3:    begin m_n1 = -7'sd18; m_0 = -7'sd7;  m_1 = 7'sd4; m_2 = 7'sd16; end
            3'd4:    begin m_n1 = -7'sd20; m_0 = -7'sd8;  m_1 = 7'sd5; m_2 = 7'sd18; end
            3'd5:    begin m_n1 = -7'sd21; m_0 = -7'sd8;  m_1 = 7'sd5; m_2 = 7'sd19; end
            3'd6:    begin m_n1 = -7'sd23; m_0 = -7'sd9;  m_1 = 7'sd5; m_2 = 7'sd20; end
            default: begin m_n1 = -7'sd25; m_0 = -7'sd10; m_1 = 7'sd6; m_2 = 7'sd22; end
        endcase
        if      (k >= m_2)  q = 3'b010;       // +2
        else if (k >= m_1)  q = 3'b001;       // +1
        else if (k >= m_0)  q = 3'b000;       //  0
        else if (k >= m_n1) q = 3'b111;       // -1
        else                q = 3'b110;       // -2
    end
endmodule

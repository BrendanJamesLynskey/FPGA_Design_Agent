module floor_to_seven_segment (
    input  wire       clk,
    input  wire       reset,
    input  wire [7:0] floor_display,
    output wire [6:0] seven_seg_out,
    output wire [3:0] seven_seg_out_anode,
    output wire [3:0] thousand,
    output wire [3:0] hundred,
    output wire [3:0] ten,
    output wire [3:0] one
);

    logic [6:0]  sseg_temp;
    logic [3:0]  an_temp;
    logic [3:0]  digit;
    logic [17:0] count;

    always_ff @(posedge clk) begin
        if (reset) count <= 18'd0;
        else       count <= count + 18'd1;
    end

    always_comb begin
        case (count[17:16])
            2'b00:   begin digit = one;      an_temp = 4'b1110; end
            2'b01:   begin digit = ten;      an_temp = 4'b1101; end
            2'b10:   begin digit = hundred;  an_temp = 4'b1011; end
            2'b11:   begin digit = thousand; an_temp = 4'b0111; end
            default: begin digit = one;      an_temp = 4'b1110; end
        endcase
        case (digit)
            4'd0:    sseg_temp = 7'h40;
            4'd1:    sseg_temp = 7'h79;
            4'd2:    sseg_temp = 7'h24;
            4'd3:    sseg_temp = 7'h30;
            4'd4:    sseg_temp = 7'h19;
            4'd5:    sseg_temp = 7'h12;
            4'd6:    sseg_temp = 7'h02;
            4'd7:    sseg_temp = 7'h78;
            4'd8:    sseg_temp = 7'h00;
            4'd9:    sseg_temp = 7'h10;
            default: sseg_temp = 7'h7F;
        endcase
    end

    assign seven_seg_out       = sseg_temp;
    assign seven_seg_out_anode = an_temp;

    Binary2BCD B1 (.num(floor_display), .thousand(thousand), .hundred(hundred), .ten(ten), .one(one));

endmodule

// formal wrapper: the display scanner with REFRESH_BITS = 1 (two clocks a digit) and a free enable, digits, blank.
module formal_scan (input logic clk, input logic enable, input logic [31:0] digits, input logic [7:0] blank);
    logic rst;
    initial rst = 1'b1;
    always @(posedge clk) rst <= 1'b0;
    logic [7:0] an;
    logic [6:0] seg;
    sevenseg_scan #(.REFRESH_BITS(1)) dut (.clk(clk), .rst(rst), .enable(enable), .digits(digits), .blank(blank), .an(an), .seg(seg));
    scan_checker chk (.clk(clk), .rst(rst), .enable(enable), .blank(blank), .an(an));
endmodule

// formal wrapper: debounce + its checker, 3-clock debounce so the bounded depth covers every transition.
module formal_debounce (input logic clk, input logic btn);
    logic rst;
    initial rst = 1'b1;                         // the design starts in reset, as the board's reset does
    always @(posedge clk) rst <= 1'b0;
    logic level, press;
    debounce #(.CYCLES(3)) dut (.clk(clk), .rst(rst), .btn(btn), .level(level), .press(press));
    debounce_checker #(.CYCLES(3)) chk (.clk(clk), .rst(rst), .btn(btn), .level(level), .press(press));
endmodule

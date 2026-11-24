module t;
  function automatic logic [3:0] f(input logic [1:0] a);
    if (a == 2'b01) return 4'd1;
    if (a == 2'b10) begin return 4'd2; end
    return 4'd3;
  endfunction
  function automatic logic [3:0] g(input logic [1:0] a);
    logic [3:0] r;
    if (a == 2'b01) r = 4'd1;
    else if (a == 2'b10) r = 4'd2;
    else r = 4'd3;
    return r;
  endfunction
  logic [3:0] x, y;
  initial begin
    for (int i = 0; i < 4; i++) begin x = f(2'(i)); y = g(2'(i)); $display("%0d %0d %0d", i, x, y); end
    $finish;
  end
endmodule

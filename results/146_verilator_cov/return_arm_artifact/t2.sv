module t2;
  function automatic logic [7:0] f(input logic [1:0] a, input logic [7:0] p);
    logic [7:0] d; d = 0;
    if (a == 2'b10) begin
      for (int i = 0; i < 8; i++) d[i] = (p[i] == 1'b0) ? 1'b1 : 1'b0;
      return d;
    end
    return 8'hFF;
  endfunction
  logic [7:0] x;
  initial begin
    for (int i = 0; i < 4; i++) begin x = f(2'(i), 8'(i * 37)); $display("%0d %h", i, x); end
    $finish;
  end
endmodule

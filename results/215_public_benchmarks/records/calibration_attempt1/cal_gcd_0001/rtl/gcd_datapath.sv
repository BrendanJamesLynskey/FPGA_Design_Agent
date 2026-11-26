module gcd_datapath #(parameter int WIDTH = 4) (
  input  logic             clk,
  input  logic             rst,
  input  logic [WIDTH-1:0] A,
  input  logic [WIDTH-1:0] B,
  input  logic             go,
  input  logic [1:0]       controlpath_state,
  output logic [WIDTH-1:0] OUT,
  output logic             equal,
  output logic             greater_than
);
  logic [WIDTH-1:0] A_ff, B_ff;
  logic             idle;

  assign idle         = (controlpath_state == 2'b00);
  assign equal        = idle ? (A == B) : (A_ff == B_ff);
  assign greater_than = idle ? (A > B)  : (A_ff > B_ff);

  always_ff @(posedge clk) begin
    if (rst) begin
      A_ff <= '0;
      B_ff <= '0;
      OUT  <= '0;
    end else if (idle) begin
      if (go) begin
        A_ff <= A;
        B_ff <= B;
        if (equal) OUT <= A;
      end
    end else if (controlpath_state != 2'b01) begin
      if (equal)             OUT  <= A_ff;
      else if (greater_than) A_ff <= A_ff - B_ff;
      else                   B_ff <= B_ff - A_ff;
    end
  end
endmodule

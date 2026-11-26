/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
module gcd_top #(parameter int WIDTH = 4) (
  input  logic             clk,
  input  logic             rst,
  input  logic [WIDTH-1:0] A,
  input  logic [WIDTH-1:0] B,
  input  logic             go,
  output logic [WIDTH-1:0] OUT,
  output logic             done,
  input  logic             \gcd_controlpath.equal ,
  input  logic             \gcd_controlpath.greater_than ,
  output logic [1:0]       \gcd_controlpath.controlpath_state
);
/* verilator lint_on UNUSEDSIGNAL */
  logic       eq_i, gt_i;

  gcd_controlpath #(.WIDTH(WIDTH)) u_ctl (
    .clk(clk), .rst(rst), .go(go), .equal(eq_i), .greater_than(gt_i),
    .controlpath_state(\gcd_controlpath.controlpath_state ), .done(done));

  gcd_datapath #(.WIDTH(WIDTH)) u_dp (
    .clk(clk), .rst(rst), .A(A), .B(B),
    .controlpath_state(\gcd_controlpath.controlpath_state ),
    .equal(eq_i), .greater_than(gt_i), .OUT(OUT));
endmodule

module gcd_controlpath #(parameter int WIDTH = 4) (
  input  logic       clk,
  input  logic       rst,
  input  logic       go,
  input  logic       equal,
  input  logic       greater_than,
  output logic [1:0] controlpath_state,
  output logic       done
);
  localparam logic [1:0] S0 = 2'b00, S1 = 2'b01, S2 = 2'b10, S3 = 2'b11;
  logic [1:0] nxt;

  always_comb begin
    nxt = S0;
    case (controlpath_state)
      S0: begin
        if (go) nxt = equal ? S1 : (greater_than ? S2 : S3);
        else    nxt = S0;
      end
      S1: nxt = S0;
      default: nxt = equal ? S1 : (greater_than ? S2 : S3);
    endcase
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      controlpath_state <= S0;
      done              <= 1'b0;
    end else begin
      controlpath_state <= nxt;
      done              <= (controlpath_state == S1);
    end
  end
endmodule

module gcd_datapath #(parameter int WIDTH = 4) (
  input  logic             clk,
  input  logic             rst,
  input  logic [WIDTH-1:0] A,
  input  logic [WIDTH-1:0] B,
  input  logic [1:0]       controlpath_state,
  output logic             equal,
  output logic             greater_than,
  output logic [WIDTH-1:0] OUT
);
  logic [WIDTH-1:0] A_ff, B_ff;
  logic [WIDTH-1:0] ca, cb;

  always_comb begin
    ca = (controlpath_state == 2'b00) ? A : A_ff;
    cb = (controlpath_state == 2'b00) ? B : B_ff;
  end

  assign equal        = (ca == cb);
  assign greater_than = (ca > cb);

  always_ff @(posedge clk) begin
    if (rst) begin
      A_ff <= '0;
      B_ff <= '0;
      OUT  <= '0;
    end else begin
      case (controlpath_state)
        2'b00: begin
          A_ff <= A;
          B_ff <= B;
        end
        2'b01: OUT <= A_ff;
        default: begin
          if (greater_than)    A_ff <= A_ff - B_ff;
          else if (!equal)     B_ff <= B_ff - A_ff;
        end
      endcase
    end
  end
endmodule

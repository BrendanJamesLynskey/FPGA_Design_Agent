// Event-based APB write controller with timeout.
// Registers use no reset in the sensitivity list (STD-RST-01); the outputs are
// gated by reset_n so that reset_n low forces every output to 0 without a
// clock edge, and by rst_seen_n so that they stay 0 until the first clock edge
// after reset release. At a clock edge with reset_n low the next state is
// computed from IDLE (the controller is forced to IDLE; an event present at
// that edge is taken as the first edge after release, as the reference model
// does).
module apb_controller #(
    parameter int TIMEOUT_CYCLES    = 15,
    parameter int TIMEOUT_CNT_WIDTH = 4,
    parameter int ADDR_WIDTH        = 32,
    parameter int DATA_WIDTH        = 32
) (
    input  logic                  clk,
    input  logic                  reset_n,
    input  logic                  select_a_i,
    input  logic                  select_b_i,
    input  logic                  select_c_i,
    input  logic [ADDR_WIDTH-1:0] addr_a_i,
    input  logic [DATA_WIDTH-1:0] data_a_i,
    input  logic [ADDR_WIDTH-1:0] addr_b_i,
    input  logic [DATA_WIDTH-1:0] data_b_i,
    input  logic [ADDR_WIDTH-1:0] addr_c_i,
    input  logic [DATA_WIDTH-1:0] data_c_i,
    input  logic                  apb_pready_i,
    output logic                  apb_psel_o,
    output logic                  apb_penable_o,
    output logic                  apb_pwrite_o,
    output logic [ADDR_WIDTH-1:0] apb_paddr_o,
    output logic [DATA_WIDTH-1:0] apb_pwdata_o
);

  logic [TIMEOUT_CNT_WIDTH-1:0] cnt;
  logic                         any_sel;
  logic                         psel_q, penable_q, pwrite_q;
  logic                         run_q;  // reset_n was high at the last edge
  logic [ADDR_WIDTH-1:0]        paddr_q;
  logic [DATA_WIDTH-1:0]        pwdata_q;
  logic                         out_en;

  assign any_sel = select_a_i | select_b_i | select_c_i;

  always_ff @(posedge clk) begin
    run_q <= reset_n;
    if (!psel_q || !reset_n) begin
      // IDLE (also forced while reset_n is low)
      cnt       <= '0;
      psel_q    <= 1'b0;
      penable_q <= 1'b0;
      pwrite_q  <= 1'b0;
      paddr_q   <= '0;
      pwdata_q  <= '0;
      if (any_sel) begin
        psel_q   <= 1'b1;
        pwrite_q <= 1'b1;
        if (select_a_i) begin
          paddr_q  <= addr_a_i;
          pwdata_q <= data_a_i;
        end else if (select_b_i) begin
          paddr_q  <= addr_b_i;
          pwdata_q <= data_b_i;
        end else begin
          paddr_q  <= addr_c_i;
          pwdata_q <= data_c_i;
        end
      end
    end else if (!penable_q) begin
      // SETUP
      penable_q <= 1'b1;
    end else begin
      // ACCESS
      if (apb_pready_i || cnt >= TIMEOUT_CNT_WIDTH'(TIMEOUT_CYCLES)) begin
        psel_q    <= 1'b0;
        penable_q <= 1'b0;
        pwrite_q  <= 1'b0;
        paddr_q   <= '0;
        pwdata_q  <= '0;
        cnt       <= '0;
      end else begin
        cnt <= cnt + 1'b1;
      end
    end
  end

  assign out_en        = reset_n & run_q;
  assign apb_psel_o    = psel_q    & out_en;
  assign apb_penable_o = penable_q & out_en;
  assign apb_pwrite_o  = pwrite_q  & out_en;
  assign apb_paddr_o   = paddr_q   & {ADDR_WIDTH{out_en}};
  assign apb_pwdata_o  = pwdata_q  & {DATA_WIDTH{out_en}};

endmodule

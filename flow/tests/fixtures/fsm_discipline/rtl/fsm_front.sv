// Shared front end for the brief 24 reference controller: the reset styles, the control-register primitive and the input stage.

// Reset styles (RST):
//   0 asynchronous assert, asynchronous release        FDCE   (plain async reset)
//   1 synchronous reset, takes priority over the enable FDRE
//   2 no reset: the register starts from its initial value (GSR at configuration)
//   3 asynchronous assert, synchronous release         FDCE behind a 2-flop ASYNC_REG release chain
//   4 synchronous reset that is only looked at on an enable tick (the reset is gated by the enable)
module fsm_reg #(parameter int W = 1, parameter logic [W-1:0] INIT = '0, parameter int RST = 0) (
  input  logic         clk,
  input  logic         rst_n,          // raw reset input, active low
  input  logic         ce,
  input  logic [W-1:0] d,
  output logic [W-1:0] q
);
  logic arst_n;
  logic [1:0] rel_q = 2'b00;
  (* ASYNC_REG = "TRUE" *) logic r0 = 1'b0;
  (* ASYNC_REG = "TRUE" *) logic r1 = 1'b0;
  generate
    if (RST == 3) begin : g_sync_release
      // the reset asserts at once and is released by the clock (reset synchroniser: two flops)
      always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) begin r0 <= 1'b0; r1 <= 1'b0; end
        else        begin r0 <= 1'b1; r1 <= r0;   end
      assign arst_n = r1;
    end else begin : g_raw
      assign arst_n = rst_n;
    end
    if (RST == 0 || RST == 3) begin : g_async
      initial q = INIT;
      always_ff @(posedge clk or negedge arst_n)
        if (!arst_n) q <= INIT; else if (ce) q <= d;
    end else if (RST == 1) begin : g_sync
      initial q = INIT;
      always_ff @(posedge clk)
        if (!rst_n) q <= INIT; else if (ce) q <= d;
    end else if (RST == 2) begin : g_none
      initial q = INIT;
      always_ff @(posedge clk) if (ce) q <= d;
    end else begin : g_sync_gated
      initial q = INIT;
      always_ff @(posedge clk) if (ce) begin if (!rst_n) q <= INIT; else q <= d; end
    end
  endgenerate
endmodule

// The asynchronous reset the state register sees: the raw reset (RST 0), or the reset released by a 2-flop chain (RST 3).
// (The FSM's own state register stays in the FSM module: a state register inside a helper is a plain vector to Vivado and is not extracted.)
module fsm_arst #(parameter int RST = 0) (input logic clk, input logic rst_n, output logic a_n);
  (* ASYNC_REG = "TRUE" *) logic r0 = 1'b0;
  (* ASYNC_REG = "TRUE" *) logic r1 = 1'b0;
  generate
    if (RST == 3) begin : g_rel
      always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) begin r0 <= 1'b0; r1 <= 1'b0; end
        else        begin r0 <= 1'b1; r1 <= r0;   end
      assign a_n = r1;
    end else begin : g_raw
      assign a_n = rst_n;
    end
  endgenerate
endmodule

// Input stage (IN): 0 the raw input, 1 one register (a synchronous input: costs a cycle, cuts the path from the pin),
// 2 two ASYNC_REG registers (a synchroniser: for an input launched by another clock).
module fsm_in #(parameter int IN = 0) (input logic clk, input logic a, output logic y);
  generate
    if (IN == 0) begin : g_raw
      assign y = a;
    end else if (IN == 1) begin : g_one
      logic q = 1'b0;
      always_ff @(posedge clk) q <= a;
      assign y = q;
    end else begin : g_two
      (* ASYNC_REG = "TRUE" *) logic s0 = 1'b0;
      (* ASYNC_REG = "TRUE" *) logic s1 = 1'b0;
      always_ff @(posedge clk) begin s0 <= a; s1 <= s0; end
      assign y = s1;
    end
  endgenerate
endmodule

// Brief 70 reset-cost bench: four small blocks (register bank, counter, DSP multiply-add, block-RAM read path) whose
// reset style is set by parameters. Synthesised out of context; see results/70_resets/README.md.
//
//   ASYNC      0: synchronous reset, 1: asynchronous reset (measured only as evidence; the house rule is synchronous)
//   ACTIVE_LOW 0: the reset port is active high (rst), 1: active low (rst_n)
//   RESET_ALL  1: every register has a reset, 0: only the control (valid, counter) registers do
//   BOTH       1: half of the register groups use the reset as written, the other half use its inverse written the other way
//                 (the same reset condition, written in both polarities); 2: the other half tests the SAME signal at the opposite
//                 level (a reset asserted when high in some places and when low in others, which is two different conditions)
//   REGRST     1: the reset passes through one register inside the module before it fans out
//   MAXFO      with REGRST: 50 puts the MAX_FANOUT = 50 attribute on that register (synthesis replicates it); 0 leaves it plain
//   BLOCKS     bit mask: 1 register bank, 2 counter, 4 DSP, 8 block RAM
module rreg #(parameter int W = 1, parameter bit RST_EN = 1, parameter bit ASYNC = 0, parameter bit LOW = 0)
  (input logic clk, input logic rst, input logic en, input logic [W-1:0] d, output logic [W-1:0] q);
  if (!RST_EN) begin : g_none
    always_ff @(posedge clk) if (en) q <= d;
  end else if (ASYNC && LOW) begin : g_al
    always_ff @(posedge clk or negedge rst) if (!rst) q <= '0; else if (en) q <= d;
  end else if (ASYNC) begin : g_ah
    always_ff @(posedge clk or posedge rst) if (rst) q <= '0; else if (en) q <= d;
  end else if (LOW) begin : g_sl
    always_ff @(posedge clk) if (!rst) q <= '0; else if (en) q <= d;
  end else begin : g_sh
    always_ff @(posedge clk) if (rst) q <= '0; else if (en) q <= d;
  end
endmodule

module rb_top #(parameter bit ASYNC = 0, parameter bit ACTIVE_LOW = 0, parameter bit RESET_ALL = 1,
                parameter int BOTH = 0, parameter bit REGRST = 0, parameter int BLOCKS = 15, parameter int MAXFO = 0)
  (input logic clk, input logic rst_in, input logic en, input logic [31:0] din, input logic [3:0] waddr,
   input logic [3:0] raddr, input logic [17:0] ma, input logic [17:0] mb,
   output logic [31:0] o_reg, output logic [31:0] o_cnt, output logic [47:0] o_dsp, output logic [31:0] o_ram, output logic [2:0] o_v);

  // the reset as the design sees it (one polarity, or both of one port)
  localparam bit L0 = (BOTH != 0) ? 1'b1 : ACTIVE_LOW;   // BOTH: the port is rst_n, half the groups use it as is
  logic rst0;
  if (REGRST && MAXFO != 0) begin : g_rr
    // one synchronous register for the reset with a fan-out limit, then fan-out (same polarity as the port); ASYNC = 0 only
    (* max_fanout = 50 *) logic r;
    always_ff @(posedge clk) r <= rst_in;
    assign rst0 = r;
  end else if (REGRST) begin : g_rr
    // one synchronous register for the reset, then fan-out (same polarity as the port); used with ASYNC = 0 only
    logic r;
    always_ff @(posedge clk) r <= rst_in;
    assign rst0 = r;
  end else begin : g_dir
    assign rst0 = rst_in;
  end
  wire rst1 = ~rst0;   // the inverse, used by the second half of the groups when BOTH

  localparam bit DR = RESET_ALL;   // data registers get a reset only in the reset-all arm

  // ---- block 1: register bank, 16 x 32 with a valid bit each -------------------------------------------------------
  logic [31:0] rd;
  logic [15:0] vld;
  if (BLOCKS & 1) begin : b1
    logic [31:0] ent [16];
    for (genvar i = 0; i < 16; i++) begin : e
      localparam bit ALT = (BOTH != 0) && (i % 2 == 1);
      wire r = (ALT && BOTH == 1) ? rst1 : rst0;
      localparam bit LW = ALT ? ~L0 : L0;
      wire we = en && (waddr == i[3:0]);
      rreg #(.W(32), .RST_EN(DR), .ASYNC(ASYNC), .LOW(LW)) u_d (.clk, .rst(r), .en(we), .d(din), .q(ent[i]));
      rreg #(.W(1), .RST_EN(1), .ASYNC(ASYNC), .LOW(LW)) u_v (.clk, .rst(r), .en(we), .d(1'b1), .q(vld[i]));
    end
    wire [31:0] sel = ent[raddr] & {32{vld[raddr]}};
    rreg #(.W(32), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_o (.clk, .rst(rst0), .en(1'b1), .d(sel), .q(rd));
  end else begin : b1n
    assign rd = '0; assign vld = '0;
  end
  assign o_reg = rd;

  // ---- block 2: counter (control) with a two-stage data pipeline ----------------------------------------------------
  logic [31:0] cnt, p1, p2;
  if (BLOCKS & 2) begin : b2
    localparam bit LW = (BOTH != 0) ? ~L0 : L0;
    wire r = (BOTH == 1) ? rst1 : rst0;
    rreg #(.W(32), .RST_EN(1), .ASYNC(ASYNC), .LOW(LW)) u_c (.clk, .rst(r), .en(en), .d(cnt + 32'd1), .q(cnt));
    rreg #(.W(32), .RST_EN(DR), .ASYNC(ASYNC), .LOW(LW)) u_p1 (.clk, .rst(r), .en(1'b1), .d(cnt ^ din), .q(p1));
    rreg #(.W(32), .RST_EN(DR), .ASYNC(ASYNC), .LOW(LW)) u_p2 (.clk, .rst(r), .en(1'b1), .d(p1), .q(p2));
  end else begin : b2n
    assign cnt = '0; assign p1 = '0; assign p2 = '0;
  end
  assign o_cnt = p2;

  // ---- block 3: DSP, p = a*b + c with input, product and output registers --------------------------------------------
  logic [47:0] pq; logic dv;
  if (BLOCKS & 4) begin : b3
    logic [17:0] a_q, b_q; logic [31:0] c_q, c_q2; logic [35:0] m_q; logic [3:0] v_q;
    rreg #(.W(18), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_a (.clk, .rst(rst0), .en(1'b1), .d(ma), .q(a_q));
    rreg #(.W(18), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_b (.clk, .rst(rst0), .en(1'b1), .d(mb), .q(b_q));
    rreg #(.W(32), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_c (.clk, .rst(rst0), .en(1'b1), .d(din), .q(c_q));
    rreg #(.W(32), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_c2 (.clk, .rst(rst0), .en(1'b1), .d(c_q), .q(c_q2));
    rreg #(.W(36), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_m (.clk, .rst(rst0), .en(1'b1),
                                                               .d(36'($signed(a_q) * $signed(b_q))), .q(m_q));
    rreg #(.W(48), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_p (.clk, .rst(rst0), .en(1'b1),
                                                               .d(48'($signed(m_q)) + 48'($signed(c_q2))), .q(pq));
    rreg #(.W(4), .RST_EN(1), .ASYNC(ASYNC), .LOW(L0)) u_v (.clk, .rst(rst0), .en(1'b1), .d({v_q[2:0], en}), .q(v_q));
    assign dv = v_q[3];
  end else begin : b3n
    assign dv = 1'b0;
  end
  assign o_dsp = pq;

  // ---- block 4: block-RAM read path (1024 x 32, read register then output register) --------------------------------
  logic [31:0] oq; logic rv;
  if (BLOCKS & 8) begin : b4
    logic [31:0] mem [1024]; logic [31:0] rq; logic [1:0] v_q;
    wire [9:0] wa = {din[5:0], waddr}; wire [9:0] ra = {din[15:10], raddr};
    always_ff @(posedge clk) begin
      if (en) mem[wa] <= din;
      rq <= mem[ra];
    end
    rreg #(.W(32), .RST_EN(DR), .ASYNC(ASYNC), .LOW(L0)) u_o (.clk, .rst(rst0), .en(1'b1), .d(rq), .q(oq));
    rreg #(.W(2), .RST_EN(1), .ASYNC(ASYNC), .LOW(L0)) u_v (.clk, .rst(rst0), .en(1'b1), .d({v_q[0], en}), .q(v_q));
    assign rv = v_q[1];
  end else begin : b4n
    assign rv = 1'b0;
  end
  assign o_ram = oq;
  assign o_v = {rv, dv, ^vld};
endmodule

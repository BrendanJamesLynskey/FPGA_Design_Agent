// Register window decode and 16x24 step memory.
module seq_regs (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    // to core
    output logic        start,
    output logic        stop,
    output logic        oneshot,
    output logic [4:0]  length,
    output logic [15:0][15:0] pat,
    output logic [15:0][7:0]  dur,
    // from core
    input  logic        running,
    input  logic        paused,
    input  logic        finished,
    input  logic [3:0]  index,
    input  logic [15:0] loops
);
  logic [15:0][23:0] mem;

  wire ctrl_wr = win_wr && (win_addr == 7'h00);
  assign start = ctrl_wr && win_wdata[0];
  assign stop  = ctrl_wr && !win_wdata[0];

  always_ff @(posedge clk) begin
    if (rst) begin
      oneshot <= 1'b0;
      length  <= 5'd4;
      mem     <= '0;
    end else if (win_wr) begin
      if (win_addr == 7'h00) oneshot <= win_wdata[1];
      if (win_addr == 7'h01 && win_wdata[4:0] != 5'd0 && win_wdata[4:0] <= 5'd16)
        length <= win_wdata[4:0];
      if (win_addr[6:4] == 3'd1) mem[win_addr[3:0]] <= win_wdata[23:0];
    end
  end

  for (genvar g = 0; g < 16; g++) begin : g_split
    assign pat[g] = mem[g][15:0];
    assign dur[g] = mem[g][23:16];
  end

  always_ff @(posedge clk) begin
    if (rst) win_rdata <= 32'h0;
    else if (win_rd) begin
      win_rdata <= 32'h0;
      if (win_addr[6:4] == 3'd1) win_rdata <= {8'h0, mem[win_addr[3:0]]};
      else begin
        case (win_addr)
          7'h00: win_rdata <= {30'h0, oneshot, running};
          7'h01: win_rdata <= {27'h0, length};
          7'h02: win_rdata <= {28'h0, index};
          7'h03: win_rdata <= {29'h0, finished, paused, running};
          7'h04: win_rdata <= {16'h0, loops};
          default: win_rdata <= 32'h0;
        endcase
      end
    end
  end
endmodule

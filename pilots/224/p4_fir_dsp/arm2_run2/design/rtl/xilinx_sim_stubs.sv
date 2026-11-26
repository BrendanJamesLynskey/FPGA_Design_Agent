// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifdef VERILATOR
`verilator_config
lint_off -rule UNUSEDSIGNAL -file "*jtag_bus.sv" -match "*"
`verilog
`endif
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off SYNCASYNCNET */
/* verilator lint_off UNDRIVEN */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */

module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic s0 = 1'b0, s1 = 1'b0, s2 = 1'b0;
    always_ff @(posedge dest_clk) begin s0 <= src_in; s1 <= s0; s2 <= s1; end
    assign dest_out = (DEST_SYNC_FF > 2) ? s2 : s1;
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    for (genvar b = 0; b < WIDTH; b++) begin : g_bit
        xpm_cdc_single #(.DEST_SYNC_FF(DEST_SYNC_FF)) u_s (
            .src_clk(src_clk), .src_in(src_in[b]), .dest_clk(dest_clk), .dest_out(dest_out[b]));
    end
endmodule

module xpm_cdc_gray #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SIM_LOSSLESS_GRAY_CHK = 0, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in_bin,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out_bin
);
    logic [WIDTH-1:0] g = '0, s0 = '0, s1 = '0, s2 = '0;
    always_ff @(posedge src_clk) g <= src_in_bin ^ (src_in_bin >> 1);
    always_ff @(posedge dest_clk) begin s0 <= g; s1 <= s0; s2 <= s1; end
    wire [WIDTH-1:0] sg = (DEST_SYNC_FF > 2) ? s2 : s1;
    always_comb begin
        dest_out_bin[WIDTH-1] = sg[WIDTH-1];
        for (int i = WIDTH - 2; i >= 0; i--) dest_out_bin[i] = dest_out_bin[i+1] ^ sg[i];
    end
endmodule

module xpm_cdc_pulse #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
    parameter int RST_USED = 1, parameter int SIM_ASSERT_CHK = 0
) (
    input logic src_clk, input logic src_rst, input logic src_pulse,
    input logic dest_clk, input logic dest_rst, output logic dest_pulse
);
    logic tg = 1'b0, s0 = 1'b0, s1 = 1'b0, s2 = 1'b0;
    always_ff @(posedge src_clk) if (src_pulse) tg <= ~tg;
    always_ff @(posedge dest_clk) begin s0 <= tg; s1 <= s0; s2 <= s1; end
    assign dest_pulse = s1 ^ s2;
endmodule

module xpm_cdc_async_rst #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int RST_ACTIVE_HIGH = 0
) (
    input logic dest_clk, input logic src_arst, output logic dest_arst
);
    logic [1:0] s = 2'b00;
    always_ff @(posedge dest_clk or posedge src_arst) begin
        if (src_arst) s <= 2'b11; else s <= {s[0], 1'b0};
    end
    assign dest_arst = s[1];
endmodule

module xpm_sim_mem #(parameter int AW = 10, parameter int DW = 16) (
    input logic clk, input logic we, input logic [AW-1:0] waddr, input logic [DW-1:0] wdata,
    input logic [AW-1:0] raddr, output logic [DW-1:0] rdata
);
    logic [DW-1:0] mem [0:(1<<AW)-1];
    initial for (int i = 0; i < (1 << AW); i++) mem[i] = '0;
    always_ff @(posedge clk) if (we) mem[waddr] <= wdata;
    assign rdata = mem[raddr];
endmodule

module xpm_sim_rd #(parameter int DW = 16, parameter int LAT = 2) (
    input logic clk, input logic en, input logic [DW-1:0] d, output logic [DW-1:0] q
);
    logic [DW-1:0] r1 = '0, r2 = '0;
    always_ff @(posedge clk) begin
        if (en) r1 <= d;
        r2 <= r1;
    end
    assign q = (LAT > 1) ? r2 : r1;
endmodule

module xpm_memory_sdpram #(
    parameter int ADDR_WIDTH_A = 6, parameter int ADDR_WIDTH_B = 6, parameter int BYTE_WRITE_WIDTH_A = 32,
    parameter string CLOCKING_MODE = "common_clock", parameter string MEMORY_PRIMITIVE = "auto",
    parameter int MEMORY_SIZE = 2048, parameter int READ_DATA_WIDTH_B = 32, parameter int READ_LATENCY_B = 2,
    parameter int WRITE_DATA_WIDTH_A = 32
) (
    input  logic sleep,
    input  logic clka, input logic ena, input logic [WRITE_DATA_WIDTH_A/BYTE_WRITE_WIDTH_A-1:0] wea,
    input  logic [ADDR_WIDTH_A-1:0] addra, input logic [WRITE_DATA_WIDTH_A-1:0] dina,
    input  logic injectsbiterra, input logic injectdbiterra,
    input  logic clkb, input logic rstb, input logic enb, input logic regceb,
    input  logic [ADDR_WIDTH_B-1:0] addrb, output logic [READ_DATA_WIDTH_B-1:0] doutb,
    output logic sbiterrb, output logic dbiterrb
);
    logic [WRITE_DATA_WIDTH_A-1:0] rd_async;
    xpm_sim_mem #(.AW(ADDR_WIDTH_A), .DW(WRITE_DATA_WIDTH_A)) u_mem (
        .clk(clka), .we(ena && wea[0]), .waddr(addra), .wdata(dina), .raddr(addrb), .rdata(rd_async));
    xpm_sim_rd #(.DW(READ_DATA_WIDTH_B), .LAT(READ_LATENCY_B)) u_rd (
        .clk(clkb), .en(enb), .d(rd_async), .q(doutb));
    assign sbiterrb = 1'b0;
    assign dbiterrb = 1'b0;
endmodule

module USR_ACCESSE2 (output logic [31:0] DATA, output logic DATAVALID, output logic CFGCLK);
    assign DATA = 32'h0;
    assign DATAVALID = 1'b1;
    assign CFGCLK = 1'b0;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module MMCME4_BASE #(
    parameter real CLKIN1_PERIOD = 10.0, parameter real CLKFBOUT_MULT_F = 5.0,
    parameter int DIVCLK_DIVIDE = 1, parameter real CLKOUT0_DIVIDE_F = 1.0
) (
    input logic CLKIN1, input logic CLKFBIN, output logic CLKFBOUT, output logic CLKOUT0,
    output logic LOCKED, input logic RST, input logic PWRDWN
);
    assign CLKFBOUT = CLKIN1;
    assign CLKOUT0 = CLKIN1;
    assign LOCKED = 1'b1;
endmodule
`endif

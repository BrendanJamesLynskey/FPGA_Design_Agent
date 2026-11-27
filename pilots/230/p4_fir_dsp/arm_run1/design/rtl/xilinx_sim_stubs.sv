// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNDRIVEN */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */
/* verilator lint_off PINCONNECTEMPTY */
/* verilator lint_off SYNCASYNCNET */

module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] s = '0;
    always_ff @(posedge dest_clk) s <= {s[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] s [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        s[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) s[i] <= s[i-1];
    end
    assign dest_out = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int RST_ACTIVE_HIGH = 0
) (
    output logic dest_arst, input logic dest_clk, input logic src_arst
);
    logic a;
    logic [DEST_SYNC_FF-1:0] ff = '0;
    assign a = (RST_ACTIVE_HIGH != 0) ? src_arst : ~src_arst;
    always_ff @(posedge dest_clk) begin
        if (a) ff <= '1;
        else   ff <= {ff[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = (RST_ACTIVE_HIGH != 0) ? ff[DEST_SYNC_FF-1] : ~ff[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_handshake #(
    parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out, output logic dest_req, input logic dest_ack
);
    logic req_t = 1'b0, ack_t = 1'b0, busy = 1'b0;
    logic [WIDTH-1:0] data_r = '0;
    logic [1:0] req_s = '0, ack_s = '0;
    initial begin src_rcv = 1'b0; dest_req = 1'b0; dest_out = '0; end
    always_ff @(posedge src_clk) begin
        ack_s <= {ack_s[0], ack_t};
        if (!src_send) src_rcv <= 1'b0;
        if (src_send && !busy && !src_rcv) begin
            data_r <= src_in; req_t <= ~req_t; busy <= 1'b1;
        end else if (busy && ack_s[1] == req_t) begin
            busy <= 1'b0; src_rcv <= 1'b1;
        end
    end
    always_ff @(posedge dest_clk) begin
        req_s <= {req_s[0], req_t};
        dest_req <= 1'b0;
        if (req_s[1] != ack_t) begin
            ack_t <= req_s[1]; dest_out <= data_r; dest_req <= 1'b1;
        end
    end
endmodule

// std-waive: STD-CDC-01 simulation-only stand-in for the Xilinx XPM memory primitive, which is itself the dual-clock crossing
module xpm_memory_sdpram #(
    parameter int ADDR_WIDTH_A = 6, parameter int ADDR_WIDTH_B = 6, parameter int BYTE_WRITE_WIDTH_A = 32,
    parameter string CLOCKING_MODE = "common_clock", parameter string MEMORY_PRIMITIVE = "auto",
    parameter int MEMORY_SIZE = 2048, parameter int READ_DATA_WIDTH_B = 32, parameter int READ_LATENCY_B = 2,
    parameter int WRITE_DATA_WIDTH_A = 32
) (
    input  logic sleep, input logic clka, input logic ena, input logic [0:0] wea,
    input  logic [ADDR_WIDTH_A-1:0] addra, input logic [WRITE_DATA_WIDTH_A-1:0] dina,
    input  logic injectsbiterra, input logic injectdbiterra,
    input  logic clkb, input logic enb, input logic [ADDR_WIDTH_B-1:0] addrb,
    output logic [READ_DATA_WIDTH_B-1:0] doutb, input logic regceb, input logic rstb,
    output logic sbiterrb, output logic dbiterrb
);
    logic [WRITE_DATA_WIDTH_A-1:0] mem [2**ADDR_WIDTH_A];
    initial begin
        for (int i = 0; i < 2**ADDR_WIDTH_A; i++) mem[i] = '0;
        doutb = '0;
    end
    always_ff @(posedge clka) if (ena && wea[0]) mem[addra] <= dina;
    always_ff @(posedge clkb) if (enb) doutb <= mem[addrb];
    assign sbiterrb = 1'b0;
    assign dbiterrb = 1'b0;
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module MMCME4_ADV #(
    parameter string BANDWIDTH = "OPTIMIZED", parameter real CLKFBOUT_MULT_F = 5.0,
    parameter real CLKIN1_PERIOD = 0.0, parameter real CLKOUT0_DIVIDE_F = 1.0, parameter int DIVCLK_DIVIDE = 1
) (
    input  logic CLKIN1, input logic CLKINSEL, input logic CLKFBIN, output logic CLKFBOUT,
    output logic CLKOUT0, output logic LOCKED, input logic PWRDWN, input logic RST
);
    logic clk_o = 1'b0;
    logic [3:0] lk = '0;
    assign CLKFBOUT = CLKIN1;
    always_ff @(posedge CLKIN1) if (!lk[3]) lk <= lk + 4'd1;
    assign LOCKED = lk[3];
    assign CLKOUT0 = CLKIN1;
endmodule
`endif

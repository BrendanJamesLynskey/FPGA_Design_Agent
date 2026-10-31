// qspi_rdid.sv: reads the configuration flash's JEDEC identification and
// nothing else. A transfer is: chip select low, the one opcode this module
// holds (RDID, 9Fh) out on DQ0, eight ID bytes in on DQ1, chip select high.
// The opcode is a constant: no register, port or parameter can change it, so
// the design cannot send a write, erase or register-write command
// (tests/test_qspi_rtl.py checks the source for that, and the simulation
// decodes every command the flash would see).
//
// SCK is HALF clocks low and HALF high (50 = 1 MHz at 100 MHz). On the board it
// leaves through STARTUPE2's USRCCLKO, which swallows its first three edges
// after configuration, so the first request is preceded by PREAMBLE clock
// pulses with chip select high (the flash ignores clocks while deselected).

module qspi_rdid #(
    parameter int HALF     = 50,
    parameter int PREAMBLE = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    output logic        busy,
    output logic        done,
    output logic [63:0] id,       // byte i (the i-th byte read) in [8i+7:8i]
    output logic        sck,
    output logic        cs_n,
    output logic        dq0,      // serial data to the flash
    input  logic        dq1       // serial data from the flash, synchronised
);
    localparam logic [7:0] RDID = 8'h9F;   // the only command this module can send

    typedef enum logic [2:0] {S_IDLE, S_PRE_LO, S_PRE_HI, S_SETUP, S_HIGH, S_LOW, S_HOLD, S_GAP} st_t;
    st_t         st;
    logic [15:0] div;
    logic [7:0]  pre_left;
    logic [6:0]  bit_no;          // 0..71: 8 opcode bits, then 64 ID bits
    logic [63:0] rx;
    logic        primed;          // the preamble has been sent since reset
    logic        tick;

    assign tick = (st != S_IDLE) && (div == 16'(HALF - 1));
    logic [7:0]  cmd_sh;          // opcode bits still to send, MSB first; zero once sent
    assign dq0  = cmd_sh[7];      // a flop output: changes only while SCK is low

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; div <= '0; pre_left <= '0; bit_no <= '0; rx <= '0; id <= '0;
            primed <= 1'b0; busy <= 1'b0; done <= 1'b0; sck <= 1'b0; cs_n <= 1'b1; cmd_sh <= '0;
        end else begin
            div <= tick ? '0 : (st == S_IDLE ? '0 : div + 16'd1);
            unique case (st)
                S_IDLE: if (go) begin
                    busy <= 1'b1; done <= 1'b0; bit_no <= '0; rx <= '0;
                    if (!primed) begin st <= S_PRE_LO; pre_left <= 8'(PREAMBLE); end
                    else begin st <= S_SETUP; cs_n <= 1'b0; cmd_sh <= RDID; end
                end
                // preamble: PREAMBLE pulses with chip select high, then one more low half before
                // chip select falls (so SCK is low when it does: mode 0)
                S_PRE_LO: if (tick) begin
                    if (pre_left == 8'd0) begin st <= S_SETUP; primed <= 1'b1; cs_n <= 1'b0; cmd_sh <= RDID; end
                    else begin st <= S_PRE_HI; sck <= 1'b1; end
                end
                S_PRE_HI: if (tick) begin st <= S_PRE_LO; sck <= 1'b0; pre_left <= pre_left - 8'd1; end
                S_SETUP: if (tick) begin st <= S_HIGH; sck <= 1'b1; end
                S_HIGH:  if (tick) begin
                    sck <= 1'b0;
                    if (bit_no >= 7'd8) rx <= {rx[62:0], dq1};
                    if (bit_no == 7'd71) st <= S_HOLD;
                    else begin st <= S_LOW; bit_no <= bit_no + 7'd1; cmd_sh <= {cmd_sh[6:0], 1'b0}; end
                end
                S_LOW:   if (tick) begin st <= S_HIGH; sck <= 1'b1; end
                S_HOLD:  if (tick) begin st <= S_GAP; cs_n <= 1'b1; end
                S_GAP:   if (tick) begin
                    st <= S_IDLE; busy <= 1'b0; done <= 1'b1;
                    for (int i = 0; i < 8; i++) id[8*i +: 8] <= rx[63 - 8*i -: 8];
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule

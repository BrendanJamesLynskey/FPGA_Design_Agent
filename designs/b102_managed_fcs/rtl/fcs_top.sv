// fcs_top.sv: KR260 self-test of an FCS stage: the owned sequencer fcs_ctrl drives the frozen, externally produced CRC-32 block
// and shows its verdict on led[0]; led[1] is the (excluded) heartbeat. The clock pin is the board's 25 MHz oscillator; the
// timing target in design.xdc is the 10G datapath's 161.13 MHz, to ask the real question of the CRC block.
module fcs_top #(
    parameter logic [31:0] BUILD_STAMP = 32'h0
) (
    input  logic       clk_25,
    output logic [1:0] led
);
    logic [3:0]  por;                                // power-on reset: a four-clock shift register (configured flip-flops start at zero)
    logic        rst;
    logic        init, en, pass, frame;
    logic [15:0] d;
    logic [31:0] crc;
    logic        blink;

    always_ff @(posedge clk_25) por <= {por[2:0], 1'b1};
    assign rst = !por[3];

    fcs_ctrl u_ctrl (.clk(clk_25), .rst(rst), .crc_i(crc), .crc_init_o(init), .crc_en_o(en), .crc_d_o(d), .pass_o(pass), .frame_o(frame));
    crc32_d16 u_crc (.clk(clk_25), .rst(rst), .init(init), .en(en), .d(d), .crc(crc));
    heartbeat u_hb (.clk(clk_25), .rst(rst), .blink(blink));

    assign led = {blink, pass};
    /* verilator lint_off UNUSED */
    logic unused;
    assign unused = &{1'b0, frame, BUILD_STAMP};
    /* verilator lint_on UNUSED */
endmodule

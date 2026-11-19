// crc32_d16.sv: OUR adapter (owned) around a frozen block that is not ours: Alex Forencich's combinational parallel LFSR/CRC
// (third_party/verilog-ethernet/lfsr.v, MIT). The block computes the next CRC state from the current state and 16 data bits;
// this file adds the register, the restart (init) and the enable, and presents the port list the sequencer already uses
// (the contract of the 'crc' component in project.yaml). Settings follow the table in the block's own header: CRC32 =
// Galois, bit-reverse, polynomial 04C11DB7, initial value FFFFFFFF; the register here is the state (the Ethernet FCS is its
// complement, which is the caller's business).
// Behaviour a user could guess wrong: crc is the register, not its complement; the word is two bytes, least significant byte
// first, always full; init restarts the register at FFFFFFFF with this word; with en low the register holds; reset wins over
// en; the register powers up at FFFFFFFF.
module crc32_d16 (
    input  logic        clk,
    input  logic        rst,
    input  logic        init,
    input  logic        en,
    input  logic [15:0] d,
    output logic [31:0] crc
);
    logic [31:0] nxt;

    lfsr #(
        .LFSR_WIDTH(32),
        .LFSR_POLY(32'h04c11db7),
        .LFSR_CONFIG("GALOIS"),
        .LFSR_FEED_FORWARD(0),
        .REVERSE(1),
        .DATA_WIDTH(16),
        .STYLE("AUTO")
    ) u_lfsr (
        .data_in(d),
        .state_in(init ? 32'hFFFFFFFF : crc),
        .data_out(),
        .state_out(nxt)
    );

    initial crc = 32'hFFFFFFFF;

    always_ff @(posedge clk) begin
        if (rst)     crc <= 32'hFFFFFFFF;
        else if (en) crc <= nxt;
    end
endmodule

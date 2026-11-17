// crc32_d16.sv: the Ethernet FCS (IEEE 802.3 CRC-32, reflected, polynomial 04C11DB7) over 16 bits (two bytes, least significant byte first) per clock.
// The producer's RTL for the block delivered as ext/crc32_d16.edf; it is the reference the netlist is proved equivalent to
// (eqy) and is not compiled into the build. The update is the CRC-32 function of designs/b96_kr260_10g/rtl/b96_pkg.sv
// (crc_upd) at 16 bits per clock instead of 64, written inline so this file stands alone: eqy's open SAT engines prove this
// width in under a minute and not the 64-bit one (results/102_managed/eqy_width_scaling.json).
//   init: the register restarts at FFFFFFFF with this word (the first word of a frame); en: take the word; rst: synchronous.
// Behaviour a user could guess wrong: crc is the register, not its complement; the word is two bytes, least significant
// byte first, always full (an odd last byte is the caller's business); with en low the register holds; reset wins over en; the register powers up at FFFFFFFF.
module crc32_d16 (
    input  logic        clk,
    input  logic        rst,
    input  logic        init,
    input  logic        en,
    input  logic [15:0] d,
    output logic [31:0] crc
);
    function automatic logic [31:0] step(input logic [31:0] c, input logic [15:0] w);
        logic [31:0] r; logic fb;
        r = c;
        for (integer i = 0; i < 16; i = i + 1) begin
            fb = r[0] ^ w[i];
            r = {1'b0, r[31:1]};
            if (fb) r = r ^ 32'hEDB88320;
        end
        step = r;
    endfunction

    initial crc = 32'hFFFFFFFF;                 // power-up value: the same as reset (the netlist's flip-flops carry INIT 1)

    always_ff @(posedge clk) begin
        if (rst)     crc <= 32'hFFFFFFFF;
        else if (en) crc <= step(init ? 32'hFFFFFFFF : crc, d);
    end
endmodule

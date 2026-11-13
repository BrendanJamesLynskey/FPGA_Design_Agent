// prbs_link.sv: simulation bench wrapper (not built): the fabric PRBS generator into the checker, a flip mask between them.
module prbs_link (
    input  logic        clk,
    input  logic        rst,
    input  logic [1:0]  sel,
    input  logic        gen_en,
    input  logic        chk_en,
    input  logic        force_err,
    input  logic [63:0] flip,        // XORed into the word between generator and checker (line errors)
    input  logic        clr,
    output logic [63:0] gen_data,
    output logic        locked,
    output logic        lost_pulse,
    output logic [63:0] words,
    output logic [63:0] err_bits,
    output logic [31:0] err_words,
    output logic [15:0] lock_losses
);
    prbs_gen64 u_gen (.clk, .rst, .sel, .en(gen_en), .force_err, .data(gen_data));
    prbs_chk64 u_chk (.clk, .rst, .sel, .en(chk_en), .data(gen_data ^ flip), .clr, .locked, .lost_pulse, .words, .err_bits,
                      .err_words, .lock_losses);
endmodule

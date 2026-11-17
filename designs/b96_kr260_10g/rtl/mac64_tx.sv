// mac64_tx.sv: 10 Gb/s Ethernet MAC transmitter on a 64-bit XGMII-style word stream (brief 96).
//
// A frame source offers whole 64-bit data words (s_valid, s_data, s_last with s_nb1 = bytes in the last word minus 1) and keeps each
// word stable until s_ready. The MAC puts the preamble in the first word (start in lane 0), adds the FCS after the last data byte
// (inverted again when s_poison is set with the last word: a deliberately bad FCS, for speculative orders that must be undone), the
// terminate character, and at least 12 byte times of gap (the interframe gap counts the terminate). No padding: the source supplies at
// least 60 bytes (asserted in simulation). Every state element holds while adv is low (the PCS gearbox pause).
// Registers on the path: x_d, x_c (the XGMII word handed to the PCS), tail (the second word of a frame end that overflows one word),
// crc. The preamble goes out one clock after s_valid first rises, so a source that raises s_valid early costs nothing.
module mac64_tx (
    input  logic        clk,
    input  logic        rst,
    input  logic        adv,
    input  logic        s_valid,
    input  logic [63:0] s_data,
    input  logic        s_last,
    input  logic [2:0]  s_nb1,
    input  logic        s_poison,
    output logic        s_ready,
    output logic [63:0] x_d,
    output logic [7:0]  x_c,
    output logic        sop,           // high with the preamble word in x_d
    output logic        eop,           // high with the word that holds the terminate character
    output logic        underrun
);
    import b96_pkg::*;
    typedef enum logic [1:0] {S_IDLE, S_DATA, S_TAIL, S_IFG} state_t;
    state_t       st;
    logic [31:0]  crc;
    logic [63:0]  tail_d;
    logic [7:0]   tail_c;
    logic [1:0]   ifg;
    localparam logic [63:0] IDLE_D = {8{X_IDLE}};
    localparam logic [63:0] PRE_D  = {8'hD5, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, X_START};
    assign s_ready = (st == S_DATA) && adv;

    // last-word construction: n data bytes (1..8), the FCS, the terminate, idles: sixteen bytes, two words. The CRC and the frame end are built for
    // every possible n at once (eight fixed-length steps, shallow) and the right one is selected by s_nb1 (a register): a variable-length CRC step
    // followed by the byte placement was a 15-level path that did not close at 161 MHz.
    logic [31:0]  crc_k [8];
    logic [143:0] fe_k [8];
    logic [31:0]  crc_n;
    logic [143:0] fe;
    for (genvar k = 0; k < 8; k++) begin : g_k
        assign crc_k[k] = crc_upd(crc, s_data, k + 1);
        assign fe_k[k]  = frame_end(s_data, k + 1, s_poison ? crc_k[k] : ~crc_k[k]);
    end
    assign crc_n = s_last ? crc_k[s_nb1] : crc_k[7];
    assign fe    = fe_k[s_nb1];
    int           n;
    assign n = int'(s_nb1) + 1;
    logic [127:0] vm;
    logic [15:0]  cv;
    assign vm = fe[127:0];
    assign cv = fe[143:128];
    always_ff @(posedge clk) begin
        sop <= 1'b0; eop <= 1'b0; underrun <= 1'b0;
        if (rst) begin
            st <= S_IDLE; crc <= '1; x_d <= IDLE_D; x_c <= 8'hFF; tail_d <= IDLE_D; tail_c <= 8'hFF; ifg <= '0;
        end else if (adv) begin
            case (st)
                S_IDLE: begin
                    x_d <= IDLE_D; x_c <= 8'hFF;
                    if (s_valid) begin x_d <= PRE_D; x_c <= 8'h01; sop <= 1'b1; crc <= '1; st <= S_DATA; end
                end
                S_DATA: begin
                    if (!s_valid) begin           // the source must not stall inside a frame
                        underrun <= 1'b1; x_d <= {8{X_ERR}}; x_c <= 8'hFF; st <= S_IFG; ifg <= 2'd1;
                    end else if (!s_last) begin
                        x_d <= s_data; x_c <= 8'h00; crc <= crc_n;
                    end else begin
                        x_d <= vm[63:0]; x_c <= cv[7:0];
                        tail_d <= vm[127:64]; tail_c <= cv[15:8];
                        if (n + 4 >= 8) begin
                            st <= S_TAIL;
                            ifg <= (n + 4 - 8 > 4) ? 2'd2 : 2'd1;
                        end else begin
                            eop <= 1'b1; st <= S_IFG;
                            ifg <= (n + 4 > 4) ? 2'd2 : 2'd1;
                        end
                    end
                end
                S_TAIL: begin
                    x_d <= tail_d; x_c <= tail_c; eop <= 1'b1; st <= S_IFG;
                end
                S_IFG: begin
                    x_d <= IDLE_D; x_c <= 8'hFF;
                    if (ifg <= 2'd1) st <= S_IDLE;
                    ifg <= ifg - 2'd1;
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule

// mac64_rx.sv: 10 Gb/s Ethernet MAC receiver on the PCS's decoded XGMII words (brief 96), cut-through.
//
// Frames start in lane 0 (start block 0x78) or lane 4 (0x33) and end with a terminate in any lane. The preamble is consumed here; data
// words (the destination address first) leave one clock after the word that carries them, byte-aligned to lane 0 whatever the start
// lane. The last bytes of a frame are its FCS: the MAC cannot know that until the terminate arrives, so it forwards every byte and
// reports the verdict at the end: m_end with the frame length (bytes, FCS included) and m_fcs_ok (the CRC residue). A frame cut by an
// error character or a second start is reported with m_err. Registers on the path: m_v/m_d/m_sof (the word), crc, the length.
// Brief 169 (EARLY = 1): the aligned word that the output register m_v/m_d/m_sof loads is also offered one clock earlier as e_v/e_d/e_sof (combinational, the
// registers' own D inputs); trade64 with EARLY = 1 decides on it. With EARLY = 0 (the default) e_* are tied low and everything else is the base file, byte for byte.
module mac64_rx #(
    parameter bit EARLY = 1'b0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        lock_i,     // PCS block lock; a frame in progress is aborted when it drops
    input  logic        x_v,
    input  logic [63:0] x_d,
    input  logic [7:0]  x_c,
    output logic        m_v,        // a data word (8 bytes, except in the word before m_end, which m_nb counts)
    output logic [63:0] m_d,
    output logic        m_sof,      // first word of a frame
    output logic [3:0]  m_nb,       // valid bytes in this word (1..8)
    output logic        m_end,      // frame finished (one clock after its last word); m_fcs_ok, m_len valid
    output logic        m_fcs_ok,
    output logic [15:0] m_len,
    output logic        m_err,      // frame aborted
    output logic        rx_sop,     // the start block was seen (pulse, with the clock the block leaves the PCS)
    output logic        e_v,        // brief 169: the word m_v/m_d/m_sof will hold after this edge (EARLY = 1 only; 0 otherwise)
    output logic [63:0] e_d,
    output logic        e_sof
);
    import b96_pkg::*;
    typedef enum logic [1:0] {R_IDLE, R_FRAME, R_FLUSH} rstate_t;
    rstate_t     st;
    logic        s4;               // frame started in lane 4
    logic        first;            // next word is the first of the frame (only used for s4: no data word yet)
    logic        any;              // a data word was already sent
    logic [31:0] crc;
    logic [31:0] hold;
    logic [15:0] len;
    logic [63:0] fl_d;             // the flush word (lane-4 starts with terminate in lanes 5-7)
    logic [3:0]  fl_nb;
    logic        end_pend;
    logic [31:0] crc_pend;
    logic [15:0] len_pend;
    logic [31:0] crc_w;
    logic [63:0] aw;               // the aligned word under construction
    int          nbi, tk;
    logic        is_term, is_data, is_start0, is_start4;
    logic [3:0]  tl;
    assign tl        = term_lane(x_d, x_c);
    assign is_term   = tl[3];
    assign tk        = int'(tl[2:0]);
    assign is_data   = (x_c == 8'h00);
    assign is_start0 = (x_c == 8'h01) && (x_d[7:0] == X_START);
    assign is_start4 = (x_c == 8'h1F) && (x_d[39:32] == X_START);
    // aligned word: lane-0 starts pass through; lane-4 starts take the previous word's upper half first
    assign aw    = s4 ? {x_d[31:0], hold} : x_d;
    assign nbi   = is_term ? (s4 ? 4 + ((tk > 4) ? 4 : tk) : tk) : 8;
    assign crc_w = crc_upd(crc, aw, 8);          // data words are always full: a fixed-length CRC step (the variable-length last word is staged below)
    // the last word's CRC (variable byte count) is computed one clock later from registers, so the receive clock closes at 161 MHz
    logic [31:0] t_crc; logic [63:0] t_aw; int t_nb; logic [15:0] t_len; logic t_v, t_last;
    logic [63:0] t2_aw; logic [3:0] t2_nb; logic t2_v;
    // the registers' D inputs (m_v, m_d, m_sof) as combinational values: the same conditions as the case below
    always_comb begin
        e_v = 1'b0; e_d = aw; e_sof = !any;
        if (EARLY && !rst && !(!lock_i && st != R_IDLE)) begin
            case (st)
                R_FRAME: if (x_v) begin
                    if (is_data) begin
                        if (!(s4 && first)) e_v = 1'b1;
                    end else if (is_term) begin
                        if (!(s4 && first) && nbi > 0) e_v = 1'b1;
                    end
                end
                R_FLUSH: begin e_v = 1'b1; e_d = fl_d; e_sof = 1'b0; end
                default: ;
            endcase
        end
    end
`ifndef SYNTHESIS
    // simulation check (EARLY = 1): the registers always hold what the early word said one clock before
    logic        eq_v; logic [63:0] eq_d; logic eq_sof;
    always @(posedge clk) begin
        eq_v <= e_v; eq_d <= e_d; eq_sof <= e_sof;
        if (EARLY && !rst && (m_v !== eq_v || (m_v && (m_d !== eq_d || m_sof !== eq_sof)))) $display("EARLY MISMATCH at %0t: m_v %b e_v %b", $time, m_v, eq_v);
    end
`endif
    always_ff @(posedge clk) begin
        m_v <= 1'b0; m_sof <= 1'b0; m_end <= 1'b0; m_err <= 1'b0; rx_sop <= 1'b0;
        if (rst) begin
            st <= R_IDLE; crc <= '1; len <= '0; s4 <= 1'b0; first <= 1'b0; any <= 1'b0; hold <= '0; m_d <= '0; m_nb <= '0;
            m_fcs_ok <= 1'b0; m_len <= '0; end_pend <= 1'b0; crc_pend <= '0; len_pend <= '0; fl_d <= '0; fl_nb <= '0;
            t_v <= 1'b0; t_last <= 1'b0; t2_v <= 1'b0; t_crc <= '0; t_aw <= '0; t_nb <= 0; t_len <= '0; t2_aw <= '0; t2_nb <= '0;
        end else if (!lock_i && st != R_IDLE) begin
            st <= R_IDLE; m_err <= 1'b1; end_pend <= 1'b0; t_v <= 1'b0; t2_v <= 1'b0;
        end else begin
            t_v <= 1'b0; t2_v <= 1'b0;
            if (t_v) begin crc_pend <= crc_upd(t_crc, t_aw, t_nb); len_pend <= t_len; end_pend <= t_last; end
            if (t2_v) begin crc_pend <= crc_upd(crc_pend, t2_aw, int'(t2_nb)); len_pend <= len_pend + 16'(t2_nb); end_pend <= 1'b1; end
            if (end_pend) begin end_pend <= 1'b0; m_end <= 1'b1; m_fcs_ok <= (crc_pend == CRC_RESIDUE); m_len <= len_pend; end
            case (st)
                R_IDLE: if (x_v) begin
                    if (is_start0 || is_start4) begin
                        st <= R_FRAME; s4 <= is_start4; first <= 1'b1; any <= 1'b0; crc <= '1; len <= '0; rx_sop <= 1'b1;
                        hold <= '0;
                    end
                end
                R_FRAME: if (x_v) begin
                    if (is_data) begin
                        if (s4 && first) begin
                            first <= 1'b0; hold <= x_d[63:32];                    // preamble tail in lanes 0-3; data starts in lane 4
                        end else begin
                            m_v <= 1'b1; m_d <= aw; m_nb <= 4'd8; m_sof <= !any; any <= 1'b1;
                            crc <= crc_w; len <= len + 16'd8; first <= 1'b0; hold <= x_d[63:32];
                        end
                    end else if (is_term) begin
                        if (s4 && first) begin                                     // a frame with no data: not valid
                            st <= R_IDLE; m_err <= 1'b1;
                        end else begin
                            if (nbi > 0) begin
                                m_v <= 1'b1; m_d <= aw; m_nb <= 4'(nbi); m_sof <= !any;
                            end
                            any <= 1'b1;
                            t_v <= 1'b1; t_crc <= crc; t_aw <= aw; t_nb <= (s4 && tk > 4) ? 8 : nbi; t_len <= len + 16'((s4 && tk > 4) ? 8 : nbi); t_last <= !(s4 && tk > 4);
                            if (s4 && tk > 4) begin                                // bytes 4..tk-1 of this word are still to go
                                st <= R_FLUSH; fl_d <= {32'd0, x_d[63:32]}; fl_nb <= 4'(tk - 4);
                            end else st <= R_IDLE;
                        end
                    end else begin                                                 // an error character, a second start, or an ordered set
                        st <= R_IDLE; m_err <= 1'b1;
                    end
                end
                R_FLUSH: begin
                    // one more word with the bytes after lane 4; the CRC and length updates of the main word are folded in here
                    m_v <= 1'b1; m_d <= fl_d; m_nb <= fl_nb; t2_v <= 1'b1; t2_aw <= fl_d; t2_nb <= fl_nb; st <= R_IDLE;
                end
                default: st <= R_IDLE;
            endcase
        end
    end
endmodule

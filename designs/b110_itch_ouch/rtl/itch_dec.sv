// itch_dec.sv: Nasdaq TotalView-ITCH 5.0 message decoder (brief 110).
//
// Takes a message from mold_rx (raw word slots and the byte offset of its first byte), aligns it, and gives one registered event per message the
// book needs: Add Order (A), Add Order with MPID (F), Order Executed (E), Order Executed with Price (C), Order Cancel (X), Order Delete (D),
// Order Replace (U), System Event (S), Stock Directory (R). Every other type is skipped by its Mold length (counted). A known type whose length
// is not the specified one is dropped and counted as malformed, as are an Add with a side other than B or S and any A, F, E, C, X, U with zero shares.
// Only the first 36 bytes of a message are kept (the MPID of F and the tail of R are not used). Latency: the event is visible two clocks after the
// last byte of the message was presented to mold_rx (one for mold_rx's output register, one here).
module itch_dec (
    input  logic          clk,
    input  logic          rst,
    input  logic          clr_cnt,
    input  logic          m_v,
    input  logic [383:0]  m_w,
    input  logic [2:0]    m_off,
    input  logic [15:0]   m_len,
    input  logic [31:0]   m_seq,
    output logic          e_v,
    output logic [2:0]    e_k,        // K_ADD .. K_SYS below
    output logic [15:0]   e_loc,
    output logic [63:0]   e_ref,
    output logic [63:0]   e_nref,
    output logic          e_sell,
    output logic [31:0]   e_sh,
    output logic [31:0]   e_px,
    output logic [63:0]   e_stock,
    output logic [7:0]    e_code,
    output logic [31:0]   e_seq,
    output logic [11*32-1:0] cnt      // m_a m_f m_e m_c m_x m_d m_u m_s m_r m_skip m_bad
);
    localparam logic [2:0] K_ADD = 3'd0, K_EXE = 3'd1, K_CAN = 3'd2, K_DEL = 3'd3, K_REP = 3'd4, K_DIR = 3'd5, K_SYS = 3'd6;

    logic [383:0] al;
    assign al = m_w >> {m_off, 3'b000};

    function automatic logic [63:0] be(input logic [383:0] a, input int o, input int n);
        logic [63:0] r;
        r = '0;
        for (int i = 0; i < n; i++) r = {r[55:0], a[8 * (o + i) +: 8]};
        return r;
    endfunction
    function automatic logic [31:0] be32(input logic [383:0] a, input int o);
        logic [31:0] r;
        r = '0;
        for (int i = 0; i < 4; i++) r = {r[23:0], a[8 * (o + i) +: 8]};
        return r;
    endfunction
    function automatic logic [15:0] be16(input logic [383:0] a, input int o);
        return {a[8 * o +: 8], a[8 * (o + 1) +: 8]};
    endfunction

    logic [7:0]  ty;
    logic [15:0] f_loc;
    logic [63:0] f_ref, f_nref, f_stk24, f_stk11;
    logic [31:0] f_sh20, f_sh19, f_sh27, f_px32, f_px31;
    logic        known, len_ok, field_ok;
    logic [2:0]  kind;
    assign ty = al[7:0];

    always_comb begin
        f_loc = be16(al, 1);    f_ref = be(al, 11, 8);  f_nref = be(al, 19, 8);
        f_sh20 = be32(al, 20);  f_sh19 = be32(al, 19);  f_sh27 = be32(al, 27);
        f_px32 = be32(al, 32);  f_px31 = be32(al, 31);  f_stk24 = be(al, 24, 8); f_stk11 = be(al, 11, 8);
    end

    always_comb begin
        known = 1'b1; len_ok = 1'b0; kind = K_ADD; field_ok = 1'b1;
        case (ty)
            "A": begin len_ok = (m_len == 16'd36); kind = K_ADD; end
            "F": begin len_ok = (m_len == 16'd40); kind = K_ADD; end
            "E": begin len_ok = (m_len == 16'd31); kind = K_EXE; end
            "C": begin len_ok = (m_len == 16'd36); kind = K_EXE; end
            "X": begin len_ok = (m_len == 16'd23); kind = K_CAN; end
            "D": begin len_ok = (m_len == 16'd19); kind = K_DEL; end
            "U": begin len_ok = (m_len == 16'd35); kind = K_REP; end
            "S": begin len_ok = (m_len == 16'd12); kind = K_SYS; end
            "R": begin len_ok = (m_len == 16'd39); kind = K_DIR; end
            default: known = 1'b0;
        endcase
        case (kind)
            K_ADD: field_ok = (al[8*19 +: 8] == "B" || al[8*19 +: 8] == "S") && (f_sh20 != 32'd0);
            K_EXE, K_CAN: field_ok = (f_sh19 != 32'd0);
            K_REP: field_ok = (f_sh27 != 32'd0);
            default: field_ok = 1'b1;
        endcase
    end

    logic [31:0] c_a, c_f, c_e, c_c, c_x, c_d, c_u, c_s, c_r, c_skip, c_bad;
    assign cnt = {c_bad, c_skip, c_r, c_s, c_u, c_d, c_x, c_c, c_e, c_f, c_a};

    always_ff @(posedge clk) begin
        e_v <= 1'b0;
        if (rst) begin
            c_a <= '0; c_f <= '0; c_e <= '0; c_c <= '0; c_x <= '0; c_d <= '0; c_u <= '0; c_s <= '0; c_r <= '0; c_skip <= '0; c_bad <= '0;
            e_k <= '0; e_loc <= '0; e_ref <= '0; e_nref <= '0; e_sell <= 1'b0; e_sh <= '0; e_px <= '0; e_stock <= '0; e_code <= '0; e_seq <= '0;
        end else begin
            if (m_v) begin
                if (!known) c_skip <= c_skip + 32'd1;
                else if (!len_ok) c_bad <= c_bad + 32'd1;
                else begin
                    case (ty)
                        "A": c_a <= c_a + 32'd1;
                        "F": c_f <= c_f + 32'd1;
                        "E": c_e <= c_e + 32'd1;
                        "C": c_c <= c_c + 32'd1;
                        "X": c_x <= c_x + 32'd1;
                        "D": c_d <= c_d + 32'd1;
                        "U": c_u <= c_u + 32'd1;
                        "S": c_s <= c_s + 32'd1;
                        default: c_r <= c_r + 32'd1;
                    endcase
                    if (!field_ok) c_bad <= c_bad + 32'd1;
                    else e_v <= 1'b1;
                end
                e_k     <= kind;
                e_loc   <= f_loc;
                e_seq   <= m_seq;
                e_code  <= al[8*11 +: 8];
                e_stock <= (kind == K_DIR) ? f_stk11 : f_stk24;
                e_sell  <= (al[8*19 +: 8] == "S");
                case (kind)
                    K_ADD: begin e_ref <= f_ref; e_nref <= '0; e_sh <= f_sh20; e_px <= f_px32; end
                    K_EXE, K_CAN: begin e_ref <= f_ref; e_nref <= '0; e_sh <= f_sh19; e_px <= '0; end
                    K_REP: begin e_ref <= f_ref; e_nref <= f_nref; e_sh <= f_sh27; e_px <= f_px31; end
                    default: begin e_ref <= f_ref; e_nref <= '0; e_sh <= '0; e_px <= '0; end
                endcase
            end
            if (clr_cnt) begin
                c_a <= '0; c_f <= '0; c_e <= '0; c_c <= '0; c_x <= '0; c_d <= '0; c_u <= '0; c_s <= '0; c_r <= '0; c_skip <= '0; c_bad <= '0;
            end
        end
    end
endmodule

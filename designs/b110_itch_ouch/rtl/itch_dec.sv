// itch_dec.sv: Nasdaq TotalView-ITCH 5.0 message decoder (brief 110).
//
// Takes a message from mold_rx (raw word slots and the byte offset of its first byte), aligns it, and gives one registered event per message the
// book needs: Add Order (A), Add Order with MPID (F), Order Executed (E), Order Executed with Price (C), Order Cancel (X), Order Delete (D),
// Order Replace (U), System Event (S), Stock Directory (R). Every other type is skipped by its Mold length (counted). A known type whose length
// is not the specified one is dropped and counted as malformed, as are an Add with a side other than B or S and any A, F, E, C, X, U with zero shares.
// Only the first 36 bytes of a message are kept (the MPID of F and the tail of R are not used). Latency: the event is visible two clocks after the
// last byte of the message was presented to mold_rx (one for mold_rx's output register, one here).
// PARSE_INPLACE (brief 191; idea from Edwards 2026, ch 12 and 13, built from scratch): 0 = the message is first shifted down by its start byte (a 384 bit
// barrel shifter, then the type test and the field extraction); 1 = the message is parsed where it lies: eight copies of the same field decoder
// (the function `decode`) each read the message with its start byte fixed (a constant shift is wiring, not logic), all eight run at once, and m_off only
// selects which copy's result is registered. Same events, counters and latency (both register the event one clock after m_v); they differ in logic depth
// and area (results/191_trading_variants/parse_inplace.md).
module itch_dec #(
    parameter int PARSE_INPLACE = 0   // 0 shift then decode; 1 eight fixed-lane decoders, m_off selects (brief 191)
) (
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

    // ------------------------------------------------------------------ the combinational half: the type test and the event fields of one view of the message
    // `a` has the message's first byte in a[7:0]; the result is what will be registered for this message (the same function serves both parse variants).
    localparam logic [2:0] K_ADD = 3'd0, K_EXE = 3'd1, K_CAN = 3'd2, K_DEL = 3'd3, K_REP = 3'd4, K_DIR = 3'd5, K_SYS = 3'd6;
    typedef struct packed {
        logic [7:0]  ty;
        logic        known, len_ok, field_ok;
        logic [2:0]  kind;
        logic [15:0] loc;
        logic [63:0] ref_, nref, stock;
        logic        sell;
        logic [31:0] sh, px;
        logic [7:0]  code;
    } fields_t;

    function automatic logic [63:0] be(input logic [383:0] x, input int o, input int n);
        logic [63:0] r;
        r = '0;
        for (int i = 0; i < n; i++) r = {r[55:0], x[8 * (o + i) +: 8]};
        return r;
    endfunction
    function automatic logic [31:0] be32(input logic [383:0] x, input int o);
        logic [31:0] r;
        r = '0;
        for (int i = 0; i < 4; i++) r = {r[23:0], x[8 * (o + i) +: 8]};
        return r;
    endfunction
    function automatic logic [15:0] be16(input logic [383:0] x, input int o);
        return {x[8 * o +: 8], x[8 * (o + 1) +: 8]};
    endfunction

    function automatic fields_t decode(input logic [383:0] a, input logic [15:0] ml);
        fields_t f;
        logic [31:0] sh20, sh19, sh27, px32, px31;
        sh20 = be32(a, 20); sh19 = be32(a, 19); sh27 = be32(a, 27); px32 = be32(a, 32); px31 = be32(a, 31);
        f = '0;
        f.ty = a[7:0];
        f.known = 1'b1; f.len_ok = 1'b0; f.kind = K_ADD; f.field_ok = 1'b1;
        case (f.ty)
            "A": begin f.len_ok = (ml == 16'd36); f.kind = K_ADD; end
            "F": begin f.len_ok = (ml == 16'd40); f.kind = K_ADD; end
            "E": begin f.len_ok = (ml == 16'd31); f.kind = K_EXE; end
            "C": begin f.len_ok = (ml == 16'd36); f.kind = K_EXE; end
            "X": begin f.len_ok = (ml == 16'd23); f.kind = K_CAN; end
            "D": begin f.len_ok = (ml == 16'd19); f.kind = K_DEL; end
            "U": begin f.len_ok = (ml == 16'd35); f.kind = K_REP; end
            "S": begin f.len_ok = (ml == 16'd12); f.kind = K_SYS; end
            "R": begin f.len_ok = (ml == 16'd39); f.kind = K_DIR; end
            default: f.known = 1'b0;
        endcase
        case (f.kind)
            K_ADD: f.field_ok = (a[8*19 +: 8] == "B" || a[8*19 +: 8] == "S") && (sh20 != 32'd0);
            K_EXE, K_CAN: f.field_ok = (sh19 != 32'd0);
            K_REP: f.field_ok = (sh27 != 32'd0);
            default: f.field_ok = 1'b1;
        endcase
        f.loc   = be16(a, 1);
        f.code  = a[8*11 +: 8];
        f.stock = (f.kind == K_DIR) ? be(a, 11, 8) : be(a, 24, 8);
        f.sell  = (a[8*19 +: 8] == "S");
        f.ref_  = be(a, 11, 8);
        case (f.kind)
            K_ADD: begin f.nref = '0; f.sh = sh20; f.px = px32; end
            K_EXE, K_CAN: begin f.nref = '0; f.sh = sh19; f.px = '0; end
            K_REP: begin f.nref = be(a, 19, 8); f.sh = sh27; f.px = px31; end
            default: begin f.nref = '0; f.sh = '0; f.px = '0; end
        endcase
        return f;
    endfunction
    fields_t     fv;                              // the fields of the message as decoded (by either variant)
    if (PARSE_INPLACE != 0) begin : g_inplace
        fields_t lane [8];
        for (genvar l = 0; l < 8; l++) begin : g_lane
            logic [383:0] a;
            assign a = m_w >> (8 * l);               // constant shift: wiring only
            assign lane[l] = decode(a, m_len);
        end
        assign fv = lane[m_off];
    end else begin : g_shift
        logic [383:0] al;
        assign al = m_w >> {m_off, 3'b000};
        assign fv = decode(al, m_len);
    end
    logic [7:0]  ty;
    logic        known, len_ok, field_ok;
    logic [2:0]  kind;
    assign ty = fv.ty; assign known = fv.known; assign len_ok = fv.len_ok; assign field_ok = fv.field_ok; assign kind = fv.kind;

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
                e_loc   <= fv.loc;
                e_seq   <= m_seq;
                e_code  <= fv.code;
                e_stock <= fv.stock;
                e_sell  <= fv.sell;
                e_ref   <= fv.ref_;
                e_nref  <= fv.nref;
                e_sh    <= fv.sh;
                e_px    <= fv.px;
            end
            if (clr_cnt) begin
                c_a <= '0; c_f <= '0; c_e <= '0; c_c <= '0; c_x <= '0; c_d <= '0; c_u <= '0; c_s <= '0; c_r <= '0; c_skip <= '0; c_bad <= '0;
            end
        end
    end
endmodule

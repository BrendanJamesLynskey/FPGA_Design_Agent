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
// (module itch_fields) each read the message with its start byte fixed (a constant shift is wiring, not logic), all eight run at once, and m_off only
// selects which copy's result is registered. Same events, counters and latency (both register the event one clock after m_v); they differ in logic depth
// and area (results/191_trading_variants/parse_inplace.md).
// itch_fields: the combinational half of the decoder for one view of the message: `a` has the message's first byte in a[7:0].
// Gives the type test (known, len_ok, field_ok, kind) and the event fields as they will be registered.
module itch_fields (
    input  logic [383:0] a,
    input  logic [15:0]  m_len,
    output logic [7:0]   ty,
    output logic         known, len_ok, field_ok,
    output logic [2:0]   kind,
    output logic [15:0]  e_loc,
    output logic [63:0]  e_ref, e_nref, e_stock,
    output logic         e_sell,
    output logic [31:0]  e_sh, e_px,
    output logic [7:0]   e_code
);
    localparam logic [2:0] K_ADD = 3'd0, K_EXE = 3'd1, K_CAN = 3'd2, K_DEL = 3'd3, K_REP = 3'd4, K_DIR = 3'd5, K_SYS = 3'd6;

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

    logic [15:0] f_loc;
    logic [63:0] f_ref, f_nref, f_stk24, f_stk11;
    logic [31:0] f_sh20, f_sh19, f_sh27, f_px32, f_px31;
    assign ty = a[7:0];

    always_comb begin
        f_loc = be16(a, 1);    f_ref = be(a, 11, 8);  f_nref = be(a, 19, 8);
        f_sh20 = be32(a, 20);  f_sh19 = be32(a, 19);  f_sh27 = be32(a, 27);
        f_px32 = be32(a, 32);  f_px31 = be32(a, 31);  f_stk24 = be(a, 24, 8); f_stk11 = be(a, 11, 8);
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
            K_ADD: field_ok = (a[8*19 +: 8] == "B" || a[8*19 +: 8] == "S") && (f_sh20 != 32'd0);
            K_EXE, K_CAN: field_ok = (f_sh19 != 32'd0);
            K_REP: field_ok = (f_sh27 != 32'd0);
            default: field_ok = 1'b1;
        endcase
    end

    always_comb begin
        e_loc   = f_loc;
        e_code  = a[8*11 +: 8];
        e_stock = (kind == K_DIR) ? f_stk11 : f_stk24;
        e_sell  = (a[8*19 +: 8] == "S");
        case (kind)
            K_ADD: begin e_ref = f_ref; e_nref = '0; e_sh = f_sh20; e_px = f_px32; end
            K_EXE, K_CAN: begin e_ref = f_ref; e_nref = '0; e_sh = f_sh19; e_px = '0; end
            K_REP: begin e_ref = f_ref; e_nref = f_nref; e_sh = f_sh27; e_px = f_px31; end
            default: begin e_ref = f_ref; e_nref = '0; e_sh = '0; e_px = '0; end
        endcase
    end
endmodule

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
    logic [7:0]  ty;
    logic        known, len_ok, field_ok;
    logic [2:0]  kind;
    logic [15:0] n_loc;
    logic [63:0] n_ref, n_nref, n_stock;
    logic        n_sell;
    logic [31:0] n_sh, n_px;
    logic [7:0]  n_code;

    if (PARSE_INPLACE) begin : g_inplace
        logic [7:0]  l_ty   [8];
        logic        l_known [8], l_len_ok [8], l_field_ok [8], l_sell [8];
        logic [2:0]  l_kind [8];
        logic [15:0] l_loc  [8];
        logic [63:0] l_ref  [8], l_nref [8], l_stock [8];
        logic [31:0] l_sh   [8], l_px [8];
        logic [7:0]  l_code [8];
        for (genvar l = 0; l < 8; l++) begin : g_lane
            logic [383:0] a;
            assign a = m_w >> (8 * l);                       // constant shift: wiring only
            itch_fields u_f (.a, .m_len, .ty(l_ty[l]), .known(l_known[l]), .len_ok(l_len_ok[l]), .field_ok(l_field_ok[l]), .kind(l_kind[l]),
                             .e_loc(l_loc[l]), .e_ref(l_ref[l]), .e_nref(l_nref[l]), .e_stock(l_stock[l]), .e_sell(l_sell[l]), .e_sh(l_sh[l]),
                             .e_px(l_px[l]), .e_code(l_code[l]));
        end
        always_comb begin
            ty = l_ty[m_off]; known = l_known[m_off]; len_ok = l_len_ok[m_off]; field_ok = l_field_ok[m_off]; kind = l_kind[m_off];
            n_loc = l_loc[m_off]; n_ref = l_ref[m_off]; n_nref = l_nref[m_off]; n_stock = l_stock[m_off]; n_sell = l_sell[m_off];
            n_sh = l_sh[m_off]; n_px = l_px[m_off]; n_code = l_code[m_off];
        end
    end else begin : g_shift
        logic [383:0] al;
        assign al = m_w >> {m_off, 3'b000};
        itch_fields u_f (.a(al), .m_len, .ty, .known, .len_ok, .field_ok, .kind, .e_loc(n_loc), .e_ref(n_ref), .e_nref(n_nref), .e_stock(n_stock),
                         .e_sell(n_sell), .e_sh(n_sh), .e_px(n_px), .e_code(n_code));
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
                e_loc   <= n_loc;
                e_seq   <= m_seq;
                e_code  <= n_code;
                e_stock <= n_stock;
                e_sell  <= n_sell;
                e_ref   <= n_ref;
                e_nref  <= n_nref;
                e_sh    <= n_sh;
                e_px    <= n_px;
            end
            if (clr_cnt) begin
                c_a <= '0; c_f <= '0; c_e <= '0; c_c <= '0; c_x <= '0; c_d <= '0; c_u <= '0; c_s <= '0; c_r <= '0; c_skip <= '0; c_bad <= '0;
            end
        end
    end
endmodule

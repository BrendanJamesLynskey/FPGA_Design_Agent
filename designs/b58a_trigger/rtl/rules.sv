// rules.sv: the run-time programmable rule table (brief 58A step 4).
//
// NR rules, each six 32-bit words (docs/rule_table.md; the schema is rules/rule_schema.json):
//   w0 control  [0] enable  [4:1] type mask (ADD, MODIFY, CANCEL, TRADE)  [6:5] side (0 any, 1 bid, 2 ask)
//               [7] any instrument  [10:8] compare (0 none, 1 <, 2 <=, 3 >, 4 >=)  [12:11] book condition
//               (0 none, 1 improves its own side, 2 crosses the other side)  [13] send an order  [14] order side
//               (0 buy, 1 sell)  [16:15] order price (0 fixed, 1 message price, 2 message price + offset)
//               [17] raise a pin  [18] which pin  [19] log
//   w1 instrument  w2 price threshold  w3 order quantity  w4 fixed price or signed offset  w5 hold-off clocks
// The host writes a shadow copy (any order, any time); commit copies every rule into the active table in one clock
// and bumps the table version, so a message is always judged against one whole table (no torn updates). The
// version used is reported with each decision: a message judged before a commit used the old ("stale") values.
//
// A decision is taken on msg_px_v (type, side, instrument and price are in): every enabled rule is checked at once
// against the message and the book entry read for it (bk_*), the lowest-numbered match that is not in hold-off fires,
// and fire_v follows one clock later.

module rules #(
    parameter int NR = 8
) (
    input  logic        clk,
    input  logic        rst,
    // host
    input  logic        h_we,
    input  logic [7:0]  h_addr,         // rule * 8 + word (words 0..5)
    input  logic [31:0] h_wdata,
    input  logic        h_commit,
    output logic [15:0] version,
    output logic [31:0] h_rdata,        // the active table, same addressing
    // message at the decision point
    input  logic        msg_px_v,
    input  logic [7:0]  msg_type,
    input  logic        msg_side,
    input  logic [15:0] msg_inst,
    input  logic [31:0] msg_px,
    input  logic        bk_valid,
    input  logic [31:0] bk_bid_px, bk_bid_sz, bk_ask_px, bk_ask_sz,
    // decision
    output logic        fire_v,
    output logic [2:0]  fire_rule,
    output logic [15:0] fire_ver,
    output logic        fire_order,
    output logic        fire_side,
    output logic [31:0] fire_qty,
    output logic [31:0] fire_px,
    output logic [31:0] fire_ref_px,    // the message price (the fat-finger reference)
    output logic [15:0] fire_inst,
    output logic        fire_pin_en,
    output logic        fire_pin_idx,
    output logic        fire_log,
    output logic        ev_holdoff      // a rule matched but was in hold-off and nothing else fired
);
    initial begin
        if (NR < 1 || NR > 8) $error("rules: NR must be in 1..8 (got %0d)", NR);
    end
    logic [31:0] sh   [NR*6];
    logic [31:0] act  [NR*6];
    logic [31:0] hold [NR];

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int j = 0; j < NR*6; j++) begin sh[j] <= '0; act[j] <= '0; end
            version <= '0;
        end else begin
            if (h_we && h_addr[2:0] < 3'd6 && h_addr[7:3] < 5'(NR)) sh[h_addr[7:3]*6 + {2'b00, h_addr[2:0]}] <= h_wdata;
            if (h_commit) begin
                for (int j = 0; j < NR*6; j++) act[j] <= sh[j];
                version <= version + 16'd1;
            end
        end
    end
    always_comb begin
        h_rdata = '0;
        if (h_addr[2:0] < 3'd6 && h_addr[7:3] < 5'(NR)) h_rdata = act[h_addr[7:3]*6 + {2'b00, h_addr[2:0]}];
    end

    // ---- match ----------------------------------------------------------------------------------------------
    logic [NR-1:0] m, free;
    always_comb begin
        for (int r = 0; r < NR; r++) begin
            logic [31:0] c, th;
            logic        tm, sm, im, cm, bm;
            c  = act[r*6];
            th = act[r*6 + 2];
            case (msg_type)
                8'h01:   tm = c[1];
                8'h02:   tm = c[2];
                8'h03:   tm = c[3];
                8'h04:   tm = c[4];
                default: tm = 1'b0;
            endcase
            case (c[6:5])
                2'd1:    sm = !msg_side;
                2'd2:    sm = msg_side;
                default: sm = 1'b1;
            endcase
            im = c[7] || (act[r*6 + 1][15:0] == msg_inst);
            case (c[10:8])
                3'd1:    cm = msg_px <  th;
                3'd2:    cm = msg_px <= th;
                3'd3:    cm = msg_px >  th;
                3'd4:    cm = msg_px >= th;
                default: cm = 1'b1;
            endcase
            case (c[12:11])
                2'd1:    bm = bk_valid && (msg_side ? (bk_ask_sz == 0 || msg_px < bk_ask_px)
                                                    : (bk_bid_sz == 0 || msg_px > bk_bid_px));
                2'd2:    bm = bk_valid && (msg_side ? (bk_bid_sz != 0 && msg_px <= bk_bid_px)
                                                    : (bk_ask_sz != 0 && msg_px >= bk_ask_px));
                default: bm = 1'b1;
            endcase
            m[r]    = c[0] && tm && sm && im && cm && bm;
            free[r] = (hold[r] == 0);
        end
    end
    logic [NR-1:0] cand;
    assign cand = m & free;
    logic [2:0] win;
    always_comb begin
        win = '0;
        for (int r = NR - 1; r >= 0; r--) if (cand[r]) win = 3'(r);
    end

    always_ff @(posedge clk) begin
        fire_v <= 1'b0;
        ev_holdoff <= 1'b0;
        if (rst) begin
            for (int r = 0; r < NR; r++) hold[r] <= '0;
            fire_rule <= '0; fire_ver <= '0; fire_order <= 1'b0; fire_side <= 1'b0; fire_qty <= '0; fire_px <= '0;
            fire_ref_px <= '0; fire_inst <= '0; fire_pin_en <= 1'b0; fire_pin_idx <= 1'b0; fire_log <= 1'b0;
        end else begin
            for (int r = 0; r < NR; r++) if (hold[r] != 0) hold[r] <= hold[r] - 32'd1;
            if (msg_px_v && cand != 0) begin
                logic [31:0] c, pw;
                c  = act[win*6];
                pw = act[win*6 + 4];
                fire_v       <= 1'b1;
                fire_rule    <= win;
                fire_ver     <= version;
                fire_order   <= c[13];
                fire_side    <= c[14];
                fire_qty     <= act[win*6 + 3];
                case (c[16:15])
                    2'd0:    fire_px <= pw;
                    2'd1:    fire_px <= msg_px;
                    default: fire_px <= msg_px + pw;
                endcase
                fire_ref_px  <= msg_px;
                fire_inst    <= msg_inst;
                fire_pin_en  <= c[17];
                fire_pin_idx <= c[18];
                fire_log     <= c[19];
                hold[win]    <= act[win*6 + 5];
            end else if (msg_px_v && m != 0) begin
                ev_holdoff <= 1'b1;
            end
        end
    end
endmodule

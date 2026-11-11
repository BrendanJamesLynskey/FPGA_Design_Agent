// match_lpm.sv: IPv4 longest-prefix match, a multibit trie with strides 8-8-8-8 in block RAM.
//
// Level 0 is the root node (256 entries); level k (1..3) holds Lk_NODES nodes of 256 entries. Entry word:
//   {has_nh, nh[ACT_W-1:0], has_child, child[CW-1:0]}
// has_nh/nh: the longest route that ends inside this node's stride and covers this entry (controlled prefix
// expansion, done by the control plane: flow/net/model.py lpm_compile). Lookup walks one level a stage, keeps the
// last next hop seen, and stops descending where has_child is 0. One lookup a clock; result 10 clocks later (input register, two clocks a level, output register).
//
// Updates are raw word writes on the RAMs' second port (cmd op 1 WRITE, cmd_addr = {level[1:0], index[13:0]},
// cmd_data[ENTRY_W-1:0] = the word), so lookups never stop. The control plane writes new child nodes before the
// parent entry that points to them, so each lookup sees the old or the new route set (make before break).
// Op 2 CLEAR zeroes level 0 (256 clocks): every lookup misses. rsp_status: 0 OK, 3 BAD_OP or address out of range.

module match_lpm #(
    parameter int ACT_W    = 16,             // next-hop / action width
    parameter int L1_NODES = 64,
    parameter int L2_NODES = 64,
    parameter int L3_NODES = 64,
    parameter int TAG_W    = 8
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             lk_valid,
    input  logic [31:0]      lk_key,
    input  logic [TAG_W-1:0] lk_tag,
    output logic             res_valid,
    output logic             res_hit,
    output logic [ACT_W-1:0] res_act,
    output logic [TAG_W-1:0] res_tag,
    input  logic             cmd_valid,
    output logic             cmd_ready,
    input  logic [3:0]       cmd_op,
    input  logic [15:0]      cmd_addr,
    input  logic [511:0]     cmd_data,
    output logic             rsp_valid,
    output logic [3:0]       rsp_status
);
    initial begin
        if (ACT_W < 1 || ACT_W > 64) $error("match_lpm: ACT_W must be in 1..64 (got %0d)", ACT_W);
        if (L1_NODES < 1 || L1_NODES > 64) $error("match_lpm: L1_NODES must be in 1..64 (got %0d)", L1_NODES);
        if (L2_NODES < 1 || L2_NODES > 64) $error("match_lpm: L2_NODES must be in 1..64 (got %0d)", L2_NODES);
        if (L3_NODES < 1 || L3_NODES > 64) $error("match_lpm: L3_NODES must be in 1..64 (got %0d)", L3_NODES);
        if (TAG_W < 1 || TAG_W > 64) $error("match_lpm: TAG_W must be in 1..64 (got %0d)", TAG_W);
    end

    localparam int CW = 6;                    // child pointer width (64 nodes a level at most)
    localparam int EW = 2 + ACT_W + CW;
    localparam int D1 = L1_NODES * 256, D2 = L2_NODES * 256, D3 = L3_NODES * 256;

    (* ram_style = "block" *) logic [EW-1:0] m0 [0:255];
    (* ram_style = "block" *) logic [EW-1:0] m1 [0:D1-1];
    (* ram_style = "block" *) logic [EW-1:0] m2 [0:D2-1];
    (* ram_style = "block" *) logic [EW-1:0] m3 [0:D3-1];
    initial begin
        for (int i = 0; i < 256; i++) m0[i] = '0;
        for (int i = 0; i < D1; i++) m1[i] = '0;
        for (int i = 0; i < D2; i++) m2[i] = '0;
        for (int i = 0; i < D3; i++) m3[i] = '0;
    end

    // ---- command port (write-only port B) ------------------------------------------------------------------
    logic [1:0]  wl;
    logic [13:0] wa;
    logic [EW-1:0] wd;
    logic        we, clearing;
    logic [7:0]  clr;
    always_ff @(posedge clk) begin
        if (we && wl == 2'd0) m0[wa[7:0]] <= wd;
        if (we && wl == 2'd1) m1[wa] <= wd;
        if (we && wl == 2'd2) m2[wa] <= wd;
        if (we && wl == 2'd3) m3[wa] <= wd;
    end

    assign cmd_ready = !clearing;
    always_ff @(posedge clk) begin
        we <= 1'b0; rsp_valid <= 1'b0;
        if (rst) begin
            clearing <= 1'b0; clr <= '0; wl <= '0; wa <= '0; wd <= '0; rsp_status <= '0;
        end else if (clearing) begin
            we <= 1'b1; wl <= 2'd0; wa <= {6'd0, clr}; wd <= '0; clr <= clr + 8'd1;
            if (clr == 8'd255) begin clearing <= 1'b0; rsp_valid <= 1'b1; rsp_status <= 4'd0; end
        end else if (cmd_valid) begin
            if (cmd_op == 4'd1) begin
                wl <= cmd_addr[15:14]; wa <= cmd_addr[13:0]; wd <= cmd_data[EW-1:0];
                rsp_valid <= 1'b1;
                case (cmd_addr[15:14])
                    2'd0: begin we <= (cmd_addr[13:8] == 6'd0);         rsp_status <= (cmd_addr[13:8] == 6'd0) ? 4'd0 : 4'd3; end
                    2'd1: begin we <= (int'(cmd_addr[13:0]) < D1);     rsp_status <= (int'(cmd_addr[13:0]) < D1) ? 4'd0 : 4'd3; end
                    2'd2: begin we <= (int'(cmd_addr[13:0]) < D2);     rsp_status <= (int'(cmd_addr[13:0]) < D2) ? 4'd0 : 4'd3; end
                    default: begin we <= (int'(cmd_addr[13:0]) < D3);  rsp_status <= (int'(cmd_addr[13:0]) < D3) ? 4'd0 : 4'd3; end
                endcase
            end else if (cmd_op == 4'd2) begin
                clearing <= 1'b1; clr <= '0;
            end else begin
                rsp_valid <= 1'b1; rsp_status <= 4'd3;
            end
        end
    end

    // ---- lookup pipeline ----------------------------------------------------------------------------------
    // Stage s (0..3) takes two clocks: the address register (k, ch -> ad), then the RAM word (q). Carried along:
    // key, tag, valid, still-descending, best next hop so far.
    logic [31:0]      k  [0:4], k2 [0:3];
    logic [TAG_W-1:0] t  [0:4], t2 [0:3];
    logic             v  [0:4], v2 [0:3];
    logic             go [0:4], go2 [0:3];
    logic             bh [0:4], bh2 [0:3];
    logic [ACT_W-1:0] bn [0:4], bn2 [0:3];
    logic [CW-1:0]    ch [0:3];               // node index into level s (ch[0] unused: the root)
    logic [13:0]      ad [0:3];
    logic [EW-1:0]    q  [0:3];

    always_comb begin
        ad[0] = {6'd0, k[0][31:24]};
        ad[1] = {ch[1], k[1][23:16]};
        ad[2] = {ch[2], k[2][15:8]};
        ad[3] = {ch[3], k[3][7:0]};
    end

    always_ff @(posedge clk) q[0] <= m0[ad[0][7:0]];
    always_ff @(posedge clk) q[1] <= m1[ad[1]];
    always_ff @(posedge clk) q[2] <= m2[ad[2]];
    always_ff @(posedge clk) q[3] <= m3[ad[3]];

    always_ff @(posedge clk) begin
        // input register
        k[0] <= lk_key; t[0] <= lk_tag; go[0] <= 1'b1; bh[0] <= 1'b0; bn[0] <= '0; ch[0] <= '0;
        for (int s = 0; s < 4; s++) begin
            // first clock of stage s: the address is presented, the rest waits for the word
            k2[s] <= k[s]; t2[s] <= t[s]; go2[s] <= go[s]; bh2[s] <= bh[s]; bn2[s] <= bn[s];
            // second clock: the word is here
            k[s + 1] <= k2[s]; t[s + 1] <= t2[s];
            if (go2[s] && q[s][EW-1]) begin bh[s + 1] <= 1'b1; bn[s + 1] <= q[s][EW-2 -: ACT_W]; end
            else                      begin bh[s + 1] <= bh2[s]; bn[s + 1] <= bn2[s]; end
            go[s + 1] <= go2[s] && q[s][CW];
            if (s < 3) ch[s + 1] <= q[s][CW-1:0];
        end
        res_tag <= t[4]; res_hit <= bh[4]; res_act <= bn[4];
        if (rst) begin
            for (int s = 0; s < 5; s++) v[s] <= 1'b0;
            for (int s = 0; s < 4; s++) v2[s] <= 1'b0;
            res_valid <= 1'b0;
        end else begin
            v[0] <= lk_valid;
            for (int s = 0; s < 4; s++) begin v2[s] <= v[s]; v[s + 1] <= v2[s]; end
            res_valid <= v[4];
        end
    end
endmodule

// match_ternary.sv: ternary match (TCAM emulation) in distributed RAM, ENTRIES rules, lowest index wins.
//
// The key is cut into NCH = KEY_W / CHUNK_W chunks. For chunk c and entry e, a 2**CHUNK_W x 1 LUT RAM holds, at address
// a, whether rule e accepts the value a in that chunk: ((a ^ value_c) & care_c) == 0. A lookup reads every chunk RAM at
// its chunk of the key (one LUT RAM read each), ANDs the NCH match vectors with the valid vector, and a priority
// encoder picks the lowest matching index; its action comes from a small action RAM. One lookup a clock; result
// 4 clocks later.
//
// Commands (cmd_addr = entry index; cmd_data: value in [KEY_W-1:0], care mask in [128 +: KEY_W] (1 = compare this
// bit), action in [256 +: ACT_W]):
//   1 WRITE   the entry is made invalid, its 2**CHUNK_W column addresses are rewritten (one a clock, all chunks at
//             once), then it is made valid: 2**CHUNK_W + 3 clocks. Lookups continue; during the rewrite the rule is
//             absent (neither the old nor the new one matches). For make-before-break, write the new rule into a
//             free entry first, then delete the old one.
//   2 DELETE  invalid at once.
// rsp_status: 0 OK, 3 BAD_OP or entry out of range.

module match_ternary #(
    parameter int KEY_W   = 40,
    parameter int ACT_W   = 16,
    parameter int ENTRIES = 32,
    parameter int CHUNK_W = 5,               // 5 (RAM32X1) or 6 (RAM64X1) suit 7-series and UltraScale+ LUT RAM
    parameter int TAG_W   = 8
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             lk_valid,
    input  logic [KEY_W-1:0] lk_key,
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
        if (KEY_W < 1 || KEY_W > 128) $error("match_ternary: KEY_W must be in 1..128 (got %0d)", KEY_W);
        if (CHUNK_W < 2 || CHUNK_W > 8) $error("match_ternary: CHUNK_W must be in 2..8 (got %0d)", CHUNK_W);
        if (KEY_W % CHUNK_W != 0) $error("match_ternary: KEY_W (%0d) must be a multiple of CHUNK_W (%0d)", KEY_W, CHUNK_W);
        if (ENTRIES < 1 || ENTRIES > 256) $error("match_ternary: ENTRIES must be in 1..256 (got %0d)", ENTRIES);
        if (ACT_W < 1 || ACT_W > 128) $error("match_ternary: ACT_W must be in 1..128 (got %0d)", ACT_W);
        if (TAG_W < 1 || TAG_W > 64) $error("match_ternary: TAG_W must be in 1..64 (got %0d)", TAG_W);
    end

    localparam int NCH = (KEY_W + CHUNK_W - 1) / CHUNK_W;
    localparam int DEPTH = 1 << CHUNK_W;
    localparam int EI_W = (ENTRIES > 1) ? $clog2(ENTRIES) : 1;

    (* ram_style = "distributed" *) logic [ACT_W-1:0] act_ram [0:ENTRIES-1];
    logic [ENTRIES-1:0] valid;
    initial for (int i = 0; i < ENTRIES; i++) act_ram[i] = '0;

    // ---- command engine: rewrite one entry's column ------------------------------------------------------------
    typedef enum logic [1:0] {W_IDLE, W_COL, W_DONE} wst_t;
    wst_t wst;
    logic [EI_W-1:0]  we_idx;
    logic [KEY_W-1:0] w_val, w_care;
    logic [ACT_W-1:0] w_act;
    logic [CHUNK_W:0] w_a;                    // column address, one bit wider to end the loop

    assign cmd_ready = (wst == W_IDLE);

    always_ff @(posedge clk) begin
        rsp_valid <= 1'b0;
        if (rst) begin
            wst <= W_IDLE; valid <= '0; we_idx <= '0; w_val <= '0; w_care <= '0; w_a <= '0; rsp_status <= '0; w_act <= '0;
        end else case (wst)
            W_IDLE: if (cmd_valid) begin
                if ((cmd_op == 4'd1 || cmd_op == 4'd2) && int'(cmd_addr) < ENTRIES) begin
                    valid[cmd_addr[EI_W-1:0]] <= 1'b0;
                    we_idx <= cmd_addr[EI_W-1:0];
                    if (cmd_op == 4'd1) begin
                        w_val <= cmd_data[KEY_W-1:0]; w_care <= cmd_data[128 +: KEY_W]; w_a <= '0; wst <= W_COL;
                        w_act <= cmd_data[256 +: ACT_W];
                    end else begin
                        rsp_valid <= 1'b1; rsp_status <= 4'd0;
                    end
                end else begin
                    rsp_valid <= 1'b1; rsp_status <= 4'd3;
                end
            end
            W_COL: begin
                w_a <= w_a + 1'b1;
                if (w_a == (CHUNK_W + 1)'(DEPTH - 1)) wst <= W_DONE;
            end
            W_DONE: begin
                // the action is written only now, with the rule invisible since W_IDLE: a lookup that matched the
                // old rule has long left the pipeline, so no result pairs the old match with the new action
                act_ram[we_idx] <= w_act;
                valid[we_idx] <= 1'b1; rsp_valid <= 1'b1; rsp_status <= 4'd0; wst <= W_IDLE;
            end
            default: wst <= W_IDLE;
        endcase
    end

    // ---- lookup -------------------------------------------------------------------------------------------------
    logic             l1_v, l2_v, l3_v;
    logic [KEY_W-1:0] l1_k;
    logic [TAG_W-1:0] l1_t, l2_t, l3_t;
    logic [ENTRIES-1:0] mv, l2_m;
    logic             l3_hit;
    logic [EI_W-1:0]  l3_idx;

    // one 2**CHUNK_W x 1 RAM per (entry, chunk): one write port (the column rewrite), one asynchronous read port
    genvar ge, gc;
    generate
        for (ge = 0; ge < ENTRIES; ge++) begin : g_e
            logic [NCH-1:0] hit_c;
            for (gc = 0; gc < NCH; gc++) begin : g_c
                (* ram_style = "distributed" *) logic r [0:DEPTH-1];
                initial for (int i = 0; i < DEPTH; i++) r[i] = 1'b0;
                always_ff @(posedge clk)
                    if (wst == W_COL && we_idx == EI_W'(ge))
                        r[w_a[CHUNK_W-1:0]] <= ((w_a[CHUNK_W-1:0] ^ w_val[gc * CHUNK_W +: CHUNK_W]) &
                                                w_care[gc * CHUNK_W +: CHUNK_W]) == '0;
                assign hit_c[gc] = r[l1_k[gc * CHUNK_W +: CHUNK_W]];
            end
            assign mv[ge] = valid[ge] && (&hit_c);
        end
    endgenerate

    always_ff @(posedge clk) begin
        if (rst) begin l1_v <= 1'b0; l2_v <= 1'b0; l3_v <= 1'b0; res_valid <= 1'b0; end
        else begin l1_v <= lk_valid; l2_v <= l1_v; l3_v <= l2_v; res_valid <= l3_v; end
        l1_k <= lk_key; l1_t <= lk_tag;
        l2_m <= mv; l2_t <= l1_t;
        // priority encoder: the lowest index wins
        l3_hit <= |l2_m; l3_idx <= '0; l3_t <= l2_t;
        for (int e = ENTRIES - 1; e >= 0; e--) if (l2_m[e]) l3_idx <= EI_W'(e);
        res_tag <= l3_t; res_hit <= l3_hit; res_act <= l3_hit ? act_ram[l3_idx] : '0;
    end
endmodule

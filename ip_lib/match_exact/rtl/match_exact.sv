// match_exact.sv: exact-match table, a two-way d-left hash in block RAM plus a small CAM stash.
//
// Two banks of 2**IDX_W one-entry buckets. Bank 0 is indexed by CRC-32 (0x04C11DB7) of the key, bank 1 by CRC-32C
// (0x1EDC6F41), both MSB-first over KEY_W bits from zero, low IDX_W bits. A key lives in bank 0 if its bucket was free
// when it was inserted, else bank 1, else the stash (STASH registers searched in parallel, the CAM emulation that
// absorbs collisions), else the insert fails with FULL. STASH alone (IDX_W = 0 is not allowed) is a pure CAM.
//
// Lookup: one key a clock, result 3 clocks later (registered key, hash into the RAM read, compare). lk_tag is carried
// alongside unchanged. Updates (cmd_*) use the RAMs' second port, so lookups never stop; each entry is one RAM word,
// written whole, so a lookup sees the old or the new entry, never half of one.
//
// Commands (cmd_data: key in [KEY_W-1:0], action in [256 +: ACT_W]):
//   1 INSERT   add, or replace the action of an existing key; marks the entry recently used
//   2 DELETE   remove the key (status NOT_FOUND if absent)
//   3 AGE      sweep: entries not used since the last sweep are removed, the others are marked unused
//   4 CLEAR    remove everything
// rsp_status: 0 OK, 1 FULL, 2 NOT_FOUND, 3 BAD_OP. INSERT/DELETE take 5 clocks, AGE and CLEAR 2 * 2**IDX_W + 3.

module match_exact #(
    parameter int KEY_W = 48,
    parameter int ACT_W = 16,
    parameter int IDX_W = 10,                // buckets per bank = 2**IDX_W
    parameter int STASH = 4,                 // CAM stash entries (0..16)
    parameter int TAG_W = 8
) (
    input  logic               clk,
    input  logic               rst,
    // lookup
    input  logic               lk_valid,
    input  logic [KEY_W-1:0]   lk_key,
    input  logic [TAG_W-1:0]   lk_tag,
    output logic               res_valid,
    output logic               res_hit,
    output logic [ACT_W-1:0]   res_act,
    output logic [TAG_W-1:0]   res_tag,
    // commands
    input  logic               cmd_valid,
    output logic               cmd_ready,
    input  logic [3:0]         cmd_op,
    input  logic [511:0]       cmd_data,
    output logic               rsp_valid,
    output logic [3:0]         rsp_status,
    // occupancy (for counters)
    output logic [IDX_W+1:0]   n_entries
);
    initial begin
        if (KEY_W < 1 || KEY_W > 256) $error("match_exact: KEY_W must be in 1..256 (got %0d)", KEY_W);
        if (ACT_W < 1 || ACT_W > 128) $error("match_exact: ACT_W must be in 1..128 (got %0d)", ACT_W);
        if (IDX_W < 2 || IDX_W > 16)  $error("match_exact: IDX_W must be in 2..16 (got %0d)", IDX_W);
        if (STASH < 0 || STASH > 16)  $error("match_exact: STASH must be in 0..16 (got %0d)", STASH);
        if (TAG_W < 1 || TAG_W > 64)  $error("match_exact: TAG_W must be in 1..64 (got %0d)", TAG_W);
    end

    localparam int EW = 2 + KEY_W + ACT_W;   // {valid, used, key, act}
    localparam int NB = 1 << IDX_W;
    localparam int SN = (STASH > 0) ? STASH : 1;

    function automatic logic [31:0] crc_key(input logic [KEY_W-1:0] k, input logic [31:0] poly);
        logic [31:0] r;
        r = 32'd0;
        for (int i = KEY_W - 1; i >= 0; i--)
            r = (r[31] ^ k[i]) ? ((r << 1) ^ poly) : (r << 1);
        return r;
    endfunction

    // ---- the two banks (port A: lookup read, port B: command read/write) --------------------------------------
    (* ram_style = "block" *) logic [EW-1:0] bank0 [0:NB-1];
    (* ram_style = "block" *) logic [EW-1:0] bank1 [0:NB-1];
    logic [IDX_W-1:0] a0, a1, b0, b1;
    logic [EW-1:0]    qa0, qa1, qb0, qb1, wd0, wd1;
    logic             we0, we1;

    initial begin
        for (int i = 0; i < NB; i++) begin bank0[i] = '0; bank1[i] = '0; end
    end
    always_ff @(posedge clk) qa0 <= bank0[a0];
    always_ff @(posedge clk) qa1 <= bank1[a1];
    always_ff @(posedge clk) begin
        if (we0) bank0[b0] <= wd0;
        qb0 <= bank0[b0];
    end
    always_ff @(posedge clk) begin
        if (we1) bank1[b1] <= wd1;
        qb1 <= bank1[b1];
    end

    // ---- stash (registers) -------------------------------------------------------------------------------------
    logic [SN-1:0]    s_valid, s_used;
    logic [KEY_W-1:0] s_key [0:SN-1];
    logic [ACT_W-1:0] s_act [0:SN-1];

    // ---- lookup pipeline ---------------------------------------------------------------------------------------
    logic             l1_v, l2_v;
    logic [KEY_W-1:0] l1_k, l2_k;
    logic [TAG_W-1:0] l1_t, l2_t;
    logic [31:0]      c0, c1, k0, k1;

    assign c0 = crc_key(l1_k, 32'h04C11DB7);
    assign c1 = crc_key(l1_k, 32'h1EDC6F41);
    assign a0 = c0[IDX_W-1:0];
    assign a1 = c1[IDX_W-1:0];

    // stash compare, in the clock the bank words arrive
    logic             l2_shit;
    logic [ACT_W-1:0] l2_sact;
    always_comb begin
        l2_shit = 1'b0; l2_sact = '0;
        for (int i = SN - 1; i >= 0; i--)
            if (STASH > 0 && s_valid[i] && s_key[i] == l2_k) begin l2_shit = 1'b1; l2_sact = s_act[i]; end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            l1_v <= 1'b0; l2_v <= 1'b0; res_valid <= 1'b0;
        end else begin
            l1_v <= lk_valid; l2_v <= l1_v; res_valid <= l2_v;
        end
        l1_k <= lk_key; l1_t <= lk_tag;
        l2_k <= l1_k;   l2_t <= l1_t;           // qa0/qa1 arrive with l2
        res_tag <= l2_t;
        if (qa0[EW-1] && qa0[ACT_W +: KEY_W] == l2_k)      begin res_hit <= 1'b1; res_act <= qa0[ACT_W-1:0]; end
        else if (qa1[EW-1] && qa1[ACT_W +: KEY_W] == l2_k) begin res_hit <= 1'b1; res_act <= qa1[ACT_W-1:0]; end
        else if (l2_shit)                                  begin res_hit <= 1'b1; res_act <= l2_sact; end
        else                                               begin res_hit <= 1'b0; res_act <= '0; end
    end

    // ---- command engine ----------------------------------------------------------------------------------------
    typedef enum logic [2:0] {C_IDLE, C_HASH, C_READ, C_DEC, C_SWEEP_RD, C_SWEEP_WR, C_DONE} cst_t;
    cst_t cst;
    logic [3:0]       op;
    logic [KEY_W-1:0] ck;
    logic [ACT_W-1:0] ca;
    logic [IDX_W-1:0] sweep;
    logic [3:0]       status;
    logic [IDX_W+1:0] count;

    assign cmd_ready = (cst == C_IDLE);
    assign k0 = crc_key(ck, 32'h04C11DB7);
    assign k1 = crc_key(ck, 32'h1EDC6F41);
    assign n_entries = count;

    // decision for INSERT / DELETE (qb0/qb1 hold the key's two buckets in C_DEC)
    logic m0, m1, ms, sfree, used0, used1, gone0, gone1;
    int   msi, sfi;
    logic [4:0] sgone;                        // stash entries an AGE sweep removes
    function automatic logic [4:0] n_unused(input logic [SN-1:0] v, input logic [SN-1:0] u);
        logic [4:0] n;
        n = '0;
        for (int i = 0; i < SN; i++) n = n + 5'((STASH > 0 && v[i] && !u[i]) ? 1 : 0);
        return n;
    endfunction
    assign sgone = n_unused(s_valid, s_used);
    always_comb begin
        m0 = qb0[EW-1] && qb0[ACT_W +: KEY_W] == ck;
        m1 = qb1[EW-1] && qb1[ACT_W +: KEY_W] == ck;
        ms = 1'b0; msi = 0; sfree = 1'b0; sfi = 0;
        for (int i = SN - 1; i >= 0; i--) begin
            if (STASH > 0 && s_valid[i] && s_key[i] == ck) begin ms = 1'b1; msi = i; end
            if (STASH > 0 && !s_valid[i])                   begin sfree = 1'b1; sfi = i; end
        end
        used0 = qb0[EW-1] && qb0[EW-2];
        used1 = qb1[EW-1] && qb1[EW-2];
        gone0 = qb0[EW-1] && !qb0[EW-2];
        gone1 = qb1[EW-1] && !qb1[EW-2];
    end

    // RAM writes (port B), combinational from the state: the write lands at the end of C_DEC or C_SWEEP_WR
    always_comb begin
        we0 = 1'b0; we1 = 1'b0; wd0 = '0; wd1 = '0;
        if (cst == C_DEC && op == 4'd1) begin
            if (m0)                          begin we0 = 1'b1; wd0 = {2'b11, ck, ca}; end
            else if (m1)                     begin we1 = 1'b1; wd1 = {2'b11, ck, ca}; end
            else if (!ms && !qb0[EW-1])      begin we0 = 1'b1; wd0 = {2'b11, ck, ca}; end
            else if (!ms && !qb1[EW-1])      begin we1 = 1'b1; wd1 = {2'b11, ck, ca}; end
        end else if (cst == C_DEC && op == 4'd2) begin
            if (m0)      we0 = 1'b1;
            else if (m1) we1 = 1'b1;
        end else if (cst == C_SWEEP_WR) begin
            we0 = 1'b1; we1 = 1'b1;
            if (op == 4'd3) begin
                wd0 = used0 ? {2'b10, qb0[EW-3:0]} : '0;
                wd1 = used1 ? {2'b10, qb1[EW-3:0]} : '0;
            end
        end
    end

    always_ff @(posedge clk) begin
        rsp_valid <= 1'b0;
        if (rst) begin
            cst <= C_IDLE; s_valid <= '0; s_used <= '0; count <= '0; rsp_status <= '0; status <= '0;
            b0 <= '0; b1 <= '0; sweep <= '0; op <= '0; ck <= '0; ca <= '0;
        end else begin
            case (cst)
                C_IDLE: if (cmd_valid) begin
                    op <= cmd_op; ck <= cmd_data[KEY_W-1:0]; ca <= cmd_data[256 +: ACT_W];
                    if (cmd_op == 4'd1 || cmd_op == 4'd2) cst <= C_HASH;
                    else if (cmd_op == 4'd3 || cmd_op == 4'd4) begin
                        sweep <= '0; b0 <= '0; b1 <= '0; cst <= C_SWEEP_RD;
                    end else begin status <= 4'd3; cst <= C_DONE; end
                end
                C_HASH: begin
                    b0 <= k0[IDX_W-1:0];
                    b1 <= k1[IDX_W-1:0];
                    cst <= C_READ;
                end
                C_READ: cst <= C_DEC;            // qb0/qb1 arrive at the end of this clock
                C_DEC: begin
                    status <= 4'd0;
                    if (op == 4'd1) begin
                        if (m0 || m1) ;
                        else if (ms) begin s_act[msi] <= ca; s_used[msi] <= 1'b1; end
                        else if (!qb0[EW-1] || !qb1[EW-1]) count <= count + 1'b1;
                        else if (sfree) begin
                            s_valid[sfi] <= 1'b1; s_used[sfi] <= 1'b1; s_key[sfi] <= ck; s_act[sfi] <= ca;
                            count <= count + 1'b1;
                        end else status <= 4'd1;
                    end else begin
                        if (m0 || m1) count <= count - 1'b1;
                        else if (ms) begin s_valid[msi] <= 1'b0; count <= count - 1'b1; end
                        else status <= 4'd2;
                    end
                    cst <= C_DONE;
                end
                C_SWEEP_RD: cst <= C_SWEEP_WR;   // qb0/qb1 = the buckets at `sweep` at the end of this clock
                C_SWEEP_WR: begin
                    if (op == 4'd3) count <= count - (IDX_W + 2)'(gone0) - (IDX_W + 2)'(gone1);
                    if (sweep == IDX_W'(NB - 1)) begin
                        cst <= C_DONE; status <= 4'd0;
                        if (op == 4'd4) begin s_valid <= '0; s_used <= '0; count <= '0; end
                        else begin
                            for (int i = 0; i < SN; i++) begin
                                if (s_valid[i] && !s_used[i]) s_valid[i] <= 1'b0;
                                s_used[i] <= 1'b0;
                            end
                            count <= count - (IDX_W + 2)'(gone0) - (IDX_W + 2)'(gone1) - (IDX_W + 2)'(sgone);
                        end
                    end else begin
                        sweep <= sweep + 1'b1; b0 <= sweep + 1'b1; b1 <= sweep + 1'b1; cst <= C_SWEEP_RD;
                    end
                end
                C_DONE: begin rsp_valid <= 1'b1; rsp_status <= status; cst <= C_IDLE; end
                default: cst <= C_IDLE;
            endcase
        end
    end
endmodule

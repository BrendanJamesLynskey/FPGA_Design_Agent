// l2_switch.sv: a learning, VLAN-aware Layer-2 switch of NP ports (IEEE 802.1Q bridge behaviour, simplified).
//
// Ingress (per port): the frame (destination address .. payload, no FCS) is stored whole in the port's buffer while
// its addresses and VLAN are captured. Frames with tuser set (bad FCS from the MAC), shorter than 14 bytes, or that
// do not fit are dropped and counted (ev_in_drop). A frame is classified to the VID of its 0x8100 tag, or to the port's
// PVID when untagged (priority-tagged VID 0 also takes the PVID).
//
// Forwarding core (one frame at a time, ports served round-robin):
//   - ingress filter: a port that is not a member of the VID drops the frame;
//   - lookup {VID, destination}; then learn {VID, source} -> ingress port (match_exact INSERT; not for a group source);
//   - known unicast to another member port: that port; known unicast to the ingress port: filtered;
//     unknown unicast, multicast and broadcast: flooded to every member port except the ingress port;
//   - the frame is copied once, written to every selected egress queue at the same time.
// Frames leave unchanged (no tag push/pop here; pkt_rewrite does that). Egress: one pkt_queue_sched a port (its queue
// 0), which drops and counts when full. age_tick starts an AGE sweep of the address table between frames: entries
// not refreshed by a frame since the previous sweep are removed.
// Configuration: pvid (12 bits a port); cfg_we/cfg_vid/cfg_mask write the member set of a VID (all VIDs start empty).
// Debug/stat outputs: ev_pick (a frame entered the core; ev_port = its port), ev_age (a sweep started),
// ev_flood, ev_filter.

module l2_switch #(
    parameter int NP      = 4,               // ports, 2..8
    parameter int IN_BYTES = 4096,           // ingress buffer bytes a port (power of two)
    parameter int EG_BYTES = 4096,           // egress buffer bytes a port (power of two)
    parameter int IDX_W   = 9,               // address table: 2 x 2**IDX_W buckets
    parameter int STASH   = 4
) (
    input  logic              clk,
    input  logic              rst,
    input  logic [NP*8-1:0]   s_tdata,
    input  logic [NP-1:0]     s_tvalid,
    output logic [NP-1:0]     s_tready,
    input  logic [NP-1:0]     s_tlast,
    input  logic [NP-1:0]     s_tuser,
    output logic [NP*8-1:0]   m_tdata,
    output logic [NP-1:0]     m_tvalid,
    input  logic [NP-1:0]     m_tready,
    output logic [NP-1:0]     m_tlast,
    output logic [NP-1:0]     m_tuser,
    input  logic [NP*12-1:0]  pvid,
    input  logic              cfg_we,
    input  logic [11:0]       cfg_vid,
    input  logic [NP-1:0]     cfg_mask,
    input  logic              age_tick,
    output logic              ev_pick,
    output logic [2:0]        ev_port,
    output logic              ev_age,
    output logic              ev_flood,
    output logic              ev_filter,
    output logic [NP-1:0]     ev_in_drop          // per port: a frame dropped at ingress
);
    initial begin
        if (NP < 2 || NP > 8) $error("l2_switch: NP must be in 2..8 (got %0d)", NP);
        if (IN_BYTES < 128 || (IN_BYTES & (IN_BYTES - 1)) != 0) $error("l2_switch: IN_BYTES must be a power of two >= 128 (got %0d)", IN_BYTES);
        if (EG_BYTES < 128 || (EG_BYTES & (EG_BYTES - 1)) != 0) $error("l2_switch: EG_BYTES must be a power of two >= 128 (got %0d)", EG_BYTES);
    end

    localparam int IAW = $clog2(IN_BYTES);
    localparam int PW = (NP > 1) ? $clog2(NP) : 1;
    localparam int NDESC = 16;
    localparam int DSW = 11 + 48 + 48 + 13;        // {len, dmac, smac, tagged, vid}

    // ---- VLAN member table ----
    logic [NP-1:0] vmem [0:4095];
    initial for (int i = 0; i < 4096; i++) vmem[i] = '0;
    always_ff @(posedge clk) if (cfg_we) vmem[cfg_vid] <= cfg_mask;

    // ---- ingress: buffer and header capture per port ----
    logic [NP-1:0]   ing_avail;
    logic [DSW-1:0]  ing_desc [0:NP-1];
    logic [IAW-1:0]  ing_rd   [0:NP-1];
    logic [7:0]      ing_q    [0:NP-1];
    logic [IAW-1:0]  rd_addr;                       // core read address (in the selected port's buffer)
    logic [PW-1:0]   ing_sel;                       // the port whose frame the core is handling
    logic [NP-1:0]   ing_pop;                       // core releases the head frame
    logic [NP-1:0]   ing_drop_ev;

    genvar gp;
    generate
        for (gp = 0; gp < NP; gp++) begin : g_in
            (* ram_style = "block" *) logic [7:0] ram [0:IN_BYTES-1];
            logic [DSW-1:0]  dq [0:NDESC-1];
            logic [4:0]      dwp, drp;
            logic [IAW:0]    wp, fp, ws;            // write, freed, frame start (wrap bit on top)
            logic [10:0]     len;
            logic [47:0]     dm, sm;
            logic [15:0]     tp;
            logic [15:0]     tci;
            logic            bad, inf;
            logic [IAW:0]    used;
            assign used = wp - fp;
            assign s_tready[gp] = 1'b1;
            always_ff @(posedge clk) begin
                if (s_tvalid[gp] && used < (IAW + 1)'(IN_BYTES)) ram[wp[IAW-1:0]] <= s_tdata[8 * gp +: 8];
                ing_q[gp] <= ram[(gp == ing_sel) ? rd_addr : '0];
            end
            assign ing_avail[gp] = (dwp != drp);
            assign ing_desc[gp] = dq[drp[3:0]];
            always_ff @(posedge clk) begin
                ing_drop_ev[gp] <= 1'b0;
                if (rst) begin
                    dwp <= '0; drp <= '0; wp <= '0; fp <= '0; ws <= '0; len <= '0; inf <= 1'b0; bad <= 1'b0;
                    dm <= '0; sm <= '0; tp <= '0; tci <= '0;
                end else begin
                    if (ing_pop[gp]) begin
                        drp <= drp + 1'b1;
                        fp  <= fp + (IAW + 1)'(dq[drp[3:0]][DSW-1 -: 11]);
                    end
                    if (s_tvalid[gp]) begin
                        logic [10:0] l;
                        logic        b;
                        l = inf ? len : 11'd0;
                        b = (inf && bad) || used >= (IAW + 1)'(IN_BYTES) || l == 11'h7FF;
                        if (l < 11'd6)                    dm[8 * (5 - l[2:0]) +: 8] <= s_tdata[8 * gp +: 8];
                        if (l >= 11'd6 && l < 11'd12)     sm[8 * (11 - l[3:0]) +: 8] <= s_tdata[8 * gp +: 8];
                        if (l == 11'd12) tp[15:8]  <= s_tdata[8 * gp +: 8];
                        if (l == 11'd13) tp[7:0]   <= s_tdata[8 * gp +: 8];
                        if (l == 11'd14) tci[15:8] <= s_tdata[8 * gp +: 8];
                        if (l == 11'd15) tci[7:0]  <= s_tdata[8 * gp +: 8];
                        if (!b) wp <= wp + 1'b1;
                        if (s_tlast[gp]) begin
                            inf <= 1'b0; bad <= 1'b0;
                            if (b || s_tuser[gp] || l < 11'd13 || (dwp - drp) == 5'd16) begin
                                wp <= inf ? ws : wp;            // give the space back
                                ing_drop_ev[gp] <= 1'b1;
                            end else begin
                                // the last byte's own fields are captured this clock: build from l
                                logic [15:0] t;
                                t = (l == 11'd15) ? {tci[15:8], s_tdata[8 * gp +: 8]} : tci;
                                dq[dwp[3:0]] <= {l + 11'd1, dm, sm, (tp == 16'h8100 && l >= 11'd15), t[11:0]};
                                dwp <= dwp + 1'b1;
                            end
                        end else begin
                            if (!inf) ws <= wp;
                            inf <= 1'b1; len <= l + 11'd1; bad <= b;
                        end
                    end
                end
            end
        end
    endgenerate
    assign ev_in_drop = ing_drop_ev;

    // ---- address table ----
    logic             lk_valid, res_valid, res_hit, cmd_valid, cmd_ready, rsp_valid;
    logic [59:0]      lk_key;
    logic [7:0]       res_act;
    logic [3:0]       cmd_op, rsp_status;
    logic [511:0]     cmd_data;
    /* verilator lint_off PINCONNECTEMPTY */
    match_exact #(.KEY_W(60), .ACT_W(8), .IDX_W(IDX_W), .STASH(STASH), .TAG_W(1)) u_tab (
        .clk(clk), .rst(rst), .lk_valid(lk_valid), .lk_key(lk_key), .lk_tag(1'b0), .res_valid(res_valid),
        .res_hit(res_hit), .res_act(res_act), .res_tag(), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .cmd_op(cmd_op), .cmd_data(cmd_data), .rsp_valid(rsp_valid), .rsp_status(rsp_status), .n_entries());
    /* verilator lint_on PINCONNECTEMPTY */

    // ---- forwarding core ----
    typedef enum logic [2:0] {F_IDLE, F_AGE, F_LOOK, F_WAIT, F_LEARN, F_COPY, F_END} fst_t;
    fst_t fst;
    logic [PW-1:0]  last;
    logic [DSW-1:0] d;
    logic [11:0]    vid;
    logic [NP-1:0]  member, fwd;
    logic [10:0]    left;
    logic           age_pend;
    logic [IAW-1:0] base;
    logic           cp_v, cp_l;                      // byte read last clock (data in ing_q now)
    logic [NP-1:0]  cp_mask;

    // round-robin pick among ports with a frame waiting
    logic [PW-1:0] pick;
    logic          any;
    always_comb begin
        any = |ing_avail;
        pick = last;
        for (int k = NP; k >= 1; k--) begin
            int q;
            q = (int'(last) + k) % NP;
            if (ing_avail[q]) pick = PW'(q);
        end
    end

    always_comb begin
        ing_pop = '0;
        if (fst == F_END) ing_pop[ing_sel] = 1'b1;
    end

    always_ff @(posedge clk) begin
        lk_valid <= 1'b0; ev_pick <= 1'b0; ev_age <= 1'b0; ev_flood <= 1'b0; ev_filter <= 1'b0;
        if (cmd_ready) cmd_valid <= 1'b0;
        if (age_tick) age_pend <= 1'b1;
        if (rst) begin
            fst <= F_IDLE; ing_sel <= '0; last <= PW'(NP - 1); age_pend <= 1'b0; cmd_valid <= 1'b0; cmd_op <= '0;
            cmd_data <= '0; d <= '0; vid <= '0; member <= '0; fwd <= '0; left <= '0; rd_addr <= '0; base <= '0;
            cp_v <= 1'b0; cp_l <= 1'b0; cp_mask <= '0; ev_port <= '0; lk_key <= '0;
        end else begin
            case (fst)
                F_IDLE: if (cmd_ready && !cmd_valid) begin
                    if (age_pend) begin
                        age_pend <= age_tick; cmd_valid <= 1'b1; cmd_op <= 4'd3; ev_age <= 1'b1; fst <= F_AGE;
                    end else if (any) begin
                        logic [DSW-1:0] dd;
                        logic [11:0]    v;
                        dd = ing_desc[pick];
                        v  = (dd[12] && dd[11:0] != 12'd0) ? dd[11:0] : pvid[12 * pick +: 12];
                        ing_sel <= pick; last <= pick; d <= dd; vid <= v;
                        ev_pick <= 1'b1; ev_port <= 3'(pick);
                        lk_valid <= 1'b1; lk_key <= {v, dd[DSW-12 -: 48]};
                        base <= ing_rd[pick];
                        fst <= F_LOOK;
                    end
                end
                F_AGE: if (rsp_valid) fst <= F_IDLE;
                F_LOOK: begin member <= vmem[vid]; fst <= F_WAIT; end
                F_WAIT: if (res_valid) begin
                    logic [47:0] dmac, smac;
                    logic [NP-1:0] m;
                    dmac = d[DSW-12 -: 48];
                    smac = d[DSW-60 -: 48];
                    if (!member[ing_sel])                                  m = '0;
                    else if (dmac[40] || !res_hit)                         m = member & ~(NP'(1) << ing_sel);
                    else if (res_act[PW-1:0] == ing_sel)                   m = '0;
                    else                                                   m = member & (NP'(1) << res_act[PW-1:0]);
                    fwd <= m;
                    ev_flood  <= member[ing_sel] && (dmac[40] || !res_hit);
                    ev_filter <= member[ing_sel] && !dmac[40] && res_hit && res_act[PW-1:0] == ing_sel;
                    // learn the source (not a group address; only on a member port)
                    if (!smac[40] && member[ing_sel]) begin
                        cmd_valid <= 1'b1; cmd_op <= 4'd1;
                        cmd_data <= '0;
                        cmd_data[59:0] <= {vid, smac};
                        cmd_data[256 +: 8] <= 8'(ing_sel);
                        fst <= F_LEARN;
                    end else begin
                        fst <= F_COPY; left <= d[DSW-1 -: 11]; rd_addr <= base;
                    end
                end
                F_LEARN: if (rsp_valid) begin fst <= F_COPY; left <= d[DSW-1 -: 11]; rd_addr <= base; end
                F_COPY: begin
                    if (left != 11'd0) begin
                        rd_addr <= rd_addr + 1'b1; left <= left - 11'd1;
                    end
                    if (left == 11'd1) fst <= F_END;
                end
                F_END: fst <= F_IDLE;
                default: fst <= F_IDLE;
            endcase
            cp_v <= (fst == F_COPY) && left != 11'd0;
            cp_l <= (fst == F_COPY) && left == 11'd1;
            cp_mask <= fwd;
        end
    end

    // ingress read pointers advance by whole frames
    generate
        for (gp = 0; gp < NP; gp++) begin : g_rd
            always_ff @(posedge clk) begin
                if (rst) ing_rd[gp] <= '0;
                else if (ing_pop[gp]) ing_rd[gp] <= ing_rd[gp] + IAW'(ing_desc[gp][DSW-1 -: 11]);
            end
        end
    endgenerate

    // ---- egress queues ----
    generate
        for (gp = 0; gp < NP; gp++) begin : g_eg
            /* verilator lint_off PINCONNECTEMPTY */
            pkt_queue_sched #(.NQ(2), .QBYTES(EG_BYTES), .DESC(32), .MAX_LEN(1522)) u_eg (
                .clk(clk), .rst(rst), .s_axis_tdata(ing_q[ing_sel]), .s_axis_tvalid(cp_v && cp_mask[gp]),
                .s_axis_tready(), .s_axis_tlast(cp_l), .s_axis_tuser(1'b0), .s_axis_tdest(3'd0),
                .m_axis_tdata(m_tdata[8 * gp +: 8]), .m_axis_tvalid(m_tvalid[gp]), .m_axis_tready(m_tready[gp]),
                .m_axis_tlast(m_tlast[gp]), .m_axis_tuser(m_tuser[gp]), .m_axis_tdest(), .sched_mode(2'd0),
                .quantum('0), .deq_en(1'b1), .drop_cnt(), .ev_drop());
            /* verilator lint_on PINCONNECTEMPTY */
        end
    endgenerate
endmodule

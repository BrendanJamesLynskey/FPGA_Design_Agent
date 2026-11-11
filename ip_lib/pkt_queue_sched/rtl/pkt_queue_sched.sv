// pkt_queue_sched.sv: packet buffer with per-queue descriptor FIFOs and a scheduler (round-robin, strict priority,
// deficit round-robin), byte-wide AXI-Stream in and out.
//
// Buffer: one RAM of NQ * QBYTES bytes, a fixed region per queue used as a ring. A packet is written at its queue's
// write pointer as it arrives (the queue is s_axis_tdest on the first beat). At tlast its descriptor {start, length,
// tuser} goes into the queue's descriptor FIFO (DESC deep). A packet that would overflow its region, or finds the
// descriptor FIFO full, or is longer than MAX_LEN, is dropped whole: the write pointer goes back to the packet's start
// and drop_cnt for that queue counts it (ev_drop pulses). The input never stalls (tready is always 1).
//
// Scheduler, chosen by sched_mode (may change between packets):
//   0 round-robin: the next non-empty queue after the last one served;
//   1 strict priority: the lowest-numbered non-empty queue;
//   2 deficit round-robin (Shreedhar and Varghese): visiting a non-empty queue adds quantum[q] to its deficit; the
//     head packet goes when its length <= deficit (deficit -= length), else the visit ends; an empty queue's deficit
//     is cleared. One scheduler step a clock.
// deq_en = 0 holds the next packet (a pause); a packet already started always finishes. Output tdest = queue.

module pkt_queue_sched #(
    parameter int NQ      = 4,               // queues: 2, 4 or 8 (the queue is tdest[log2(NQ)-1:0])
    parameter int QBYTES  = 2048,            // bytes a queue region, power of two, 64..65536
    parameter int DESC    = 16,              // descriptors a queue, power of two, 2..256
    parameter int MAX_LEN = 1522             // longest packet accepted, bytes (<= QBYTES)
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic [7:0]            s_axis_tdata,
    input  logic                  s_axis_tvalid,
    output logic                  s_axis_tready,
    input  logic                  s_axis_tlast,
    input  logic                  s_axis_tuser,
    input  logic [2:0]            s_axis_tdest,
    output logic [7:0]            m_axis_tdata,
    output logic                  m_axis_tvalid,
    input  logic                  m_axis_tready,
    output logic                  m_axis_tlast,
    output logic                  m_axis_tuser,
    output logic [2:0]            m_axis_tdest,
    input  logic [1:0]            sched_mode,
    input  logic [NQ*16-1:0]      quantum,      // bytes, per queue (DRR)
    input  logic                  deq_en,
    output logic [NQ*16-1:0]      drop_cnt,
    output logic                  ev_drop
);
    initial begin
        if (NQ != 2 && NQ != 4 && NQ != 8) $error("pkt_queue_sched: NQ must be 2, 4 or 8 (got %0d)", NQ);
        if (QBYTES < 64 || QBYTES > 65536 || (QBYTES & (QBYTES - 1)) != 0)
            $error("pkt_queue_sched: QBYTES must be a power of two in 64..65536 (got %0d)", QBYTES);
        if (DESC < 2 || DESC > 256 || (DESC & (DESC - 1)) != 0)
            $error("pkt_queue_sched: DESC must be a power of two in 2..256 (got %0d)", DESC);
        if (MAX_LEN < 1 || MAX_LEN > QBYTES) $error("pkt_queue_sched: MAX_LEN must be in 1..QBYTES (got %0d)", MAX_LEN);
    end

    localparam int AW = $clog2(QBYTES);       // offset within a region
    localparam int QW = $clog2(NQ);
    localparam int DW = $clog2(DESC);
    localparam int LW = 17;                   // packet length bits

    // ---- packet RAM ----
    (* ram_style = "block" *) logic [7:0] ram [0:NQ*QBYTES-1];
    logic [QW+AW-1:0] ram_wa, ram_ra;
    logic [7:0]       ram_wd, ram_q;
    logic             ram_we;
    always_ff @(posedge clk) begin
        if (ram_we) ram[ram_wa] <= ram_wd;
        ram_q <= ram[ram_ra];
    end

    // ---- descriptor FIFOs (distributed RAM) ----
    logic [AW+LW:0] dmem [0:NQ*DESC-1];        // {tuser, length, start}
    logic [DW:0]    dwp [0:NQ-1], drp [0:NQ-1];
    logic [NQ-1:0]  nonempty;
    always_comb for (int q = 0; q < NQ; q++) nonempty[q] = (dwp[q] != drp[q]);

    // ---- ring pointers: write (wp), packet start (ws), and freed (fp), each with a wrap bit ----
    logic [AW:0] wp [0:NQ-1], fp [0:NQ-1];

    // ================================================================ enqueue
    logic          in_pkt, bad;
    logic [QW-1:0] iq;
    logic [AW:0]   ws;                         // start of the packet being written
    logic [LW-1:0] ilen;
    logic [QW-1:0] dq_q;
    logic [LW-1:0] dq_len;

    assign s_axis_tready = 1'b1;
    logic [QW-1:0] cq;                          // queue of this beat
    logic [AW:0]   cw;                          // write pointer for this beat
    logic [AW:0]   used;
    logic          room;
    always_comb begin
        cq   = in_pkt ? iq : s_axis_tdest[QW-1:0];
        cw   = in_pkt ? wp[iq] : wp[cq];
        used = cw - fp[cq];
        room = (used < (AW + 1)'(QBYTES));
        ram_we = s_axis_tvalid && !(in_pkt && bad) && room;
        ram_wa = {cq, cw[AW-1:0]};
        ram_wd = s_axis_tdata;
    end

    always_ff @(posedge clk) begin
        ev_drop <= 1'b0;
        if (rst) begin
            in_pkt <= 1'b0; bad <= 1'b0; iq <= '0; ws <= '0; ilen <= '0;
            for (int q = 0; q < NQ; q++) begin wp[q] <= '0; dwp[q] <= '0; end
            drop_cnt <= '0;
        end else begin
            if (s_axis_tvalid) begin
                logic          nbad;
                logic [AW:0]   start;
                logic [LW-1:0] len;
                start = in_pkt ? ws : wp[cq];
                len   = in_pkt ? ilen + 1'b1 : LW'(1);
                nbad  = (in_pkt && bad) || !room || (int'(len) > MAX_LEN);
                if (ram_we) wp[cq] <= cw + 1'b1;
                if (s_axis_tlast) begin
                    in_pkt <= 1'b0; bad <= 1'b0;
                    if (nbad || (dwp[cq] - drp[cq]) == (DW + 1)'(DESC)) begin
                        wp[cq] <= start;                     // drop: give the space back
                        drop_cnt[16 * cq +: 16] <= drop_cnt[16 * cq +: 16] + 16'd1;
                        ev_drop <= 1'b1;
                    end else begin
                        dmem[{cq, dwp[cq][DW-1:0]}] <= {s_axis_tuser, len, start[AW-1:0]};
                        dwp[cq] <= dwp[cq] + 1'b1;
                    end
                end else begin
                    in_pkt <= 1'b1; iq <= cq; ws <= start; ilen <= len; bad <= nbad;
                end
            end
        end
    end

    // ================================================================ scheduler
    typedef enum logic [1:0] {D_PICK, D_SEND, D_LAST} dst_t;
    dst_t dst;
    logic [QW-1:0]  cur;                        // DRR: queue being visited; RR: last served
    logic           visited;
    logic [LW:0]    deficit [0:NQ-1];
    logic [QW-1:0]  sel;                        // queue chosen this clock
    logic           go;                         // start sending sel
    logic [AW+LW:0] head [0:NQ-1];
    always_comb for (int q = 0; q < NQ; q++) head[q] = dmem[{QW'(q), drp[q][DW-1:0]}];

    logic [QW-1:0] nxt;                         // DRR / RR next queue after cur
    always_comb nxt = (cur == QW'(NQ - 1)) ? '0 : cur + 1'b1;

    // RR and SP choice (combinational)
    logic [QW-1:0] rr_sel, sp_sel;
    logic          any;
    always_comb begin
        any = |nonempty;
        sp_sel = '0;
        for (int q = NQ - 1; q >= 0; q--) if (nonempty[q]) sp_sel = QW'(q);
        rr_sel = cur;
        for (int k = NQ; k >= 1; k--) begin
            int q;
            q = (int'(cur) + k) % NQ;
            if (nonempty[q]) rr_sel = QW'(q);
        end
    end

    // ================================================================ dequeue (read engine with a 2-entry skid)
    logic [AW-1:0] rpos;                        // read offset in the region
    logic [LW-1:0] rleft;                       // bytes still to read
    logic          ruser;
    logic [QW-1:0] rq;
    logic          rd_issue, rd_v, rd_l;        // a read issued last clock (data in ram_q now)
    logic [7:0]    sk_d [0:1];
    logic          sk_l [0:1], sk_u [0:1];
    logic [2:0]    sk_t [0:1];
    logic [1:0]    sk_n;
    logic          pop;

    assign pop = m_axis_tvalid && m_axis_tready;
    assign rd_issue = (dst == D_SEND) && (rleft != '0) && ((32'(sk_n) + 32'(rd_v) - 32'(pop)) < 2);
    assign ram_ra = {rq, rpos};
    assign m_axis_tvalid = (sk_n != 2'd0);
    assign m_axis_tdata = sk_d[0];
    assign m_axis_tlast = sk_l[0];
    assign m_axis_tuser = sk_u[0] && sk_l[0];
    assign m_axis_tdest = sk_t[0];

    always_ff @(posedge clk) begin
        if (rst) begin
            dst <= D_PICK; cur <= QW'(NQ - 1); visited <= 1'b0; rpos <= '0; rleft <= '0; ruser <= 1'b0; rq <= '0;
            rd_v <= 1'b0; rd_l <= 1'b0; sk_n <= '0;
            for (int q = 0; q < NQ; q++) begin drp[q] <= '0; fp[q] <= '0; deficit[q] <= '0; end
        end else begin
            // skid buffer: pop the head, then append the RAM word that arrived
            begin
                logic [1:0] n;
                n = sk_n;
                if (pop) begin
                    sk_d[0] <= sk_d[1]; sk_l[0] <= sk_l[1]; sk_u[0] <= sk_u[1]; sk_t[0] <= sk_t[1];
                    n = n - 2'd1;
                end
                if (rd_v) begin
                    if (n == 2'd0) begin sk_d[0] <= ram_q; sk_l[0] <= rd_l; sk_u[0] <= ruser; sk_t[0] <= 3'(rq); end
                    else           begin sk_d[1] <= ram_q; sk_l[1] <= rd_l; sk_u[1] <= ruser; sk_t[1] <= 3'(rq); end
                    n = n + 2'd1;
                end
                sk_n <= n;
            end
            rd_v <= rd_issue;
            rd_l <= rd_issue && (rleft == LW'(1));
            if (rd_issue) begin rpos <= rpos + 1'b1; rleft <= rleft - 1'b1; end

            case (dst)
                D_PICK: if (deq_en && any) begin
                    go = 1'b0;
                    sel = cur;
                    if (sched_mode == 2'd1) begin go = 1'b1; sel = sp_sel; end
                    else if (sched_mode == 2'd2) begin
                        // one DRR step
                        if (!visited) begin
                            if (nonempty[cur]) begin
                                deficit[cur] <= deficit[cur] + (LW + 1)'(quantum[16 * cur +: 16]); visited <= 1'b1;
                            end else begin
                                deficit[cur] <= '0; cur <= nxt;
                            end
                        end else if (nonempty[cur] && {1'b0, head[cur][AW +: LW]} <= deficit[cur]) begin
                            go = 1'b1; sel = cur;
                            deficit[cur] <= deficit[cur] - {1'b0, head[cur][AW +: LW]};
                        end else begin
                            if (!nonempty[cur]) deficit[cur] <= '0;
                            cur <= nxt; visited <= 1'b0;
                        end
                    end else begin
                        go = 1'b1; sel = rr_sel; cur <= rr_sel;
                    end
                    if (go) begin
                        rq <= sel; rpos <= head[sel][AW-1:0]; rleft <= head[sel][AW +: LW]; ruser <= head[sel][AW+LW];
                        drp[sel] <= drp[sel] + 1'b1;
                        dq_q <= sel; dq_len <= head[sel][AW +: LW];
                        dst <= D_SEND;
                    end
                end
                D_SEND: if (rleft == '0 || (rd_issue && rleft == LW'(1))) begin
                    dst <= D_LAST;
                end
                D_LAST: begin
                    // all bytes read: the region space is free again
                    fp[dq_q] <= fp[dq_q] + (AW + 1)'(dq_len);
                    dst <= D_PICK;
                end
                default: dst <= D_PICK;
            endcase
        end
    end
endmodule

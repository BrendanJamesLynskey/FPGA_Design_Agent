// probe_common.svh (brief 69): the shared part of every AMD-IP probe bench. Include it inside a testbench module, then
// instantiate the IP under test on the bus signals declared here (awaddr ... rresp) and write the probes.
//
//   - clock 100 MHz, active-low synchronous reset aresetn (do_reset re-applies it mid-run);
//   - the transactor engine axil_tx_master (brief 59A) makes every ordinary access: wr(), rd();
//   - raw drive (raw_en = 1) takes the five channels over for the probes the transactor cannot make
//     (second address before the first response, AW without W, a response held back);
//   - our AXI4-Lite protocol checker axil_checker watches the same wires all the time; rep() prints it with every probe,
//     and the mask it prints is "which rules were broken since the previous probe line".
// Every result line is  PROBE|<probe>|<key=value ...> chk=0x<rule mask>  and nothing else is parsed by run_probe.py.
`timescale 1ns/1ps

    localparam int AW_B = 32;
    logic aclk = 1'b0, aresetn = 1'b0;
    always #5 aclk = ~aclk;
    int unsigned cyc = 0;
    always @(posedge aclk) cyc <= cyc + 1;

    // ---- the bus the IP sees
    logic [AW_B-1:0] awaddr, araddr;
    logic [2:0]      awprot, arprot;
    logic            awvalid, wvalid, arvalid, bready, rready;
    logic [31:0]     wdata;
    logic [3:0]      wstrb;
    wire             awready, wready, arready, bvalid, rvalid;
    wire  [1:0]      bresp, rresp;
    wire  [31:0]     rdata;

    // ---- transactor engine
    logic        m_start = 1'b0, m_is_read = 1'b0;
    logic [AW_B-1:0] m_addr = '0;
    logic [31:0] m_wdata = '0;
    logic [3:0]  m_wstrb = 4'hF;
    logic [1:0]  m_order = 2'd0;
    logic [7:0]  m_gap = 8'd0, m_valid_p = 8'd0, m_ready_p = 8'd255;
    logic [31:0] m_thr = 32'd0;
    wire         m_busy, m_done, m_pend_aw, m_pend_w, m_pend_b, m_pend_ar, m_pend_r;
    wire  [1:0]  m_resp;
    wire  [31:0] m_rdata, m_latency;
    wire  [AW_B-1:0] t_awaddr, t_araddr;
    wire  [2:0]  t_awprot, t_arprot;
    wire         t_awvalid, t_wvalid, t_arvalid, t_bready, t_rready;
    wire  [31:0] t_wdata;
    wire  [3:0]  t_wstrb;

    axil_tx_master #(.ADDR_W(AW_B), .DATA_W(32)) u_tx (
        .clk(aclk), .rst(!aresetn), .start(m_start), .is_read(m_is_read), .addr(m_addr), .wdata(m_wdata),
        .wstrb(m_wstrb), .order(m_order), .gap(m_gap), .inject(2'd0), .thr(m_thr), .valid_p(m_valid_p),
        .ready_p(m_ready_p), .busy(m_busy), .done(m_done), .resp(m_resp), .rdata(m_rdata), .latency(m_latency),
        .pend_aw(m_pend_aw), .pend_w(m_pend_w), .pend_b(m_pend_b), .pend_ar(m_pend_ar), .pend_r(m_pend_r),
        .m_awaddr(t_awaddr), .m_awprot(t_awprot), .m_awvalid(t_awvalid), .m_awready(awready),
        .m_wdata(t_wdata), .m_wstrb(t_wstrb), .m_wvalid(t_wvalid), .m_wready(wready),
        .m_bresp(bresp), .m_bvalid(bvalid), .m_bready(t_bready),
        .m_araddr(t_araddr), .m_arprot(t_arprot), .m_arvalid(t_arvalid), .m_arready(arready),
        .m_rdata(rdata), .m_rresp(rresp), .m_rvalid(rvalid), .m_rready(t_rready));

    // ---- raw drive and the mux
    logic            raw_en = 1'b0;
    logic [AW_B-1:0] r_awaddr = '0, r_araddr = '0;
    logic            r_awvalid = 1'b0, r_wvalid = 1'b0, r_arvalid = 1'b0, r_bready = 1'b0, r_rready = 1'b0;
    logic [31:0]     r_wdata = '0;
    logic [3:0]      r_wstrb = 4'hF;
    assign awaddr  = raw_en ? r_awaddr  : t_awaddr;
    assign araddr  = raw_en ? r_araddr  : t_araddr;
    assign awprot  = 3'b000;
    assign arprot  = 3'b000;
    assign awvalid = raw_en ? r_awvalid : t_awvalid;
    assign wvalid  = raw_en ? r_wvalid  : t_wvalid;
    assign arvalid = raw_en ? r_arvalid : t_arvalid;
    assign bready  = raw_en ? r_bready  : t_bready;
    assign rready  = raw_en ? r_rready  : t_rready;
    assign wdata   = raw_en ? r_wdata   : t_wdata;
    assign wstrb   = raw_en ? r_wstrb   : t_wstrb;

    // ---- our protocol checker, always on
    wire [9:0] chk_viol;
    wire       chk_trig, chk_any;
    wire [31:0] chk_rd;
    logic [9:0] chk_acc = '0;
    axil_checker #(.ADDR_W(AW_B), .DATA_W(32)) u_chk (
        .aclk(aclk), .aresetn(aresetn), .clear(1'b0), .en(10'h3FF), .now(cyc),
        .awaddr(awaddr), .awprot(awprot), .awvalid(awvalid), .awready(awready), .wdata(wdata), .wstrb(wstrb),
        .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arprot(arprot), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .viol(chk_viol), .trig(chk_trig), .any(chk_any), .rd_sel(6'd0), .rd_data(chk_rd));
    always @(posedge aclk) chk_acc <= chk_acc | chk_viol;

    // ---- timing knobs for the transactor: a free-running pseudo-random throttle word (only used when the knobs are not 0/255)
    always @(posedge aclk) m_thr <= $urandom;

    // ---- reporting
    task automatic rep(input string probe, input string res);
        $display("PROBE|%s|%s chk=0x%03x", probe, res, chk_acc);
        chk_acc = '0;
    endtask
    function automatic string rname(input logic [1:0] r);
        case (r) 2'b00: return "OKAY"; 2'b01: return "EXOKAY"; 2'b10: return "SLVERR"; default: return "DECERR"; endcase
    endfunction

    // ---- access tasks (transactor). `hung` is set when no response arrives within `TMO` clocks.
    int TMO = 400;
    bit hung = 1'b0;
    logic [1:0]  last_resp;
    logic [31:0] last_rdata;
    int unsigned last_lat;
    task automatic wr(input logic [AW_B-1:0] a, input logic [31:0] d, input logic [3:0] s = 4'hF, input int order = 0);
        int n;
        raw_en = 1'b0;
        while (m_busy) @(posedge aclk);
        @(negedge aclk);
        m_addr = a; m_wdata = d; m_wstrb = s; m_is_read = 1'b0; m_order = order[1:0]; m_gap = 8'd2; m_start = 1'b1;
        @(negedge aclk); m_start = 1'b0;
        n = 0; hung = 1'b0;
        while (!m_done && n < TMO) begin @(posedge aclk); n++; end
        if (n >= TMO) begin hung = 1'b1; last_resp = 2'b11; last_lat = 0; end
        else begin last_resp = m_resp; last_lat = m_latency; end
        @(posedge aclk);
    endtask
    task automatic rd(input logic [AW_B-1:0] a);
        int n;
        raw_en = 1'b0;
        while (m_busy) @(posedge aclk);
        @(negedge aclk);
        m_addr = a; m_is_read = 1'b1; m_start = 1'b1;
        @(negedge aclk); m_start = 1'b0;
        n = 0; hung = 1'b0;
        while (!m_done && n < TMO) begin @(posedge aclk); n++; end
        if (n >= TMO) begin hung = 1'b1; last_resp = 2'b11; last_rdata = 32'hDEADDEAD; last_lat = 0; end
        else begin last_resp = m_resp; last_rdata = m_rdata; last_lat = m_latency; end
        @(posedge aclk);
    endtask
    // read, return the data only
    task automatic rdv(input logic [AW_B-1:0] a, output logic [31:0] v);
        rd(a); v = last_rdata;
    endtask
    function automatic string hexs(input logic [31:0] v); return $sformatf("0x%08x", v); endfunction

    // ---- reset
    task automatic do_reset(input int n = 4);
        raw_en = 1'b0;
        @(negedge aclk); aresetn = 1'b0;
        repeat (n) @(negedge aclk);
        aresetn = 1'b1;
        repeat (3) @(negedge aclk);
    endtask

    // ---- handshake cycle stamps (cyc as read at the edge: the clock edge the handshake completes on)
    int unsigned awcyc = 0, wcyc = 0, bcyc = 0, arcyc = 0, rcyc = 0;
    always @(posedge aclk) begin
        if (awvalid && awready) awcyc <= cyc;
        if (wvalid  && wready)  wcyc  <= cyc;
        if (bvalid  && bready)  bcyc  <= cyc;
        if (arvalid && arready) arcyc <= cyc;
        if (rvalid  && rready)  rcyc  <= cyc;
    end

    // ---- raw probes. Every raw task samples the handshakes AT the clock edge (values the edge sees), then changes its
    // drive 1 ns later. The raw drive owns the bus (raw_en) for the task's duration only.
    // outstanding_rd: two reads issued back to back with RREADY low for `hold` clocks, then released.
    int ar_hs, r_hs, r_before_release, ar_held;
    logic [31:0] raw_r0, raw_r1;
    logic [1:0]  raw_rr0, raw_rr1;
    task automatic outstanding_rd(input logic [AW_B-1:0] a0, input logic [AW_B-1:0] a1, input int hold = 24);
        int i, n_ar = 0; bit s_ar, s_r;
        raw_en = 1'b1; r_rready = 1'b0; r_arvalid = 1'b0; ar_hs = 0; r_hs = 0; r_before_release = 0; ar_held = 0;
        @(negedge aclk);
        r_araddr = a0; r_arvalid = 1'b1;
        for (i = 0; i < 4 * hold; i++) begin
            @(posedge aclk);
            s_ar = r_arvalid && arready; s_r = rvalid && r_rready;
            if (i < hold && rvalid) r_before_release = 1;
            #1;
            if (i < hold && s_ar) ar_held++;
            if (s_ar) begin ar_hs++; n_ar++; if (n_ar == 1) r_araddr = a1; else r_arvalid = 1'b0; end
            if (s_r) begin if (r_hs == 0) begin raw_r0 = rdata; raw_rr0 = rresp; end else if (r_hs == 1) begin raw_r1 = rdata; raw_rr1 = rresp; end r_hs++; end
            if (i == hold - 1) r_rready = 1'b1;
        end
        @(negedge aclk); r_arvalid = 1'b0; r_rready = 1'b0; raw_en = 1'b0;
        repeat (4) @(posedge aclk);
    endtask
    // outstanding_wr: two writes (AW+W together) issued back to back with BREADY low for `hold` clocks, then released.
    int aw_hs, w_hs, b_hs, b_before_release, aw_held, w_held;
    logic [1:0] raw_b0, raw_b1;
    task automatic outstanding_wr(input logic [AW_B-1:0] a0, input logic [31:0] d0, input logic [AW_B-1:0] a1,
                                  input logic [31:0] d1, input int hold = 24);
        int i, aw_n = 0, w_n = 0; bit s_aw, s_w, s_b;
        raw_en = 1'b1; r_bready = 1'b0; aw_hs = 0; w_hs = 0; b_hs = 0; b_before_release = 0; aw_held = 0; w_held = 0; r_wstrb = 4'hF;
        @(negedge aclk);
        r_awaddr = a0; r_wdata = d0; r_awvalid = 1'b1; r_wvalid = 1'b1;
        for (i = 0; i < 4 * hold; i++) begin
            @(posedge aclk);
            s_aw = r_awvalid && awready; s_w = r_wvalid && wready; s_b = bvalid && r_bready;
            if (i < hold && bvalid) b_before_release = 1;
            #1;
            if (i < hold && s_aw) aw_held++;
            if (i < hold && s_w) w_held++;
            if (s_aw) begin aw_hs++; aw_n++; if (aw_n == 1) r_awaddr = a1; else r_awvalid = 1'b0; end
            if (s_w)  begin w_hs++;  w_n++;  if (w_n == 1)  r_wdata = d1;  else r_wvalid = 1'b0; end
            if (s_b)  begin if (b_hs == 0) raw_b0 = bresp; else if (b_hs == 1) raw_b1 = bresp; b_hs++; end
            if (i == hold - 1) r_bready = 1'b1;
        end
        @(negedge aclk); r_awvalid = 1'b0; r_wvalid = 1'b0; r_bready = 1'b0; raw_en = 1'b0;
        repeat (4) @(posedge aclk);
    endtask
    // channel_alone: drive only AW (is_w = 0) or only W (is_w = 1) for `hold` clocks with BREADY high; report whether the
    // lone channel was accepted and whether a response came without the other channel. Then complete the write.
    bit alone_acc, alone_resp;
    task automatic channel_alone(input bit is_w, input logic [AW_B-1:0] a, input logic [31:0] d, input int hold = 20);
        int i; bit s_aw, s_w, s_b;
        raw_en = 1'b1; r_bready = 1'b1; alone_acc = 0; alone_resp = 0; r_wstrb = 4'hF;
        @(negedge aclk);
        r_awaddr = a; r_wdata = d;
        if (is_w) r_wvalid = 1'b1; else r_awvalid = 1'b1;
        for (i = 0; i < hold; i++) begin
            @(posedge aclk);
            s_aw = r_awvalid && awready; s_w = r_wvalid && wready; s_b = bvalid && r_bready;
            #1;
            if (is_w && s_w) begin alone_acc = 1; r_wvalid = 1'b0; end
            if (!is_w && s_aw) begin alone_acc = 1; r_awvalid = 1'b0; end
            if (s_b) alone_resp = 1;
        end
        // complete the transaction with the other channel
        @(negedge aclk);
        if (is_w) r_awvalid = 1'b1; else r_wvalid = 1'b1;
        for (i = 0; i < hold; i++) begin
            @(posedge aclk);
            s_aw = r_awvalid && awready; s_w = r_wvalid && wready;
            #1;
            if (s_aw) r_awvalid = 1'b0;
            if (s_w) r_wvalid = 1'b0;
        end
        @(negedge aclk); r_awvalid = 1'b0; r_wvalid = 1'b0; r_bready = 1'b0; raw_en = 1'b0;
        repeat (4) @(posedge aclk);
    endtask

    // ---- generic read scan of a window: lists words that are not (OKAY, 0); a hung access is reported and the IP reset
    bit scan_skip [4096];
    string scan_str; int scan_zero;
    task automatic scan_rd(input int unsigned base, input int unsigned words);
        logic [31:0] x;
        scan_str = ""; scan_zero = 0;
        for (int w = 0; w < words; w++) begin
            if (scan_skip[w]) continue;
            rdv(base + 4 * w, x);
            if (hung) begin scan_str = {scan_str, $sformatf("o%0x=HANG ", 4 * w)}; do_reset(4); end
            else if (last_resp != 2'b00 || x != 0) scan_str = {scan_str, $sformatf("o%0x=%s/%s ", 4 * w, hexs(x), rname(last_resp))};
            else scan_zero++;
        end
    endtask

    // ---- generic register discovery, for an IP whose map is not known to the bench: from reset, read every word of the
    // window, then for each word w: reset, write `pat` to w, read w back, read every other word and list those that changed
    // (an alias or a linked register). Reads may have side effects (a FIFO pop): a word that reads differently twice in
    // a row at reset is listed as `volatile`.
    string disc_reset, disc_rb, disc_alias, disc_volatile, disc_wresp; int disc_rmask, disc_wmask, disc_hangs;
    logic [31:0] disc_b0 [1024];
    task automatic discover(input int unsigned words, input logic [31:0] pat);
        logic [31:0] x, y;
        disc_reset = ""; disc_rb = ""; disc_alias = ""; disc_volatile = ""; disc_rmask = 0; disc_wmask = 0; disc_hangs = 0; disc_wresp = "";
        do_reset(4);
        for (int w = 0; w < words; w++) begin
            rdv(4 * w, x); disc_b0[w] = x; disc_rmask |= 1 << last_resp;
            if (hung) begin disc_hangs++; do_reset(4); end
            if (x != 0 || last_resp != 2'b00) disc_reset = {disc_reset, $sformatf("o%0x=%s/%s ", 4 * w, hexs(x), rname(last_resp))};
        end
        for (int w = 0; w < words; w++) begin
            do_reset(3); wr(4 * w, pat); disc_wmask |= 1 << last_resp;
            if (hung) begin disc_hangs++; do_reset(4); disc_wresp = {disc_wresp, $sformatf("o%0x=HANG ", 4 * w)}; continue; end
            if (last_resp != 2'b00) disc_wresp = {disc_wresp, $sformatf("o%0x=%s ", 4 * w, rname(last_resp))};
            rdv(4 * w, x);
            if (x !== disc_b0[w]) disc_rb = {disc_rb, $sformatf("o%0x=%s ", 4 * w, hexs(x))};
            for (int w2 = 0; w2 < words; w2++) begin
                if (w2 == w) continue;
                rdv(4 * w2, y);
                if (hung) begin disc_hangs++; do_reset(4); end
                else if (y !== disc_b0[w2]) disc_alias = {disc_alias, $sformatf("o%0x->o%0x ", 4 * w, 4 * w2)};
            end
        end
        do_reset(4);
        for (int w = 0; w < words; w++) begin
            rdv(4 * w, x); rdv(4 * w, y);
            if (x !== y) disc_volatile = {disc_volatile, $sformatf("o%0x ", 4 * w)};
        end
        do_reset(4);
    endtask
    task automatic report_discover(input string name);
        rep({name, "_reset_nonzero"}, disc_reset);
        rep({name, "_write_readback"}, {$sformatf("pattern_written; words_that_read_differently_after_write: "), disc_rb});
        rep({name, "_write_links"}, {"write_to_word->other_word_changed: ", disc_alias});
        rep({name, "_responses"}, $sformatf("read_resp_mask=0x%x write_resp_mask=0x%x (bit0 OKAY bit1 EXOKAY bit2 SLVERR bit3 DECERR) hangs=%0d non_okay_writes: %s volatile_reads: %s", disc_rmask, disc_wmask, disc_hangs, disc_wresp, disc_volatile));
    endtask

    // ---- bus_tail: the access-level probes every bench shares, run on one plain read/write register `wa` (reads back what is
    // written, low bits at least) and a second register `wb` for the outstanding probes. Latency, AW/W order, WSTRB,
    // unaligned addresses, outstanding transactions, a lone AW or W.
    task automatic bus_tail(input logic [AW_B-1:0] wa, input logic [AW_B-1:0] wb, input bit has_wstrb = 1'b1, input string no_wstrb_text = "no_wstrb_port=1");
        logic [31:0] a, b, c;
        do_reset(4);
        wr(wa, 32'h5); a = last_lat; rd(wa); b = last_lat; rep("latency", $sformatf("write=%0d read=%0d", a, b));
        wr(wa, 32'h1, 4'hF, 1); rdv(wa, a); wr(wa, 32'h2, 4'hF, 2); rdv(wa, b);
        rep("aw_w_order", $sformatf("aw_first=%s w_first=%s hung=%0d", hexs(a), hexs(b), hung));
        if (has_wstrb) begin
            wr(wa, 32'h0); wr(wa, 32'h3, 4'b0000); rdv(wa, a);
            wr(wa, 32'h0); wr(wa, 32'h0000_0300, 4'b0001); rdv(wa, b);
            wr(wa, 32'h0); wr(wa, 32'h0000_0300, 4'b0010); rdv(wa, c);
            rep("wstrb", $sformatf("from_0: write_3_strb0000=%s write_0x300_strb0001=%s write_0x300_strb0010=%s", hexs(a), hexs(b), hexs(c)));
        end else rep("wstrb", no_wstrb_text);
        wr(wa, 32'h0); wr(wa + 1, 32'h3); rdv(wa, a); wr(wa, 32'h0); wr(wa + 2, 32'h3); rdv(wa, b); wr(wa, 32'h0); wr(wa + 3, 32'h3); rdv(wa, c);
        rep("unaligned_write", $sformatf("write_at_wa+1_reads_wa=%s write_at_wa+2_reads_wa=%s write_at_wa+3_reads_wa=%s", hexs(a), hexs(b), hexs(c)));
        wr(wa, 32'h3); rdv(wa + 1, a); rdv(wa + 2, b); rdv(wa + 3, c);
        rep("unaligned_read", $sformatf("wa_holds_3: read_wa+1=%s read_wa+2=%s read_wa+3=%s", hexs(a), hexs(b), hexs(c)));
        wr(wa, 32'h0);
        outstanding_rd(wa, wb, 24);
        rep("outstanding_rd", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_wr(wa, 32'h1, wb, 32'h2, 24); rdv(wa, a); rdv(wb, b);
        rep("outstanding_wr", $sformatf("aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_valid_while_low=%0d b_total=%0d wa=%s wb=%s", aw_held, w_held, b_before_release, b_hs, hexs(a), hexs(b)));
        channel_alone(1'b0, wa, 32'h1, 20); rdv(wa, a);
        rep("aw_alone", $sformatf("aw_accepted=%0d b_without_w=%0d wa_after_completion=%s", alone_acc, alone_resp, hexs(a)));
        channel_alone(1'b1, wa, 32'h2, 20); rdv(wa, a);
        rep("w_alone", $sformatf("w_accepted=%0d b_without_aw=%0d wa_after_completion=%s", alone_acc, alone_resp, hexs(a)));
    endtask

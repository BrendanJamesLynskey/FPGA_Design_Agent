// sg_dma.sv: a scatter-gather DMA engine between an AXI4 memory-mapped master and one AXI4-Stream port, driven by a ring of
// descriptors in memory and an AXI4-Lite control port (brief 241; owner decision 28: favour AMBA AXI).
//
// DIR = 0 (MM2S): memory to stream. Each descriptor names a source buffer; the engine reads it in INCR bursts and sends the beats on
//                 m_axis_*, with tlast on the last beat of the descriptor's buffer.
// DIR = 1 (S2MM): stream to memory. Each descriptor names a destination buffer of LEN bytes; the engine takes exactly LEN bytes from
//                 s_axis_* (tlast is ignored) and writes them in INCR bursts. The stream port of the other direction is tied off.
//
// A descriptor is 16 bytes, four little-endian 32-bit words, in a ring of RING_SIZE entries at RING_BASE (registers, below):
//   word 0  buffer address, bits 31:0
//   word 1  buffer address, bits 63:32 (bits above ADDR_W are ignored)
//   word 2  [23:0] length in bytes; [31] IOC (raise the interrupt when this descriptor completes, ahead of the coalescing count)
//   word 3  status, written by the engine only: [31] DONE, [30] ERR (an SLVERR or DECERR on a data beat), [29] BAD (misaligned or
//           zero-length descriptor, nothing moved), [25:24] the first non-OKAY response code, [23:0] bytes moved
// The buffer address and the length must be multiples of DATA_W/8 bytes, and the length at least one beat; otherwise the descriptor is
// completed with BAD set and nothing is moved. Software writes words 0 to 2, then advances HEAD; the engine owns the entry from the
// HEAD write until word 3 shows DONE, and software must not touch it in between (the driver contract, DATASHEET.md).
//
// Bursts: INCR only, AxSIZE = log2(DATA_W/8), at most MAX_BURST beats, never across a 4 KB boundary (AXI4 A3.4.1); up to OUTSTANDING
// data bursts are issued ahead of their data (MM2S) or of their response (S2MM). Descriptor fetch, data and status write-back run one
// descriptor at a time: there is no descriptor prefetch (a gap, DATASHEET.md). ID signals are not carried (every transaction has the
// same ID, so responses return in order). AxCACHE is the parameter AXCACHE on every transaction; the engine does no cache maintenance.
//
// Registers (AXI4-Lite, 32 bit, word aligned; addr[5:2] selects, wstrb is ignored, an unmapped read returns 0, an unmapped write is
// dropped, both with OKAY):
//   0x00 CTRL        [0] RUN, [1] IRQ_EN
//   0x04 STATUS      [0] IDLE (ro), [1] HALTED (sticky, write 1 to clear), [2] IRQ (sticky, write 1 to clear; also clears the coalescing count)
//   0x08 RING_LO     ring base address bits 31:4 (bits 3:0 read 0: the ring is 16-byte aligned)
//   0x0C RING_HI     ring base address bits 63:32
//   0x10 RING_SIZE   entries in the ring (1 to 65535); 0 keeps the engine idle
//   0x14 HEAD        producer index written by software (must stay below RING_SIZE)
//   0x18 TAIL        consumer index (ro): the next entry the engine will take
//   0x1C IRQ_THRESH  completions per interrupt (0 behaves as 1); the interrupt also fires when the ring drains, or at once on an IOC descriptor
//   0x20 DONE_COUNT  descriptors completed since reset (ro, wraps at 2^32)
//   0x24 ERR         [1:0] first non-OKAY data response of the latest error, [2] descriptor fetch or status write failed (the engine halts),
//                    [3] a data beat answered SLVERR or DECERR (sticky); write 1 to clear a bit
// Reset: aresetn, active low, synchronous; every register is 0.
module sg_dma #(
    parameter int ADDR_W      = 32,
    parameter int DATA_W      = 32,
    parameter int MAX_BURST   = 16,
    parameter int OUTSTANDING = 4,
    parameter int DIR         = 0,
    parameter int AXCACHE     = 3
) (
    input  logic                 aclk,
    input  logic                 aresetn,
    // AXI4-Lite control slave
    input  logic                 s_axi_awvalid,
    output logic                 s_axi_awready,
    input  logic [5:0]           s_axi_awaddr,
    input  logic                 s_axi_wvalid,
    output logic                 s_axi_wready,
    input  logic [31:0]          s_axi_wdata,
    input  logic [3:0]           s_axi_wstrb,
    output logic                 s_axi_bvalid,
    input  logic                 s_axi_bready,
    output logic [1:0]           s_axi_bresp,
    input  logic                 s_axi_arvalid,
    output logic                 s_axi_arready,
    input  logic [5:0]           s_axi_araddr,
    output logic                 s_axi_rvalid,
    input  logic                 s_axi_rready,
    output logic [31:0]          s_axi_rdata,
    output logic [1:0]           s_axi_rresp,
    // AXI4 memory-mapped master
    output logic                 m_axi_awvalid,
    input  logic                 m_axi_awready,
    output logic [ADDR_W-1:0]    m_axi_awaddr,
    output logic [7:0]           m_axi_awlen,
    output logic [2:0]           m_axi_awsize,
    output logic [1:0]           m_axi_awburst,
    output logic [3:0]           m_axi_awcache,
    output logic                 m_axi_wvalid,
    input  logic                 m_axi_wready,
    output logic [DATA_W-1:0]    m_axi_wdata,
    output logic [DATA_W/8-1:0]  m_axi_wstrb,
    output logic                 m_axi_wlast,
    input  logic                 m_axi_bvalid,
    output logic                 m_axi_bready,
    input  logic [1:0]           m_axi_bresp,
    output logic                 m_axi_arvalid,
    input  logic                 m_axi_arready,
    output logic [ADDR_W-1:0]    m_axi_araddr,
    output logic [7:0]           m_axi_arlen,
    output logic [2:0]           m_axi_arsize,
    output logic [1:0]           m_axi_arburst,
    output logic [3:0]           m_axi_arcache,
    input  logic                 m_axi_rvalid,
    output logic                 m_axi_rready,
    input  logic [DATA_W-1:0]    m_axi_rdata,
    input  logic [1:0]           m_axi_rresp,
    input  logic                 m_axi_rlast,
    // AXI4-Stream: s_axis is used when DIR = 1, m_axis when DIR = 0
    input  logic                 s_axis_tvalid,
    output logic                 s_axis_tready,
    input  logic [DATA_W-1:0]    s_axis_tdata,
    output logic                 m_axis_tvalid,
    input  logic                 m_axis_tready,
    output logic [DATA_W-1:0]    m_axis_tdata,
    output logic                 m_axis_tlast,
    output logic                 irq
);
    localparam int BYTES  = DATA_W / 8;
    localparam int BSH    = $clog2(BYTES);
    localparam int DBEATS = 16 / BYTES;
    localparam int OCW    = $clog2(OUTSTANDING + 1);

    initial begin
        if (DATA_W != 32 && DATA_W != 64 && DATA_W != 128) $error("sg_dma: DATA_W must be 32, 64 or 128");
        if (ADDR_W < 32 || ADDR_W > 64) $error("sg_dma: ADDR_W must be 32 to 64");
        if (MAX_BURST < 1 || MAX_BURST > 256) $error("sg_dma: MAX_BURST must be 1 to 256");
        if (OUTSTANDING < 1 || OUTSTANDING > 16) $error("sg_dma: OUTSTANDING must be 1 to 16");
        if (DIR != 0 && DIR != 1) $error("sg_dma: DIR must be 0 (MM2S) or 1 (S2MM)");
    end

    localparam logic [2:0] S_IDLE = 3'd0, S_DAR = 3'd1, S_DRD = 3'd2, S_DEC = 3'd3, S_XFER = 3'd4, S_WA = 3'd5, S_WB = 3'd6;

    // ---- registers
    logic        run, irq_en, halted, irq_pend;
    logic [63:0] ring_base;
    logic [15:0] ring_size, head, tail, irq_thr, since_irq;
    logic [31:0] done_cnt;
    logic [3:0]  err_reg;

    logic [2:0]  st;
    logic [127:0] desc_sh;
    logic [1:0]  dbeat;
    logic [ADDR_W-1:0] a_addr;
    logic [23:0] a_rem, x_len;
    logic [8:0]  d_beat;
    logic [8:0]  a_n;                            // beats of the next burst, registered; valid only while a_ok
    logic        a_ok;                           // a_addr and a_rem have not changed for a clock, so a_n is their burst length
    localparam int PW = (OUTSTANDING > 1) ? $clog2(OUTSTANDING) : 1;
    logic [8:0]  bq_n [OUTSTANDING];             // burst lengths issued and not yet through the data side, oldest at rp
    logic        bq_last [OUTSTANDING];          // the burst is the last of its descriptor
    logic [PW-1:0] wp, rp;
    logic [OCW-1:0] out_cnt, w_ahead;
    logic        x_ioc, x_bad, x_err;
    logic [1:0]  x_code;
    logic        aw_done, desc_err;

    logic [ADDR_W-1:0] desc_addr;                // the entry being worked on, latched when it is taken: the ring registers may change under it
    wire [ADDR_W-1:0] wb_addr   = desc_addr + ADDR_W'(12);
    wire [23:0] dec_len = desc_sh[87:64];
    wire [31:0] status_word = {1'b1, x_err, x_bad, 3'b000, x_code, x_bad ? 24'd0 : x_len};

    // ---- burst split: beats of the burst that starts at address a (its low 12 bits matter) with rem bytes left. a_n registers it, so the
    // data-side counters see a flop and not this comparison.
    function automatic [8:0] nbeats(input [11:0] a, input [23:0] rem);
        reg [10:0] t;
        reg [23:0] remb;
        reg [8:0]  r, n;
        begin
            t    = 11'((13'd4096 - {1'b0, a}) >> BSH);          // beats to the 4 KB boundary, 1 to 1024
            remb = rem >> BSH;
            r    = (|remb[23:9]) ? 9'h1FF : remb[8:0];
            n    = 9'(MAX_BURST);
            if (t < 11'(MAX_BURST)) n = t[8:0];
            if (r < n) n = r;
            nbeats = n;
        end
    endfunction

    wire [23:0] a_bytes = {15'd0, a_n} << BSH;
    wire        fifo_nz = (DIR == 0) ? (out_cnt != '0) : (w_ahead != '0);     // a burst has been addressed and its data is not all through
    wire [8:0]  d_n     = bq_n[rp];
    wire        d_last  = bq_last[rp];

    wire issue_ok = (st == S_XFER) && (a_rem != 24'd0) && (out_cnt < OCW'(OUTSTANDING)) && a_ok;
    wire desc_ok  = run && !halted && (ring_size != 16'd0) && (head != tail);

    // ---- AXI4 master: address channels
    assign m_axi_arvalid = (st == S_DAR) || (DIR == 0 && issue_ok);
    assign m_axi_araddr  = (st == S_DAR) ? desc_addr : a_addr;
    assign m_axi_arlen   = (st == S_DAR) ? 8'(DBEATS - 1) : 8'(a_n - 9'd1);
    assign m_axi_arsize  = 3'(BSH);
    assign m_axi_arburst = 2'b01;
    assign m_axi_arcache = 4'(AXCACHE);

    assign m_axi_awvalid = (st == S_WA && !aw_done) || (DIR == 1 && issue_ok);
    assign m_axi_awaddr  = (st == S_WA) ? wb_addr : a_addr;
    assign m_axi_awlen   = (st == S_WA) ? 8'd0 : 8'(a_n - 9'd1);
    assign m_axi_awsize  = (st == S_WA) ? 3'd2 : 3'(BSH);
    assign m_axi_awburst = 2'b01;
    assign m_axi_awcache = 4'(AXCACHE);

    // ---- AXI4 master: read data. Descriptor beats are taken here; data beats go to m_axis (DIR = 0).
    wire data_phase = (st == S_XFER);
    assign m_axi_rready  = (st == S_DRD) || (DIR == 0 && data_phase && m_axis_tready && fifo_nz);     // data only for a burst that was addressed
    assign m_axis_tvalid = (DIR == 0) && data_phase && m_axi_rvalid && fifo_nz;
    assign m_axis_tdata  = m_axi_rdata;
    assign m_axis_tlast  = (DIR == 0) && d_last && (d_beat == d_n - 9'd1);

    // ---- AXI4 master: write data. Status write (one 32-bit lane) or stream beats (DIR = 1).
    wire        w_data_ok = (DIR == 1) && data_phase && (w_ahead != '0);
    wire [1:0]  lane      = wb_addr[3:2] & 2'((BYTES >> 2) - 1);      // which 32-bit lane of the beat the status word sits in
    assign m_axi_wvalid = (st == S_WA && aw_done) || (w_data_ok && s_axis_tvalid);   // the status data follows its address
    assign m_axi_wdata  = (st == S_WA) ? {(DATA_W/32){status_word}} : s_axis_tdata;
    assign m_axi_wstrb  = (st == S_WA) ? (({{(DATA_W/8-4){1'b0}}, 4'hF}) << (4 * lane)) : {(DATA_W/8){1'b1}};
    assign m_axi_wlast  = (st == S_WA) ? 1'b1 : (d_beat == d_n - 9'd1);
    assign s_axis_tready = w_data_ok && m_axi_wready;
    assign m_axi_bready = (DIR == 1 && data_phase && out_cnt != w_ahead) || (st == S_WB);     // a data response only for a burst whose data has all gone

    wire ar_hs = m_axi_arvalid && m_axi_arready;
    wire aw_hs = m_axi_awvalid && m_axi_awready;
    wire w_hs  = m_axi_wvalid && m_axi_wready;
    wire b_hs  = m_axi_bvalid && m_axi_bready;
    wire r_hs  = m_axi_rvalid && m_axi_rready;
    wire a_hs  = (DIR == 0) ? ar_hs : aw_hs;
    wire d_beat_hs = (DIR == 0) ? (data_phase && r_hs) : (data_phase && w_hs);
    wire d_burst_end = d_beat_hs && (d_beat == d_n - 9'd1);
    wire x_done = (a_rem == 24'd0) && (out_cnt == '0);

    wire [15:0] tail_next = (tail + 16'd1 == ring_size) ? 16'd0 : tail + 16'd1;

    // ---- control registers (AXI4-Lite)
    wire reg_wr = s_axi_awvalid && s_axi_wvalid && !s_axi_bvalid;
    wire reg_rd = s_axi_arvalid && !s_axi_rvalid;
    assign s_axi_awready = reg_wr;
    assign s_axi_wready  = reg_wr;
    assign s_axi_bresp   = 2'b00;
    assign s_axi_arready = reg_rd;
    assign s_axi_rresp   = 2'b00;
    assign irq = irq_en && irq_pend;

    function automatic [31:0] reg_read(input [3:0] w);
        case (w)
            4'd0: reg_read = {30'd0, irq_en, run};
            4'd1: reg_read = {29'd0, irq_pend, halted, st == S_IDLE};
            4'd2: reg_read = ring_base[31:0];
            4'd3: reg_read = ring_base[63:32];
            4'd4: reg_read = {16'd0, ring_size};
            4'd5: reg_read = {16'd0, head};
            4'd6: reg_read = {16'd0, tail};
            4'd7: reg_read = {16'd0, irq_thr};
            4'd8: reg_read = done_cnt;
            4'd9: reg_read = {28'd0, err_reg};
            default: reg_read = 32'd0;
        endcase
    endfunction

    wire [15:0] n_done = since_irq + 16'd1;
    wire fire = x_ioc || (n_done >= ((irq_thr == 16'd0) ? 16'd1 : irq_thr)) || (tail_next == head);

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            run <= 1'b0; irq_en <= 1'b0; halted <= 1'b0; irq_pend <= 1'b0;
            ring_base <= '0; ring_size <= '0; head <= '0; tail <= '0; irq_thr <= '0; since_irq <= '0; done_cnt <= '0; err_reg <= '0;
            st <= S_IDLE; desc_addr <= '0; desc_sh <= '0; dbeat <= '0; a_addr <= '0; a_rem <= '0; x_len <= '0; d_beat <= '0; a_n <= '0; a_ok <= 1'b0; wp <= '0; rp <= '0;
            out_cnt <= '0; w_ahead <= '0; x_ioc <= 1'b0; x_bad <= 1'b0; x_err <= 1'b0; x_code <= 2'b00; aw_done <= 1'b0; desc_err <= 1'b0;
            s_axi_bvalid <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rdata <= '0;
        end else begin
            // AXI4-Lite response channels
            if (reg_wr) begin
                s_axi_bvalid <= 1'b1;
                case (s_axi_awaddr[5:2])
                    4'd0: begin run <= s_axi_wdata[0]; irq_en <= s_axi_wdata[1]; end
                    4'd1: begin
                        if (s_axi_wdata[1]) halted <= 1'b0;
                        if (s_axi_wdata[2]) begin irq_pend <= 1'b0; since_irq <= 16'd0; end
                    end
                    4'd2: ring_base[31:4]  <= s_axi_wdata[31:4];           // the ring is 16-byte aligned: bits 3:0 are 0
                    4'd3: ring_base[63:32] <= s_axi_wdata;
                    4'd4: ring_size <= s_axi_wdata[15:0];
                    4'd5: head <= s_axi_wdata[15:0];
                    4'd7: irq_thr <= s_axi_wdata[15:0];
                    4'd9: err_reg <= err_reg & ~s_axi_wdata[3:0];
                    default: ;
                endcase
            end else if (s_axi_bready) s_axi_bvalid <= 1'b0;
            if (reg_rd) begin s_axi_rvalid <= 1'b1; s_axi_rdata <= reg_read(s_axi_araddr[5:2]); end
            else if (s_axi_rready) s_axi_rvalid <= 1'b0;

            // the engine
            case (st)
                S_IDLE: if (desc_ok) begin
                    st <= S_DAR; dbeat <= 2'd0; desc_err <= 1'b0;
                    desc_addr <= ring_base[ADDR_W-1:0] + {{(ADDR_W-20){1'b0}}, tail, 4'b0000};
                end
                S_DAR: if (ar_hs) st <= S_DRD;
                S_DRD: if (r_hs) begin
                    desc_sh <= (desc_sh >> DATA_W) | ({{(128-DATA_W){1'b0}}, m_axi_rdata} << (128 - DATA_W));
                    if (m_axi_rresp != 2'b00) desc_err <= 1'b1;
                    if (dbeat == 2'(DBEATS - 1)) begin                 // every beat of the burst is taken, whatever its response
                        if (desc_err || m_axi_rresp != 2'b00) begin
                            halted <= 1'b1; err_reg[2] <= 1'b1; st <= S_IDLE;     // descriptor fetch failed: halt, tail not advanced
                        end else st <= S_DEC;
                    end else dbeat <= dbeat + 2'd1;
                end
                S_DEC: begin
                    a_addr <= desc_sh[ADDR_W-1:0];
                    a_rem <= desc_sh[87:64]; x_len <= desc_sh[87:64];
                    x_ioc <= desc_sh[95]; a_ok <= 1'b0; d_beat <= 9'd0; out_cnt <= '0; w_ahead <= '0; wp <= '0; rp <= '0;
                    x_err <= 1'b0; x_code <= 2'b00; aw_done <= 1'b0;
                    if (dec_len == 24'd0 || (|(dec_len & 24'(BYTES - 1))) || (|(desc_sh[31:0] & 32'(BYTES - 1)))) begin
                        x_bad <= 1'b1; st <= S_WA;
                    end else begin
                        x_bad <= 1'b0; st <= S_XFER;
                    end
                end
                S_XFER: begin
                    // address side: one burst per handshake; a_n follows the new address a clock later (a_ok low in between)
                    a_n <= nbeats(a_addr[11:0], a_rem);
                    a_ok <= !a_hs;
                    if (a_hs) begin
                        a_addr <= a_addr + ADDR_W'(a_bytes);
                        a_rem  <= a_rem - a_bytes;
                        bq_n[wp] <= a_n;
                        bq_last[wp] <= (a_rem == a_bytes);
                        wp <= (wp == PW'(OUTSTANDING - 1)) ? '0 : wp + 1'b1;
                    end
                    // data side: bursts come off the queue in the order they were addressed
                    if (d_beat_hs) begin
                        if (d_beat == d_n - 9'd1) begin
                            d_beat <= 9'd0;
                            rp <= (rp == PW'(OUTSTANDING - 1)) ? '0 : rp + 1'b1;
                        end else d_beat <= d_beat + 9'd1;
                        if (DIR == 0 && m_axi_rresp != 2'b00) begin
                            if (!x_err) x_code <= m_axi_rresp;
                            x_err <= 1'b1; err_reg[3] <= 1'b1; err_reg[1:0] <= m_axi_rresp;
                        end
                    end
                    // outstanding bursts: issued, minus finished (R last beat for MM2S, B response for S2MM)
                    if (DIR == 0) begin
                        out_cnt <= out_cnt + OCW'(ar_hs) - OCW'(d_burst_end);
                    end else begin
                        out_cnt <= out_cnt + OCW'(aw_hs) - OCW'(b_hs && out_cnt != '0);       // a response with nothing outstanding is ignored
                        w_ahead <= w_ahead + OCW'(aw_hs) - OCW'(d_burst_end);
                        if (b_hs && m_axi_bresp != 2'b00) begin
                            if (!x_err) x_code <= m_axi_bresp;
                            x_err <= 1'b1; err_reg[3] <= 1'b1; err_reg[1:0] <= m_axi_bresp;
                        end
                    end
                    if (x_done) st <= S_WA;
                end
                S_WA: begin
                    if (aw_hs) aw_done <= 1'b1;
                    if (w_hs) st <= S_WB;
                end
                S_WB: if (b_hs) begin
                    st <= S_IDLE;
                    if (m_axi_bresp != 2'b00) begin
                        halted <= 1'b1; err_reg[2] <= 1'b1;                      // status write failed: halt, tail not advanced
                    end else begin
                        tail <= tail_next;
                        done_cnt <= done_cnt + 32'd1;
                        if (fire) begin irq_pend <= 1'b1; since_irq <= 16'd0; end
                        else since_irq <= n_done;
                    end
                end
                default: st <= S_IDLE;
            endcase
        end
    end
`ifdef FORMAL
    // Invariants for the k-induction proofs (formal/formal_sg_dma.sv): facts about the engine's own registers that hold in every reachable state.
    wire [PW:0] f_cnt = (DIR == 0) ? out_cnt : w_ahead;
    always @(*) if (aresetn) begin
        i_desc: assert (desc_addr[3:0] == 4'd0 && ring_base[3:0] == 4'd0);
        if (st == S_XFER) begin
            i_align_addr: assert ((a_addr & ADDR_W'(BYTES - 1)) == 0);
            i_align_rem: assert ((a_rem & 24'(BYTES - 1)) == 0);
            i_out: assert (out_cnt <= OCW'(OUTSTANDING));
            if (DIR == 1) i_ahead: assert (w_ahead <= out_cnt);
            i_an: assert (!a_ok || a_n == nbeats(a_addr[11:0], a_rem));
            i_ptr: assert (int'(wp) < OUTSTANDING && int'(rp) < OUTSTANDING && ((int'(wp) - int'(rp) + OUTSTANDING) % OUTSTANDING) == (int'(f_cnt) % OUTSTANDING));
            i_beat: assert (f_cnt == '0 ? d_beat == 9'd0 : d_beat < d_n);
        end
    end
    // every queued burst length is between 1 and MAX_BURST
    generate for (genvar k = 0; k < OUTSTANDING; k++) begin : g_fq
        always @(*) if (aresetn && st == S_XFER && ((k - int'(rp) + OUTSTANDING) % OUTSTANDING) < int'(f_cnt))
            i_fifo: assert (bq_n[k] != 9'd0 && bq_n[k] <= 9'(MAX_BURST));
    end endgenerate
`ifdef COVER
    always @(posedge aclk) if (aresetn) begin
        i_desc__ante: cover (st == S_DAR);
        i_align_addr__ante: cover (st == S_XFER);
        i_align_rem__ante: cover (st == S_XFER);
        i_out__ante: cover (st == S_XFER && out_cnt != '0);
        if (DIR == 1) i_ahead__ante: cover (st == S_XFER && w_ahead != '0);
        i_an__ante: cover (st == S_XFER && a_ok);
        i_ptr__ante: cover (st == S_XFER && f_cnt != '0);
        i_fifo__ante: cover (st == S_XFER && f_cnt != '0);
        i_beat__ante: cover (st == S_XFER && f_cnt != '0 && d_beat != 9'd0);
    end
`endif
`endif
endmodule

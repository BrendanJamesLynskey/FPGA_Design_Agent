// axil_demo_periph: our own small AXI4-Lite peripheral, the brief 59A demonstration target, with seeded bugs that a
// run-time input selects (so one bitstream shows the clean peripheral and each bug).
//
// Registers (byte offset within its 4 KB window):
//   0x00 ID     RO  0x5950_4C31                 0x04-0x10 R0-R3  RW, byte strobes honoured
//   0x14 COUNT  RO  clocks counted while run_en is high  0x18 WCOUNT RO  writes done      0x1C BUG RO  bug_sel
//   writes to a read-only register: SLVERR; any address from 0x20 up: DECERR (reads return 0)
// Handshakes: AW and W are accepted independently (either may come first); BVALID one cycle after both are held;
// AWREADY/WREADY/ARREADY stall in a fixed pseudo-random pattern (a 5-bit LFSR, one cycle in four low) when STALL = 1.
// COUNT and the stall LFSR start from reset and advance only while run_en is high (the transactor runs), so a run is
// cycle-for-cycle repeatable: the board and the simulation see the same READY pattern and read the same COUNT values.
//
// bug_sel (0: none):
//   1 B_EARLY   BVALID raised as soon as AW is held, without waiting for W         -> rule 5 (B_EARLY) when W comes later
//   2 R_LIVE    RDATA not registered: follows the live register while RVALID waits -> rule 4 (R_HOLD) on COUNT, RREADY low
//   3 R_GLITCH  RVALID dropped for one cycle the first time it is stalled            -> rule 4 (R_HOLD) when RREADY is low
//   4 NO_STRB   WSTRB ignored: every write writes all four bytes                    -> no rule; the scoreboard catches it
//   5 EXOKAY    a write to R3 answers EXOKAY                                         -> rule 8 (EXOKAY)
/* verilator lint_off UNUSEDSIGNAL */   // the peripheral decodes only address bits 11:2 and ignores AxPROT
module axil_demo_periph #(
    parameter int STALL = 1
) (
    input  logic        aclk,
    input  logic        aresetn,
    input  logic [2:0]  bug_sel,
    input  logic        run_en,
    input  logic [31:0] s_awaddr,
    input  logic [2:0]  s_awprot,
    input  logic        s_awvalid,
    output logic        s_awready,
    input  logic [31:0] s_wdata,
    input  logic [3:0]  s_wstrb,
    input  logic        s_wvalid,
    output logic        s_wready,
    output logic [1:0]  s_bresp,
    output logic        s_bvalid,
    input  logic        s_bready,
    input  logic [31:0] s_araddr,
    input  logic [2:0]  s_arprot,
    input  logic        s_arvalid,
    output logic        s_arready,
    output logic [31:0] s_rdata,
    output logic [1:0]  s_rresp,
    output logic        s_rvalid,
    input  logic        s_rready
);
    logic [31:0] r [4];
    logic [31:0] count = '0, wcount = '0;
    logic        aw_full = 1'b0, w_full = 1'b0, early = 1'b0, bv = 1'b0, rv = 1'b0, glitched = 1'b0, gap = 1'b0;
    logic [11:0] aw_a = '0, ar_a = '0;
    logic [31:0] w_d = '0, rd_r = '0;
    logic [3:0]  w_s = '0;
    logic [1:0]  b_r = '0, r_r = '0;
    logic [4:0]  stl = 5'h1;
    initial for (int i = 0; i < 4; i++) r[i] = '0;

    wire stall = (STALL != 0) && (stl[1:0] == 2'b00);
    assign s_awready = !aw_full && !stall;
    assign s_wready  = !w_full && !stall;
    assign s_arready = !rv && !stall;
    assign s_bvalid  = bv;
    assign s_bresp   = b_r;
    assign s_rvalid  = rv && !gap;
    assign s_rresp   = r_r;

    function automatic logic [31:0] rd_val(input logic [11:0] a);
        case (a[11:2])
            10'd0: rd_val = 32'h5950_4C31;
            10'd1: rd_val = r[0];
            10'd2: rd_val = r[1];
            10'd3: rd_val = r[2];
            10'd4: rd_val = r[3];
            10'd5: rd_val = count;
            10'd6: rd_val = wcount;
            10'd7: rd_val = 32'(bug_sel);
            default: rd_val = 32'h0;
        endcase
    endfunction
    function automatic logic [1:0] rd_resp(input logic [11:0] a);
        rd_resp = (a[11:2] < 10'd8) ? 2'b00 : 2'b11;
    endfunction
    // bug 2's live read path, written out (a function call in a continuous assignment is not re-evaluated by every
    // simulator when a register it reads changes)
    logic [31:0] live;
    always_comb begin
        case (ar_a[11:2])
            10'd0: live = 32'h5950_4C31;
            10'd1: live = r[0];
            10'd2: live = r[1];
            10'd3: live = r[2];
            10'd4: live = r[3];
            10'd5: live = count;
            10'd6: live = wcount;
            10'd7: live = 32'(bug_sel);
            default: live = 32'h0;
        endcase
    end
    assign s_rdata = (bug_sel == 3'd2) ? live : rd_r;

    wire awhs = s_awvalid && s_awready, whs = s_wvalid && s_wready, bhs = bv && s_bready;
    wire arhs = s_arvalid && s_arready, rhs = s_rvalid && s_rready;
    wire [3:0]  strb_eff = (bug_sel == 3'd4) ? 4'hF : w_s;
    wire [31:0] bm = {{8{strb_eff[3]}}, {8{strb_eff[2]}}, {8{strb_eff[1]}}, {8{strb_eff[0]}}};

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            count <= '0; stl <= 5'h1;
        end else if (run_en) begin
            count <= count + 1'b1;
            stl   <= {stl[3:0], stl[4] ^ stl[2]};
        end
        if (!aresetn) begin
            aw_full <= 1'b0; w_full <= 1'b0; early <= 1'b0; bv <= 1'b0; rv <= 1'b0; glitched <= 1'b0; gap <= 1'b0;
            for (int i = 0; i < 4; i++) r[i] <= '0;
            wcount <= '0;
        end else begin
            // ---- write path
            if (awhs) begin aw_full <= 1'b1; aw_a <= s_awaddr[11:0]; end
            if (whs)  begin w_full  <= 1'b1; w_d  <= s_wdata; w_s <= s_wstrb; end
            if (bhs) bv <= 1'b0;
            if (bug_sel == 3'd1 && aw_full && !w_full && !bv && !early) begin
                bv <= 1'b1; early <= 1'b1;                                // bug 1: the response before the data
                b_r <= (aw_a[11:2] >= 10'd1 && aw_a[11:2] <= 10'd4) ? 2'b00 : (aw_a[11:2] < 10'd8 ? 2'b10 : 2'b11);
            end
            if (aw_full && w_full && (early || !bv)) begin
                aw_full <= 1'b0; w_full <= 1'b0;
                if (aw_a[11:2] >= 10'd1 && aw_a[11:2] <= 10'd4) begin
                    r[aw_a[3:2] - 2'd1] <= (r[aw_a[3:2] - 2'd1] & ~bm) | (w_d & bm);
                    wcount <= wcount + 1'b1;
                end
                if (early) early <= 1'b0;
                else begin
                    bv <= 1'b1;
                    b_r <= (aw_a[11:2] >= 10'd1 && aw_a[11:2] <= 10'd4) ? ((bug_sel == 3'd5 && aw_a[11:2] == 10'd4) ? 2'b01 : 2'b00)
                         : (aw_a[11:2] < 10'd8 ? 2'b10 : 2'b11);
                end
            end
            // ---- read path
            if (arhs) begin rv <= 1'b1; ar_a <= s_araddr[11:0]; rd_r <= rd_val(s_araddr[11:0]); r_r <= rd_resp(s_araddr[11:0]); glitched <= 1'b0; end
            gap <= 1'b0;
            if (bug_sel == 3'd3 && rv && !gap && !s_rready && !glitched) begin gap <= 1'b1; glitched <= 1'b1; end  // bug 3
            if (rhs) rv <= 1'b0;
        end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */

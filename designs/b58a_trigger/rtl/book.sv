// book.sv: top of book per instrument (best bid and ask, price and size, and the last trade price) in block RAM.
//
// The core reads an instrument's entry when the message's instrument field completes (rd_v) and has it on the next
// clock (q_*); the rule check uses that entry, which is the book before this message. When the message ends (upd_v)
// the entry is updated from the message (Bench Feed v1 semantics, docs/bench_feed_v1.md):
//   ADD     the side's best level becomes (price, size)
//   MODIFY  the same; a price that differs from the side's best is counted as a mismatch
//   CANCEL  the side becomes empty (price 0, size 0)
//   TRADE   last := price; at the side's best price the size falls by the traded size (empty at 0), otherwise mismatch
// Instruments >= NINST are outside the book: not read or written, counted. A second, read-only port serves the host.
// clear writes every entry to zero, one a clock (busy meanwhile; messages are not applied while busy).

module book #(
    parameter int NINST = 256           // instruments held; a power of two
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        clear,
    output logic        busy,
    input  logic        rd_v,
    input  logic [15:0] rd_inst,
    output logic [31:0] q_bid_px, q_bid_sz, q_ask_px, q_ask_sz, q_last,
    output logic        q_valid,        // the instrument read last is inside the book (held)
    input  logic        upd_v,
    input  logic [7:0]  upd_type,
    input  logic        upd_side,
    input  logic [31:0] upd_px,
    input  logic [31:0] upd_sz,
    output logic        ev_mismatch,
    output logic        ev_range,
    output logic        ev_bad_type,
    // host port
    input  logic [15:0] h_inst,
    output logic [159:0] h_q
);
    localparam int AW = $clog2(NINST);
    initial begin
        if (NINST < 2 || NINST > 4096 || (1 << AW) != NINST) $error("book: NINST must be a power of two in 2..4096 (got %0d)", NINST);
    end
    // entry: {last, ask_sz, ask_px, bid_sz, bid_px}. The RAM has plain ports (one write, two registered reads) so
    // that it maps to block RAM: port A reads at the instrument field and writes at the message end or while clearing;
    // port B is the host's read.
    (* ram_style = "block" *) logic [159:0] mem [NINST];
    logic [159:0]  q_raw;
    logic [AW-1:0] a_cur;
    logic          in_range;
    logic [AW:0]   clr_a;
    logic          we;
    logic [AW-1:0] wa;
    logic [159:0]  wd;

    assign busy = !clr_a[AW];

    // port A: the write or else the fast-path read (an update and a read never fall in one clock: a message's
    // instrument field is at least four bytes after the previous message's end); port B: the host
    logic [AW-1:0] aa;
    assign aa = we ? wa : rd_inst[AW-1:0];
    always_ff @(posedge clk) begin
        if (we) mem[aa] <= wd;
        else if (rd_v) q_raw <= mem[aa];
    end
    always_ff @(posedge clk) h_q <= mem[h_inst[AW-1:0]];
    logic [159:0] q;
    assign q = in_range ? q_raw : 160'd0;

    logic [31:0] bpx, bsz, apx, asz, lst, npx, nsz;
    logic        mism, upd_ok;
    always_comb begin
        {lst, asz, apx, bsz, bpx} = q;
        mism = 1'b0;
        npx = upd_side ? apx : bpx;
        nsz = upd_side ? asz : bsz;
        case (upd_type)
            8'h01: begin npx = upd_px; nsz = upd_sz; end
            8'h02: begin mism = (npx != upd_px); npx = upd_px; nsz = upd_sz; end
            8'h03: begin npx = '0; nsz = '0; end
            8'h04: begin
                lst = upd_px;
                if (npx == upd_px && nsz != 0) begin
                    nsz = (nsz > upd_sz) ? nsz - upd_sz : 32'd0;
                    if (nsz == 0) npx = '0;
                end else mism = 1'b1;
            end
            default: ;
        endcase
        upd_ok = upd_v && in_range && !busy && upd_type >= 8'h01 && upd_type <= 8'h04;
        we = busy || upd_ok;
        wa = busy ? clr_a[AW-1:0] : a_cur;
        wd = busy ? 160'd0 : (upd_side ? {lst, nsz, npx, bsz, bpx} : {lst, asz, apx, nsz, npx});
    end

    always_ff @(posedge clk) begin
        ev_mismatch <= 1'b0; ev_range <= 1'b0; ev_bad_type <= 1'b0;
        if (rst) begin
            clr_a <= '0; a_cur <= '0; in_range <= 1'b0;
        end else if (busy) begin
            clr_a <= clr_a + 1'b1;
        end else begin
            if (clear) clr_a <= '0;
            if (rd_v) begin
                in_range <= (rd_inst < 16'(NINST));
                a_cur    <= rd_inst[AW-1:0];
                if (!(rd_inst < 16'(NINST))) ev_range <= 1'b1;
            end else if (upd_v && in_range) begin
                if (upd_type == 8'h00 || upd_type > 8'h04) ev_bad_type <= 1'b1;
                else ev_mismatch <= mism;
            end
        end
    end
    assign {q_last, q_ask_sz, q_ask_px, q_bid_sz, q_bid_px} = q;
    assign q_valid = in_range;
endmodule

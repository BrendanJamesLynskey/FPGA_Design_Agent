// Reader side (clk_rd only): FIFO read pointer, slow-read gate, PRBS-31 check, reader counters, snapshot sender.
/* verilator lint_off DECLFILENAME */
module p5_rd_side #(
    parameter int          W           = 32,
    parameter logic [30:0] SEED        = 31'h7FFFFFFF,
    parameter int          SLOW_PERIOD = 8
) (
    input  logic           clk,
    input  logic           rst,         // active high, synchronous to clk
    input  logic           clr,         // CLEAR level (synchronised)
    input  logic           slow,        // SLOW_READ level (synchronised)
    input  logic           inj_lvl,     // INJECT pending level (synchronised)
    input  logic           snap_req,    // snapshot request toggle (synchronised)
    input  logic [9:0]     wgray,       // write pointer, gray, synchronised
    input  logic [31:0]    dout,        // RAM read data (head word)
    output logic [8:0]     raddr,
    output logic [9:0]     rgray,       // read pointer, gray, registered
    output logic           inj_done,
    output logic           err_flag,
    output logic           hs_send,
    output logic [3*W-1:0] hs_data,
    input  logic           hs_rcv
);
    localparam int SW = (SLOW_PERIOD > 1) ? $clog2(SLOW_PERIOD) : 1;

    logic [9:0]    rptr;
    logic [30:0]   prbs;
    logic [SW-1:0] slow_cnt;
    logic [W-1:0]  words_r, errs;
    logic          snap_q;
    logic [1:0]    st;

    wire hold  = rst | clr;
    wire empty = (rgray == wgray);
    wire allow = ~slow | (slow_cnt == '0);
    wire pop   = allow & ~empty & ~hold;

    wire [9:0] rptr_n = rptr + 10'd1;
    assign raddr = pop ? rptr_n[8:0] : rptr[8:0];

    logic [31:0] exp_word;
    logic [30:0] prbs_n;
    p5_prbs31 u_prbs (.s(prbs), .word(exp_word), .s_next(prbs_n));

    wire        inj_now = inj_lvl & ~inj_done;
    wire [31:0] got     = dout ^ {31'b0, inj_now};
    wire        mism    = (got != exp_word);

    always_ff @(posedge clk) begin
        if (rst) slow_cnt <= '0;
        else if (slow_cnt == SW'(SLOW_PERIOD - 1)) slow_cnt <= '0;
        else slow_cnt <= slow_cnt + SW'(1);

        if (hold) begin
            rptr    <= '0;
            rgray   <= '0;
            prbs    <= SEED;
            words_r <= '0;
            errs    <= '0;
        end else if (pop) begin
            rptr    <= rptr_n;
            rgray   <= rptr_n ^ (rptr_n >> 1);
            prbs    <= prbs_n;
            words_r <= words_r + W'(1);
            errs    <= errs + W'(mism);
        end

        if (rst) inj_done <= 1'b0;
        else     inj_done <= inj_lvl & (inj_done | pop);

        err_flag <= (errs != '0);

        if (rst) begin
            st     <= 2'd0;
            snap_q <= snap_req;
        end else begin
            case (st)
                2'd0: if (snap_req != snap_q) begin
                    snap_q  <= snap_req;
                    hs_data <= {{W{1'b0}}, errs, words_r};
                    st      <= 2'd1;
                end
                2'd1:    if (hs_rcv)  st <= 2'd2;
                default: if (!hs_rcv) st <= 2'd0;
            endcase
        end
    end
    assign hs_send = (st == 2'd1);
endmodule

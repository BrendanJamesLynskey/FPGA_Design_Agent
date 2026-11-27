// prbs_rd: reader domain (clk_rd only). Pop gate with SLOW_READ divider, PRBS-31 checker, single-shot inject,
// WORDS_R / DATA_ERRS / UNDERFLOWS counters and the snapshot sender (staging register + handshake control).
module prbs_rd #(
    parameter logic [30:0] PRBS_SEED            = 31'h7FFFFFFF,
    parameter int          SLOW_READ_DIV_CYCLES = 8
) (
    input  logic        clk_rd,
    input  logic        slow_r,
    input  logic        clr_r,
    input  logic        inj_r,
    input  logic        snap_r,
    input  logic [31:0] fifo_dout,
    input  logic        fifo_empty,
    input  logic        rd_rst_busy,
    output logic        rd_en,
    output logic        err_r,
    output logic [95:0] stage,
    output logic        hs_send,
    input  logic        hs_rcv
);
    localparam int DIVW = $clog2(SLOW_READ_DIV_CYCLES);

    logic [30:0] prbs_r = PRBS_SEED;
    logic [30:0] prbs_r_next;
    logic [31:0] prbs_r_word;
    prbs31_next u_prbs_r (.state(prbs_r), .next_state(prbs_r_next), .word(prbs_r_word));

    logic [DIVW-1:0] div = '0;
    logic            pop_ok;
    logic            attempt;
    logic            pop;
    logic            inj_prev = 1'b0, snap_prev = 1'b0;
    logic            inj_armed = 1'b0;
    logic            pop_q = 1'b0, mm_q = 1'b0;
    logic            uf_evt;
    logic [31:0]     words_r = '0, data_errs = '0, underflows = '0;

    initial err_r = 1'b0;

    assign pop_ok  = !slow_r || (div == '0);
    assign attempt = pop_ok && !clr_r && !rd_rst_busy;
    assign pop     = attempt && !fifo_empty;
    assign rd_en   = pop;
    assign uf_evt  = pop && fifo_empty;           // never: the reader is gated by empty

    always_ff @(posedge clk_rd) begin
        inj_prev  <= inj_r;
        snap_prev <= snap_r;
        if (slow_r && !clr_r) div <= (div == DIVW'(SLOW_READ_DIV_CYCLES - 1)) ? '0 : div + 1'b1;
        else                  div <= '0;
        if (clr_r) begin
            prbs_r     <= PRBS_SEED;
            words_r    <= '0;
            data_errs  <= '0;
            underflows <= '0;
            err_r      <= 1'b0;
            pop_q      <= 1'b0;
            mm_q       <= 1'b0;
        end else begin
            pop_q <= pop;
            mm_q  <= ((fifo_dout ^ {31'd0, inj_armed}) != prbs_r_word);
            if (pop) begin
                prbs_r    <= prbs_r_next;
                inj_armed <= 1'b0;
            end
            if (pop_q) words_r <= words_r + 32'd1;
            if (pop_q && mm_q) begin
                data_errs <= data_errs + 32'd1;
                err_r     <= 1'b1;
            end
            if (uf_evt) begin
                underflows <= underflows + 32'd1;
                err_r      <= 1'b1;
            end
        end
        if (inj_r != inj_prev) inj_armed <= 1'b1;
    end

    // snapshot sender
    localparam logic [1:0] S_IDLE = 2'd0, S_SEND = 2'd1, S_WAIT = 2'd2;
    logic [1:0] hs_state = S_IDLE;
    logic       pend     = 1'b0;
    logic       snap_ev;
    assign snap_ev = (snap_r != snap_prev);

    initial begin
        stage   = '0;
        hs_send = 1'b0;
    end

    always_ff @(posedge clk_rd) begin
        if (snap_ev) pend <= 1'b1;
        case (hs_state)
            S_IDLE: if (pend || snap_ev) begin
                stage    <= {words_r, data_errs, underflows};
                hs_send  <= 1'b1;
                hs_state <= S_SEND;
                pend     <= 1'b0;
            end
            S_SEND: if (hs_rcv) begin
                hs_send  <= 1'b0;
                hs_state <= S_WAIT;
            end
            S_WAIT: if (!hs_rcv) hs_state <= S_IDLE;
            default: hs_state <= S_IDLE;
        endcase
    end
endmodule

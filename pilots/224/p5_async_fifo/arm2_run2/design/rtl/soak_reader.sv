// Reader side in clk_gt156: pops the FIFO, checks against a local PRBS-31, counts, and serves the snapshot handshake.
module soak_reader #(
    parameter int PRBS_SEED                = 2147483647,
    parameter int SLOW_READ_PERIOD_CYCLES  = 8
) (
    input  logic        clk,
    input  logic        rst,            // synchronous, active high, in clk
    input  logic        clr_pulse,
    input  logic        inj_pulse,
    input  logic        snap_pulse,
    input  logic        slow,
    // FIFO read side
    input  logic [31:0] fifo_dout,
    input  logic        fifo_empty,
    input  logic        fifo_rd_rst_busy,
    input  logic        fifo_underflow,
    output logic        fifo_rd_en,
    // outputs
    output logic [9:0]  rcnt,
    output logic        err_flag,
    // snapshot handshake source
    output logic [95:0] hs_data,
    output logic        hs_send,
    input  logic        hs_rcv
);
    logic [31:0] words_r, data_errs, unfls;
    logic [30:0] prbs;
    logic [30:0] prbs_n;
    logic [31:0] exp_w;
    logic        dv, inj;
    logic [3:0]  slow_cnt;

    prbs31_word u_prbs (.s(prbs), .s_n(prbs_n), .w(exp_w));

    wire slow_ok = !slow || (slow_cnt == 4'(SLOW_READ_PERIOD_CYCLES - 1));
    assign fifo_rd_en = !fifo_empty && !fifo_rd_rst_busy && slow_ok;
    assign rcnt = words_r[9:0];

    always_ff @(posedge clk) begin
        if (rst || !slow || slow_cnt == 4'(SLOW_READ_PERIOD_CYCLES - 1)) slow_cnt <= '0;
        else slow_cnt <= slow_cnt + 4'd1;
    end

    always_ff @(posedge clk) begin
        if (rst || clr_pulse) begin
            prbs      <= 31'(PRBS_SEED);
            words_r   <= '0;
            data_errs <= '0;
            unfls     <= '0;
            dv        <= 1'b0;
            inj       <= 1'b0;
            err_flag  <= 1'b0;
        end else begin
            dv <= fifo_rd_en;
            if (dv) begin
                prbs    <= prbs_n;
                words_r <= words_r + 32'd1;
                inj     <= 1'b0;
                if ((fifo_dout ^ {31'b0, inj}) != exp_w) data_errs <= data_errs + 32'd1;
            end
            if (fifo_underflow) unfls <= unfls + 32'd1;
            if (inj_pulse) inj <= 1'b1;
            err_flag <= (data_errs != 32'd0) || (unfls != 32'd0);
        end
    end

    // snapshot handshake: latch the counters when the request arrives, hold them until the writer side has them
    typedef enum logic [1:0] {S_IDLE, S_SEND, S_WAIT} st_t;
    st_t  st;
    logic snap_pend;
    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; hs_send <= 1'b0; snap_pend <= 1'b0; hs_data <= '0;
        end else begin
            if (snap_pulse && st != S_IDLE) snap_pend <= 1'b1;
            case (st)
                S_IDLE: if (snap_pulse || snap_pend) begin
                    hs_data   <= {unfls, data_errs, words_r};
                    hs_send   <= 1'b1;
                    snap_pend <= 1'b0;
                    st        <= S_SEND;
                end
                S_SEND: if (hs_rcv) begin hs_send <= 1'b0; st <= S_WAIT; end
                S_WAIT: if (!hs_rcv) st <= S_IDLE;
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule

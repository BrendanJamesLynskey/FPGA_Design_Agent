// tx_mux.sv: the transmit multiplexer in front of mac64_tx (brief 127): three frame sources, one MAC.
//   A  frame_src of the 96 design (probe, feed, test and Bench Feed order frames): holds its words until the MAC takes them
//   R  the replay source: frames the host loaded into a 256-word memory over the register bus (synthetic MoldUDP64 frames for the fibre loopback), sent back to back with gaps
//   O  the order frame of order_seg (or tcp_fast): a stream of 15 words that cannot be paused, so it goes through a small FIFO and a head register
// One owner at a time (`own`), chosen only while the MAC is not in the middle of a frame (own = none). O wins a clock in which its stream starts (o_sof) and the MAC is free; A and R
// wait by holding their `valid` (frame_src and the replay engine both keep a word stable until it is taken). An order frame whose first word finds the MAC owned by A or R is
// dropped whole and counted (`ord_drop`): it was already fired by the risk logic (its position and number are used): that is the price of not holding orders back.
// The MAC's `adv` (the gearbox pause, one clock in 33) holds the MAC; the FIFO absorbs it. Timing of O: stream word 0 is visible in clock G+1 (G = the clock `go` is high): it
// loads the head register at the end of G+1, s_valid is up in G+2, the MAC's start strobe (preamble word in its output register) is in G+3.
// Replay memory format (docs/itch_integration.md section 6): per frame one header word {31'd0, poison, gap clocks[15:0], length bytes[15:0]} (length 0 ends the list; poison makes the
// MAC's FCS of that frame wrong: a frame for the receiver's bad-FCS path; at the end marker the gap field is the pause before the next pass when rp_loops asks for several) followed by
// ceil(length/8) data words; byte 0 of the frame in bits 7:0 of the first data word; the frame without its FCS, length 60 to 1514 (the MAC does not pad: a shorter frame is
// skipped and counted in `rp_err`). `gap` clocks of silence follow the previous frame's last word accepted by the MAC.
module tx_mux (
    input  logic        clk,
    input  logic        rst,
    // MAC
    output logic        s_valid,
    output logic [63:0] s_data,
    output logic        s_last,
    output logic [2:0]  s_nb1,
    output logic        s_poison,
    input  logic        s_ready,
    input  logic        mac_sop,
    // source A
    input  logic        a_valid,
    input  logic [63:0] a_data,
    input  logic        a_last,
    input  logic [2:0]  a_nb1,
    input  logic        a_poison,
    output logic        a_ready,
    // source O
    input  logic        o_v,
    input  logic [63:0] o_d,
    input  logic        o_sof,
    input  logic        o_eof,
    input  logic [7:0]  o_keep,
    input  logic        o_poison,
    input  logic        o_unres,
    input  logic        fcs_poison,          // level from itch_path: the trigger frame's verdict makes the frame in flight unacceptable
    output logic        ord_start,           // one clock: the order frame was granted the MAC (its first word is in the head register next clock)
    output logic        ord_drop,            // one clock: the order frame found the MAC owned and is dropped
    output logic        ord_end,             // one clock: the order frame's last word is taken by the MAC; ord_end_* say how it was poisoned
    output logic        ord_end_seg, ord_end_unres, ord_end_fcs, ord_end_ofl,
    output logic        ord_sop,             // one clock: the MAC's start strobe of the order frame
    output logic        ord_busy,            // the order frame still holds the MAC or the FIFO
    output logic        own_a,               // the owner is A (for the counters of tx_path)
    // replay: host commands (already in this clock domain)
    input  logic        rp_start,
    input  logic        rp_stop,
    input  logic [15:0] rp_loops,            // passes over the memory per RP_START (0 or 1: one)
    input  logic        wr_we,               // one clock: write wr_data into the replay memory at wr_addr
    input  logic [7:0]  wr_addr,
    input  logic [63:0] wr_data,
    output logic [31:0] rp_frames,
    output logic [31:0] rp_err,
    output logic        rp_busy,
    // order FIFO observation
    output logic [31:0] n_ofl
);
    // ------------------------------------------------------------------ owner
    typedef enum logic [1:0] {OWN_NONE = 2'd0, OWN_A = 2'd1, OWN_R = 2'd2, OWN_O = 2'd3} own_t;
    own_t own;
    logic o_take;
    logic r_valid, r_last, r_ready, r_req, r_poison;
    logic [63:0] r_data;
    logic [2:0]  r_nb1;
    logic        head_v, head_last, head_pz_seg, head_pz_unres, head_pz_ofl;
    logic [63:0] head_d;
    logic [2:0]  head_nb1;
    logic        o_consume, wd_fire;
    assign own_a    = (own == OWN_A);
    assign o_take   = o_v && o_sof && own == OWN_NONE;
    assign ord_start = o_take;
    assign ord_drop = o_v && o_sof && own != OWN_NONE;
    assign a_ready  = s_ready && own == OWN_A;
    assign r_ready  = s_ready && own == OWN_R;
    assign o_consume = s_ready && own == OWN_O && head_v;
    always_comb begin
        s_valid = 1'b0; s_data = '0; s_last = 1'b0; s_nb1 = 3'd0; s_poison = 1'b0;
        case (own)
            OWN_A: begin s_valid = a_valid; s_data = a_data; s_last = a_last; s_nb1 = a_nb1; s_poison = a_poison; end
            OWN_R: begin s_valid = r_valid; s_data = r_data; s_last = r_last; s_nb1 = r_nb1; s_poison = r_poison; end
            OWN_O: begin s_valid = head_v; s_data = head_d; s_last = head_last; s_nb1 = head_nb1; s_poison = head_last && (head_pz_seg || head_pz_ofl || fcs_poison); end
            default: ;
        endcase
    end
    always_ff @(posedge clk) begin
        if (rst) own <= OWN_NONE;
        else if (wd_fire) own <= OWN_NONE;       // the order frame never finished (never seen): give the MAC back
        else begin
            case (own)
                OWN_NONE: if (o_take) own <= OWN_O; else if (a_valid) own <= OWN_A; else if (r_req) own <= OWN_R;
                OWN_A: if (a_valid && a_last && s_ready) own <= OWN_NONE;
                OWN_R: if (r_valid && r_last && s_ready) own <= OWN_NONE;
                OWN_O: if (head_v && head_last && s_ready) own <= OWN_NONE;
                default: own <= OWN_NONE;
            endcase
        end
    end

    // ------------------------------------------------------------------ order stream: FIFO and head register
    logic [63:0] fq_d [0:7];
    logic [5:0]  fq_f [0:7];                 // {unres, last, seg poison, nb1[2:0]}
    logic [2:0]  wp, rp;
    logic [3:0]  fcnt;
    logic        in_acc;                     // the frame being streamed was granted the MAC
    logic        ofl_l;
    logic [2:0]  in_nb1;
    logic        in_w, in_last;
    logic [6:0]  own_wd;
    always_comb begin
        in_nb1 = 3'd0;
        for (int i = 0; i < 8; i++) if (o_keep[i]) in_nb1 = 3'(i);
    end
    assign in_w = o_v && (o_take || (in_acc && !o_sof));
    assign in_last = o_eof;
    logic fifo_pop, bypass, can_load, fifo_wr;
    assign can_load = !head_v || o_consume;
    assign bypass   = can_load && (fcnt == 4'd0) && in_w;
    assign fifo_pop = can_load && (fcnt != 4'd0);
    assign fifo_wr  = in_w && !bypass && (fcnt != 4'd8);
    assign wd_fire  = (own == OWN_O) && (own_wd == 7'd100);
    assign ord_busy = (own == OWN_O) || (fcnt != 4'd0) || head_v;
    assign ord_end  = (o_consume && head_last) || wd_fire;
    assign ord_end_seg   = head_pz_seg;
    assign ord_end_unres = head_pz_unres;
    assign ord_end_ofl   = head_pz_ofl || wd_fire;
    assign ord_end_fcs   = fcs_poison;
    assign ord_sop  = mac_sop && own == OWN_O;
    always_ff @(posedge clk) begin
        if (rst) begin
            wp <= '0; rp <= '0; fcnt <= '0; in_acc <= 1'b0; head_v <= 1'b0; head_d <= '0; head_last <= 1'b0; head_nb1 <= '0; head_pz_seg <= 1'b0; head_pz_unres <= 1'b0;
            head_pz_ofl <= 1'b0; ofl_l <= 1'b0; n_ofl <= '0; own_wd <= '0;
        end else begin
            own_wd <= (own == OWN_O) ? own_wd + 7'd1 : 7'd0;
            if (o_take) begin in_acc <= 1'b1; ofl_l <= 1'b0; end
            if (o_v && (o_eof || (o_sof && !o_take))) in_acc <= 1'b0;
            if (o_consume) head_v <= 1'b0;
            if (can_load) begin
                if (fcnt != 4'd0) begin
                    head_v <= 1'b1; head_d <= fq_d[rp]; head_last <= fq_f[rp][3]; head_nb1 <= fq_f[rp][2:0]; head_pz_seg <= fq_f[rp][3] && fq_f[rp][4];
                    head_pz_unres <= fq_f[rp][3] && fq_f[rp][5]; head_pz_ofl <= fq_f[rp][3] && ofl_l;
                    rp <= rp + 3'd1;
                end else if (in_w) begin
                    head_v <= 1'b1; head_d <= o_d; head_last <= in_last; head_nb1 <= in_nb1; head_pz_seg <= in_last && o_poison;
                    head_pz_unres <= in_last && o_unres; head_pz_ofl <= in_last && ofl_l;
                end
            end
            if (in_w && !bypass && fcnt == 4'd8) begin ofl_l <= 1'b1; n_ofl <= n_ofl + 32'd1; end
            if (fifo_wr) begin
                fq_d[wp] <= o_d; fq_f[wp] <= {in_last && o_unres, in_last && o_poison, in_last, in_nb1}; wp <= wp + 3'd1;
            end
            if (wd_fire) begin n_ofl <= n_ofl + 32'd1; head_v <= 1'b0; fcnt <= '0; rp <= wp; end
            else case ({fifo_wr, fifo_pop})
                2'b10: fcnt <= fcnt + 4'd1;
                2'b01: fcnt <= fcnt - 4'd1;
                default: ;
            endcase
        end
    end

    // ------------------------------------------------------------------ replay memory and engine
    logic [63:0] rmem [0:255];
    initial for (int i = 0; i < 256; i++) rmem[i] = 64'd0;        // powers up as zeros: a zero header word ends the list
    always_ff @(posedge clk) if (wr_we) rmem[wr_addr] <= wr_data;
    typedef enum logic [2:0] {R_IDLE, R_HDR, R_GAP, R_RUN, R_PGAP} rst_t;
    rst_t        rst_s;
    logic [7:0]  ptr;
    logic [15:0] gapc, wl, flen, passes;
    logic        r_pz;
    logic [32:0] hw;                      // the header word's used bits: poison, gap, length
    logic [63:0] rq;
    logic        r_acc;
    logic [7:0]  raddr;
    logic [63:0] rdw;
    assign raddr   = (rst_s == R_RUN && r_acc) ? ptr + 8'd1 : ptr;       // one read port: the header word, the first data word and the next data word are all rmem[raddr]
    assign rdw     = rmem[raddr];
    assign hw      = rdw[32:0];
    assign r_valid = (rst_s == R_RUN);
    assign r_req   = r_valid;
    assign r_data  = rq;
    assign r_last  = (wl == 16'd1);
    assign r_nb1   = r_last ? 3'((flen - 16'd1) & 16'd7) : 3'd7;
    assign r_poison = r_pz && r_last;
    assign rp_busy = (rst_s != R_IDLE);
    assign r_acc   = r_valid && r_ready;
    always_ff @(posedge clk) begin
        if (rst) begin
            rst_s <= R_IDLE; ptr <= '0; gapc <= '0; wl <= '0; flen <= '0; rq <= '0; rp_frames <= '0; rp_err <= '0; passes <= '0; r_pz <= 1'b0;
        end else begin
            case (rst_s)
                R_IDLE: if (rp_start) begin ptr <= 8'd0; passes <= (rp_loops == 16'd0) ? 16'd1 : rp_loops; rst_s <= R_HDR; end
                R_PGAP: begin
                    if (gapc == 16'd0) begin ptr <= 8'd0; rst_s <= R_HDR; end else gapc <= gapc - 16'd1;
                end
                R_HDR: begin
                    if (hw[15:0] == 16'd0) begin
                        if (passes > 16'd1) begin passes <= passes - 16'd1; gapc <= hw[31:16]; rst_s <= R_PGAP; end
                        else rst_s <= R_IDLE;
                    end
                    else if (hw[15:0] < 16'd60 || hw[15:0] > 16'd1514 || ({1'b0, ptr} + 9'd1 + 9'((hw[15:0] + 16'd7) >> 3)) > 9'd256) begin
                        rp_err <= rp_err + 32'd1; rst_s <= R_IDLE;
                    end else begin
                        gapc <= hw[31:16]; flen <= hw[15:0]; r_pz <= hw[32]; wl <= (hw[15:0] + 16'd7) >> 3; ptr <= ptr + 8'd1; rst_s <= R_GAP;
                    end
                end
                R_GAP: begin
                    rq <= rdw;
                    if (gapc == 16'd0) rst_s <= R_RUN; else gapc <= gapc - 16'd1;
                end
                R_RUN: begin
                    if (r_acc) begin
                        ptr <= ptr + 8'd1; wl <= wl - 16'd1; rq <= rdw;
                        if (r_last) begin rp_frames <= rp_frames + 32'd1; rst_s <= R_HDR; end
                    end
                end
                default: rst_s <= R_IDLE;
            endcase
            if (rp_stop) rst_s <= R_IDLE;
        end
    end
endmodule

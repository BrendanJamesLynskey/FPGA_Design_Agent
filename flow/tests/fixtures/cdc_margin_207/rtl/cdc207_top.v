// cdc207_top: the brief 207 crossing set, one flat module so register names are the same in Vivado and Quartus.
// Two asynchronous clocks, clk_a and clk_b. Our own RTL, written for the experiment (no benchmark material).
//
//   C1  level synchroniser (lvl_*) and toggle pulse synchroniser (tg_*): 2 ASYNC_REG stages in clk_b
//   C2  asynchronous FIFO, 128 x 8, Gray pointers (AW+1 = 8 bits) crossed through 2 ASYNC_REG stages each way;
//       the memory is written in clk_a and read (registered) in clk_b after the pointer has crossed
//   C3  16-bit req/ack handshake: data held in clk_a (hs_hold_a), request toggle through 3 stages, CE capture in clk_b,
//       ack toggle back through 2 stages
//   C4  16-bit configuration bus: held in clk_a (cfg_hold_a), toggle through 2 stages, CE capture in clk_b (no ack)
//   C5  reset release: asynchronous reset input arst_n, asserted asynchronously, released through 2 ASYNC_REG stages
//   filler: a registered multiply-accumulate in each domain, to see what a constraint variant costs elsewhere
//
// BAD selects a seeded fault: 0 none; 1 the FIFO crosses BINARY pointers bit by bit (B1); 2 the level synchroniser has
// one stage: its first flop feeds logic directly (B2). B3 (pulled-apart bus) is a placement variant of BAD=0, made in
// the constraints, not here.
// Resets: synchronous active-high rst_a / rst_b inside each domain (house rule); the only asynchronous reset is the C5
// bridge.

module cdc207_top #(
    parameter integer BAD = 0,
    parameter integer AW  = 7
) (
    input  wire        clk_a,
    input  wire        clk_b,
    input  wire        rst_a,
    input  wire        rst_b,
    input  wire        arst_n,
    // C1
    input  wire        lvl_in_a,
    input  wire        pls_in_a,
    output reg  [7:0]  lvl_cnt_b,
    output reg  [7:0]  pls_cnt_b,
    // C2
    input  wire [7:0]  din_a,
    input  wire        wr_a,
    output wire        full_a,
    input  wire        rd_b,
    output reg  [7:0]  dout_b,
    output wire        empty_b,
    // C3
    input  wire [15:0] hs_data_a,
    input  wire        hs_go_a,
    output wire        hs_busy_a,
    output reg  [15:0] hs_data_b,
    output reg         hs_valid_b,
    // C4
    input  wire [15:0] cfg_in_a,
    input  wire        cfg_we_a,
    output reg  [15:0] cfg_b,
    // C5
    output reg  [7:0]  rcnt_b,
    // filler
    input  wire [15:0] fa_x,
    input  wire [15:0] fa_y,
    output reg  [31:0] fa_acc,
    input  wire [15:0] fb_x,
    input  wire [15:0] fb_y,
    output reg  [31:0] fb_acc
);

    // ---------------- C1: level and toggle-pulse synchronisers ----------------
    reg lvl_a = 1'b0;
    reg tg_a  = 1'b0;
    always @(posedge clk_a) begin
        if (rst_a) begin
            lvl_a <= 1'b0;
            tg_a  <= 1'b0;
        end else begin
            lvl_a <= lvl_in_a;
            if (pls_in_a) tg_a <= ~tg_a;
        end
    end

    (* ASYNC_REG = "TRUE" *) reg lvl_s1 = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg lvl_s2 = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg tg_s1  = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg tg_s2  = 1'b0;
    reg tg_s3 = 1'b0;
    always @(posedge clk_b) begin
        lvl_s1 <= lvl_a;
        lvl_s2 <= lvl_s1;
        tg_s1  <= tg_a;
        tg_s2  <= tg_s1;
        tg_s3  <= tg_s2;
    end
    wire lvl_use = (BAD == 2) ? lvl_s1 : lvl_s2;   // B2: one stage, the first flop feeds the counter directly
    always @(posedge clk_b) begin
        if (rst_b) begin
            lvl_cnt_b <= 8'd0;
            pls_cnt_b <= 8'd0;
        end else begin
            if (lvl_use)         lvl_cnt_b <= lvl_cnt_b + 8'd1;
            if (tg_s2 ^ tg_s3)   pls_cnt_b <= pls_cnt_b + 8'd1;
        end
    end

    // ---------------- C2: asynchronous FIFO with Gray pointers ----------------
    reg [7:0] mem [0:(1<<AW)-1];
    reg [AW:0] wbin_a = 0, wgray_a = 0;     // write pointer, binary and Gray (clk_a)
    reg [AW:0] rbin_b = 0, rgray_b = 0;     // read pointer (clk_b)
    (* ASYNC_REG = "TRUE" *) reg [AW:0] wq1_b = 0;
    (* ASYNC_REG = "TRUE" *) reg [AW:0] wq2_b = 0;
    (* ASYNC_REG = "TRUE" *) reg [AW:0] rq1_a = 0;
    (* ASYNC_REG = "TRUE" *) reg [AW:0] rq2_a = 0;

    function [AW:0] bin2gray(input [AW:0] b);
        bin2gray = b ^ (b >> 1);
    endfunction
    function [AW:0] gray2bin(input [AW:0] g);
        integer i;
        begin
            gray2bin[AW] = g[AW];
            for (i = AW - 1; i >= 0; i = i - 1) gray2bin[i] = gray2bin[i+1] ^ g[i];
        end
    endfunction

    // the value each side sends: Gray (good) or binary (B1)
    wire [AW:0] wsend_a = (BAD == 1) ? wbin_a : wgray_a;
    wire [AW:0] rsend_b = (BAD == 1) ? rbin_b : rgray_b;
    // the far pointer in binary, as each side sees it
    wire [AW:0] wseen_b = (BAD == 1) ? wq2_b : gray2bin(wq2_b);
    wire [AW:0] rseen_a = (BAD == 1) ? rq2_a : gray2bin(rq2_a);

    assign full_a  = (wbin_a[AW] != rseen_a[AW]) && (wbin_a[AW-1:0] == rseen_a[AW-1:0]);
    assign empty_b = (rbin_b == wseen_b);

    wire [AW:0] wbin_nx = wbin_a + {{AW{1'b0}}, 1'b1};
    always @(posedge clk_a) begin
        if (rst_a) begin
            wbin_a  <= 0;
            wgray_a <= 0;
        end else if (wr_a && !full_a) begin
            mem[wbin_a[AW-1:0]] <= din_a;
            wbin_a  <= wbin_nx;
            wgray_a <= bin2gray(wbin_nx);
        end
    end
    always @(posedge clk_a) begin
        rq1_a <= rsend_b;
        rq2_a <= rq1_a;
    end

    wire [AW:0] rbin_nx = rbin_b + {{AW{1'b0}}, 1'b1};
    always @(posedge clk_b) begin
        wq1_b <= wsend_a;
        wq2_b <= wq1_b;
        if (rst_b) begin
            rbin_b  <= 0;
            rgray_b <= 0;
            dout_b  <= 8'd0;
        end else if (rd_b && !empty_b) begin
            dout_b  <= mem[rbin_b[AW-1:0]];
            rbin_b  <= rbin_nx;
            rgray_b <= bin2gray(rbin_nx);
        end
    end

    // ---------------- C3: req/ack handshake, 16 bits ----------------
    reg [15:0] hs_hold_a = 16'd0;
    reg        req_a = 1'b0;
    reg        ack_b = 1'b0;   // clk_b: the acknowledge toggle (declared here, used by clk_a below)
    (* ASYNC_REG = "TRUE" *) reg aq1_a = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg aq2_a = 1'b0;
    assign hs_busy_a = req_a ^ aq2_a;
    always @(posedge clk_a) begin
        aq1_a <= ack_b;
        aq2_a <= aq1_a;
        if (rst_a) begin
            req_a <= 1'b0;
        end else if (hs_go_a && !hs_busy_a) begin
            hs_hold_a <= hs_data_a;
            req_a     <= ~req_a;
        end
    end
    (* ASYNC_REG = "TRUE" *) reg rq1_b = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg rq2_b = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg rq3_b = 1'b0;
    reg rq4_b = 1'b0;
    always @(posedge clk_b) begin
        rq1_b <= req_a;
        rq2_b <= rq1_b;
        rq3_b <= rq2_b;
        rq4_b <= rq3_b;
        ack_b <= rq3_b;
        hs_valid_b <= 1'b0;
        if (rq3_b ^ rq4_b) begin
            hs_data_b  <= hs_hold_a;
            hs_valid_b <= 1'b1;
        end
    end

    // ---------------- C4: configuration bus, CE capture, no ack ----------------
    reg [15:0] cfg_hold_a = 16'd0;
    reg        ctg_a = 1'b0;
    always @(posedge clk_a) begin
        if (cfg_we_a) begin
            cfg_hold_a <= cfg_in_a;
            ctg_a      <= ~ctg_a;
        end
    end
    (* ASYNC_REG = "TRUE" *) reg ct1_b = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg ct2_b = 1'b0;
    reg ct3_b = 1'b0;
    always @(posedge clk_b) begin
        ct1_b <= ctg_a;
        ct2_b <= ct1_b;
        ct3_b <= ct2_b;
        if (ct2_b ^ ct3_b) cfg_b <= cfg_hold_a;
    end

    // ---------------- C5: reset release bridge ----------------
    (* ASYNC_REG = "TRUE" *) reg rb1_b = 1'b0;
    (* ASYNC_REG = "TRUE" *) reg rb2_b = 1'b0;
    always @(posedge clk_b or negedge arst_n) begin
        if (!arst_n) begin
            rb1_b <= 1'b0;
            rb2_b <= 1'b0;
        end else begin
            rb1_b <= 1'b1;
            rb2_b <= rb1_b;
        end
    end
    always @(posedge clk_b) begin
        if (!rb2_b) rcnt_b <= 8'd0;
        else        rcnt_b <= rcnt_b + 8'd1;
    end

    // ---------------- filler: one MAC per domain ----------------
    reg [31:0] fa_p = 0, fb_p = 0;
    always @(posedge clk_a) begin
        fa_p   <= fa_x * fa_y;
        fa_acc <= fa_acc + fa_p + {fa_acc[28:0], 3'b000};
    end
    always @(posedge clk_b) begin
        fb_p   <= fb_x * fb_y;
        fb_acc <= fb_acc + fb_p + {fb_acc[28:0], 3'b000};
    end

endmodule

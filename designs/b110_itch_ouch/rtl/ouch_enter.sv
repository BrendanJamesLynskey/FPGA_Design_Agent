// ouch_enter.sv: OUCH 5.0 Enter Order builder in a SoupBinTCP 3.00 Unsequenced Data packet (brief 110).
//
// One 59-byte frame, eight 64-bit words (byte 0 in bits 7:0), one word a clock: SoupBinTCP length 0x0039 (type byte plus the 56 byte message),
// 'U', then the Enter Order of OUCH 5.0 section 2.1 (47 fixed bytes) and a 9 byte option appendage (MinQty and CustomerType). Byte map:
//   0-1 length, 2 'U', 3 'O', 4-7 UserRefNum, 8 side 'B', 9-12 quantity, 13-20 symbol, 21-28 price (8 bytes, four implied decimals),
//   29 time in force, 30 display, 31 capacity, 32 intermarket sweep eligibility, 33 cross type, 34-47 ClOrdID ('FDA110' and the order number as
//   eight upper-case hex digits), 48-49 appendage length (9), 50-52 MinQty tag value header, 52-55 MinQty, 56-58 CustomerType element.
// TCP is not here: the frame goes to a stub port (o_*). A TCP stack, or a fast path for pre-built segments, takes it from there (docs/tcp_plan.md).
//
// SPECULATIVE START: `go` loads the frame's fields and puts word 0 on the output at once, in the clock after `go`, before the risk verdict is known
// when go_spec is set. The verdict then comes as `commit` or `abort`. An abort stops the frame (the words already out are void: o_abort is high for
// one clock, o_v is low) and the consumer discards it. An abort that arrives when no frame is in flight is reported on `late` (the frame had
// already left; with the pipeline of book_core it cannot happen: the verdict is 4 clocks before the frame ends).
module ouch_enter (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    input  logic        go_spec,
    input  logic [63:0] f_sym,
    input  logic [31:0] f_px,
    input  logic [31:0] f_qty,
    input  logic [31:0] f_ref,
    input  logic        commit,
    input  logic        abort,
    input  logic [7:0]  cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic [31:0] cfg_minqty,
    output logic        busy,
    output logic        late,
    output logic        spec_pend,
    output logic        o_v,
    output logic [63:0] o_d,
    output logic        o_sof,
    output logic        o_eof,
    output logic [7:0]  o_keep,
    output logic        o_abort
);
    logic [63:0] r_sym;
    logic [31:0] r_px, r_qty, r_ref;
    logic [2:0]  widx;
    logic [63:0] c_sym;
    logic [31:0] c_px, c_qty, c_ref;
    logic [2:0]  c_i;
    assign c_sym = busy ? r_sym : f_sym;
    assign c_px  = busy ? r_px  : f_px;
    assign c_qty = busy ? r_qty : f_qty;
    assign c_ref = busy ? r_ref : f_ref;
    assign c_i   = busy ? widx : 3'd0;

    function automatic logic [7:0] hexa(input logic [3:0] n);
        hexa = (n < 4'd10) ? (8'h30 + {4'd0, n}) : (8'h41 + {4'd0, n} - 8'd10);
    endfunction

    logic [511:0] fr;
    always_comb begin
        fr = '0;
        fr[8*0 +: 8] = 8'h00; fr[8*1 +: 8] = 8'h39; fr[8*2 +: 8] = "U"; fr[8*3 +: 8] = "O";
        fr[8*4 +: 8] = c_ref[31:24]; fr[8*5 +: 8] = c_ref[23:16]; fr[8*6 +: 8] = c_ref[15:8]; fr[8*7 +: 8] = c_ref[7:0];
        fr[8*8 +: 8] = "B";
        fr[8*9 +: 8] = c_qty[31:24]; fr[8*10 +: 8] = c_qty[23:16]; fr[8*11 +: 8] = c_qty[15:8]; fr[8*12 +: 8] = c_qty[7:0];
        for (int i = 0; i < 8; i++) fr[8*(13+i) +: 8] = c_sym[8*(7-i) +: 8];
        fr[8*25 +: 8] = c_px[31:24]; fr[8*26 +: 8] = c_px[23:16]; fr[8*27 +: 8] = c_px[15:8]; fr[8*28 +: 8] = c_px[7:0];
        fr[8*29 +: 8] = cfg_tif; fr[8*30 +: 8] = cfg_display; fr[8*31 +: 8] = cfg_capacity; fr[8*32 +: 8] = cfg_ise; fr[8*33 +: 8] = cfg_cross;
        fr[8*34 +: 8] = "F"; fr[8*35 +: 8] = "D"; fr[8*36 +: 8] = "A"; fr[8*37 +: 8] = "1"; fr[8*38 +: 8] = "1"; fr[8*39 +: 8] = "0";
        for (int i = 0; i < 8; i++) fr[8*(40+i) +: 8] = hexa(c_ref[4*(7-i) +: 4]);
        fr[8*48 +: 8] = 8'h00; fr[8*49 +: 8] = 8'h09;
        fr[8*50 +: 8] = 8'd5; fr[8*51 +: 8] = 8'd3;
        fr[8*52 +: 8] = cfg_minqty[31:24]; fr[8*53 +: 8] = cfg_minqty[23:16]; fr[8*54 +: 8] = cfg_minqty[15:8]; fr[8*55 +: 8] = cfg_minqty[7:0];
        fr[8*56 +: 8] = 8'd2; fr[8*57 +: 8] = 8'd4; fr[8*58 +: 8] = cfg_custtype;
    end

    always_ff @(posedge clk) begin
        o_abort <= 1'b0;
        late    <= 1'b0;
        if (rst) begin
            busy <= 1'b0; widx <= '0; o_v <= 1'b0; o_d <= '0; o_sof <= 1'b0; o_eof <= 1'b0; o_keep <= '0; spec_pend <= 1'b0;
            r_sym <= '0; r_px <= '0; r_qty <= '0; r_ref <= '0;
        end else begin
            o_v <= 1'b0; o_sof <= 1'b0; o_eof <= 1'b0;
            if (commit) spec_pend <= 1'b0;
            if (abort) begin
                if (busy) begin
                    busy <= 1'b0; o_abort <= 1'b1; spec_pend <= 1'b0;
                end else late <= 1'b1;
            end else if (go && !busy) begin
                busy <= 1'b1; widx <= 3'd1; spec_pend <= go_spec;
                r_sym <= f_sym; r_px <= f_px; r_qty <= f_qty; r_ref <= f_ref;
                o_v <= 1'b1; o_sof <= 1'b1; o_d <= fr[63:0]; o_keep <= 8'hFF;
            end else if (busy) begin
                o_v <= 1'b1; o_d <= fr[64*c_i +: 64];
                if (widx == 3'd7) begin
                    o_eof <= 1'b1; o_keep <= 8'h07; busy <= 1'b0;
                end
                widx <= widx + 3'd1;
            end
        end
    end
endmodule

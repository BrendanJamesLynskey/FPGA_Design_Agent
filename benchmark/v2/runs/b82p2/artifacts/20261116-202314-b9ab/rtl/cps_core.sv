// cps_core: command packet screener. One byte per byte_valid pulse (bit 8 = end flag).
// Pipeline after the write pulse: cycle 1 absorbs the byte (count, CRC, hold-back, buffer),
// cycle 2 (end flag only) computes the class flags, cycle 3 picks the class, updates
// counters / kept fields and clears the packet state. Whole packet done 3 clocks after the end write.
// The CRC register is stored inverted (cinv = ~crc) so that its reset value 0 is the CRC init 0xFFFFFFFF.
// Payload bytes beyond the first six are counted but not stored (a good packet carries at most six).
module cps_core (
    input  logic         clk,
    input  logic         rst,
    input  logic         byte_valid,
    input  logic [8:0]   byte_in,
    output logic [3:0]   result,
    output logic [7:0]   ptype,
    output logic [15:0]  pseq,
    output logic [15:0]  pay0,
    output logic [31:0]  pay1,
    output logic [15:0]  last_seq,
    output logic         have,
    output logic         busy,
    output logic [111:0] ctrs        // 7 x 16 bit, counter i at [16*i +: 16]
);
    function automatic logic [31:0] crc_byte(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++)
            r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        return r;
    endfunction

    // stage 1 input registers
    logic       in_v, in_e;
    logic [7:0] in_d;

    // packet state
    logic [8:0]  cnt;
    logic [31:0] cinv;
    logic [7:0]  sh0, sh1, sh2, sh3;      // sh0 oldest of the last four bytes
    logic [7:0]  f_type, f_len;
    logic [15:0] f_seq;
    logic [7:0]  pbuf0, pbuf1, pbuf2, pbuf3, pbuf4, pbuf5;

    // stage valid and flags
    logic cls_v, com_v;
    logic fl_long, fl_short, fl_crc, fl_type, fl_len, fl_rep, fl_stale;

    // ---- stage 2 combinational flags
    logic [9:0]  n10, lim;
    logic        c_long, c_short;
    logic [7:0]  need;
    logic        c_typeok;
    logic [15:0] delta;

    always_comb begin
        n10      = {1'b0, cnt};
        lim      = {2'b0, f_len} + 10'd8;
        c_long   = (cnt >= 9'd4) && ((f_len > 8'd8) || (n10 > lim));
        c_short  = !c_long && (n10 < lim);
        c_typeok = (f_type >= 8'd1) && (f_type <= 8'd5);
        case (f_type)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
        delta = f_seq - last_seq;
    end

    // ---- stage 3 combinational class
    logic [3:0] code;
    always_comb begin
        if (fl_long)       code = 4'd4;
        else if (fl_short) code = 4'd3;
        else if (fl_crc)   code = 4'd2;
        else if (fl_type)  code = 4'd7;
        else if (fl_len)   code = 4'd8;
        else if (fl_rep)   code = 4'd5;
        else if (fl_stale) code = 4'd6;
        else               code = 4'd1;
    end

    logic [2:0] cidx;
    always_comb begin
        case (code)
            4'd1:    cidx = 3'd0;
            4'd2:    cidx = 3'd1;
            4'd3:    cidx = 3'd2;
            4'd4:    cidx = 3'd3;
            4'd5:    cidx = 3'd4;
            4'd6:    cidx = 3'd5;
            default: cidx = 3'd6;
        endcase
    end

    logic [15:0] ctr [7];
    always_comb begin
        for (int i = 0; i < 7; i++) ctrs[16*i +: 16] = ctr[i];
    end

    // datapath registers without reset
    always_ff @(posedge clk) begin
        in_d <= byte_in[7:0];
        if (in_v) begin
            sh0 <= sh1; sh1 <= sh2; sh2 <= sh3; sh3 <= in_d;
            case (cnt)
                9'd0:  f_type <= in_d;
                9'd1:  f_len  <= in_d;
                9'd2:  f_seq[15:8] <= in_d;
                9'd3:  f_seq[7:0]  <= in_d;
                9'd4:  pbuf0 <= in_d;
                9'd5:  pbuf1 <= in_d;
                9'd6:  pbuf2 <= in_d;
                9'd7:  pbuf3 <= in_d;
                9'd8:  pbuf4 <= in_d;
                9'd9:  pbuf5 <= in_d;
                default: ;
            endcase
        end
        if (cls_v) begin
            fl_long  <= c_long;
            fl_short <= c_short;
            fl_crc   <= (cinv != {sh3, sh2, sh1, sh0});
            fl_type  <= !c_typeok;
            fl_len   <= (need != f_len);
            fl_rep   <= have && (delta == 16'd0);
            fl_stale <= have && delta[15];
        end
    end

    // control and state with synchronous reset
    always_ff @(posedge clk) begin
        if (rst) begin
            in_v   <= 1'b0;
            in_e   <= 1'b0;
            cls_v  <= 1'b0;
            com_v  <= 1'b0;
            cnt    <= 9'd0;
            cinv   <= 32'd0;
            busy   <= 1'b0;
            result <= 4'd0;
            ptype  <= 8'd0;
            pseq   <= 16'd0;
            pay0   <= 16'd0;
            pay1   <= 32'd0;
            last_seq <= 16'd0;
            have   <= 1'b0;
            for (int i = 0; i < 7; i++) ctr[i] <= 16'd0;
        end else begin
            in_v  <= byte_valid;
            in_e  <= byte_in[8];
            cls_v <= in_v && in_e;
            com_v <= cls_v;

            if (in_v) begin
                busy <= 1'b1;
                if (cnt != 9'd511) cnt <= cnt + 9'd1;
                if (cnt >= 9'd4) cinv <= ~crc_byte(~cinv, sh0);
            end

            if (com_v) begin
                busy   <= 1'b0;
                cnt    <= 9'd0;
                cinv   <= 32'd0;
                result <= code;
                ctr[cidx] <= ctr[cidx] + 16'd1;
                if (code == 4'd1) begin
                    ptype    <= f_type;
                    pseq     <= f_seq;
                    last_seq <= f_seq;
                    have     <= 1'b1;
                    pay0     <= (f_len >= 8'd2) ? {pbuf0, pbuf1} : 16'd0;
                    pay1     <= (f_len >= 8'd6) ? {pbuf2, pbuf3, pbuf4, pbuf5} : 32'd0;
                end
            end
        end
    end
endmodule

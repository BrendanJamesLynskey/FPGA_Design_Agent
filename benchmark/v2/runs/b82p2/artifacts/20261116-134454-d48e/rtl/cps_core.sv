// cps_core: packet screener. One byte per write; CRC-32 byte-wise (reflected 0xEDB88320).
// The last four bytes are held in a shift register, so the CRC covers all bytes but the last four.
module cps_core #(
    parameter int TIMEOUT_CYCLES = 100_000_000
) (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic        byte_vld,     // one-cycle pulse
    input  logic [7:0]  byte_data,
    input  logic        byte_end,
    output logic        busy,
    output logic        done,         // one-cycle pulse: class valid
    output logic [3:0]  cls,          // 1 good, 2 crc, 3 short, 4 long, 5 repeat, 6 stale, 7 type, 8 length
    output logic [7:0]  g_type,       // fields of the packet just accepted (valid with done and cls==1)
    output logic [15:0] g_seq,
    output logic [15:0] g_pay0,
    output logic [31:0] g_pay1,
    output logic [15:0] last_seq,
    output logic        have_seq
);
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'h0, d};
        for (int i = 0; i < 8; i++) r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        return r;
    endfunction

    typedef enum logic [1:0] {S_IDLE, S_RX, S_FIN} state_t;
    state_t state;

    logic [31:0] crc;
    logic [7:0]  sh0, sh1, sh2, sh3;      // sh0 newest, sh3 oldest of the last four bytes
    logic [4:0]  n;                       // bytes so far, saturating at 31
    logic [7:0]  ptype, plen;
    logic [15:0] pseq;
    logic [7:0]  p0, p1, p2, p3, p4, p5;  // payload bytes 4..9
    logic [26:0] idle_cnt;

    wire [31:0] crc_next = (n >= 5'd4) ? crc8(crc, sh3) : crc;

    // classification of the finished packet
    wire [31:0] rx_crc  = {sh0, sh1, sh2, sh3};
    wire [31:0] calc    = ~crc;
    wire [8:0]  need_n  = 9'd8 + {1'b0, plen};
    wire        is_short_n = (n < 5'd4);
    wire        is_long  = (plen > 8'd8) || ({4'b0, n} > need_n);
    wire        is_short = ({4'b0, n} < need_n);
    wire        crc_bad  = (calc != rx_crc);
    wire        type_ok  = (ptype >= 8'd1) && (ptype <= 8'd5);
    logic [7:0] need;
    always_comb begin
        case (ptype)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
    end
    wire [15:0] dseq = pseq - last_seq;
    wire        seq_ok = !have_seq || ((dseq != 16'd0) && !dseq[15]);

    logic [3:0] cls_c;
    always_comb begin
        if (is_short_n)          cls_c = 4'd3;
        else if (is_long)        cls_c = 4'd4;
        else if (is_short)       cls_c = 4'd3;
        else if (crc_bad)        cls_c = 4'd2;
        else if (!type_ok)       cls_c = 4'd7;
        else if (plen != need)   cls_c = 4'd8;
        else if (seq_ok)         cls_c = 4'd1;
        else if (dseq == 16'd0)  cls_c = 4'd5;
        else                     cls_c = 4'd6;
    end

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            state    <= S_IDLE;
            busy     <= 1'b0;
            have_seq <= 1'b0;
            last_seq <= 16'h0;
            idle_cnt <= 27'd0;
            n        <= 5'd0;
            crc      <= 32'hFFFF_FFFF;
            cls      <= 4'd0;
            g_type   <= 8'h0;
            g_seq    <= 16'h0;
            g_pay0   <= 16'h0;
            g_pay1   <= 32'h0;
        end else begin
            case (state)
                S_IDLE, S_RX: begin
                    if (byte_vld) begin
                        idle_cnt <= 27'd0;
                        crc <= crc_next;
                        sh0 <= byte_data; sh1 <= sh0; sh2 <= sh1; sh3 <= sh2;
                        if (n != 5'd31) n <= n + 5'd1;
                        case (n)
                            5'd0: ptype <= byte_data;
                            5'd1: plen  <= byte_data;
                            5'd2: pseq[15:8] <= byte_data;
                            5'd3: pseq[7:0]  <= byte_data;
                            5'd4: p0 <= byte_data;
                            5'd5: p1 <= byte_data;
                            5'd6: p2 <= byte_data;
                            5'd7: p3 <= byte_data;
                            5'd8: p4 <= byte_data;
                            5'd9: p5 <= byte_data;
                            default: ;
                        endcase
                        if (byte_end) begin
                            state <= S_FIN;
                            busy  <= 1'b0;
                        end else begin
                            state <= S_RX;
                            busy  <= 1'b1;
                        end
                    end else if (state == S_RX) begin
                        if (idle_cnt >= 27'(TIMEOUT_CYCLES - 1)) begin
                            // timeout: drop the packet as too short
                            state    <= S_IDLE;
                            busy     <= 1'b0;
                            n        <= 5'd0;
                            crc      <= 32'hFFFF_FFFF;
                            idle_cnt <= 27'd0;
                            cls      <= 4'd3;
                            done     <= 1'b1;
                        end else begin
                            idle_cnt <= idle_cnt + 27'd1;
                        end
                    end
                end
                S_FIN: begin
                    state <= S_IDLE;
                    n     <= 5'd0;
                    crc   <= 32'hFFFF_FFFF;
                    cls   <= cls_c;
                    done  <= 1'b1;
                    if (cls_c == 4'd1) begin
                        g_type   <= ptype;
                        g_seq    <= pseq;
                        g_pay0   <= (plen == 8'd0) ? 16'h0 : {p0, p1};
                        g_pay1   <= (plen == 8'd6) ? {p2, p3, p4, p5} : 32'h0;
                        last_seq <= pseq;
                        have_seq <= 1'b1;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule

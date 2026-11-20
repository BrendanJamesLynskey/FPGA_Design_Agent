// udp_reply: builds a frame (hdr0, hdr1, seq, length, payload, CRC-32 low byte first) in a byte buffer,
// one byte per clock. Used for the reply and for the telemetry frame.
// len is 0 until the build is complete, and 0 after clr. Words are read four bytes at a time, first byte on
// top, zero past the end.
module udp_reply (
    input  logic         clk,
    input  logic         rst,
    input  logic         start,        // latch the inputs and build
    input  logic         clr,          // forget the frame
    input  logic [7:0]   hdr0,
    input  logic [7:0]   hdr1,
    input  logic [15:0]  seq,
    input  logic [4:0]   plen,         // 0..17
    input  logic [135:0] payload,      // byte j at [8*j +: 8]
    output logic         busy,
    output logic [7:0]   len,
    input  logic [6:0]   rd_idx,
    output logic [31:0]  rd_word
);
    typedef enum logic [1:0] {R_IDLE, R_BODY, R_TRAIL} rstate_t;
    rstate_t state;

    logic [7:0]   h0, h1;
    logic [15:0]  sq;
    logic [4:0]   pl;
    logic [7:0]   pay [0:16];
    logic [4:0]   n;
    logic [1:0]   k;
    logic [31:0]  crc;
    logic [7:0]   mem [0:31];

    logic [4:0]   tot;
    assign tot = 5'd5 + pl;

    logic [4:0]   pi;
    assign pi = n - 5'd5;

    logic [7:0] cur;
    always_comb begin
        case (n)
            5'd0:    cur = h0;
            5'd1:    cur = h1;
            5'd2:    cur = sq[15:8];
            5'd3:    cur = sq[7:0];
            5'd4:    cur = {3'b000, pl};
            default: cur = (pi < 5'd17) ? pay[pi] : 8'h00;
        endcase
    end

    logic [31:0] crc_nx;
    crc32_byte u_crc (.c(crc), .d(cur), .n(crc_nx));

    logic [31:0] fin;
    logic [7:0]  fin_byte;
    assign fin = ~crc;
    always_comb begin
        case (k)
            2'd0:    fin_byte = fin[7:0];
            2'd1:    fin_byte = fin[15:8];
            2'd2:    fin_byte = fin[23:16];
            default: fin_byte = fin[31:24];
        endcase
    end

    assign busy = (state != R_IDLE);

    always_ff @(posedge clk) begin
        if (state == R_BODY) mem[n] <= cur;
        else if (state == R_TRAIL) mem[n] <= fin_byte;
    end

    always_ff @(posedge clk) begin
        if (start) begin
            for (int j = 0; j < 17; j++) pay[j] <= payload[8*j +: 8];
        end
    end

    always_ff @(posedge clk) begin
        if (rst || clr) begin
            state <= R_IDLE;
            len   <= 8'd0;
        end else if (start) begin
            h0    <= hdr0;
            h1    <= hdr1;
            sq    <= seq;
            pl    <= plen;
            n     <= 5'd0;
            k     <= 2'd0;
            crc   <= 32'hFFFFFFFF;
            len   <= 8'd0;
            state <= R_BODY;
        end else begin
            case (state)
                R_BODY: begin
                    crc <= crc_nx;
                    n   <= n + 5'd1;
                    if (n == tot - 5'd1) state <= R_TRAIL;
                end
                R_TRAIL: begin
                    n <= n + 5'd1;
                    k <= k + 2'd1;
                    if (k == 2'd3) begin
                        state <= R_IDLE;
                        len   <= {3'b000, tot} + 8'd4;
                    end
                end
                default: ;
            endcase
        end
    end

    // read side
    logic [8:0] b0, b1, b2, b3;
    assign b0 = {rd_idx, 2'b00};
    assign b1 = b0 + 9'd1;
    assign b2 = b0 + 9'd2;
    assign b3 = b0 + 9'd3;
    logic [8:0] lenx;
    assign lenx = {1'b0, len};

    always_comb begin
        rd_word[31:24] = (b0 < lenx) ? mem[b0[4:0]] : 8'h00;
        rd_word[23:16] = (b1 < lenx) ? mem[b1[4:0]] : 8'h00;
        rd_word[15:8]  = (b2 < lenx) ? mem[b2[4:0]] : 8'h00;
        rd_word[7:0]   = (b3 < lenx) ? mem[b3[4:0]] : 8'h00;
    end
endmodule

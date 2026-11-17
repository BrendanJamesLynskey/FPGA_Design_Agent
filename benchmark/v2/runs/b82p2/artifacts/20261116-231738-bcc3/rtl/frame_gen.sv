// frame_gen: builds type, status, sequence (2 bytes), payload length, payload and CRC-32
// (low byte first) one byte per clock, writing each byte to a buffer. Total 9 + plen bytes.
module frame_gen #(
    parameter int PB = 17           // payload bytes capacity
) (
    input  logic              clk,
    input  logic              rst,
    input  logic              start,
    input  logic [7:0]        typ,
    input  logic [7:0]        status,
    input  logic [15:0]       seq,
    input  logic [4:0]        plen,
    input  logic [8*PB-1:0]   payload,   // first payload byte on top
    output logic              we,
    output logic [4:0]        idx,
    output logic [7:0]        data,
    output logic              done,
    output logic [5:0]        len
);
    logic          run;
    logic [5:0]    bi;
    logic [7:0]    l_typ, l_status;
    logic [15:0]   l_seq;
    logic [4:0]    l_plen;
    logic [8*PB-1:0] sr;
    logic [31:0]   crc, fcrc, crc_nx;
    logic [7:0]    byte_o;
    logic [5:0]    dend;
    logic          in_data;

    assign dend    = 6'd5 + {1'b0, l_plen};
    assign in_data = bi < dend;

    always_comb begin
        if (bi < 6'd5) begin
            case (bi[2:0])
                3'd0:    byte_o = l_typ;
                3'd1:    byte_o = l_status;
                3'd2:    byte_o = l_seq[15:8];
                3'd3:    byte_o = l_seq[7:0];
                default: byte_o = {3'b0, l_plen};
            endcase
        end else if (in_data) begin
            byte_o = sr[8*PB-1 -: 8];
        end else begin
            byte_o = fcrc[7:0];
        end
    end

    crc32_byte u_crc (.c(crc), .d(byte_o), .n(crc_nx));

    assign we   = run;
    assign idx  = bi[4:0];
    assign data = byte_o;
    assign done = run && ((bi + 6'd1) == len);

    always_ff @(posedge clk) begin
        if (rst)        run <= 1'b0;
        else if (start) run <= 1'b1;
        else if (done)  run <= 1'b0;
    end

    always_ff @(posedge clk) begin
        if (start) begin
            l_typ    <= typ;
            l_status <= status;
            l_seq    <= seq;
            l_plen   <= plen;
            sr       <= payload;
            crc      <= 32'hFFFFFFFF;
            bi       <= 6'd0;
            len      <= 6'd9 + {1'b0, plen};
        end else if (run) begin
            bi <= bi + 6'd1;
            if (in_data) begin
                crc  <= crc_nx;
                fcrc <= ~crc_nx;
                if (bi >= 6'd5) sr <= sr << 8;
            end else begin
                fcrc <= {8'h00, fcrc[31:8]};
            end
        end
    end
endmodule

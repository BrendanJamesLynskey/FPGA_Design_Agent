// frame_crc: CRC-32 (IEEE 802.3, reflected, init FFFFFFFF, final XOR FFFFFFFF) of every frame's pixel words, plus
// frame statistics (brief 30). The host (or a model) computes the same CRC over the same words, so the board can
// check every frame itself and the video capture is needed only for the analogue path. Each pixel word is fed
// least-significant byte first, PIX_W/8 bytes per word.
module frame_crc #(
    parameter int PIX_W = 24                 // pixel word width in bits, a multiple of 8
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             frame_start,    // one-clock pulse at the first pixel's clock or before; ends the previous frame
    input  logic             pix_valid,
    input  logic [PIX_W-1:0] pix_data,
    input  logic [31:0]      crc_expect,     // the model's CRC of the frame (compared when the frame ends)
    output logic [31:0]      crc_last,       // CRC of the last completed frame
    output logic [31:0]      pix_last,       // pixel count of the last completed frame
    output logic [31:0]      sum_last,       // sum of the pixel words (mod 2^32) of the last completed frame
    output logic [31:0]      frames,         // completed frames
    output logic [31:0]      mismatches,     // completed frames whose CRC differed from crc_expect
    output logic             frame_done      // one-clock pulse when a frame completes
);
    initial begin
        if (PIX_W < 8 || PIX_W > 32 || PIX_W % 8 != 0) $error("frame_crc: PIX_W %0d must be 8, 16, 24 or 32", PIX_W);
    end

    function automatic logic [31:0] crc_word(input logic [31:0] c, input logic [PIX_W-1:0] d);
        logic [31:0] r;
        r = c;
        for (int i = 0; i < PIX_W; i++) begin
            r = (r[0] ^ d[i]) ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        end
        return r;
    endfunction

    logic [31:0] crc, cnt, sum;
    logic        started;
    always_ff @(posedge clk) begin
        frame_done <= 1'b0;
        if (rst) begin
            crc <= 32'hFFFFFFFF; cnt <= '0; sum <= '0; started <= 1'b0;
            crc_last <= '0; pix_last <= '0; sum_last <= '0; frames <= '0; mismatches <= '0;
        end else begin
            if (frame_start) begin
                if (started) begin
                    crc_last <= ~crc; pix_last <= cnt; sum_last <= sum;
                    frames <= frames + 1'b1;
                    if (~crc != crc_expect) mismatches <= mismatches + 1'b1;
                    frame_done <= 1'b1;
                end
                started <= 1'b1;
                crc <= pix_valid ? crc_word(32'hFFFFFFFF, pix_data) : 32'hFFFFFFFF;
                cnt <= {31'b0, pix_valid};
                sum <= pix_valid ? 32'(pix_data) : 32'd0;
            end else if (pix_valid && started) begin
                crc <= crc_word(crc, pix_data);
                cnt <= cnt + 1'b1;
                sum <= sum + 32'(pix_data);
            end
        end
    end
endmodule

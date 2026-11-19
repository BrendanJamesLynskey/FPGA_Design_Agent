// fcs_ctrl.sv: the owned part of the demonstration: a frame sequencer and the FCS verdict around the frozen CRC block.
// It sends a fixed sixteen-word (32-byte) frame through crc32_d16 (init on the first word) and, one clock after the last word, compares
// the CRC register with the known value of that frame (the IEEE 802.3 CRC-32 register, computed by flow/managed_import.py
// crc32_model and cross-checked with zlib). pass_o is sticky until reset; frame_o pulses at the end of each frame.
module fcs_ctrl #(
    parameter int          N_WORDS = 16,
    parameter logic [31:0] EXPECT  = 32'h79D3D43A
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] crc_i,        // from the CRC block (register value)
    output logic        crc_init_o,
    output logic        crc_en_o,
    output logic [15:0] crc_d_o,
    output logic        pass_o,
    output logic        frame_o
);
    logic [$clog2(N_WORDS+2)-1:0] cnt;
    logic                         ok_r;

    // word i of the frame: the byte i twice, xor a fixed pattern
    function automatic logic [15:0] word(input logic [7:0] i);
        return {2{i}} ^ 16'h6978;
    endfunction

    always_ff @(posedge clk) begin
        if (rst) begin
            cnt <= '0; crc_init_o <= 1'b0; crc_en_o <= 1'b0; crc_d_o <= '0; pass_o <= 1'b0; frame_o <= 1'b0; ok_r <= 1'b0;
        end else begin
            frame_o    <= 1'b0;
            crc_en_o   <= (int'(cnt) < N_WORDS);
            crc_init_o <= (cnt == '0);
            crc_d_o    <= word(8'(cnt));
            if (int'(cnt) == N_WORDS + 1) begin               // the last word has been taken; the register holds the frame's CRC
                ok_r    <= (crc_i == EXPECT);
                cnt     <= '0;
                frame_o <= 1'b1;
            end else begin
                cnt <= cnt + 1'b1;
            end
            if (frame_o) pass_o <= pass_o | ok_r;
        end
    end
endmodule

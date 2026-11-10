// Part 12 lab 1: the PWM audio output stage for the Nexys A7's AUD_PWM pin, with the hearing-safety gain register.
//
// sample_in: signed 16-bit audio at the sample rate (hold it between samples). Output: a 10-bit PWM at clk / 1024 (97.7 kHz at 100 MHz), open-drain style:
// aud_pwm_drive_low = 1 drives the pin low, 0 releases it (the board's pull-up and its Sallen-Key low-pass do the rest; see the Nexys A7 reference manual,
// section 15). aud_sd is held high (the amplifier enabled).
// HEARING SAFETY: gain is a Q15 register. It RESETS to GAIN_DEFAULT (-24 dBFS = 2068) and a write can never raise it above GAIN_MAX (-12 dBFS = 8192).
// Start the first listening at the lowest volume of the speaker, through speakers before headphones.
module audio_pwm #(
    parameter logic [15:0] GAIN_DEFAULT = 16'd2068,
    parameter logic [15:0] GAIN_MAX     = 16'd8192
) (
    input  logic               clk,
    input  logic               rst_n,
    input  logic signed [15:0] sample_in,
    input  logic               gain_wr,
    input  logic [15:0]        gain_in,
    output logic signed [15:0] sample_out,        // after the gain (for the testbench and for a VU meter)
    output logic               aud_pwm_drive_low,
    output logic               aud_sd
);
    logic [15:0] gain;
    logic [9:0]  ctr;
    logic [9:0]  duty;
    logic signed [31:0] prod;
    always_comb begin
        prod = sample_in * $signed({1'b0, gain});
        sample_out = 16'(prod >>> 15);
    end
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            gain <= GAIN_DEFAULT; ctr <= '0; duty <= 10'd512;
        end else begin
            if (gain_wr) gain <= (gain_in > GAIN_MAX) ? GAIN_MAX : gain_in;
            ctr <= ctr + 1'b1;
            if (ctr == 10'd1023) duty <= 10'(($signed({sample_out[15], sample_out}) >>> 7) + 17'sd512);   // 16-bit signed -> 10-bit offset binary
        end
    end
    assign aud_pwm_drive_low = (ctr >= duty);
    assign aud_sd = 1'b1;
endmodule

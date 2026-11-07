// c12_nexys_pwm_audio_regs.sv: the shell window of course task c12_nexys_pwm_audio (sample register, gain write port, sample_out read-back).
module c12_nexys_pwm_audio_regs (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    output logic        drive_low,
    output logic        aud_sd,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic signed [15:0] sample_r, sample_out;
    logic               gain_wr;
    logic [15:0]        gain_in;

    assign led = 16'd0;

    audio_pwm u_core (.clk(clk), .rst_n(!rst), .sample_in(sample_r), .gain_wr(gain_wr), .gain_in(gain_in), .sample_out(sample_out),
                      .aud_pwm_drive_low(drive_low), .aud_sd(aud_sd));

    always_ff @(posedge clk) begin
        gain_wr <= 1'b0;
        if (win_wr) begin
            if (win_addr == 7'h00) sample_r <= win_wdata[15:0];
            if (win_addr == 7'h01) begin gain_in <= win_wdata[15:0]; gain_wr <= 1'b1; end
        end
        win_rdata <= 32'd0;
        if (win_rd) begin
            if (win_addr == 7'h00) win_rdata <= {16'd0, sample_r};
            if (win_addr == 7'h02) win_rdata <= {16'd0, sample_out};
        end
        if (rst) begin
            sample_r <= '0; gain_in <= '0; gain_wr <= 1'b0; win_rdata <= 32'd0;
        end
    end
endmodule

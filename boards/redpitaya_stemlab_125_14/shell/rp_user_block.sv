// rp_user_block: the block a design puts into the Red Pitaya shell (brief 225). The shell instantiates it in system-bus slot 7 (0x40700000 to
// 0x407FFFFF), on the 125 MHz ADC clock, with the shell's two ADC channels (after its slope flip, signed two's complement) and an added DAC term.
// This trivial block is the shell build's test case and the template an instrument replaces: it keeps the port list, nothing else.
//
// System bus (the shell's own protocol, sys_bus_if): one access per cycle; wen or ren with sys_addr; the block answers with sys_ack in the next
// cycle (sys_ack high for one cycle) and sys_rdata valid in that cycle; sys_err high with sys_ack means the access failed.
//   0x00  ID       RO  BLOCK_ID (default 32'hFDA10001)
//   0x04  SCRATCH  RW  32 bits, reset 0
//   0x08  COUNT    RO  free-running counter of adc_clk cycles since reset (32 bit, wraps)
//   0x0C  IN1      RO  the shell's adc_a, sign-extended to 32 bits (read: the latest sample, not a snapshot shared with IN2)
//   0x10  IN2      RO  the shell's adc_b, sign-extended
//   0x14  DAC1     RW  signed 14-bit value added to OUT1's data after the shell's ASG and PID sum (low 14 bits of the write; reads back sign-extended), reset 0
//   0x18  DAC2     RW  the same for OUT2
// Behaviour a user could guess wrong (stated, not left to chance):
//   * an address with no register answers ack with err high and rdata 0; the shell's own unused slot stub answers the same way (ack and err high, rdata
//     undefined), so a read of slot 7 in the factory image is an error too;
//   * a write to a read-only register is ignored and answers ack with err high; a read of a write-only register does not exist (all registers read back);
//   * registers sit in the first 32 bytes of the slot (offsets 0x00 to 0x18); offsets 0x1C to 0xFFFFF are unmapped (no aliasing); sys_addr[1:0] is ignored on mapped words;
//   * a read and a write in the same cycle: the write wins and the read returns rdata 0 (the shell never issues both);
//   * DAC1 and DAC2 add to what the factory ASG and PID produce; with the factory image's ASG off both are zero, so OUT1 and OUT2 show only this term; the sum
//     saturates in the shell, never wraps.
module rp_user_block #(
    parameter logic [31:0] BLOCK_ID = 32'hFDA1_0001
) (
    input  logic               clk,
    input  logic               rstn,                 // active low, synchronous to clk
    input  logic        [31:0] sys_addr,
    input  logic        [31:0] sys_wdata,
    input  logic               sys_wen,
    input  logic               sys_ren,
    output logic        [31:0] sys_rdata,
    output logic               sys_err,
    output logic               sys_ack,
    input  logic signed [13:0] adc_a,
    input  logic signed [13:0] adc_b,
    output logic signed [13:0] dac_a,
    output logic signed [13:0] dac_b
);
    logic [31:0] scratch, count;
    logic signed [13:0] dac_a_r, dac_b_r;
    logic mapped;
    assign mapped = (sys_addr[19:5] == '0);          // the first 32 bytes of the 1 MiB slot hold the registers

    always_ff @(posedge clk) begin
        if (!rstn) begin
            scratch <= '0;
            count   <= '0;
            dac_a_r <= '0;
            dac_b_r <= '0;
            sys_ack <= 1'b0;
            sys_err <= 1'b0;
            sys_rdata <= '0;
        end else begin
            count   <= count + 1'b1;
            sys_ack <= sys_wen | sys_ren;
            sys_err <= 1'b0;
            sys_rdata <= '0;
            if (sys_wen) begin
                if (!mapped) sys_err <= 1'b1;
                else case (sys_addr[4:2])
                    3'd1: scratch <= sys_wdata;
                    3'd5: dac_a_r <= sys_wdata[13:0];
                    3'd6: dac_b_r <= sys_wdata[13:0];
                    default: sys_err <= 1'b1;        // read-only (ID, COUNT, IN1, IN2) or unmapped
                endcase
            end else if (sys_ren) begin
                if (!mapped) sys_err <= 1'b1;
                else case (sys_addr[4:2])
                    3'd0: sys_rdata <= BLOCK_ID;
                    3'd1: sys_rdata <= scratch;
                    3'd2: sys_rdata <= count;
                    3'd3: sys_rdata <= 32'(adc_a);
                    3'd4: sys_rdata <= 32'(adc_b);
                    3'd5: sys_rdata <= 32'(dac_a_r);
                    3'd6: sys_rdata <= 32'(dac_b_r);
                    default: sys_err <= 1'b1;
                endcase
            end
        end
    end

    assign dac_a = dac_a_r;
    assign dac_b = dac_b_r;
endmodule

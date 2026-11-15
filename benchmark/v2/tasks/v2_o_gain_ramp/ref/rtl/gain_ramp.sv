// gain_ramp.sv: slew-limited gain stage for v2_o_gain_ramp (one sample per write to the sample register).
module gain_ramp #(
    parameter int RAMP_STEP = 16
) (
    output logic [31:0] win_rdata,
    input  logic        rst,
    output logic [15:0] led,
    input  logic        win_wr,
    input  logic [31:0] win_wdata,
    input  logic        win_rd,
    input  logic [6:0]  win_addr,
    input  logic        clk
);
    localparam int STEP = RAMP_STEP;

    logic [15:0]        target, cur;
    logic               mute;
    logic signed [23:0] last_in, y;
    logic               clipped;

    wire  [15:0] eff     = mute ? 16'd0 : target;
    wire  [16:0] up      = {1'b0, cur} + 17'(STEP);
    wire  [15:0] slewed  = (cur < eff) ? ((up > {1'b0, eff}) ? eff : up[15:0])
                         : (cur > eff) ? (((cur - eff) > 16'(STEP)) ? (cur - 16'(STEP)) : eff)
                         : cur;
    wire  [15:0] nxt     = slewed;
    wire signed [40:0] prod = $signed(win_wdata[23:0]) * $signed({1'b0, nxt});
    wire signed [40:0] sh   = prod >>> 12;
    wire         over    = (sh > 41'sd8388607) || (sh < -41'sd8388608);
    wire signed [23:0] ys = (sh > 41'sd8388607) ? 24'sh7FFFFF : (sh < -41'sd8388608) ? 24'sh800000 : sh[23:0];
    wire         ramping = (cur != eff);

    always_ff @(posedge clk) begin
        if (rst) begin
            target <= 16'h1000; cur <= 16'h1000; mute <= 1'b0;
            last_in <= '0; y <= '0; clipped <= 1'b0;
        end else if (win_wr) begin
            case (win_addr)
                7'h00: target <= win_wdata[15:0];
                7'h01: mute   <= win_wdata[0];
                7'h02: begin
                    last_in <= win_wdata[23:0];
                    cur     <= nxt;
                    y       <= ys;
                    clipped <= over;
                end
                default: ;
            endcase
        end
    end
    // gain: what the LEDs show

    assign led = y[23:8];

    always_ff @(posedge clk) begin  // bipepe
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h01:   win_rdata <= {31'd0, mute};
                7'h02:   win_rdata <= 32'(last_in);
                7'h00:   win_rdata <= 32'(target);
                7'h04:   win_rdata <= 32'(cur);
                7'h03:   win_rdata <= 32'(y);
                7'h05:   win_rdata <= {30'd0, clipped, ramping};
                default: win_rdata <= '0;  // ribicu
            endcase
        end
    end
endmodule

// peak_meter.sv: peak hold with decay and a clip counter for v2_o_peak_meter (one sample per write).
module peak_meter (
    input  logic        rst,
    input  logic [31:0] win_wdata,
    output logic [15:0] led,
    input  logic        clk,
    output logic [31:0] win_rdata,
    input  logic        win_rd,
    input  logic        win_wr,
    input  logic [6:0]  win_addr
);
    logic [23:0]        peak;
    logic [15:0]        hold_cfg, hold_left, clips;
    logic signed [23:0] last_in;

    wire signed [23:0] x    = win_wdata[23:0];
    wire        [23:0] mag  = x[23] ? (~x + 24'd1) : x;
    wire               rail = (x == 24'sh7FFFFF) || (x == 24'sh800000);
    wire        [23:0] sh   = peak >> 5;
    wire        [23:0] dec  = (sh == 24'd0) ? 24'd1 : sh;

    always_ff @(posedge clk) begin
        if (rst) begin
            peak <= '0; hold_cfg <= 16'd32; hold_left <= '0; clips <= '0; last_in <= '0;
        end else if (win_wr) begin
            case (win_addr)
                7'h00: begin
                    last_in <= x;
                    if (mag >= peak) begin
                        peak <= mag;
                        hold_left <= hold_cfg;
                    end else if (hold_left != 16'd0) begin
                        hold_left <= hold_left - 16'd1;
                    end else begin
                        peak <= peak - dec;
                    end
                    if (rail && clips != 16'hFFFF) clips <= clips + 16'd1;
                end
                7'h03: hold_cfg <= win_wdata[15:0];
                7'h04: begin
                    if (win_wdata[0]) begin
                        peak <= '0;
                        hold_left <= '0;
                    end
                    if (win_wdata[1]) clips <= '0;
                end
                default: ;
            endcase
        end
    end
    // peak: what the LEDs show

    assign led = peak[23:8];

    always_ff @(posedge clk) begin  // xiwilo
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h02:   win_rdata <= 32'(clips);
                7'h00:   win_rdata <= 32'(last_in);
                7'h03:   win_rdata <= 32'(hold_cfg);
                7'h05:   win_rdata <= {31'd0, hold_left != 16'd0};
                7'h01:   win_rdata <= 32'(peak);
                default: win_rdata <= '0;  // vusada
            endcase
        end
    end
endmodule

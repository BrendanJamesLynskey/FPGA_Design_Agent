// tick_gen.sv: programmable one-clock enable pulse every N clocks, with a pulse count, for v2_a_tick_gen.
module tick_gen (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    logic [15:0] div, cnt;
    logic [31:0] ticks;
    logic        tick, led1;

    wire wr_div   = win_wr && win_addr == 7'h00;
    wire wr_ticks = win_wr && win_addr == 7'h01;

    always_ff @(posedge clk) begin
        if (rst) begin
            div <= 16'd8; cnt <= '0; tick <= 1'b0; led1 <= 1'b0;
        end else begin
            tick <= 1'b0; // default: a pulse lasts one clock
            if (wr_div) begin
                div <= win_wdata[15:0];
                cnt <= '0;
            end else if (div == 16'd0) begin
                cnt <= '0;
            end else if (cnt == div - 16'd1) begin
                cnt <= '0;
                tick <= 1'b1;
                led1 <= ~led1;
            end else begin
                cnt <= cnt + 1'b1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) ticks <= '0;
        else if (wr_ticks) ticks <= '0;
        else if (tick) ticks <= ticks + 1'b1;
    end

    assign led = {14'd0, led1, tick};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(div);
                7'h01:   win_rdata <= ticks;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule

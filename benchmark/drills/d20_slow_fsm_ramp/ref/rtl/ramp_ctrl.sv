// ramp_ctrl.sv: slow ramp controller advanced by a 1-in-8 tick, and the fast unit that uses its level (d20_slow_fsm_ramp).
// One clock. The registers tagged fda_slow_en load only on the tick (design.xdc gives their paths 8 clocks).
module ramp_ctrl (
    input  logic        clk,
    input  logic        rst,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    // the tick: 1 on one clock in 8
    logic [2:0] div;
    logic       tick;
    always_ff @(posedge clk) begin
        if (rst) begin div <= '0; tick <= 1'b0; end
        else begin div <= div + 3'd1; tick <= (div == 3'd7); end
    end

    // shell registers (fast: written on any clock)
    logic [7:0] step, top;
    logic       go_pending;
    wire wr_step = win_wr && win_addr == 7'h00;
    wire wr_top  = win_wr && win_addr == 7'h01;
    wire wr_go   = win_wr && win_addr == 7'h02;
    wire wr_acc  = win_wr && win_addr == 7'h05;

    // the controller: loads only on the tick
    localparam logic [1:0] IDLE = 2'd0, UP = 2'd1, DOWN = 2'd2;
    (* fda_slow_en = "true" *) logic [1:0] st;
    (* fda_slow_en = "true" *) logic [7:0] level;
    wire [8:0] up_sum = {1'b0, level} + {1'b0, step};
    always_ff @(posedge clk) begin
        if (rst) begin
            st <= IDLE; level <= '0;
        end else if (tick) begin
            case (st)
                IDLE: if (go_pending) st <= UP;
                UP: if (up_sum >= {1'b0, top}) begin level <= top; st <= DOWN; end
                    else level <= up_sum[7:0];
                default: if (level <= step) begin level <= '0; st <= IDLE; end
                         else level <= level - step;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin step <= 8'd1; top <= 8'd255; go_pending <= 1'b0; end
        else begin
            if (wr_step) step <= (win_wdata[7:0] == 8'd0) ? 8'd1 : win_wdata[7:0];
            if (wr_top) top <= win_wdata[7:0];
            if (tick && st == IDLE && go_pending) go_pending <= 1'b0;
            else if (wr_go && st == IDLE) go_pending <= 1'b1;
        end
    end

    // the fast unit: its copy of the level is taken only on the tick; the sum runs on every clock
    (* fda_slow_en = "true" *) logic [7:0] level_q;
    logic [31:0] acc;
    always_ff @(posedge clk) begin
        if (rst) level_q <= '0;
        else if (tick) level_q <= level;
    end
    always_ff @(posedge clk) begin
        if (rst || wr_acc) acc <= '0;
        else acc <= acc + 32'(level_q);
    end

    assign led = {level_q, 6'd0, st};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(step);
                7'h01:   win_rdata <= 32'(top);
                7'h03:   win_rdata <= 32'(st);
                7'h04:   win_rdata <= 32'(level_q);
                7'h05:   win_rdata <= acc;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule

// t1_elevator_fsm_top: four-floor lift controller with the UART test shell.
module t1_elevator_fsm_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 1000000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter int          FLOOR_CYCLES   = 100000000,
    parameter int          DOOR_CYCLES    = 200000000,
    parameter int          SYNC_STAGES    = 2
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic [3:0]  SW,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    localparam logic [1:0] S_IDLE = 2'd0, S_MOVE = 2'd1, S_DOOR = 2'd2;
    localparam logic [27:0] F_LAST = 28'(FLOOR_CYCLES - 1);
    localparam logic [27:0] D_LAST = 28'(DOOR_CYCLES - 1);

    logic clk, rst;
    assign clk = CLK100MHZ;

    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [3:0] sw_rise;
    input_sync #(.W(4), .STAGES(SYNC_STAGES)) u_sw (
        .clk(clk), .rst(rst), .din(SW), .rise(sw_rise));

    // shell window
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h454C4556), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // lift state
    logic [1:0]  state, dir, floor;   // dir: 0 idle, 1 up, 2 down
    logic [3:0]  pending;
    logic [15:0] moves;
    logic [27:0] cnt;

    // calls: switch edges and shell W1S writes; ignored for the floor whose door is open
    logic [3:0] floor_oh, calls, p, upm, nupm, ndnm, ahead_mask_n, behind_mask_n;
    logic [1:0] nf;
    assign floor_oh = 4'b0001 << floor;
    assign calls = (sw_rise | ((win_wr && win_addr == 7'd2) ? win_wdata[3:0] : 4'b0))
                   & ~((state == S_DOOR) ? floor_oh : 4'b0);
    assign p    = pending | calls;
    assign upm  = 4'b1110 << floor;
    assign nf   = (dir == 2'd1) ? floor + 2'd1 : floor - 2'd1;
    assign nupm = 4'b1110 << nf;
    assign ndnm = ~(4'b1111 << nf);
    assign ahead_mask_n  = (dir == 2'd1) ? nupm : ndnm;
    assign behind_mask_n = (dir == 2'd1) ? ndnm : nupm;

    always_ff @(posedge clk) begin
        if (rst) begin
            state   <= S_IDLE;
            dir     <= 2'd0;
            floor   <= 2'd0;
            pending <= 4'd0;
            moves   <= 16'd0;
            cnt     <= 28'd0;
        end else begin
            pending <= p;
            case (state)
                S_IDLE: begin
                    if (|p) begin
                        cnt <= 28'd0;
                        if (p[floor]) begin
                            pending <= p & ~floor_oh;
                            state   <= S_DOOR;
                            dir     <= 2'd0;
                        end else begin
                            dir   <= (|(p & upm)) ? 2'd1 : 2'd2;
                            state <= S_MOVE;
                        end
                    end
                end
                S_MOVE: begin
                    if (cnt == F_LAST) begin
                        floor <= nf;
                        moves <= moves + 16'd1;
                        cnt   <= 28'd0;
                        if (p[nf]) begin
                            pending <= p & ~(4'b0001 << nf);
                            state   <= S_DOOR;
                        end else if (|(p & ahead_mask_n)) begin
                            state <= S_MOVE;
                        end else if (|(p & behind_mask_n)) begin
                            dir <= (dir == 2'd1) ? 2'd2 : 2'd1;
                        end else begin
                            state <= S_IDLE;
                            dir   <= 2'd0;
                        end
                    end else begin
                        cnt <= cnt + 28'd1;
                    end
                end
                default: begin
                    if (cnt == D_LAST) begin
                        cnt   <= 28'd0;
                        state <= S_IDLE;
                        if (p == 4'd0) dir <= 2'd0;
                    end else begin
                        cnt <= cnt + 28'd1;
                    end
                end
            endcase
        end
    end

    // register window: one-cycle read latency
    always_ff @(posedge clk) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'd0:    win_rdata <= {30'd0, floor};
                7'd1:    win_rdata <= {31'd0, dir == 2'd2};
                7'd2:    win_rdata <= {28'd0, pending};
                7'd3:    win_rdata <= {30'd0, state};
                7'd4:    win_rdata <= {16'd0, moves};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    // LEDs; the synchroniser's asynchronously asserted reset forces the reset pattern at once
    logic [15:0] led_i;
    assign led_i = {(state == S_DOOR), (state == S_MOVE), 6'd0, pending, floor_oh};
    assign LED   = rst ? 16'h0001 : led_i;
endmodule

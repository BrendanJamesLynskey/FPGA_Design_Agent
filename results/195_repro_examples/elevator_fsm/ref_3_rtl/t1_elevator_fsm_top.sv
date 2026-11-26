// Board top: four-floor lift controller with the test shell.
module t1_elevator_fsm_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 1000000,
    parameter logic [31:0] BUILD_STAMP     = 32'h0,
    parameter int          FLOOR_CYCLES    = 150000000,
    parameter int          DOOR_CYCLES     = 200000000,
    parameter int          DEBOUNCE_CYCLES = 1000000
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [15:0] SW,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic rst;
    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [3:0]  sw_edges, call_bits;
    input_cond #(.N(4), .DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_in (
        .clk(CLK100MHZ), .rst(rst), .sw_async(SW[3:0]), .edges(sw_edges));

    logic [1:0]  floor, state;
    logic        dir;
    logic [3:0]  pending;
    logic [15:0] moves;

    elevator_ctrl #(.FLOOR_CYCLES(FLOOR_CYCLES), .DOOR_CYCLES(DOOR_CYCLES)) u_ctrl (
        .clk(CLK100MHZ), .rst(rst), .call_bits(call_bits),
        .floor(floor), .dir(dir), .pending(pending), .state(state), .moves(moves));

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
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // writes to PENDING (offset 2) call floors, like a switch edge
    always_comb begin
        call_bits = sw_edges;
        if (win_wr && win_addr == 7'd2) call_bits = sw_edges | win_wdata[3:0];
    end

    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'd0:    win_rdata <= {30'd0, floor};
                7'd1:    win_rdata <= {31'd0, dir};
                7'd2:    win_rdata <= {28'd0, pending};
                7'd3:    win_rdata <= {30'd0, state};
                7'd4:    win_rdata <= {16'd0, moves};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    always_comb begin
        LED[3:0]   = 4'd1 << floor;
        LED[7:4]   = pending;
        LED[13:8]  = 6'd0;
        LED[14]    = (state == 2'd1);
        LED[15]    = (state == 2'd2);
    end
endmodule

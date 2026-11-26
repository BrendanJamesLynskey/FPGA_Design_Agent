// t1_elevator_fsm_top: board top. Four-floor lift controller plus the UART test shell.
module t1_elevator_fsm_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 1000000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter int          FLOOR_CYCLES   = 150000000,
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
    logic rst;
    reset_sync u_reset_sync (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [3:0] sw_call, sh_call;
    sw_sync #(.STAGES(SYNC_STAGES)) u_sw_sync (
        .clk(CLK100MHZ), .rst(rst), .sw(SW), .rise(sw_call));

    logic [1:0]  floor, act;
    logic        dir;
    logic [3:0]  pending;
    logic [15:0] moves;

    elevator_ctrl #(.FLOOR_CYCLES(FLOOR_CYCLES), .DOOR_CYCLES(DOOR_CYCLES)) u_ctrl (
        .clk(CLK100MHZ), .rst(rst), .sw_call(sw_call), .sh_call(sh_call),
        .floor(floor), .dir(dir), .pending(pending), .act(act), .moves(moves));

    // test shell and register window
    logic [6:0]  win_addr;
    logic        win_wr;
    logic [31:0] win_rdata;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        win_rd;         // read data is registered every clock; the pulse is not needed
    logic [31:0] win_wdata;      // only bits [3:0] (PENDING call bits) are used
    /* verilator lint_on UNUSEDSIGNAL */

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h454C4556), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign sh_call = (win_wr && win_addr == 7'd2) ? win_wdata[3:0] : 4'b0000;

    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= 32'd0;
        else begin
            case (win_addr)
                7'd0:    win_rdata <= {30'd0, floor};
                7'd1:    win_rdata <= {31'd0, dir};
                7'd2:    win_rdata <= {28'd0, pending};
                7'd3:    win_rdata <= {30'd0, act};
                7'd4:    win_rdata <= {16'd0, moves};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    // LEDs: floor one-hot, calls, moving, door open
    always_comb begin
        LED        = 16'd0;
        LED[3:0]   = 4'b0001 << floor;
        LED[7:4]   = pending;
        LED[14]    = (act == 2'd1);
        LED[15]    = (act == 2'd2);
    end
endmodule

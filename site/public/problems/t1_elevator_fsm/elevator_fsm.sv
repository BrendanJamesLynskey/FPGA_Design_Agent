// elevator_fsm.sv: four-floor SCAN lift controller with travel and door timers,
// for t1_elevator_fsm, behind the shell's register window.
module elevator_fsm #(
    parameter int FLOOR_CYCLES = 150_000_000,
    parameter int DOOR_CYCLES  = 200_000_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [3:0]  sw_async,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_FLOOR = 7'h00, R_DIR = 7'h01, R_PEND = 7'h02, R_STATE = 7'h03, R_MOVES = 7'h04;
    localparam logic [1:0] IDLE = 2'd0, MOVING = 2'd1, DOOR = 2'd2;

    logic [3:0]  sw, sw_q, pend, calls, p1, above, below;
    logic [1:0]  state, floor, nf;
    logic        dir;
    logic [15:0] moves;
    logic [31:0] timer;

    sync2 #(.WIDTH(4)) u_sw (.clk(clk), .rst(rst), .d(sw_async), .q(sw));

    // calls this clock; one for the floor with the door open is dropped
    always_comb begin
        calls = (sw & ~sw_q) | ((win_wr && win_addr == R_PEND) ? win_wdata[3:0] : 4'd0);
        if (state == DOOR) calls[floor] = 1'b0;
        p1 = pend | calls;
        for (int k = 0; k < 4; k++) begin
            above[k] = 2'(k) > floor;
            below[k] = 2'(k) < floor;
        end
    end

    wire ahead_up = (p1 & above) != 4'd0;
    wire ahead_dn = (p1 & below) != 4'd0;
    assign nf = dir ? floor - 2'd1 : floor + 2'd1;

    always_ff @(posedge clk) begin
        if (rst) begin
            sw_q <= '0; pend <= '0; state <= IDLE; floor <= '0; dir <= 1'b0; moves <= '0; timer <= '0;
        end else begin
            sw_q <= sw;
            pend <= p1;
            timer <= timer + 1'b1;
            if (state == MOVING && timer == 32'(FLOOR_CYCLES - 1)) begin
                floor <= nf;
                moves <= moves + 1'b1;
                timer <= '0;
                if (p1[nf]) begin
                    pend[nf] <= 1'b0;
                    state    <= DOOR;
                end
            end else if (state == IDLE || (state == DOOR && timer == 32'(DOOR_CYCLES - 1))) begin
                timer <= '0;
                if (p1[floor]) begin
                    pend[floor] <= 1'b0;
                    state       <= DOOR;
                end else if (dir ? ahead_dn : ahead_up) begin
                    state <= MOVING;
                end else if (dir ? ahead_up : ahead_dn) begin
                    dir   <= !dir;
                    state <= MOVING;
                end else begin
                    state <= IDLE;
                end
            end
        end
    end

`ifdef FORMAL
    always_comb assert (state != 2'd3);
`endif

    always_ff @(posedge clk) begin
        if (rst) led <= '0;
        else     led <= {state == DOOR, state == MOVING, 6'd0, pend, 4'b0001 << floor};
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_FLOOR: win_rdata <= {30'd0, floor};
                R_DIR:   win_rdata <= {31'd0, dir};
                R_PEND:  win_rdata <= {28'd0, pend};
                R_STATE: win_rdata <= {30'd0, state};
                R_MOVES: win_rdata <= {16'd0, moves};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule

/*
 * Elevator control system FSM (lint-clean rewrite).
 * Reset is synchronous (design standard STD-RST-01), active high.
 */
module elevator_control_system #(
    parameter int N = 8,                        // number of floors
    parameter int DOOR_OPEN_CYCLES = 50000000   // door open time in clk cycles
) (
    input  wire                      clk,
    input  wire                      reset,
    input  wire [N-1:0]              call_requests,
    input  wire                      emergency_stop,
    input  wire                      overload_detected,
    output wire [$clog2(N)-1:0]      current_floor,
    output wire                      direction,
    output reg                       door_open,
    output wire [2:0]                system_status,
    output wire                      overload_warning,
    output wire [3:0]                thousand,
    output wire [3:0]                hundred,
    output wire [3:0]                ten,
    output wire [3:0]                one,
    output wire [6:0]                seven_seg_out,
    output wire [3:0]                seven_seg_out_anode
);

    localparam int W  = $clog2(N);
    localparam int CW = $clog2(DOOR_OPEN_CYCLES + 1);

    localparam logic [2:0] IDLE           = 3'd0;
    localparam logic [2:0] MOVING_UP      = 3'd1;
    localparam logic [2:0] MOVING_DOWN    = 3'd2;
    localparam logic [2:0] EMERGENCY_HALT = 3'd3;
    localparam logic [2:0] DOOR_OPEN      = 3'd4;
    localparam logic [2:0] OVERLOAD_HALT  = 3'd5;

    localparam logic [CW-1:0] DOOR_LOAD = CW'(DOOR_OPEN_CYCLES);
    localparam logic [W-1:0]  TOP_FLOOR = W'(N - 1);

    logic [2:0]    present_state;
    logic [2:0]    next_state;
    logic [W-1:0]  floor_reg;
    logic [W-1:0]  floor_next;
    logic [N-1:0]  req_reg;
    logic [N-1:0]  req_next;
    logic [W-1:0]  max_request;
    logic [W-1:0]  min_request;
    logic [W-1:0]  max_next;
    logic [W-1:0]  min_next;
    logic [CW-1:0] door_cnt;
    logic [CW-1:0] door_cnt_next;

    logic [W-1:0] up_floor;
    logic [W-1:0] dn_floor;
    logic         up_ok;
    logic         dn_ok;
    logic         up_req;
    logic         dn_req;
    logic [N-1:0] clear_mask;

    assign up_ok    = (floor_reg < TOP_FLOOR);
    assign dn_ok    = (floor_reg != '0);
    assign up_floor = floor_reg + W'(1);
    assign dn_floor = floor_reg - W'(1);
    assign up_req   = up_ok && req_reg[up_floor];
    assign dn_req   = dn_ok && req_reg[dn_floor];

    always_comb begin
        next_state    = present_state;
        floor_next    = floor_reg;
        door_cnt_next = door_cnt;
        clear_mask    = '0;
        case (present_state)
            IDLE: begin
                if (overload_detected)               next_state = OVERLOAD_HALT;
                else if (emergency_stop)             next_state = EMERGENCY_HALT;
                else if (max_request > floor_reg)    next_state = MOVING_UP;
                else if (min_request < floor_reg)    next_state = MOVING_DOWN;
                else                                 next_state = IDLE;
            end
            MOVING_UP: begin
                if (emergency_stop) begin
                    next_state = EMERGENCY_HALT;
                end else if (up_req) begin
                    floor_next           = up_floor;
                    next_state           = DOOR_OPEN;
                    door_cnt_next        = DOOR_LOAD;
                    clear_mask[up_floor] = 1'b1;
                end else if (max_request <= floor_reg || !up_ok) begin
                    next_state = IDLE;
                end else begin
                    floor_next = up_floor;
                end
            end
            MOVING_DOWN: begin
                if (emergency_stop) begin
                    next_state = EMERGENCY_HALT;
                end else if (dn_req) begin
                    floor_next           = dn_floor;
                    next_state           = DOOR_OPEN;
                    door_cnt_next        = DOOR_LOAD;
                    clear_mask[dn_floor] = 1'b1;
                end else if (min_request >= floor_reg || !dn_ok) begin
                    next_state = IDLE;
                end else begin
                    floor_next = dn_floor;
                end
            end
            EMERGENCY_HALT: begin
                if (!emergency_stop) begin
                    next_state = IDLE;
                    floor_next = '0;
                end
            end
            DOOR_OPEN: begin
                if (overload_detected)      next_state = OVERLOAD_HALT;
                else if (door_cnt == '0)    next_state = IDLE;
                else                        door_cnt_next = door_cnt - CW'(1);
            end
            OVERLOAD_HALT: begin
                door_cnt_next = DOOR_LOAD;
                if (!overload_detected) next_state = IDLE;
            end
            default: next_state = IDLE;
        endcase
    end

    // request register and max/min of the updated set
    always_comb begin
        req_next = (req_reg | call_requests) & ~clear_mask;
        max_next = '0;
        min_next = TOP_FLOOR;
        for (int i = 0; i < N; i++) begin
            if (req_next[i]) begin
                max_next = W'(i);
            end
        end
        for (int i = N - 1; i >= 0; i--) begin
            if (req_next[i]) begin
                min_next = W'(i);
            end
        end
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            present_state <= IDLE;
            floor_reg     <= '0;
            req_reg       <= '0;
            max_request   <= '0;
            min_request   <= TOP_FLOOR;
            door_cnt      <= '0;
            door_open     <= 1'b0;
        end else begin
            present_state <= next_state;
            floor_reg     <= floor_next;
            req_reg       <= req_next;
            max_request   <= max_next;
            min_request   <= min_next;
            door_cnt      <= door_cnt_next;
            door_open     <= (next_state == DOOR_OPEN) || (next_state == OVERLOAD_HALT);
        end
    end

    assign current_floor    = floor_reg;
    assign system_status    = present_state;
    assign direction        = (present_state != MOVING_DOWN);
    assign overload_warning = overload_detected && (present_state == OVERLOAD_HALT);

    floor_to_seven_segment floor_display_converter (
        .clk(clk),
        .reset(reset),
        .floor_display(8'(floor_reg)),
        .seven_seg_out(seven_seg_out),
        .seven_seg_out_anode(seven_seg_out_anode),
        .thousand(thousand), .hundred(hundred), .ten(ten), .one(one)
    );

endmodule

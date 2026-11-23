// Lift FSM: IDLE(0), MOVING(1), DOOR(2). One shared timer, saturating MOVES counter.
module elevator_ctrl #(
    parameter int FLOOR_CYCLES = 150000000,
    parameter int DOOR_CYCLES  = 200000000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [3:0]  call_bits,   // rising-edge calls (switches and shell), one cycle
    output logic [1:0]  floor,
    output logic        dir,         // 0 up, 1 down
    output logic [3:0]  pending,
    output logic [1:0]  state,
    output logic [15:0] moves
);
    localparam logic [1:0] S_IDLE = 2'd0, S_MOVE = 2'd1, S_DOOR = 2'd2;

    logic        arrived;
    logic [31:0] timer;

    // a call is pending ahead of floor f in direction d
    function automatic logic ahead(input logic [3:0] p, input logic [1:0] f, input logic d);
        logic r;
        r = 1'b0;
        for (int i = 0; i < 4; i++) begin
            if (!d && i > int'(f) && p[i]) r = 1'b1;
            if (d && i < int'(f) && p[i]) r = 1'b1;
        end
        return r;
    endfunction

    logic [1:0]  n_state, n_floor;
    logic        n_arrived, n_dir;
    logic [31:0] n_timer, t_inc;
    logic [3:0]  n_pend, bits;
    logic [15:0] n_moves;
    logic        ahead_same, ahead_opp;

    always_comb begin
        n_state   = state;
        n_arrived = arrived;
        n_timer   = timer;
        n_floor   = floor;
        n_dir     = dir;
        n_pend    = pending;
        n_moves   = moves;
        t_inc     = timer + 32'd1;
        ahead_same = 1'b0;
        ahead_opp  = 1'b0;

        case (state)
            S_IDLE: begin
                ahead_same = ahead(pending, floor, dir);
                ahead_opp  = ahead(pending, floor, ~dir);
                if (arrived) begin
                    n_arrived = 1'b0;
                    n_state   = S_DOOR;
                    n_timer   = 32'd0;
                    n_pend[floor] = 1'b0;
                end else if (pending[floor]) begin
                    n_state = S_DOOR;
                    n_timer = 32'd0;
                    n_pend[floor] = 1'b0;
                end else if (ahead_same) begin
                    n_state = S_MOVE;
                    n_timer = 32'd0;
                end else if (ahead_opp) begin
                    n_dir   = ~dir;
                    n_state = S_MOVE;
                    n_timer = 32'd0;
                end
            end
            S_MOVE: begin
                n_timer = t_inc;
                if (int'(t_inc) >= FLOOR_CYCLES) begin
                    n_timer = 32'd0;
                    if (!dir && floor != 2'd3) n_floor = floor + 2'd1;
                    if (dir && floor != 2'd0)  n_floor = floor - 2'd1;
                    if (moves != 16'hFFFF) n_moves = moves + 16'd1;
                    ahead_same = ahead(pending, n_floor, dir);
                    ahead_opp  = ahead(pending, n_floor, ~dir);
                    if (pending[n_floor]) begin
                        n_state   = S_IDLE;
                        n_arrived = 1'b1;
                    end else if (ahead_same) begin
                        n_state = S_MOVE;
                    end else if (ahead_opp) begin
                        n_dir   = ~dir;
                        n_state = S_MOVE;
                    end else begin
                        n_state = S_IDLE;
                    end
                end
            end
            default: begin
                n_timer = t_inc;
                if (int'(t_inc) >= DOOR_CYCLES) begin
                    n_state = S_IDLE;
                    n_timer = 32'd0;
                end
            end
        endcase

        // new calls: ignored for the floor being served
        bits = call_bits;
        if (n_state == S_DOOR || n_arrived) bits[n_floor] = 1'b0;
        n_pend = n_pend | bits;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state   <= S_IDLE;
            arrived <= 1'b0;
            timer   <= 32'd0;
            floor   <= 2'd0;
            dir     <= 1'b0;
            pending <= 4'd0;
            moves   <= 16'd0;
        end else begin
            state   <= n_state;
            arrived <= n_arrived;
            timer   <= n_timer;
            floor   <= n_floor;
            dir     <= n_dir;
            pending <= n_pend;
            moves   <= n_moves;
        end
    end
endmodule

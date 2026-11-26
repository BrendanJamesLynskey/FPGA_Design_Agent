// elevator_ctrl: four-floor lift FSM with one shared down counter.
// act: 0 idle, 1 moving, 2 door open.
// A shell call takes effect in the same clock it arrives (the FSM decision sees it);
// a switch call (already two clocks old at the synchroniser output) is merged after the decision.
module elevator_ctrl #(
    parameter int FLOOR_CYCLES = 150000000,
    parameter int DOOR_CYCLES  = 200000000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [3:0]  sw_call,   // switch rising-edge pulses
    input  logic [3:0]  sh_call,   // shell call pulses
    output logic [1:0]  floor,
    output logic        dir,       // 0 up, 1 down
    output logic [3:0]  pending,
    output logic [1:0]  act,
    output logic [15:0] moves
);
    localparam logic [1:0] IDLE = 2'd0, MOVING = 2'd1, DOOR = 2'd2;

    logic [31:0] rem;

    function automatic logic ahead(input logic [3:0] p, input logic [1:0] f, input logic d);
        logic r;
        r = 1'b0;
        for (int i = 0; i < 4; i++) begin
            if (d ? (i < int'(f)) : (i > int'(f))) r = r | p[i];
        end
        return r;
    endfunction

    function automatic logic behind(input logic [3:0] p, input logic [1:0] f, input logic d);
        logic r;
        r = 1'b0;
        for (int i = 0; i < 4; i++) begin
            if (d ? (i > int'(f)) : (i < int'(f))) r = r | p[i];
        end
        return r;
    endfunction

    logic [1:0]  nact, nfloor;
    logic        ndir, open_now;
    logic [31:0] nrem;
    logic [15:0] nmoves;
    logic [3:0]  clr, sw_ok, sh_ok, pend_eff;

    always_comb begin
        // a call for the floor whose door is open is ignored
        sh_ok    = (act == DOOR) ? ~(4'b0001 << floor) : 4'b1111;
        pend_eff = pending | (sh_call & sh_ok);
        nact     = act;
        nfloor   = floor;
        ndir     = dir;
        nrem     = rem - 32'd1;
        nmoves   = moves;
        open_now = 1'b0;
        case (act)
            IDLE: begin
                if (pend_eff[floor]) begin
                    open_now = 1'b1;
                end else if (ahead(pend_eff, floor, dir)) begin
                    nact = MOVING;
                    nrem = 32'(FLOOR_CYCLES);
                end else if (behind(pend_eff, floor, dir)) begin
                    ndir = ~dir;
                end
            end
            MOVING: begin
                if (rem[31:1] == 31'd0) begin
                    if (dir) begin
                        if (floor != 2'd0) nfloor = floor - 2'd1;
                    end else begin
                        if (floor != 2'd3) nfloor = floor + 2'd1;
                    end
                    nmoves = moves + 16'd1;
                    if (pend_eff[nfloor]) begin
                        open_now = 1'b1;
                    end else if (ahead(pend_eff, nfloor, dir)) begin
                        nact = MOVING;
                        nrem = 32'(FLOOR_CYCLES);
                    end else begin
                        nact = IDLE;
                    end
                end
            end
            DOOR: begin
                if (rem[31:1] == 31'd0) nact = IDLE;
            end
            default: nact = IDLE;
        endcase
        if (open_now) begin
            nact = DOOR;
            nrem = 32'(DOOR_CYCLES);
        end
        clr   = open_now ? (4'b0001 << nfloor) : 4'b0000;
        sw_ok = (nact == DOOR) ? ~(4'b0001 << nfloor) : 4'b1111;
    end

    always_ff @(posedge clk) begin
        rem <= nrem;
        if (rst) begin
            floor   <= 2'd0;
            dir     <= 1'b0;
            pending <= 4'b0;
            act     <= IDLE;
            moves   <= 16'd0;
        end else begin
            floor   <= nfloor;
            dir     <= ndir;
            act     <= nact;
            moves   <= nmoves;
            pending <= (pend_eff | (sw_call & sw_ok)) & ~clr;
        end
    end
endmodule

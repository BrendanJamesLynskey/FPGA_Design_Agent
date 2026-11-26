// Priority-based interrupt controller with starvation detection.
// rst_n (active low, asynchronous to clk) is used as a synchronous clear and
// also forces the outputs to 0 combinationally, so outputs read 0 as soon as
// rst_n is low.
/* verilator lint_off DECLFILENAME */
module interrupt_controller (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        reset_interrupts,
    input  wire [9:0]  interrupt_requests,
    input  wire        interrupt_ack,
    input  wire        interrupt_trig,
    input  wire [9:0]  interrupt_mask,
    input  wire [3:0]  priority_override,
    input  wire [3:0]  override_interrupt_id,
    input  wire        priority_override_en,
    output wire [3:0]  interrupt_id,
    output wire        interrupt_valid,
    output wire [9:0]  interrupt_status,
    output wire [9:0]  missed_interrupts,
    output wire        starvation_detected
);

    parameter STARVATION_THRESHOLD   = 5;
    parameter SERVICE_TIMEOUT_CYCLES = 15;

    localparam [2:0]
        IDLE          = 3'b000,
        PRIORITY_CALC = 3'b001,
        SERVICE_PREP  = 3'b010,
        SERVICING     = 3'b011,
        COMPLETION    = 3'b100,
        ERROR         = 3'b111;

    reg [2:0] current_state;
    reg [9:0] pending_interrupts;
    reg [3:0] wait_counters [0:9];
    reg [9:0] status_r;
    reg [9:0] missed_r;
    reg [3:0] service_timer;
    reg [3:0] sel_id;
    reg [3:0] id_r;
    reg       valid_r;
    reg       starv_r;

    // combinational next-state values
    reg [3:0] wait_nxt [0:9];
    reg [4:0] eff_prio [0:9];
    reg [9:0] avail;
    reg [9:0] clr_vec;
    reg       starv_nxt;
    reg [3:0] best_id;
    reg [4:0] best_prio;
    reg       best_found;
    reg [4:0] timer_inc;

    always_comb begin
        avail = pending_interrupts & ~interrupt_mask;
        starv_nxt = 1'b0;
        for (int i = 0; i < 10; i++) begin
            wait_nxt[i] = wait_counters[i];
            if (avail[i]) begin
                if (!status_r[i] && wait_counters[i] != 4'd15)
                    wait_nxt[i] = wait_counters[i] + 4'd1;
                if (int'(wait_nxt[i]) >= STARVATION_THRESHOLD)
                    starv_nxt = 1'b1;
            end else begin
                wait_nxt[i] = 4'd0;
            end
        end
        for (int i = 0; i < 10; i++) begin
            if (priority_override_en && override_interrupt_id == 4'(i))
                eff_prio[i] = {1'b0, priority_override};
            else
                eff_prio[i] = 5'(9 - i) +
                    ((int'(wait_nxt[i]) >= STARVATION_THRESHOLD) ? 5'd5 : 5'd0);
        end
        best_found = 1'b0;
        best_id    = 4'd0;
        best_prio  = 5'd0;
        for (int i = 0; i < 10; i++) begin
            if (avail[i] && (!best_found || eff_prio[i] > best_prio)) begin
                best_found = 1'b1;
                best_id    = 4'(i);
                best_prio  = eff_prio[i];
            end
        end
        timer_inc = {1'b0, service_timer} + 5'd1;
        clr_vec = 10'd0;
        if (current_state == COMPLETION)
            clr_vec[sel_id] = 1'b1;
    end

    always_ff @(posedge clk) begin
        if (!rst_n || reset_interrupts) begin
            current_state      <= IDLE;
            pending_interrupts <= 10'd0;
            status_r           <= 10'd0;
            missed_r           <= 10'd0;
            service_timer      <= 4'd0;
            id_r               <= 4'd0;
            sel_id             <= 4'd0;
            valid_r            <= 1'b0;
            starv_r            <= 1'b0;
            for (int i = 0; i < 10; i++) wait_counters[i] <= 4'd0;
        end else begin
            starv_r <= starv_r | starv_nxt;
            for (int i = 0; i < 10; i++) wait_counters[i] <= wait_nxt[i];
            pending_interrupts <= (pending_interrupts & ~clr_vec) |
                                  (interrupt_requests & ~interrupt_mask);
            missed_r           <= missed_r | (interrupt_requests & interrupt_mask);
            case (current_state)
                IDLE: begin
                    if (interrupt_trig && (|avail))
                        current_state <= PRIORITY_CALC;
                end
                PRIORITY_CALC: begin
                    if (!best_found) begin
                        current_state <= IDLE;
                    end else begin
                        sel_id        <= best_id;
                        current_state <= SERVICE_PREP;
                    end
                end
                SERVICE_PREP: begin
                    id_r             <= sel_id;
                    valid_r          <= 1'b1;
                    status_r[sel_id] <= 1'b1;
                    service_timer    <= 4'd0;
                    current_state    <= SERVICING;
                end
                SERVICING: begin
                    if (interrupt_ack) begin
                        current_state <= COMPLETION;
                    end else begin
                        service_timer <= timer_inc[3:0];
                        if (int'(timer_inc) >= SERVICE_TIMEOUT_CYCLES)
                            current_state <= ERROR;
                    end
                end
                COMPLETION: begin
                    status_r[sel_id]      <= 1'b0;
                    wait_counters[sel_id] <= 4'd0;
                    valid_r               <= 1'b0;
                    current_state         <= IDLE;
                end
                default: begin
                    status_r      <= 10'd0;
                    valid_r       <= 1'b0;
                    current_state <= IDLE;
                end
            endcase
        end
    end

    wire r = rst_n;
    assign interrupt_valid     = r & valid_r;
    assign interrupt_id        = (r & valid_r) ? id_r : 4'd0;
    assign interrupt_status    = r ? status_r : 10'd0;
    assign missed_interrupts   = r ? missed_r : 10'd0;
    assign starvation_detected = r & starv_r;

endmodule
/* verilator lint_on DECLFILENAME */

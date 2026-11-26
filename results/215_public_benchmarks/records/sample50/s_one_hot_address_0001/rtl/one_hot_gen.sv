module one_hot_gen #(
    parameter int NS_A = 8,
    parameter int NS_B = 4
) (
    input  logic                 clk,
    input  logic                 rst_async_n,
    input  logic [1:0]           i_config,
    input  logic                 i_start,
    output logic                 o_ready,
    output logic [NS_A+NS_B-1:0] o_address_one_hot
);

typedef enum logic [1:0] {IDLE = 2'b00, REGION_A = 2'b01, REGION_B = 2'b10} state_t;

state_t state_ff, state_nx;
logic [NS_A-1:0] region_A_ff, region_A_nx;
logic [NS_B-1:0] region_B_ff, region_B_nx;
logic A_to_B, B_to_A;
logic [1:0] config_ff;

localparam logic [NS_A-1:0] MSB_A = NS_A'(1) << (NS_A - 1);
localparam logic [NS_B-1:0] MSB_B = NS_B'(1) << (NS_B - 1);

assign A_to_B = config_ff[1] & ~config_ff[0];
assign B_to_A = config_ff[1] &  config_ff[0];

assign o_address_one_hot = {region_A_ff, region_B_ff};

// Synchronous reset (active low at the port, sampled on clk).
always_ff @(posedge clk) begin : input_register
    if (!rst_async_n) begin
        config_ff <= 2'b00;
    end else if (i_start && state_ff == IDLE) begin
        config_ff <= i_config;
    end
end

always_ff @(posedge clk) begin : reset_regs
    if (!rst_async_n) begin
        o_ready     <= 1'b1;
        state_ff    <= IDLE;
        region_A_ff <= '0;
        region_B_ff <= '0;
    end else begin
        o_ready     <= (state_nx == IDLE);
        state_ff    <= state_nx;
        region_A_ff <= region_A_nx;
        region_B_ff <= region_B_nx;
    end
end

always_comb begin : drive_regions
    region_A_nx = '0;
    region_B_nx = '0;
    case (state_ff)
        IDLE: begin
            if (i_start) begin
                if (i_config[0]) region_B_nx = MSB_B;
                else             region_A_nx = MSB_A;
            end
        end
        REGION_A: begin
            region_A_nx = region_A_ff >> 1;
            if (region_A_ff[0] && A_to_B) region_B_nx = MSB_B;
        end
        REGION_B: begin
            region_B_nx = region_B_ff >> 1;
            if (region_B_ff[0] && B_to_A) region_A_nx = MSB_A;
        end
        default: ;
    endcase
end

always_comb begin : update_state
    state_nx = IDLE;
    case (state_ff)
        IDLE: begin
            if (i_start) begin
                if (i_config[0]) state_nx = REGION_B;
                else             state_nx = REGION_A;
            end
        end
        REGION_A: begin
            if (!region_A_ff[0])  state_nx = REGION_A;
            else if (A_to_B)      state_nx = REGION_B;
        end
        REGION_B: begin
            if (!region_B_ff[0])  state_nx = REGION_B;
            else if (B_to_A)      state_nx = REGION_A;
        end
        default: ;
    endcase
end

endmodule : one_hot_gen

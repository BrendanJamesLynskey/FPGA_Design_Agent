// sw_sync: STAGES-FF synchroniser for each asynchronous switch plus an edge-detect
// register. rise[i] is high for one clock after a rising edge on sw[i].
module sw_sync #(
    parameter int STAGES = 2
) (
    input  logic       clk,
    input  logic       rst,
    input  logic [3:0] sw,
    output logic [3:0] rise
);
    localparam int N = (STAGES < 1) ? 1 : STAGES;

    (* ASYNC_REG = "TRUE" *) logic [3:0] sync [N];
    logic [3:0] prev;

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < N; i++) sync[i] <= 4'b0;
            prev <= 4'b0;
        end else begin
            sync[0] <= sw;
            for (int i = 1; i < N; i++) sync[i] <= sync[i-1];
            prev <= sync[N-1];
        end
    end

    assign rise = sync[N-1] & ~prev;
endmodule

// burst_ctl.sv: the burst sequencer of the shell window (course task): runs `TOTAL` clocks after GO; `en` is MASK[cnt] for the first 32 of them; `idx` counts the enables so far.
module burst_ctl #(
    parameter int TOTAL = 64
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    input  logic [31:0] mask,
    output logic        active,
    output logic [6:0]  cnt,
    output logic        en,
    output logic [5:0]  idx,
    output logic        done
);
    assign en = active && (cnt < 7'd32) && mask[cnt[4:0]];
    always_ff @(posedge clk) begin
        if (rst) begin
            active <= 1'b0; cnt <= '0; idx <= '0; done <= 1'b0;
        end else if (go) begin
            active <= 1'b1; cnt <= '0; idx <= '0; done <= 1'b0;
        end else if (active) begin
            cnt <= cnt + 1'b1;
            if (en) idx <= idx + 1'b1;
            if (cnt == TOTAL - 1) begin active <= 1'b0; done <= 1'b1; end
        end
    end
endmodule

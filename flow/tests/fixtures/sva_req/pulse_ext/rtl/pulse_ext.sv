// pulse_ext: a start pulse makes busy high for four clock cycles, then done pulses for one cycle (fixture of brief 218; not a shipped design).
module pulse_ext (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic busy,
    output logic done
);
    logic [2:0] cnt;
    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (!rst_n) begin
            busy <= 1'b0;
            cnt  <= 3'd0;
        end else if (!busy) begin
            if (start) begin
                busy <= 1'b1;
                cnt  <= 3'd3;
            end
        end else if (cnt == 3'd0) begin
            busy <= 1'b0;
            done <= 1'b1;
        end else begin
            cnt <= cnt - 3'd1;
        end
    end
endmodule

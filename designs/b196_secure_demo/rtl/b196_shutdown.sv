// b196_shutdown.sv: the latched safe-shutdown of the production_secure build (brief 196, sysmon_shutdown).
// Any alarm bit seen for one clock sets `shutdown`; it stays set until the design is reset by power or by a new configuration
// (there is no way to clear it from the fabric: a hot or under-volted device is not restarted by itself).
// `cause` latches which alarm came first (bit per alarm), so a debug-free production part can still say why it stopped.
// Reset: rst, synchronous, active high.
module b196_shutdown #(
    parameter int N = 5                    // alarm inputs: OT, TEMP, VCCINT, VCCAUX, VCCBRAM
) (
    input  logic         clk,
    input  logic         rst,
    input  logic [N-1:0] alarm,            // already in the clk domain (SYSMONE4 outputs are synchronous to DCLK = clk)
    output logic         shutdown,
    output logic [N-1:0] cause
);
    always_ff @(posedge clk) begin
        if (rst) begin
            shutdown <= 1'b0;
            cause    <= '0;
        end else if (|alarm) begin
            if (!shutdown) cause <= alarm;
            shutdown <= 1'b1;
        end
    end
endmodule

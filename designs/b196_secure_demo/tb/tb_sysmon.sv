// tb_sysmon.sv: the SYSMONE4 unisim model (Vivado 2026.1) configured by this design's INIT values, driven from an analog stimulus file
// (-d SIM_FILE="<file>"), and the latched shutdown behind it. Prints "RESULT <first shutdown time in ns, or -1> <cause>" after SIM_NS of
// simulated time. Run by tests/run_sysmon_sim.py under xsim with -d SYNTHESIS so that the wrapper instantiates the model.
`timescale 1ns/1ps
module tb_sysmon;
    logic clk = 0;
    logic rst = 1;
    wire shutdown;
    wire [4:0] cause;
    b196_sysmon_guard #(.SIM_FILE(`SIM_FILE)) dut (.clk(clk), .rst(rst), .sim_alarm(5'b0), .shutdown(shutdown), .cause(cause));
    always #20 clk = ~clk;                        // 25 MHz
    integer t_first = -1;
    always @(posedge clk) if (shutdown && t_first < 0) t_first = $time;
    initial begin
        repeat (8) @(posedge clk);
        rst = 0;
        #(`SIM_NS);
        $display("RESULT %0d %0d", t_first, cause);
        $finish;
    end
endmodule

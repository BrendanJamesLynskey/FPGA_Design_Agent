// Latency of the reference controller's output styles (brief 24): clocks from an input event to the output it causes
// (0 = in the same clock the input is present).
// One scripted transaction, three DUTs (OUT = 0 combinational, 1 registered, 2 lookahead).
// Prints "LAT out=<n> cmd_valid_to_cmd_ack=<c> cmd_valid_to_req=<c> gnt_to_addr_v=<c> gnt_to_valid=<c> ack_to_rsp_valid=<c>".
module tb_latency;
  logic clk = 0; always #5 clk = ~clk;
  integer cyc = 0; always @(negedge clk) cyc <= cyc + 1;      // the cycle number: it changes at the falling edge, the inputs are driven then
  logic rst_n = 0, cmd_valid = 0, gnt = 0, ack = 0, nack = 0, rsp_ready = 0;
  logic [2:0] ca, rq, av, vl, rv, cr, lt, er;
  integer t_cmd = -1, t_gnt = -1, t_ack = -1;
  integer r_ca[3], r_rq[3], r_av[3], r_vl[3], r_rv[3];
  genvar g;
  for (g = 0; g < 3; g++) begin : d
    logic cmd_ready, cmd_ack, bus_req, bus_addr_v, bus_valid, bus_last, rsp_valid, rsp_err;
    ctl_sep #(.OUT(g)) u (.clk, .rst_n, .ce(1'b1), .cmd_valid, .cmd_ready, .cmd_ack, .gnt, .ack, .nack, .bus_req, .bus_addr_v, .bus_valid,
                          .bus_last, .rsp_valid, .rsp_err, .rsp_ready);
    initial begin r_ca[g] = -99; r_rq[g] = -99; r_av[g] = -99; r_vl[g] = -99; r_rv[g] = -99; end
    always @(posedge clk) begin           // outputs as seen just before this edge (the value the partner samples)
      if (cmd_ack && r_ca[g] == -99 && t_cmd >= 0) r_ca[g] <= cyc - t_cmd;
      if (bus_req && r_rq[g] == -99 && t_cmd >= 0) r_rq[g] <= cyc - t_cmd;
      if (bus_addr_v && r_av[g] == -99 && t_gnt >= 0) r_av[g] <= cyc - t_gnt;
      if (bus_valid && r_vl[g] == -99 && t_gnt >= 0) r_vl[g] <= cyc - t_gnt;
      if (rsp_valid && r_rv[g] == -99 && t_ack >= 0) r_rv[g] <= cyc - t_ack;
    end
  end
  integer i;
  initial begin
    repeat (3) @(negedge clk); #1 rst_n = 1; repeat (4) @(negedge clk);
    #1 cmd_valid = 1; t_cmd = cyc;           // the cycle in which the input is first present
    @(negedge clk); #1 cmd_valid = 0;
    repeat (5) @(negedge clk);
    #1 gnt = 1; t_gnt = cyc; @(negedge clk); #1 gnt = 0;
    repeat (8) @(negedge clk);
    #1 ack = 1; t_ack = cyc; @(negedge clk); #1 ack = 0;
    repeat (6) @(negedge clk);
    for (i = 0; i < 3; i++)
      $display("LAT out=%0d cmd_valid_to_cmd_ack=%0d cmd_valid_to_req=%0d gnt_to_addr_v=%0d gnt_to_valid=%0d ack_to_rsp_valid=%0d", i, r_ca[i], r_rq[i], r_av[i], r_vl[i], r_rv[i]);
    $finish;
  end
endmodule

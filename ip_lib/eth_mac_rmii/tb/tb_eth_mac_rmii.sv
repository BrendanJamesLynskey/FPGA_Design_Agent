// tb_eth_mac_rmii: file-driven testbench (the brief-19 harness method: Python writes stimulus files, this bench
// drives them and writes what the design produced; Python compares bit-exact; nothing here judges the result).
//
// Plusargs:
//   +rx_line=<f>  one line a clock: "<crs_dv> <rxd 0..3> <rx_er>" driven on the RMII receive pins
//   +tx_stim=<f>  one line a beat: "<gap> <tdata hex> <tlast> <tuser>"; gap = idle clocks before offering this beat
//   +rx_resp=<f>  written: "<cycle> <tdata hex> <tlast> <tuser>" for every receive beat
//   +tx_wire=<f>  written: "<cycle> <tx_en> <txd>" for every clock with tx_en high, and the first clock it drops
//   +loop=1       receive pins driven from the transmit pins (one clock later) instead of rx_line
//   +speed10=1    10 Mb/s mode
//   +cycles=<n>   clocks to run
`timescale 1ns/1ps
module tb_eth_mac_rmii;
    parameter int MIN_FRAME = 64, MIN_DATA = 60, IFG = 12;
    localparam int MAXL = 4_000_000;
    localparam int MAXB = 400_000;
    reg clk = 1'b0;
    always #10 clk = ~clk;               // 50 MHz
    reg rst = 1'b1;

    reg        crs_dv = 1'b0, rx_er = 1'b0;
    reg  [1:0] rxd = 2'b00;
    wire       tx_en;
    wire [1:0] txd;
    wire [7:0] rx_tdata;
    wire       rx_tvalid, rx_tlast, rx_tuser;
    reg  [7:0] tx_tdata = 8'h00;
    reg        tx_tvalid = 1'b0, tx_tlast = 1'b0, tx_tuser = 1'b0;
    wire       tx_tready;
    wire       ev_rx_ok, ev_rx_bad, ev_rx_fcs_err, ev_rx_runt, ev_tx_sent, ev_tx_underrun;
    reg        speed_100 = 1'b1;

    eth_mac_rmii #(.MIN_FRAME(MIN_FRAME), .MIN_DATA(MIN_DATA), .IFG_BYTES(IFG)) dut (
        .clk(clk), .rst(rst), .speed_100(speed_100),
        .rmii_crs_dv(crs_dv), .rmii_rxd(rxd), .rmii_rx_er(rx_er), .rmii_tx_en(tx_en), .rmii_txd(txd),
        .rx_axis_tdata(rx_tdata), .rx_axis_tvalid(rx_tvalid), .rx_axis_tlast(rx_tlast), .rx_axis_tuser(rx_tuser),
        .tx_axis_tdata(tx_tdata), .tx_axis_tvalid(tx_tvalid), .tx_axis_tready(tx_tready), .tx_axis_tlast(tx_tlast),
        .tx_axis_tuser(tx_tuser),
        .ev_rx_ok(ev_rx_ok), .ev_rx_bad(ev_rx_bad), .ev_rx_fcs_err(ev_rx_fcs_err), .ev_rx_runt(ev_rx_runt),
        .ev_tx_sent(ev_tx_sent), .ev_tx_underrun(ev_tx_underrun));

    reg [3:0]  line_mem [0:MAXL-1];      // {rx_er, crs_dv, rxd}
    integer    n_line = 0;
    reg [7:0]  b_data [0:MAXB-1];
    reg        b_last [0:MAXB-1];
    reg        b_user [0:MAXB-1];
    integer    b_gap  [0:MAXB-1];
    integer    n_beat = 0;

    reg [8*512-1:0] f_rx_line, f_tx_stim, f_rx_resp, f_tx_wire;
    integer fd, rc, a, b, c, g, loop, sp10, cycles, cyc, bi, gapc;
    integer n_ok, n_bad, n_fcs, n_runt, n_sent, n_under;
    reg [7:0] d8;
    integer frx, ftx;

    initial begin
        loop = 0; sp10 = 0; cycles = 100000;
        if (!$value$plusargs("rx_line=%s", f_rx_line)) f_rx_line = "";
        if (!$value$plusargs("tx_stim=%s", f_tx_stim)) f_tx_stim = "";
        if (!$value$plusargs("rx_resp=%s", f_rx_resp)) f_rx_resp = "rx_resp.txt";
        if (!$value$plusargs("tx_wire=%s", f_tx_wire)) f_tx_wire = "tx_wire.txt";
        rc = $value$plusargs("loop=%d", loop);
        rc = $value$plusargs("speed10=%d", sp10);
        rc = $value$plusargs("cycles=%d", cycles);
        speed_100 = (sp10 == 0);
        if (f_rx_line != "") begin
            fd = $fopen(f_rx_line, "r");
            while (!$feof(fd) && n_line < MAXL) begin
                rc = $fscanf(fd, "%d %d %d\n", a, b, c);
                if (rc == 3) begin line_mem[n_line] = {c[0], a[0], b[1:0]}; n_line = n_line + 1; end
            end
            $fclose(fd);
        end
        if (f_tx_stim != "") begin
            fd = $fopen(f_tx_stim, "r");
            while (!$feof(fd) && n_beat < MAXB) begin
                rc = $fscanf(fd, "%d %h %d %d\n", g, d8, a, b);
                if (rc == 4) begin
                    b_gap[n_beat] = g; b_data[n_beat] = d8; b_last[n_beat] = a[0]; b_user[n_beat] = b[0];
                    n_beat = n_beat + 1;
                end
            end
            $fclose(fd);
        end
        frx = $fopen(f_rx_resp, "w");
        ftx = $fopen(f_tx_wire, "w");
    end

    reg tx_en_q = 1'b0;
    reg [1:0] txd_q = 2'b00;
    initial begin
        cyc = 0; bi = 0; gapc = 0;
        n_ok = 0; n_bad = 0; n_fcs = 0; n_runt = 0; n_sent = 0; n_under = 0;
        repeat (4) @(posedge clk);
        rst <= 1'b0;
        forever begin
            @(posedge clk);
            // record what the design did in the cycle that just ended
            if (rx_tvalid) $fdisplay(frx, "%0d %h %0d %0d", cyc, rx_tdata, rx_tlast, rx_tuser);
            if (tx_en || tx_en_q) $fdisplay(ftx, "%0d %0d %0d", cyc, tx_en, txd);
            n_ok = n_ok + ev_rx_ok; n_bad = n_bad + ev_rx_bad; n_fcs = n_fcs + ev_rx_fcs_err;
            n_runt = n_runt + ev_rx_runt; n_sent = n_sent + ev_tx_sent; n_under = n_under + ev_tx_underrun;
            // transmit stream: a beat offered stays until taken
            if (tx_tvalid && tx_tready) begin bi = bi + 1; gapc = 0; end
            if (tx_tvalid && !tx_tready) begin
            end else if (bi < n_beat && gapc >= b_gap[bi]) begin
                tx_tvalid <= 1'b1; tx_tdata <= b_data[bi]; tx_tlast <= b_last[bi]; tx_tuser <= b_user[bi];
            end else begin
                tx_tvalid <= 1'b0;
                if (bi < n_beat) gapc = gapc + 1;
            end
            // receive pins
            tx_en_q <= tx_en; txd_q <= txd;
            if (loop != 0) begin
                crs_dv <= tx_en; rxd <= txd; rx_er <= 1'b0;
            end else if (cyc < n_line) begin
                {rx_er, crs_dv, rxd} <= line_mem[cyc];
            end else begin
                {rx_er, crs_dv, rxd} <= 4'b0000;
            end
            cyc = cyc + 1;
            if (cyc >= cycles) begin
                $fdisplay(frx, "# ev_ok %0d", n_ok);
                $fdisplay(frx, "# ev_bad %0d", n_bad);
                $fdisplay(frx, "# ev_fcs %0d", n_fcs);
                $fdisplay(frx, "# ev_runt %0d", n_runt);
                $fdisplay(frx, "# ev_sent %0d", n_sent);
                $fdisplay(frx, "# ev_under %0d", n_under);
                $fdisplay(frx, "# beats_taken %0d", bi);
                $fclose(frx); $fclose(ftx);
                $display("TB_DONE cycles=%0d", cyc);
                $finish;
            end
        end
    end
endmodule

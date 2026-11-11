// tb_match_table: file-driven bench for the three match tables behind axil_table_ctrl (brief-19 harness method).
// TABLE selects the core: 0 match_exact, 1 match_lpm, 2 match_ternary. Two independent streams run at once:
//   +lk=<f>    lookups: "<gap> <key hex>" a line; gap idle clocks before this lookup (0 = back to back)
//   +cmd=<f>   AXI4-Lite program: "W <addr hex> <data hex>" write, "P" poll STATUS until not busy,
//              "D <n>" wait n clocks, "G" wait until the lookup stream has started
//   +lk_after=<n> start the lookups once n polls have completed (after a bulk load)
//   +resp=<f>  written: "R <cycle> <hit> <act hex> <tag hex>" for each result,
//              "I <cycle> <tag hex>" for each lookup issued, "C"/"K <cycle> <hex>" when the core takes a command / answers, "S <cycle> <status hex>" for each poll that found the core idle, then "# k v" lines
// Python compares bit-exact; this bench judges nothing.
`timescale 1ns/1ps
module tb_match_table;
    parameter int TABLE    = 0;
    parameter int KEY_W    = 48;
    parameter int ACT_W    = 16;
    parameter int IDX_W    = 6;
    parameter int STASH    = 4;
    parameter int ENTRIES  = 32;
    parameter int CHUNK_W  = 5;
    parameter int L1_NODES = 8;
    parameter int L2_NODES = 8;
    parameter int L3_NODES = 8;
    localparam int TAG_W = 20;
    localparam int MAXL = 200_000;

    reg clk = 1'b0;
    always #4 clk = ~clk;
    reg rst = 1'b1;

    reg  [6:0]   awaddr = 0, araddr = 0;
    reg          awvalid = 0, wvalid = 0, bready = 1, arvalid = 0, rready = 1;
    reg  [31:0]  wdata = 0;
    wire         awready, wready, bvalid, arready, rvalid;
    wire [1:0]   bresp, rresp;
    wire [31:0]  rdata;
    wire         cmd_valid, cmd_ready, rsp_valid;
    wire [3:0]   cmd_op, rsp_status;
    wire [15:0]  cmd_addr;
    wire [511:0] cmd_data;

    axil_table_ctrl u_ctrl (
        .clk(clk), .rst(rst), .s_axil_awaddr(awaddr), .s_axil_awvalid(awvalid), .s_axil_awready(awready),
        .s_axil_wdata(wdata), .s_axil_wvalid(wvalid), .s_axil_wready(wready), .s_axil_bresp(bresp),
        .s_axil_bvalid(bvalid), .s_axil_bready(bready), .s_axil_araddr(araddr), .s_axil_arvalid(arvalid),
        .s_axil_arready(arready), .s_axil_rdata(rdata), .s_axil_rresp(rresp), .s_axil_rvalid(rvalid),
        .s_axil_rready(rready), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_op(cmd_op), .cmd_addr(cmd_addr),
        .cmd_data(cmd_data), .rsp_valid(rsp_valid), .rsp_status(rsp_status));

    reg              lk_valid = 1'b0;
    reg  [KEY_W-1:0] lk_key = '0;
    reg  [TAG_W-1:0] lk_tag = '0;
    wire             res_valid, res_hit;
    wire [ACT_W-1:0] res_act;
    wire [TAG_W-1:0] res_tag;

    generate
        if (TABLE == 0) begin : g_exact
            /* verilator lint_off PINCONNECTEMPTY */
            match_exact #(.KEY_W(KEY_W), .ACT_W(ACT_W), .IDX_W(IDX_W), .STASH(STASH), .TAG_W(TAG_W)) dut (
                .clk(clk), .rst(rst), .lk_valid(lk_valid), .lk_key(lk_key), .lk_tag(lk_tag), .res_valid(res_valid),
                .res_hit(res_hit), .res_act(res_act), .res_tag(res_tag), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
                .cmd_op(cmd_op), .cmd_data(cmd_data), .rsp_valid(rsp_valid), .rsp_status(rsp_status),
                .n_entries());
        end else if (TABLE == 1) begin : g_lpm
            match_lpm #(.ACT_W(ACT_W), .L1_NODES(L1_NODES), .L2_NODES(L2_NODES), .L3_NODES(L3_NODES),
                        .TAG_W(TAG_W)) dut (
                .clk(clk), .rst(rst), .lk_valid(lk_valid), .lk_key(lk_key[31:0]), .lk_tag(lk_tag),
                .res_valid(res_valid), .res_hit(res_hit), .res_act(res_act), .res_tag(res_tag),
                .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_op(cmd_op), .cmd_addr(cmd_addr),
                .cmd_data(cmd_data), .rsp_valid(rsp_valid), .rsp_status(rsp_status));
        end else begin : g_tern
            match_ternary #(.KEY_W(KEY_W), .ACT_W(ACT_W), .ENTRIES(ENTRIES), .CHUNK_W(CHUNK_W), .TAG_W(TAG_W)) dut (
                .clk(clk), .rst(rst), .lk_valid(lk_valid), .lk_key(lk_key), .lk_tag(lk_tag), .res_valid(res_valid),
                .res_hit(res_hit), .res_act(res_act), .res_tag(res_tag), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
                .cmd_op(cmd_op), .cmd_addr(cmd_addr), .cmd_data(cmd_data), .rsp_valid(rsp_valid),
                .rsp_status(rsp_status));
            /* verilator lint_on PINCONNECTEMPTY */
        end
    endgenerate

    reg [255:0] lk_mem [0:MAXL-1];
    integer     lk_gap [0:MAXL-1];
    integer     n_lk = 0, npoll = 0, lk_after = 0, fd, rc, g, cyc = 0, fo, nres = 0, started = 0, lk_done = 0, cmd_done = 0, nw = 0;
    reg [8*512-1:0] f_lk, f_cmd, f_resp;
    reg [255:0] k;
    reg [8*8-1:0] op;
    reg [31:0] a32, d32, st;

    always @(posedge clk) begin
        cyc <= cyc + 1;
        if (lk_valid) $fdisplay(fo, "I %0d %h", cyc, lk_tag);
        if (cmd_valid && cmd_ready) $fdisplay(fo, "C %0d %h", cyc, cmd_op);
        if (rsp_valid) $fdisplay(fo, "K %0d %h", cyc, rsp_status);
        if (res_valid) begin
            $fdisplay(fo, "R %0d %0d %h %h", cyc, res_hit, res_act, res_tag);
            nres = nres + 1;
        end
    end

    // The slave is idle when awready/wready/arready are high; the handshake then happens at the next edge.
    task automatic axil_write(input [6:0] a, input [31:0] d);
        begin
            @(posedge clk);
            while (!(awready && wready)) @(posedge clk);
            awaddr <= a; awvalid <= 1'b1; wdata <= d; wvalid <= 1'b1;
            @(posedge clk);
            awvalid <= 1'b0; wvalid <= 1'b0;
            while (!bvalid) @(posedge clk);
            nw = nw + 1;
        end
    endtask

    task automatic axil_read(input [6:0] a, output [31:0] d);
        begin
            @(posedge clk);
            while (!arready) @(posedge clk);
            araddr <= a; arvalid <= 1'b1;
            @(posedge clk);
            arvalid <= 1'b0;
            while (!rvalid) @(posedge clk);
            d = rdata;
        end
    endtask

    // lookups
    integer i, j;
    initial begin
        rc = $value$plusargs("lk=%s", f_lk);
        rc = $value$plusargs("cmd=%s", f_cmd);
        rc = $value$plusargs("resp=%s", f_resp);
        fo = $fopen(f_resp, "w");
        fd = $fopen(f_lk, "r");
        while (!$feof(fd) && n_lk < MAXL) begin
            rc = $fscanf(fd, "%d %h\n", g, k);
            if (rc == 2) begin lk_gap[n_lk] = g; lk_mem[n_lk] = k; n_lk = n_lk + 1; end
        end
        $fclose(fd);
        repeat (4) @(posedge clk);
        rst <= 1'b0;
        repeat (2) @(posedge clk);
        started = 1;
        rc = $value$plusargs("lk_after=%d", lk_after);
        wait (npoll >= lk_after);
        for (i = 0; i < n_lk; i = i + 1) begin
            for (j = 0; j < lk_gap[i]; j = j + 1) begin @(posedge clk); lk_valid <= 1'b0; end
            @(posedge clk);
            lk_valid <= 1'b1; lk_key <= lk_mem[i][KEY_W-1:0]; lk_tag <= i[TAG_W-1:0];
        end
        @(posedge clk);
        lk_valid <= 1'b0;
        repeat (20) @(posedge clk);
        lk_done = 1;
    end

    // AXI4-Lite program
    initial begin
        wait (started == 1);
        fd = $fopen(f_cmd, "r");
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%s", op);
            if (op == "W") begin
                rc = $fscanf(fd, "%h %h\n", a32, d32);
                axil_write(a32[6:0], d32);
            end else if (op == "P") begin
                st = 32'h1;
                while (st[0]) axil_read(7'h44, st);
                $fdisplay(fo, "S %0d %h", cyc, st);
                npoll = npoll + 1;
            end else if (op == "D") begin
                rc = $fscanf(fd, "%d\n", g);
                repeat (g) @(posedge clk);
            end
            op = "";
        end
        $fclose(fd);
        cmd_done = 1;
    end

    initial begin
        wait (lk_done == 1 && cmd_done == 1);
        repeat (10) @(posedge clk);
        $fdisplay(fo, "# results %0d", nres);
        $fdisplay(fo, "# writes %0d", nw);
        $fdisplay(fo, "# cycles %0d", cyc);
        $fclose(fo);
        $display("TB_DONE");
        $finish;
    end
endmodule

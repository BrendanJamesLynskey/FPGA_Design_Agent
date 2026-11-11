// tb_l2_switch: file-driven bench for a 4-port l2_switch (brief-19 harness method). Writes every egress beat and the
// core's event order (which port's frame it took, when it aged the table); Python replays that order through the
// model and compares the egress streams bit-exact. This bench judges nothing.
//   +stim<p>=<f>  "<tdata hex> <tlast> <tuser>" for port p (0..3)    +sched=<f> +nsched=<n> (valid per port, offset)
//   +cfg=<f>      "V <vid hex> <mask hex>" (written before traffic) and "A <cycle>" (age tick at that clock)
//   +pvid=<hex 4 x 12 bits>   +resp=<f>
`timescale 1ns/1ps
module tb_l2_switch;
    localparam int NP = 4, MAXB = 200_000, MAXS = 8192;
    parameter int IDX_W = 9;
    reg clk = 1'b0;
    always #4 clk = ~clk;
    reg rst = 1'b1;

    reg  [NP*8-1:0]  s_tdata = 0;
    reg  [NP-1:0]    s_tvalid = 0, s_tlast = 0, s_tuser = 0;
    wire [NP-1:0]    s_tready;
    wire [NP*8-1:0]  m_tdata;
    wire [NP-1:0]    m_tvalid, m_tlast, m_tuser;
    reg  [NP-1:0]    m_tready = '1;
    reg  [NP*12-1:0] pvid = 0;
    reg              cfg_we = 0, age_tick = 0;
    reg  [11:0]      cfg_vid = 0;
    reg  [NP-1:0]    cfg_mask = 0;
    wire             ev_pick, ev_age, ev_flood, ev_filter;
    wire [NP-1:0]    ev_in_drop;
    wire [2:0]       ev_port;

    l2_switch #(.NP(NP), .IDX_W(IDX_W)) dut (
        .clk(clk), .rst(rst), .s_tdata(s_tdata), .s_tvalid(s_tvalid), .s_tready(s_tready), .s_tlast(s_tlast),
        .s_tuser(s_tuser), .m_tdata(m_tdata), .m_tvalid(m_tvalid), .m_tready(m_tready), .m_tlast(m_tlast),
        .m_tuser(m_tuser), .pvid(pvid), .cfg_we(cfg_we), .cfg_vid(cfg_vid), .cfg_mask(cfg_mask),
        .age_tick(age_tick), .ev_pick(ev_pick), .ev_port(ev_port), .ev_age(ev_age), .ev_flood(ev_flood),
        .ev_filter(ev_filter), .ev_in_drop(ev_in_drop));

    reg [9:0] mem [0:NP-1][0:MAXB-1];
    integer   nb [0:NP-1];
    integer   sent [0:NP-1];
    reg       sv [0:MAXS-1];
    reg       sr [0:MAXS-1];
    integer   age_at [0:255];
    integer   n_age = 0, ai = 0;
    integer   ns = 1, fd, rc, a1, b1, c1, p, cyc = 0, idle = 0, fo, n_drop = 0, n_flood = 0, n_filter = 0;
    reg [8*512-1:0] fn, f_resp, f_sched, f_cfg;
    reg [8*8-1:0] op;
    reg [7:0] d8;
    reg [47:0] pv;
    integer alldone;

    initial begin
        rc = $value$plusargs("resp=%s", f_resp);
        if ($value$plusargs("pvid=%h", pv)) pvid = pv;
        sv[0] = 1; sr[0] = 1;
        if ($value$plusargs("sched=%s", f_sched)) begin
            rc = $value$plusargs("nsched=%d", ns);
            fd = $fopen(f_sched, "r");
            for (a1 = 0; a1 < ns; a1 = a1 + 1) begin rc = $fscanf(fd, "%d %d\n", b1, c1); sv[a1] = b1[0]; sr[a1] = c1[0]; end
            $fclose(fd);
        end
        for (p = 0; p < NP; p = p + 1) begin
            nb[p] = 0; sent[p] = 0;
            case (p)
                0: rc = $value$plusargs("stim0=%s", fn);
                1: rc = $value$plusargs("stim1=%s", fn);
                2: rc = $value$plusargs("stim2=%s", fn);
                default: rc = $value$plusargs("stim3=%s", fn);
            endcase
            fd = $fopen(fn, "r");
            while (!$feof(fd) && nb[p] < MAXB) begin
                rc = $fscanf(fd, "%h %d %d\n", d8, a1, b1);
                if (rc == 3) begin mem[p][nb[p]] = {b1[0], a1[0], d8}; nb[p] = nb[p] + 1; end
            end
            $fclose(fd);
        end
        fo = $fopen(f_resp, "w");
        repeat (3) @(posedge clk);
        rst <= 1'b0;
        // configuration
        rc = $value$plusargs("cfg=%s", f_cfg);
        fd = $fopen(f_cfg, "r");
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%s", op);
            if (op == "V") begin
                rc = $fscanf(fd, "%h %h\n", a1, b1);
                @(posedge clk); cfg_we <= 1'b1; cfg_vid <= a1[11:0]; cfg_mask <= b1[NP-1:0];
                @(posedge clk); cfg_we <= 1'b0;
            end else if (op == "A") begin
                rc = $fscanf(fd, "%d\n", a1);
                age_at[n_age] = a1; n_age = n_age + 1;
            end
            op = "";
        end
        $fclose(fd);
        forever begin
            @(posedge clk);
            for (p = 0; p < NP; p = p + 1)
                if (m_tvalid[p] && m_tready[p])
                    $fdisplay(fo, "D%0d %0d %h %0d %0d", p, cyc, m_tdata[8 * p +: 8], m_tlast[p], m_tuser[p]);
            if (ev_pick) $fdisplay(fo, "P %0d %h", cyc, ev_port);
            if (ev_age) $fdisplay(fo, "G %0d", cyc);
            for (p = 0; p < NP; p = p + 1) n_drop = n_drop + ev_in_drop[p]; n_flood = n_flood + ev_flood; n_filter = n_filter + ev_filter;
            alldone = 1;
            for (p = 0; p < NP; p = p + 1) begin
                if (s_tvalid[p] && s_tready[p]) sent[p] = sent[p] + 1;
                if (s_tvalid[p] && !s_tready[p]) begin
                end else if (sent[p] < nb[p] && sv[(cyc + 17 * p) % ns]) begin
                    s_tvalid[p] <= 1'b1; {s_tuser[p], s_tlast[p], s_tdata[8 * p +: 8]} <= mem[p][sent[p]];
                end else s_tvalid[p] <= 1'b0;
                m_tready[p] <= sr[(cyc + 5 + 13 * p) % ns];
                if (sent[p] < nb[p]) alldone = 0;
            end
            age_tick <= (ai < n_age && cyc == age_at[ai]);
            if (ai < n_age && cyc == age_at[ai]) ai = ai + 1;
            cyc = cyc + 1;
            if (alldone) idle = idle + 1;
            if (idle > 20000 || cyc > 20_000_000) begin
                $fdisplay(fo, "# in_drops %0d", n_drop);
                $fdisplay(fo, "# floods %0d", n_flood);
                $fdisplay(fo, "# filtered %0d", n_filter);
                $fdisplay(fo, "# cycles %0d", cyc);
                $fclose(fo);
                $display("TB_DONE");
                $finish;
            end
        end
    end
endmodule

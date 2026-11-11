// tb_pkt_rewrite: file-driven bench (brief-19 harness method). The packet stream and the per-packet meta words come
// from files, each under its own seeded valid schedule; the output under a ready schedule. Output beats are written
// with their tdest; Python compares bit-exact. This bench judges nothing.
//   +stim=<f>  "<tdata hex> <tlast> <tuser>"      +meta=<f> "<hdr hex> <act hex>" a packet
//   +sched=<f> "<valid> <ready>" (cyclic), +nsched=<n>   +resp=<f>
`timescale 1ns/1ps
module tb_pkt_rewrite;
    localparam int MAXB = 400_000, MAXP = 8192, MAXS = 8192;
    reg clk = 1'b0;
    always #4 clk = ~clk;
    reg rst = 1'b1;

    reg  [7:0]   s_tdata = 0;
    reg          s_tvalid = 0, s_tlast = 0, s_tuser = 0;
    wire         s_tready;
    reg  [479:0] hdr = 0;
    reg  [159:0] act = 0;
    reg          mvalid = 0;
    wire         mready;
    wire [7:0]   m_tdata;
    wire         m_tvalid, m_tlast, m_tuser;
    wire [6:0]   m_tdest;
    reg          m_tready = 1;
    wire         ev_drop, ev_ttl;

    pkt_rewrite dut (.clk(clk), .rst(rst), .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .s_axis_tlast(s_tlast), .s_axis_tuser(s_tuser), .s_meta_hdr(hdr), .s_meta_act(act), .s_meta_tvalid(mvalid),
        .s_meta_tready(mready), .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .m_axis_tlast(m_tlast), .m_axis_tuser(m_tuser), .m_axis_tdest(m_tdest), .ev_drop(ev_drop), .ev_ttl_drop(ev_ttl));

    reg [9:0]   mem [0:MAXB-1];
    reg [479:0] mh [0:MAXP-1];
    reg [159:0] ma [0:MAXP-1];
    reg         sv [0:MAXS-1];
    reg         sr [0:MAXS-1];
    integer nb = 0, np = 0, ns = 1, fd, rc, a1, b1, c1, cyc = 0, sent = 0, msent = 0, idle = 0, fo, ndrop = 0, nttl = 0;
    reg [8*512-1:0] f_stim, f_meta, f_sched, f_resp;
    reg [7:0] d8;
    reg [479:0] h;
    reg [159:0] ac;

    initial begin
        rc = $value$plusargs("stim=%s", f_stim);
        rc = $value$plusargs("meta=%s", f_meta);
        rc = $value$plusargs("resp=%s", f_resp);
        sv[0] = 1; sr[0] = 1;
        if ($value$plusargs("sched=%s", f_sched)) begin
            rc = $value$plusargs("nsched=%d", ns);
            fd = $fopen(f_sched, "r");
            for (a1 = 0; a1 < ns; a1 = a1 + 1) begin rc = $fscanf(fd, "%d %d\n", b1, c1); sv[a1] = b1[0]; sr[a1] = c1[0]; end
            $fclose(fd);
        end
        fd = $fopen(f_stim, "r");
        while (!$feof(fd) && nb < MAXB) begin
            rc = $fscanf(fd, "%h %d %d\n", d8, a1, b1);
            if (rc == 3) begin mem[nb] = {b1[0], a1[0], d8}; nb = nb + 1; end
        end
        $fclose(fd);
        fd = $fopen(f_meta, "r");
        while (!$feof(fd) && np < MAXP) begin
            rc = $fscanf(fd, "%h %h\n", h, ac);
            if (rc == 2) begin mh[np] = h; ma[np] = ac; np = np + 1; end
        end
        $fclose(fd);
        fo = $fopen(f_resp, "w");
        repeat (3) @(posedge clk);
        rst <= 1'b0;
        forever begin
            @(posedge clk);
            if (m_tvalid && m_tready) $fdisplay(fo, "D %0d %h %0d %0d %h", cyc, m_tdata, m_tlast, m_tuser, m_tdest);
            if (s_tvalid && s_tready) begin
                if (sent == 0) $fdisplay(fo, "# first_in %0d", cyc);
                sent = sent + 1;
            end
            if (mvalid && mready) msent = msent + 1;
            ndrop = ndrop + ev_drop; nttl = nttl + ev_ttl;
            if (s_tvalid && !s_tready) begin
            end else if (sent < nb && sv[cyc % ns]) begin
                s_tvalid <= 1'b1; {s_tuser, s_tlast, s_tdata} <= mem[sent];
            end else s_tvalid <= 1'b0;
            if (mvalid && !mready) begin
            end else if (msent < np && sv[(cyc + 11) % ns]) begin
                mvalid <= 1'b1; hdr <= mh[msent]; act <= ma[msent];
            end else mvalid <= 1'b0;
            m_tready <= sr[(cyc + 3) % ns];
            cyc = cyc + 1;
            if (sent >= nb) idle = idle + 1;
            if (idle > 300 || cyc > 20_000_000) begin
                $fdisplay(fo, "# sent %0d", sent);
                $fdisplay(fo, "# drops %0d", ndrop);
                $fdisplay(fo, "# ttl_drops %0d", nttl);
                $fdisplay(fo, "# cycles %0d", cyc);
                $fclose(fo);
                $display("TB_DONE");
                $finish;
            end
        end
    end
endmodule

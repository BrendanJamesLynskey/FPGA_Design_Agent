// tb_pkt_queue_sched: file-driven bench (brief-19 harness method). Writes every output beat with its queue and the
// drop counters; Python compares. This bench judges nothing.
//   +stim=<f>  "<tdata hex> <tlast> <tuser> <queue hex>"   +sched=<f> +nsched=<n>   +resp=<f>
//   +mode=<0|1|2>  +quantum=<hex, NQ x 16 bits>  +hold=1 (deq_en low until every input beat is in)
`timescale 1ns/1ps
module tb_pkt_queue_sched;
    parameter int NQ = 4, QBYTES = 2048, DESC = 16, MAX_LEN = 1522;
    localparam int MAXB = 400_000, MAXS = 8192;
    reg clk = 1'b0;
    always #4 clk = ~clk;
    reg rst = 1'b1;

    reg  [7:0]  s_tdata = 0;
    reg         s_tvalid = 0, s_tlast = 0, s_tuser = 0;
    reg  [2:0]  s_tdest = 0;
    wire        s_tready;
    wire [7:0]  m_tdata;
    wire        m_tvalid, m_tlast, m_tuser;
    wire [2:0]  m_tdest;
    reg         m_tready = 1, deq_en = 1;
    reg  [1:0]  mode = 0;
    reg  [NQ*16-1:0] quantum = '0;
    wire [NQ*16-1:0] drops;
    wire        ev_drop;

    pkt_queue_sched #(.NQ(NQ), .QBYTES(QBYTES), .DESC(DESC), .MAX_LEN(MAX_LEN)) dut (
        .clk(clk), .rst(rst), .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .s_axis_tlast(s_tlast), .s_axis_tuser(s_tuser), .s_axis_tdest(s_tdest), .m_axis_tdata(m_tdata),
        .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready), .m_axis_tlast(m_tlast), .m_axis_tuser(m_tuser),
        .m_axis_tdest(m_tdest), .sched_mode(mode), .quantum(quantum), .deq_en(deq_en), .drop_cnt(drops),
        .ev_drop(ev_drop));

    reg [12:0] mem [0:MAXB-1];
    reg        sv [0:MAXS-1];
    reg        sr [0:MAXS-1];
    integer nb = 0, ns = 1, fd, rc, a1, b1, c1, e1, cyc = 0, sent = 0, idle = 0, fo, hold = 0, md = 0, q;
    reg [8*512-1:0] f_stim, f_sched, f_resp;
    reg [7:0] d8;
    reg [127:0] qh;

    initial begin
        rc = $value$plusargs("stim=%s", f_stim);
        rc = $value$plusargs("resp=%s", f_resp);
        rc = $value$plusargs("hold=%d", hold);
        rc = $value$plusargs("mode=%d", md);
        mode = md[1:0];
        if ($value$plusargs("quantum=%h", qh)) quantum = qh[NQ*16-1:0];
        sv[0] = 1; sr[0] = 1;
        if ($value$plusargs("sched=%s", f_sched)) begin
            rc = $value$plusargs("nsched=%d", ns);
            fd = $fopen(f_sched, "r");
            for (a1 = 0; a1 < ns; a1 = a1 + 1) begin rc = $fscanf(fd, "%d %d\n", b1, c1); sv[a1] = b1[0]; sr[a1] = c1[0]; end
            $fclose(fd);
        end
        fd = $fopen(f_stim, "r");
        while (!$feof(fd) && nb < MAXB) begin
            rc = $fscanf(fd, "%h %d %d %h\n", d8, a1, b1, e1);
            if (rc == 4) begin mem[nb] = {e1[2:0], b1[0], a1[0], d8}; nb = nb + 1; end
        end
        $fclose(fd);
        fo = $fopen(f_resp, "w");
        deq_en = (hold == 0);
        repeat (3) @(posedge clk);
        rst <= 1'b0;
        forever begin
            @(posedge clk);
            if (m_tvalid && m_tready) $fdisplay(fo, "D %0d %h %0d %0d %h", cyc, m_tdata, m_tlast, m_tuser, m_tdest);
            if (s_tvalid && s_tready) begin
                if (sent == 0) $fdisplay(fo, "# first_in %0d", cyc);
                sent = sent + 1;
            end
            if (s_tvalid && !s_tready) begin
            end else if (sent < nb && sv[cyc % ns]) begin
                s_tvalid <= 1'b1; {s_tdest, s_tuser, s_tlast, s_tdata} <= mem[sent];
            end else s_tvalid <= 1'b0;
            m_tready <= sr[(cyc + 3) % ns];
            if (sent >= nb && !s_tvalid) deq_en <= 1'b1;
            cyc = cyc + 1;
            if (sent >= nb) idle = idle + 1;
            if (idle > 3000 + 2 * nb || cyc > 20_000_000) begin
                for (q = 0; q < NQ; q = q + 1) $fdisplay(fo, "# drop%0d %0d", q, drops[16 * q +: 16]);
                $fdisplay(fo, "# cycles %0d", cyc);
                $fclose(fo);
                $display("TB_DONE");
                $finish;
            end
        end
    end
endmodule

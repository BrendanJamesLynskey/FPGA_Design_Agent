// tb_pkt_parser: file-driven bench (brief-19 harness method). Drives the packet stream from a file under a seeded
// valid/ready gap schedule (flow/ipgen/harness.py format), and writes every output beat and header word with its
// cycle. Python compares bit-exact; this bench judges nothing.
//   +stim=<f>   "<tdata hex> <tlast> <tuser>" a line
//   +sched=<f>  "<valid-allowed> <ready-allowed>" a line, read cyclically (ready also gates m_hdr_tready)
//   +resp=<f>   written: "D <cycle> <tdata> <tlast> <tuser>" and "H <cycle> <hdr hex>", then "# k v" lines
//   +nsched=<n> lines in the schedule file
`timescale 1ns/1ps
module tb_pkt_parser;
    parameter int MAX_VLAN = 2;
    localparam int MAXB = 600_000;
    localparam int MAXS = 8192;
    reg clk = 1'b0;
    always #4 clk = ~clk;
    reg rst = 1'b1;

    reg  [7:0]   s_tdata = 8'h00;
    reg          s_tvalid = 1'b0, s_tlast = 1'b0, s_tuser = 1'b0;
    wire         s_tready;
    wire [7:0]   m_tdata;
    wire         m_tvalid, m_tlast, m_tuser;
    reg          m_tready = 1'b1, h_tready = 1'b1;
    wire [479:0] h_tdata;
    wire         h_tvalid;

    pkt_parser #(.MAX_VLAN(MAX_VLAN)) dut (
        .clk(clk), .rst(rst),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
        .s_axis_tuser(s_tuser),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready), .m_axis_tlast(m_tlast),
        .m_axis_tuser(m_tuser), .m_hdr_tdata(h_tdata), .m_hdr_tvalid(h_tvalid), .m_hdr_tready(h_tready));

    reg [9:0] mem [0:MAXB-1];            // {tuser, tlast, tdata}
    reg       sv [0:MAXS-1];
    reg       sr [0:MAXS-1];
    integer   nb = 0, ns = 1, fd, rc, a, b, c, cyc, sent, idle, fo;
    reg [8*512-1:0] f_stim, f_sched, f_resp;
    reg [7:0] d8;

    initial begin
        rc = $value$plusargs("stim=%s", f_stim);
        rc = $value$plusargs("resp=%s", f_resp);
        sv[0] = 1'b1; sr[0] = 1'b1;
        if ($value$plusargs("sched=%s", f_sched)) begin
            rc = $value$plusargs("nsched=%d", ns);
            fd = $fopen(f_sched, "r");
            for (a = 0; a < ns; a = a + 1) begin rc = $fscanf(fd, "%d %d\n", b, c); sv[a] = b[0]; sr[a] = c[0]; end
            $fclose(fd);
        end
        fd = $fopen(f_stim, "r");
        while (!$feof(fd) && nb < MAXB) begin
            rc = $fscanf(fd, "%h %d %d\n", d8, a, b);
            if (rc == 3) begin mem[nb] = {b[0], a[0], d8}; nb = nb + 1; end
        end
        $fclose(fd);
        fo = $fopen(f_resp, "w");
        cyc = 0; sent = 0; idle = 0;
        repeat (3) @(posedge clk);
        rst <= 1'b0;
        forever begin
            @(posedge clk);
            if (m_tvalid && m_tready) $fdisplay(fo, "D %0d %h %0d %0d", cyc, m_tdata, m_tlast, m_tuser);
            if (h_tvalid && h_tready) $fdisplay(fo, "H %0d %h", cyc, h_tdata);
            if (s_tvalid && s_tready) begin
                if (sent == 0) $fdisplay(fo, "# first_in %0d", cyc);
                sent = sent + 1;
            end
            if (s_tvalid && !s_tready) begin
            end else if (sent < nb && sv[cyc % ns]) begin
                s_tvalid <= 1'b1; {s_tuser, s_tlast, s_tdata} <= mem[sent];
            end else s_tvalid <= 1'b0;
            m_tready <= sr[(cyc + 3) % ns];
            h_tready <= sr[(cyc + 5) % ns];
            cyc = cyc + 1;
            if (sent >= nb) idle = idle + 1;
            if (idle > 200 || cyc > 20_000_000) begin
                $fdisplay(fo, "# sent %0d", sent);
                $fdisplay(fo, "# cycles %0d", cyc);
                $fclose(fo);
                $display("TB_DONE");
                $finish;
            end
        end
    end
endmodule

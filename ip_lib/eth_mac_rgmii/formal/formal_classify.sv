// formal_classify.sv: eth_rx_classify's address filter against the rule written again here from IEEE 802.3 3.2.3 and
// the contract (own address, broadcast, promiscuous, multicast by exact table or hash), for any byte stream with gaps
// and any configuration held steady within a frame. The hash index is computed here bit by bit from the CRC-32
// definition. Bounded (bmc) and by k-induction (prove).
module formal_classify (
    input logic        clk,
    input logic        in_valid, in_sof,
    input logic [7:0]  in_data,
    input logic [47:0] own_mac, mc_addr,
    input logic        promisc, bcast_en, mcast_all, mc_we, mc_en,
    input logic [63:0] mc_hash,
    input logic [3:0]  mc_idx
);
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    logic rst;
    assign rst = !f_past;
    logic da_valid, match, is_own, is_bcast, is_mcast, is_vlan, is_ctrl, is_pause;
    logic [15:0] tci, quanta;
    eth_rx_classify #(.MC_EXACT(2)) dut (.clk, .rst, .in_valid, .in_sof, .in_data, .own_mac, .promisc, .bcast_en,
        .mcast_all, .mc_hash, .mc_we, .mc_idx, .mc_addr, .mc_en, .da_valid, .match, .is_own, .is_bcast, .is_mcast,
        .is_vlan, .tci, .is_ctrl, .is_pause, .quanta);
    // configuration and table writes only between frames (the contract: static while frames arrive)
    logic f_in;                         // inside a frame's address bytes or its verdict
    logic [2:0] f_k;
    logic [47:0] f_da;
    logic [31:0] f_crc;
    logic        f_tv [2];
    logic [47:0] f_ta [2];
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= 1'b0; f_k <= '0; f_da <= '0; f_crc <= '1; end
        else if (in_valid && in_sof) begin f_in <= 1'b1; f_k <= 3'd1; f_da <= {40'd0, in_data}; f_crc <= crc8(32'hFFFF_FFFF, in_data); end
        else if (in_valid && f_k < 3'd6 && f_k != 3'd0) begin f_k <= f_k + 3'd1; f_da <= {f_da[39:0], in_data}; f_crc <= crc8(f_crc, in_data); end
        else if (da_valid) f_in <= 1'b0;
        if (rst) begin f_tv[0] <= 1'b0; f_tv[1] <= 1'b0; f_ta[0] <= '0; f_ta[1] <= '0; end
        else if (mc_we && mc_idx < 4'd2) begin f_tv[mc_idx[0]] <= mc_en; f_ta[mc_idx[0]] <= mc_addr; end
    end
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c;
        for (int i = 0; i < 8; i++) begin
            if (x[0] ^ b[i]) x = (x >> 1) ^ 32'hEDB88320; else x = x >> 1;
        end
        crc8 = x;
    endfunction
    always_ff @(posedge clk) if (f_past && !rst && (f_in || $past(f_in))) begin
        assume ($stable(own_mac) && $stable(promisc) && $stable(bcast_en) && $stable(mcast_all) && $stable(mc_hash) && !mc_we);
    end
    logic f_exp;
    always_comb begin
        f_exp = promisc || f_da == own_mac || (f_da == 48'hFFFF_FFFF_FFFF && bcast_en) ||
                (f_da[40] && f_da != 48'hFFFF_FFFF_FFFF &&
                 (mcast_all || (f_tv[0] && f_ta[0] == f_da) || (f_tv[1] && f_ta[1] == f_da) || mc_hash[f_crc[5:0]]));
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        if (da_valid && !$past(da_valid)) begin
            assert (f_k == 3'd6);
            assert (match == f_exp);
            assert (is_bcast == (f_da == 48'hFFFF_FFFF_FFFF) && is_mcast == f_da[40] && is_own == (f_da == own_mac));
        end
        cover (da_valid && match && is_mcast && !is_bcast && !mcast_all && !promisc);
    end
endmodule

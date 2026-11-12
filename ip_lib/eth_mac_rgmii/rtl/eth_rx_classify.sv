// eth_rx_classify.sv: receive address filter and frame classifier, watching a MAC's byte stream (ip_lib).
//
// Input: the frame's bytes from the destination address on (in_sof on the first), one per in_valid, as mac_rx's
// cut-through view or any MAC's receive stream gives them. Nothing is delayed or changed; the block only looks.
//
// Address filter (IEEE 802.3 clause 3.2.3, the individual/group bit is bit 0 of the first destination byte):
//   match = promisc
//        or the destination is own_mac
//        or it is the broadcast address and bcast_en
//        or it is another group (multicast) address and (mcast_all, or an enabled entry of the exact table holds it,
//           or the hash table's bit for it is set).
//   Hash: the bit index is the 6 least significant bits of the CRC-32 register (reflected polynomial 0xEDB88320,
//   initial value all ones, not inverted) after the 6 destination bytes, the same value as Linux's
//   ether_crc_le(6, addr) & 0x3f; mc_hash[index] enables it.
//   The exact table has MC_EXACT entries, written one at a time (mc_we, mc_idx, mc_addr, mc_en).
// da_valid rises 2 clocks after the sixth byte and stays high until the next frame starts; match, is_own, is_bcast
// and is_mcast are valid while it is high.
//
// Classifier (valid from the clock after byte 17 until the next frame; the frame's end comes later for every frame
// of 18 bytes or more):
//   is_vlan, tci  : an 802.1Q (0x8100) or 802.1ad (0x88A8) tag at bytes 12-13; its TCI at bytes 14-15
//   is_ctrl       : EtherType 0x8808, a MAC control frame (IEEE 802.3 clause 31)
//   is_pause      : a control frame with opcode 0x0001 to 01-80-C2-00-00-01 or to own_mac (annex 31B); quanta is
//                   bytes 16-17, in units of 512 bit times

module eth_rx_classify #(
    parameter int MC_EXACT = 4          // exact-match multicast entries, 0..16
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_valid,
    input  logic        in_sof,
    input  logic [7:0]  in_data,
    // configuration (static while frames arrive)
    input  logic [47:0] own_mac,        // first byte on the wire in [47:40]
    input  logic        promisc,
    input  logic        bcast_en,
    input  logic        mcast_all,
    input  logic [63:0] mc_hash,
    input  logic        mc_we,
    input  logic [3:0]  mc_idx,
    input  logic [47:0] mc_addr,
    input  logic        mc_en,
    // results
    output logic        da_valid,
    output logic        match,
    output logic        is_own,
    output logic        is_bcast,
    output logic        is_mcast,
    output logic        is_vlan,
    output logic [15:0] tci,
    output logic        is_ctrl,
    output logic        is_pause,
    output logic [15:0] quanta
);
    initial begin
        if (MC_EXACT < 0 || MC_EXACT > 16) $error("eth_rx_classify: MC_EXACT must be in 0..16 (got %0d)", MC_EXACT);
    end
    localparam int NE = (MC_EXACT > 0) ? MC_EXACT : 1;

    function automatic logic [31:0] crc32_byte(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c;
        for (int i = 0; i < 8; i++)
            x = (x[0] ^ b[i]) ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        crc32_byte = x;
    endfunction

    logic [4:0]  k;                     // index of the next byte (saturates at 31)
    logic [47:0] da;
    logic [31:0] hcrc;
    logic        da_done;
    logic [15:0] et, w14, w16;
    logic        mc_v [NE];
    logic [47:0] mc_a [NE];

    always_ff @(posedge clk) begin
        if (rst) begin
            k <= 5'd31; da <= '0; hcrc <= '1; da_done <= 1'b0; et <= '0; w14 <= '0; w16 <= '0;   // bytes before a first SOF are ignored
        end else if (in_valid) begin
            if (in_sof) begin
                k <= 5'd1; da <= {40'd0, in_data}; hcrc <= crc32_byte(32'hFFFF_FFFF, in_data); da_done <= 1'b0;
                et <= '0; w14 <= '0; w16 <= '0;
            end else begin
                if (k != 5'd31) k <= k + 5'd1;
                if (k < 5'd6) begin da <= {da[39:0], in_data}; hcrc <= crc32_byte(hcrc, in_data); end
                if (k == 5'd5) da_done <= 1'b1;
                case (k)
                    5'd12: et[15:8]  <= in_data;
                    5'd13: et[7:0]   <= in_data;
                    5'd14: w14[15:8] <= in_data;
                    5'd15: w14[7:0]  <= in_data;
                    5'd16: w16[15:8] <= in_data;
                    5'd17: w16[7:0]  <= in_data;
                    default: ;
                endcase
            end
        end
    end

    // the exact table
    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < NE; i++) begin mc_v[i] <= 1'b0; mc_a[i] <= '0; end
        end else if (mc_we && MC_EXACT > 0 && int'(mc_idx) < MC_EXACT) begin
            mc_v[mc_idx] <= mc_en; mc_a[mc_idx] <= mc_addr;
        end
    end

    // the verdict, registered once the address is complete
    logic hit_exact, d_bcast, d_mcast, d_own;
    always_comb begin
        hit_exact = 1'b0;
        for (int i = 0; i < MC_EXACT; i++) if (mc_v[i] && mc_a[i] == da) hit_exact = 1'b1;
    end
    assign d_bcast = (da == 48'hFFFF_FFFF_FFFF);
    assign d_mcast = da[40];
    assign d_own   = (da == own_mac);
    always_ff @(posedge clk) begin
        if (rst || (in_valid && in_sof)) begin
            da_valid <= 1'b0; match <= 1'b0; is_own <= 1'b0; is_bcast <= 1'b0; is_mcast <= 1'b0;
        end else if (da_done && !da_valid) begin
            da_valid <= 1'b1;
            is_own   <= d_own;
            is_bcast <= d_bcast;
            is_mcast <= d_mcast;
            match    <= promisc || d_own || (d_bcast && bcast_en) ||
                        (d_mcast && !d_bcast && (mcast_all || hit_exact || mc_hash[hcrc[5:0]]));
        end
    end

    assign is_vlan  = (et == 16'h8100) || (et == 16'h88A8);
    assign tci      = is_vlan ? w14 : 16'h0000;
    assign is_ctrl  = (et == 16'h8808);
    assign is_pause = is_ctrl && w14 == 16'h0001 && (da == 48'h0180_C200_0001 || d_own);
    assign quanta   = w16;
endmodule

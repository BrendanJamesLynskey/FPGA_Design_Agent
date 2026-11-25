-- fir16: 16-tap symmetric FIR, one sample per clock when in_v = '1'. Delay line, 16 multipliers, a 4-level adder tree and a
-- saturating output stage. Seven register stages from in_v to out_v: 1 (delay line) + 1 (products) + 4 (tree) + 1 (output); out_v is high after
-- the 6th clock edge that follows the edge that took the sample.
-- The coefficient table starts at default_coefs (fir_pkg) and is rewritten through a synchronous write port: coef_wr, coef_addr, coef_data.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fir_pkg.all;

entity fir16 is
    port (
        clk       : in  std_logic;
        rst       : in  std_logic;
        in_v      : in  std_logic;
        in_d      : in  std_logic_vector(DW - 1 downto 0);
        coef_wr   : in  std_logic;
        coef_addr : in  std_logic_vector(3 downto 0);
        coef_data : in  std_logic_vector(CW - 1 downto 0);
        out_v     : out std_logic;
        out_d     : out std_logic_vector(DW - 1 downto 0);
        sat_seen  : out std_logic
    );
end entity fir16;

architecture rtl of fir16 is
    signal line_q  : sample_vec_t;
    signal coefs   : coef_vec_t := default_coefs;
    signal prods   : prod_vec_t;
    signal prods_q : prod_vec_t;
    signal v0, v1  : std_logic;
    signal tree_v  : std_logic;
    signal tree_s  : signed(AW - 1 downto 0);
    signal sat_q   : std_logic;
begin
    -- delay line
    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                line_q <= (others => (others => '0'));
                v0     <= '0';
            else
                v0 <= in_v;
                if in_v = '1' then
                    line_q(0) <= signed(in_d);
                    for i in 1 to TAPS - 1 loop
                        line_q(i) <= line_q(i - 1);
                    end loop;
                end if;
            end if;
        end if;
    end process;

    -- coefficient write port
    process (clk)
    begin
        if rising_edge(clk) then
            if coef_wr = '1' then
                coefs(to_integer(unsigned(coef_addr))) <= signed(coef_data);
            end if;
        end if;
    end process;

    g_mul : for i in 0 to TAPS - 1 generate
        prods(i) <= line_q(i) * coefs(i);
    end generate g_mul;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                prods_q <= (others => (others => '0'));
                v1      <= '0';
            else
                prods_q <= prods;
                v1      <= v0;
            end if;
        end if;
    end process;

    u_tree : entity work.fir_add_tree
        port map (clk => clk, rst => rst, in_v => v1, prods => prods_q, out_v => tree_v, out_sum => tree_s);

    process (clk)
        variable shifted : signed(AW - 1 downto 0);
    begin
        if rising_edge(clk) then
            if rst = '1' then
                out_v  <= '0';
                out_d  <= (others => '0');
                sat_q  <= '0';
            else
                out_v <= tree_v;
                if tree_v = '1' then
                    shifted := shift_right(tree_s, 10);         -- Q10 coefficients
                    out_d   <= std_logic_vector(sat16(shifted));
                    if shifted > to_signed(2 ** (DW - 1) - 1, AW) or shifted < to_signed(-(2 ** (DW - 1)), AW) then
                        sat_q <= '1';
                    end if;
                end if;
            end if;
        end if;
    end process;
    sat_seen <= sat_q;
end architecture rtl;

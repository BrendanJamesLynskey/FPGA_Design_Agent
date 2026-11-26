-- fir_add_tree: a registered binary adder tree over TAPS products (4 levels), valid travels with the data.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fir_pkg.all;

entity fir_add_tree is
    port (
        clk     : in  std_logic;
        rst     : in  std_logic;
        in_v    : in  std_logic;
        prods   : in  prod_vec_t;
        out_v   : out std_logic;
        out_sum : out signed(AW - 1 downto 0)
    );
end entity fir_add_tree;

architecture rtl of fir_add_tree is
    type lvl8_t  is array (0 to 7) of signed(AW - 1 downto 0);
    type lvl4_t  is array (0 to 3) of signed(AW - 1 downto 0);
    type lvl2_t  is array (0 to 1) of signed(AW - 1 downto 0);
    signal l1 : lvl8_t;
    signal l2 : lvl4_t;
    signal l3 : lvl2_t;
    signal l4 : signed(AW - 1 downto 0);
    signal v  : std_logic_vector(1 to 4);
begin
    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                v  <= (others => '0');
                l1 <= (others => (others => '0'));
                l2 <= (others => (others => '0'));
                l3 <= (others => (others => '0'));
                l4 <= (others => '0');
            else
                v <= in_v & v(1 to 3);
                for i in 0 to 7 loop
                    l1(i) <= resize(prods(2 * i), AW) + resize(prods(2 * i + 1), AW);
                end loop;
                for i in 0 to 3 loop
                    l2(i) <= l1(2 * i) + l1(2 * i + 1);
                end loop;
                for i in 0 to 1 loop
                    l3(i) <= l2(2 * i) + l2(2 * i + 1);
                end loop;
                l4 <= l3(0) + l3(1);
            end if;
        end if;
    end process;
    out_v   <= v(4);
    out_sum <= l4;
end architecture rtl;

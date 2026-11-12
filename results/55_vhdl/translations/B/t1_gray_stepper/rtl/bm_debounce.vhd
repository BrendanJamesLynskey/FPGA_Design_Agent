library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity bm_debounce is
    generic (
        CYCLES : integer := 1_000_000
    );
    port (
        clk     : in  std_logic;
        rst     : in  std_logic;
        d_async : in  std_logic;
        level   : out std_logic;
        rise    : out std_logic
    );
end entity bm_debounce;

architecture rtl of bm_debounce is
    function clog2(n : positive) return positive is
        variable v    : natural := n - 1;
        variable bits : natural := 0;
    begin
        while v > 0 loop
            bits := bits + 1;
            v := v / 2;
        end loop;

        if bits = 0 then
            return 1;
        else
            return bits;
        end if;
    end function;

    constant CW : positive := clog2(CYCLES + 1);

    signal d        : std_logic := '0';
    signal level_reg : std_logic := '0';
    signal rise_reg  : std_logic := '0';
    signal run       : unsigned(CW - 1 downto 0) := (others => '0');
begin
    u_sync : entity work.sync2_vh
        port map (
            clk => clk,
            rst => rst,
            d   => d_async,
            q   => d
        );

    process (clk)
    begin
        if rising_edge(clk) then
            rise_reg <= '0';

            if rst = '1' then
                level_reg <= '0';
                run       <= (others => '0');
            elsif d = level_reg then
                run <= (others => '0');
            elsif run = to_unsigned(CYCLES - 1, CW) then
                level_reg <= d;
                run       <= (others => '0');
                rise_reg  <= d;
            else
                run <= run + to_unsigned(1, CW);
            end if;
        end if;
    end process;

    level <= level_reg;
    rise  <= rise_reg;
end architecture rtl;

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
    function counter_width(n : integer) return natural is
        variable value : natural := 1;
        variable width : natural := 0;
        variable limit : natural;
    begin
        if n < 1 then
            return 1;
        end if;

        limit := n + 1;
        while value < limit loop
            value := value * 2;
            width := width + 1;
        end loop;

        if width = 0 then
            return 1;
        end if;
        return width;
    end function;

    constant CW : natural := counter_width(CYCLES);

    signal d_sync : std_logic;
    signal level_i : std_logic;
    signal run     : unsigned(CW - 1 downto 0);
    signal rise_i  : std_logic;
begin
    u_sync : entity work.sync2_vh
        port map (
            clk => clk,
            rst => rst,
            d   => d_async,
            q   => d_sync
        );

    process (clk)
    begin
        if rising_edge(clk) then
            rise_i <= '0';

            if rst = '1' then
                level_i <= '0';
                run     <= (others => '0');
            elsif d_sync = level_i then
                run <= (others => '0');
            elsif run = to_unsigned(CYCLES - 1, CW) then
                level_i <= d_sync;
                run     <= (others => '0');
                rise_i  <= d_sync;
            else
                run <= run + 1;
            end if;
        end if;
    end process;

    level <= level_i;
    rise  <= rise_i;
end architecture rtl;

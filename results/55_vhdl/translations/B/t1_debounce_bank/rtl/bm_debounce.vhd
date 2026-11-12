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
        variable value : natural := n - 1;
        variable bits  : natural := 0;
    begin
        while value > 0 loop
            bits  := bits + 1;
            value := value / 2;
        end loop;

        if bits = 0 then
            return 1;
        else
            return bits;
        end if;
    end function;

    constant CW : positive := clog2(CYCLES + 1);

    component sync2 is
        port (
            clk : in  std_logic;
            rst : in  std_logic;
            d   : in  std_logic;
            q   : out std_logic
        );
    end component;

    signal d       : std_logic := '0';
    signal run     : unsigned(CW - 1 downto 0) := (others => '0');
    signal level_r : std_logic := '0';
    signal rise_r  : std_logic := '0';
begin
    u_sync : sync2
        port map (
            clk => clk,
            rst => rst,
            d   => d_async,
            q   => d
        );

    level <= level_r;
    rise  <= rise_r;

    process (clk)
    begin
        if rising_edge(clk) then
            rise_r <= '0';

            if rst = '1' then
                level_r <= '0';
                run     <= (others => '0');
                rise_r  <= '0';
            elsif d = level_r then
                run <= (others => '0');
            elsif run = to_unsigned(CYCLES - 1, CW) then
                level_r <= d;
                run     <= (others => '0');
                rise_r  <= d;
            else
                run <= run + 1;
            end if;
        end if;
    end process;
end architecture rtl;

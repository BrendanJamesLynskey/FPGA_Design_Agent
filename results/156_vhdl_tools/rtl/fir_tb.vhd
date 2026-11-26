-- fir_tb: a pure-VHDL testbench of fir16 (no cocotb, no VPI/VHPI), for the simulator-speed measurement of brief 156.
-- A 32-bit LFSR feeds samples; the outputs are folded into a checksum; the last line reports the checksum and the counts.
-- Generic CYCLES is the number of clocks. Every simulator must print the same checksum.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fir_pkg.all;

entity fir_tb is
    generic (CYCLES : natural := 300000);
end entity fir_tb;

architecture sim of fir_tb is
    signal clk   : std_logic := '0';
    signal rst   : std_logic := '1';
    signal in_v  : std_logic := '0';
    signal in_d  : std_logic_vector(DW - 1 downto 0) := (others => '0');
    signal out_v : std_logic;
    signal out_d : std_logic_vector(DW - 1 downto 0);
    signal sat   : std_logic;
    signal done  : boolean := false;
    signal c_wr  : std_logic := '0';
    signal c_a   : std_logic_vector(3 downto 0) := (others => '0');
    signal c_d   : std_logic_vector(CW - 1 downto 0) := (others => '0');
begin
    dut : entity work.fir16
        port map (clk => clk, rst => rst, in_v => in_v, in_d => in_d, coef_wr => c_wr, coef_addr => c_a, coef_data => c_d,
                  out_v => out_v, out_d => out_d, sat_seen => sat);

    clkgen : process
    begin
        while not done loop
            clk <= '0'; wait for 5 ns;
            clk <= '1'; wait for 5 ns;
        end loop;
        wait;
    end process;

    stim : process (clk)
        variable lfsr : unsigned(31 downto 0) := x"ACE1_1234";
        variable n    : natural := 0;
        variable sum  : unsigned(31 downto 0) := (others => '0');
        variable cnt  : natural := 0;
    begin
        if rising_edge(clk) then
            if n = 4 then
                rst <= '0';
            end if;
            if n > 5 and n < CYCLES then
                lfsr := lfsr(30 downto 0) & (lfsr(31) xor lfsr(21) xor lfsr(1) xor lfsr(0));
                in_v <= lfsr(7) or lfsr(11) or lfsr(13);            -- about 7 clocks in 8 carry a sample
                in_d <= std_logic_vector(lfsr(23 downto 8));
            else
                in_v <= '0';
            end if;
            if out_v = '1' then
                sum := (sum rol 5) xor resize(unsigned(out_d), 32);
                cnt := cnt + 1;
            end if;
            if n = CYCLES + 20 then
                report "CHECKSUM=" & integer'image(to_integer(sum(30 downto 0))) & " OUTPUTS=" & integer'image(cnt) & " SAT=" & std_logic'image(sat);
                done <= true;
            end if;
            n := n + 1;
        end if;
    end process;
end architecture sim;

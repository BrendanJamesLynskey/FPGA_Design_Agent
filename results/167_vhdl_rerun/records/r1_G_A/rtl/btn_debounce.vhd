-- btn_debounce: accepts a new level of the synchronised button only after it has
-- held for DEBOUNCE_CYCLES clocks. press is a one-clock pulse on each rising edge
-- of the accepted level; release gives no pulse.
library ieee;
use ieee.std_logic_1164.all;

entity btn_debounce is
  generic (
    DEBOUNCE_CYCLES : integer := 2000000);
  port (
    clk   : in  std_logic;
    rst   : in  std_logic;   -- synchronous, active high
    btn   : in  std_logic;   -- already synchronised to clk
    press : out std_logic);  -- one clock per accepted rising edge
end entity btn_debounce;

architecture rtl of btn_debounce is
  signal acc     : std_logic := '0';
  signal cnt     : integer range 0 to DEBOUNCE_CYCLES := 0;
  signal edge_r  : std_logic := '0';   -- accepted rising edge, first stage
  signal press_r : std_logic := '0';   -- accepted rising edge, output stage
begin

  press <= press_r;

  p_acc : process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        acc    <= '0';
        cnt    <= 0;
        edge_r <= '0';
      else
        edge_r <= '0';
        if btn = acc then
          cnt <= 0;
        elsif cnt = DEBOUNCE_CYCLES - 1 then
          -- the new level has now held for DEBOUNCE_CYCLES clocks
          cnt <= 0;
          acc <= btn;
          if btn = '1' then
            edge_r <= '1';
          end if;
        else
          cnt <= cnt + 1;
        end if;
      end if;
    end if;
  end process p_acc;

  -- output register stage: one clock later than the accepting edge
  p_out : process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        press_r <= '0';
      else
        press_r <= edge_r;
      end if;
    end if;
  end process p_out;

end architecture rtl;

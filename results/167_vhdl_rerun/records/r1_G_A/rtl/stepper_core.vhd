-- stepper_core: 10-bit binary count, 32-bit applied-step counter, pending-step count,
-- TICK_CYCLES tick counter, automatic-step counter, auto_en and 16-bit rate.
-- Each request (button or automatic) is queued in pend and one step is applied per clock,
-- so simultaneous requests become consecutive applied steps.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity stepper_core is
  generic (
    TICK_CYCLES : integer := 100000);
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;   -- synchronous, active high
    btn_step   : in  std_logic;   -- one-clock button step request
    dir_down   : in  std_logic;   -- sw[15]: 1 = decrement, sampled at each applied step
    cnt_we     : in  std_logic;   -- COUNT_BIN write (does not change step_cnt or tick)
    cnt_wdata  : in  std_logic_vector(9 downto 0);
    ctrl_we    : in  std_logic;   -- CTRL write
    ctrl_auto  : in  std_logic;   -- CTRL bit 0
    rate_we    : in  std_logic;   -- RATE_MS write
    rate_wdata : in  std_logic_vector(15 downto 0);
    bin        : out std_logic_vector(9 downto 0);
    step_cnt   : out std_logic_vector(31 downto 0);
    auto_en    : out std_logic;
    rate       : out std_logic_vector(15 downto 0));
end entity stepper_core;

architecture rtl of stepper_core is
  function b2i (x : std_logic) return integer is
  begin
    if x = '1' then
      return 1;
    else
      return 0;
    end if;
  end function b2i;

  signal bin_r    : unsigned(9 downto 0)  := (others => '0');
  signal step_r   : unsigned(31 downto 0) := (others => '0');
  signal auto_r   : std_logic             := '0';
  signal rate_r   : unsigned(15 downto 0) := (others => '0');
  signal arc      : unsigned(15 downto 0) := (others => '0');  -- ticks counted toward next auto step
  signal pend     : unsigned(3 downto 0)  := (others => '0');  -- queued step requests
  signal tick_c   : integer range 0 to TICK_CYCLES - 1 := 0;
  signal tick_now : std_logic := '0';   -- '1' on the clock the tick counter wraps
  signal auto_req : std_logic := '0';   -- automatic request on this clock
begin

  bin      <= std_logic_vector(bin_r);
  step_cnt <= std_logic_vector(step_r);
  auto_en  <= auto_r;
  rate     <= std_logic_vector(rate_r);

  -- Free-running TICK_CYCLES counter, cleared by reset so its phase is defined from reset.
  -- Button steps and register writes never touch it.
  tick_now <= '1' when tick_c = TICK_CYCLES - 1 else '0';

  p_tick : process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        tick_c <= 0;
      elsif tick_now = '1' then
        tick_c <= 0;
      else
        tick_c <= tick_c + 1;
      end if;
    end if;
  end process p_tick;

  -- Automatic request: the tick that completes rate ticks (rate nonzero, auto_en set).
  auto_req <= '1' when (tick_now = '1' and auto_r = '1' and rate_r /= 0 and
                        (resize(arc, 17) + 1 >= resize(rate_r, 17))) else '0';

  p_ctrl : process (clk)
    variable total : integer range 0 to 31;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        bin_r  <= (others => '0');
        step_r <= (others => '0');
        auto_r <= '0';
        rate_r <= (others => '0');
        arc    <= (others => '0');
        pend   <= (others => '0');
      else
        -- automatic tick counter: counts only while enabled with a nonzero rate
        if auto_r = '0' or rate_r = 0 then
          arc <= (others => '0');
        elsif tick_now = '1' then
          if auto_req = '1' then
            arc <= (others => '0');
          else
            arc <= arc + 1;
          end if;
        end if;

        -- register writes from the window
        if ctrl_we = '1' then
          auto_r <= ctrl_auto;
        end if;
        if rate_we = '1' then
          rate_r <= unsigned(rate_wdata);
        end if;

        -- queue and apply one step per clock
        total := to_integer(pend) + b2i(btn_step) + b2i(auto_req);
        if total > 0 then
          pend <= to_unsigned(total - 1, 4);
          if cnt_we = '1' then
            bin_r <= unsigned(cnt_wdata);
          elsif dir_down = '1' then
            bin_r <= bin_r - 1;
          else
            bin_r <= bin_r + 1;
          end if;
          step_r <= step_r + 1;
        else
          pend <= (others => '0');
          if cnt_we = '1' then
            bin_r <= unsigned(cnt_wdata);
          end if;
        end if;
      end if;
    end if;
  end process p_ctrl;

end architecture rtl;

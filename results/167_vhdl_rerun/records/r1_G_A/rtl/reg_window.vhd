-- reg_window: decodes the window word address (win_addr = byte offset / 4; the shell's
-- ADDR is 0x80 + win_addr) for the six registers:
--   win 0 = 0x00 ID (RO), win 1 = 0x04 COUNT_BIN (RW), win 2 = 0x08 GRAY_RD (RO),
--   win 3 = 0x0C CTRL (RW, bit 0 auto_en), win 4 = 0x10 RATE_MS (RW, 16 bit),
--   win 5 = 0x14 STEP_CNT (RO, 32 bit).
-- Writes are pulses to stepper_core; reads are registered and valid one clock after win_rd.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity reg_window is
  port (
    clk        : in  std_logic;
    win_addr   : in  std_logic_vector(6 downto 0);
    win_wr     : in  std_logic;
    win_rd     : in  std_logic;
    win_wdata  : in  std_logic_vector(31 downto 0);
    win_rdata  : out std_logic_vector(31 downto 0);
    bin        : in  std_logic_vector(9 downto 0);
    gray       : in  std_logic_vector(9 downto 0);
    step_cnt   : in  std_logic_vector(31 downto 0);
    auto_en    : in  std_logic;
    rate       : in  std_logic_vector(15 downto 0);
    cnt_we     : out std_logic;
    cnt_wdata  : out std_logic_vector(9 downto 0);
    ctrl_we    : out std_logic;
    ctrl_auto  : out std_logic;
    rate_we    : out std_logic;
    rate_wdata : out std_logic_vector(15 downto 0));
end entity reg_window;

architecture rtl of reg_window is
  signal rdata_r : std_logic_vector(31 downto 0) := (others => '0');
begin

  win_rdata  <= rdata_r;

  cnt_we     <= '1' when (win_wr = '1' and win_addr = "0000001") else '0';
  ctrl_we    <= '1' when (win_wr = '1' and win_addr = "0000011") else '0';
  rate_we    <= '1' when (win_wr = '1' and win_addr = "0000100") else '0';
  cnt_wdata  <= win_wdata(9 downto 0);
  ctrl_auto  <= win_wdata(0);
  rate_wdata <= win_wdata(15 downto 0);

  p_read : process (clk)
  begin
    if rising_edge(clk) then
      if win_rd = '1' then
        case to_integer(unsigned(win_addr)) is
          when 0 => rdata_r <= x"47524159";
          when 1 => rdata_r <= std_logic_vector(resize(unsigned(bin), 32));
          when 2 => rdata_r <= std_logic_vector(resize(unsigned(gray), 32));
          when 3 => rdata_r <= x"0000000" & "000" & auto_en;
          when 4 => rdata_r <= std_logic_vector(resize(unsigned(rate), 32));
          when 5 => rdata_r <= step_cnt;
          when others => rdata_r <= (others => '0');
        end case;
      end if;
    end if;
  end process p_read;

end architecture rtl;

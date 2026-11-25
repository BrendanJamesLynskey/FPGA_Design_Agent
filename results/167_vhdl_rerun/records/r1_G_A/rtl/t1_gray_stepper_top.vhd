-- t1_gray_stepper_top: board top for the 10-bit Gray-code stepper (Nexys A7-100T).
-- Port names are the master XDC's (CLK100MHZ, CPU_RESETN, BTNU, SW, LED, UART_TXD_IN,
-- UART_RXD_OUT), as ARCHITECTURE.md and architecture.yaml declare them; design.xdc maps the pins.
-- Single clock domain (CLK100MHZ).
-- Asynchronous inputs: CPU_RESETN (reset_sync), BTNU and SW(15) (sync2 each).
-- UART_TXD_IN is synchronised inside fpga_shell (uart_rx).
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity t1_gray_stepper_top is
  generic (
    CLKS_PER_BIT    : integer := 868;
    TIMEOUT_CYCLES  : integer := 1000000;
    DEBOUNCE_CYCLES : integer := 2000000;
    TICK_CYCLES     : integer := 100000;
    BUILD_STAMP     : std_logic_vector(31 downto 0) := x"00000000");
  port (
    CLK100MHZ    : in  std_logic;
    CPU_RESETN   : in  std_logic;
    BTNU         : in  std_logic;
    SW           : in  std_logic_vector(15 downto 0);
    LED          : out std_logic_vector(15 downto 0);
    UART_TXD_IN  : in  std_logic;
    UART_RXD_OUT : out std_logic);
end entity t1_gray_stepper_top;

architecture rtl of t1_gray_stepper_top is

  component fpga_shell is
    generic (
      CLKS_PER_BIT   : integer := 868;
      TIMEOUT_CYCLES : integer := 100000;
      DESIGN_ID      : std_logic_vector(31 downto 0) := x"00000000";
      BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000");
    port (
      clk       : in  std_logic;
      rst       : in  std_logic;
      uart_rx   : in  std_logic;
      uart_tx   : out std_logic;
      win_addr  : out std_logic_vector(6 downto 0);
      win_wr    : out std_logic;
      win_rd    : out std_logic;
      win_wdata : out std_logic_vector(31 downto 0);
      win_rdata : in  std_logic_vector(31 downto 0));
  end component fpga_shell;

  component reset_sync is
    port (
      clk         : in  std_logic;
      rst_n_async : in  std_logic;
      rst         : out std_logic);
  end component reset_sync;

  component sync2 is
    generic (
      WIDTH : integer := 1);
    port (
      clk : in  std_logic;
      rst : in  std_logic;
      d   : in  std_logic_vector(WIDTH - 1 downto 0);
      q   : out std_logic_vector(WIDTH - 1 downto 0));
  end component sync2;

  component btn_debounce is
    generic (
      DEBOUNCE_CYCLES : integer := 2000000);
    port (
      clk   : in  std_logic;
      rst   : in  std_logic;
      btn   : in  std_logic;
      press : out std_logic);
  end component btn_debounce;

  component stepper_core is
    generic (
      TICK_CYCLES : integer := 100000);
    port (
      clk        : in  std_logic;
      rst        : in  std_logic;
      btn_step   : in  std_logic;
      dir_down   : in  std_logic;
      cnt_we     : in  std_logic;
      cnt_wdata  : in  std_logic_vector(9 downto 0);
      ctrl_we    : in  std_logic;
      ctrl_auto  : in  std_logic;
      rate_we    : in  std_logic;
      rate_wdata : in  std_logic_vector(15 downto 0);
      bin        : out std_logic_vector(9 downto 0);
      step_cnt   : out std_logic_vector(31 downto 0);
      auto_en    : out std_logic;
      rate       : out std_logic_vector(15 downto 0));
  end component stepper_core;

  component reg_window is
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
  end component reg_window;

  signal rst        : std_logic;
  signal btn_q      : std_logic_vector(0 downto 0);
  signal sw15_q     : std_logic_vector(0 downto 0);
  signal btn_press  : std_logic;
  signal dir_down   : std_logic;

  signal win_addr   : std_logic_vector(6 downto 0);
  signal win_wr     : std_logic;
  signal win_rd     : std_logic;
  signal win_wdata  : std_logic_vector(31 downto 0);
  signal win_rdata  : std_logic_vector(31 downto 0);

  signal bin        : std_logic_vector(9 downto 0);
  signal gray       : std_logic_vector(9 downto 0);
  signal step_cnt   : std_logic_vector(31 downto 0);
  signal auto_en    : std_logic;
  signal rate       : std_logic_vector(15 downto 0);

  signal cnt_we     : std_logic;
  signal cnt_wdata  : std_logic_vector(9 downto 0);
  signal ctrl_we    : std_logic;
  signal ctrl_auto  : std_logic;
  signal rate_we    : std_logic;
  signal rate_wdata : std_logic_vector(15 downto 0);

begin

  -- Reset: CPU_RESETN (active low, async assert, sync release) -> rst (active high).
  u_rst : reset_sync
    port map (
      clk         => CLK100MHZ,
      rst_n_async => CPU_RESETN,
      rst         => rst);

  -- Asynchronous button and switch: two-flop synchronisers. They are not reset:
  -- a reset would hold them and add latency to the button path after release.
  u_sync_btn : sync2
    generic map (WIDTH => 1)
    port map (
      clk => CLK100MHZ,
      rst => '0',
      d   => (0 => BTNU),
      q   => btn_q);

  u_sync_sw15 : sync2
    generic map (WIDTH => 1)
    port map (
      clk => CLK100MHZ,
      rst => '0',
      d   => (0 => SW(15)),
      q   => sw15_q);

  dir_down <= sw15_q(0);

  u_debounce : btn_debounce
    generic map (DEBOUNCE_CYCLES => DEBOUNCE_CYCLES)
    port map (
      clk   => CLK100MHZ,
      rst   => rst,
      btn   => btn_q(0),
      press => btn_press);

  u_core : stepper_core
    generic map (TICK_CYCLES => TICK_CYCLES)
    port map (
      clk        => CLK100MHZ,
      rst        => rst,
      btn_step   => btn_press,
      dir_down   => dir_down,
      cnt_we     => cnt_we,
      cnt_wdata  => cnt_wdata,
      ctrl_we    => ctrl_we,
      ctrl_auto  => ctrl_auto,
      rate_we    => rate_we,
      rate_wdata => rate_wdata,
      bin        => bin,
      step_cnt   => step_cnt,
      auto_en    => auto_en,
      rate       => rate);

  -- Gray code of the count: one bit changes per applied step.
  gray <= bin xor ('0' & bin(9 downto 1));

  u_shell : fpga_shell
    generic map (
      CLKS_PER_BIT   => CLKS_PER_BIT,
      TIMEOUT_CYCLES => TIMEOUT_CYCLES,
      DESIGN_ID      => x"47524159",
      BUILD_STAMP    => BUILD_STAMP)
    port map (
      clk       => CLK100MHZ,
      rst       => rst,
      uart_rx   => UART_TXD_IN,
      uart_tx   => UART_RXD_OUT,
      win_addr  => win_addr,
      win_wr    => win_wr,
      win_rd    => win_rd,
      win_wdata => win_wdata,
      win_rdata => win_rdata);

  u_window : reg_window
    port map (
      clk        => CLK100MHZ,
      win_addr   => win_addr,
      win_wr     => win_wr,
      win_rd     => win_rd,
      win_wdata  => win_wdata,
      win_rdata  => win_rdata,
      bin        => bin,
      gray       => gray,
      step_cnt   => step_cnt,
      auto_en    => auto_en,
      rate       => rate,
      cnt_we     => cnt_we,
      cnt_wdata  => cnt_wdata,
      ctrl_we    => ctrl_we,
      ctrl_auto  => ctrl_auto,
      rate_we    => rate_we,
      rate_wdata => rate_wdata);

  -- LEDs: LED(9 downto 0) Gray count, LED(14 downto 10) zero, LED(15) auto mode.
  LED <= auto_en & "00000" & gray;

end architecture rtl;

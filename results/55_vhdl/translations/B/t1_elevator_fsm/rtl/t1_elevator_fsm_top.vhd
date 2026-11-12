library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity t1_elevator_fsm_top is
  generic (
    CLKS_PER_BIT   : integer := 868;
    TIMEOUT_CYCLES : integer := 100_000;
    FLOOR_CYCLES   : integer := 150_000_000;
    DOOR_CYCLES    : integer := 200_000_000;
    BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000"
  );
  port (
    CLK100MHZ  : in  std_logic;
    CPU_RESETN : in  std_logic;
    SW         : in  std_logic_vector(15 downto 0);
    LED        : out std_logic_vector(15 downto 0);
    UART_TXD_IN : in  std_logic;
    UART_RXD_OUT : out std_logic
  );
end entity t1_elevator_fsm_top;

architecture rtl of t1_elevator_fsm_top is
  component reset_sync is
    port (
      clk           : in  std_logic;
      rst_n_async   : in  std_logic;
      rst           : out std_logic
    );
  end component;

  component fpga_shell is
    generic (
      CLKS_PER_BIT   : integer := 868;
      TIMEOUT_CYCLES : integer := 100000;
      DESIGN_ID      : std_logic_vector(31 downto 0) := x"00000000";
      BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000"
    );
    port (
      clk       : in  std_logic;
      rst       : in  std_logic;
      uart_rx   : in  std_logic;
      uart_tx   : out std_logic;
      win_addr  : out std_logic_vector(6 downto 0);
      win_wr    : out std_logic;
      win_rd    : out std_logic;
      win_wdata : out std_logic_vector(31 downto 0);
      win_rdata : in  std_logic_vector(31 downto 0)
    );
  end component;

  signal clk       : std_logic := '0';
  signal rst       : std_logic := '0';
  signal win_wr    : std_logic;
  signal win_rd    : std_logic;
  signal win_addr  : std_logic_vector(6 downto 0);
  signal win_wdata : std_logic_vector(31 downto 0);
  signal win_rdata : std_logic_vector(31 downto 0);
begin
  clk <= CLK100MHZ;

  u_rst : reset_sync
    port map (
      clk         => clk,
      rst_n_async => CPU_RESETN,
      rst         => rst
    );

  u_shell : fpga_shell
    generic map (
      CLKS_PER_BIT   => CLKS_PER_BIT,
      TIMEOUT_CYCLES => TIMEOUT_CYCLES,
      DESIGN_ID      => x"454C4556",
      BUILD_STAMP    => BUILD_STAMP
    )
    port map (
      clk       => clk,
      rst       => rst,
      uart_rx   => UART_TXD_IN,
      uart_tx   => UART_RXD_OUT,
      win_addr  => win_addr,
      win_wr    => win_wr,
      win_rd    => win_rd,
      win_wdata => win_wdata,
      win_rdata => win_rdata
    );

  u_lift : entity work.elevator_fsm
    generic map (
      FLOOR_CYCLES => FLOOR_CYCLES,
      DOOR_CYCLES  => DOOR_CYCLES
    )
    port map (
      clk       => clk,
      rst       => rst,
      sw_async  => SW(3 downto 0),
      led       => LED,
      win_addr  => win_addr,
      win_wr    => win_wr,
      win_rd    => win_rd,
      win_wdata => win_wdata,
      win_rdata => win_rdata
    );
end architecture rtl;

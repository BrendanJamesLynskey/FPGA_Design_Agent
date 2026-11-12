library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity d24_registered_outputs_top is
  generic (
    CLKS_PER_BIT   : integer := 868;
    TIMEOUT_CYCLES : integer := 100000;
    BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000"
  );
  port (
    CLK100MHZ  : in  std_logic;
    CPU_RESETN : in  std_logic;
    JA1        : in  std_logic;
    JA2        : in  std_logic;
    JA3        : in  std_logic;
    JA4        : in  std_logic;
    JA7        : in  std_logic;
    JB1        : out std_logic;
    JB2        : out std_logic;
    JB3        : out std_logic;
    JB4        : out std_logic;
    JB7        : out std_logic;
    JB8        : out std_logic;
    JB9        : out std_logic;
    JB10       : out std_logic;
    UART_TXD_IN : in  std_logic;
    UART_RXD_OUT : out std_logic
  );
end entity d24_registered_outputs_top;

architecture rtl of d24_registered_outputs_top is
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

  signal rst       : std_logic;
  signal win_wr    : std_logic;
  signal win_rd    : std_logic;
  signal win_addr  : std_logic_vector(6 downto 0);
  signal win_wdata : std_logic_vector(31 downto 0);
  signal win_rdata : std_logic_vector(31 downto 0);

  signal core_req       : std_logic;
  signal core_addr_v    : std_logic;
  signal core_valid     : std_logic;
  signal core_last      : std_logic;
  signal core_rsp_valid : std_logic;
  signal core_rsp_err   : std_logic;
  signal core_cmd_ready : std_logic;
  signal core_cmd_ack   : std_logic;
begin
  u_rst : entity work.reset_sync
    port map (
      clk         => CLK100MHZ,
      rst_n_async => CPU_RESETN,
      rst         => rst
    );

  u_shell : fpga_shell
    generic map (
      CLKS_PER_BIT   => CLKS_PER_BIT,
      TIMEOUT_CYCLES => TIMEOUT_CYCLES,
      DESIGN_ID      => x"52474F55",
      BUILD_STAMP    => BUILD_STAMP
    )
    port map (
      clk       => CLK100MHZ,
      rst       => rst,
      uart_rx   => UART_TXD_IN,
      uart_tx   => UART_RXD_OUT,
      win_addr  => win_addr,
      win_wr    => win_wr,
      win_rd    => win_rd,
      win_wdata => win_wdata,
      win_rdata => win_rdata
    );

  u_core : entity work.burst_ctl
    port map (
      clk         => CLK100MHZ,
      rst         => rst,
      cmd_valid   => JA1,
      gnt         => JA2,
      ack         => JA3,
      nack        => JA4,
      rsp_ready   => JA7,
      o_req       => core_req,
      o_addr_v    => core_addr_v,
      o_valid     => core_valid,
      o_last      => core_last,
      o_rsp_valid => core_rsp_valid,
      o_rsp_err   => core_rsp_err,
      o_cmd_ready => core_cmd_ready,
      o_cmd_ack   => core_cmd_ack,
      win_addr    => win_addr,
      win_wr      => win_wr,
      win_rd      => win_rd,
      win_wdata   => win_wdata,
      win_rdata   => win_rdata
    );

  JB1  <= core_req;
  JB2  <= core_addr_v;
  JB3  <= core_valid;
  JB4  <= core_last;
  JB7  <= core_rsp_valid;
  JB8  <= core_rsp_err;
  JB9  <= core_cmd_ready;
  JB10 <= core_cmd_ack;
end architecture rtl;

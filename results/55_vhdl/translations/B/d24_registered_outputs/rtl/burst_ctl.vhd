library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity burst_ctl is
  port (
    clk          : in  std_logic;
    rst          : in  std_logic;
    cmd_valid    : in  std_logic;
    gnt          : in  std_logic;
    ack          : in  std_logic;
    nack         : in  std_logic;
    rsp_ready    : in  std_logic;
    o_req        : out std_logic;
    o_addr_v     : out std_logic;
    o_valid      : out std_logic;
    o_last       : out std_logic;
    o_rsp_valid  : out std_logic;
    o_rsp_err    : out std_logic;
    o_cmd_ready  : out std_logic;
    o_cmd_ack    : out std_logic;
    win_addr     : in  std_logic_vector(6 downto 0);
    win_wr       : in  std_logic;
    win_rd       : in  std_logic;
    win_wdata    : in  std_logic_vector(31 downto 0);
    win_rdata    : out std_logic_vector(31 downto 0)
  );
end entity burst_ctl;

architecture rtl of burst_ctl is
  type state_t is (IDLE, LOAD, REQ, ADDR, DATA, TURN, WACK, RETRY, RESP, ERR, COOL);

  signal st       : state_t := IDLE;
  signal nx       : state_t := IDLE;
  signal cnt      : unsigned(3 downto 0) := (others => '0');
  signal bursts   : unsigned(15 downto 0) := (others => '0');
  signal errs     : unsigned(15 downto 0) := (others => '0');
  signal win_data : std_logic_vector(31 downto 0) := (others => '0');

  signal zero     : std_logic;
  signal clear    : std_logic;
begin
  zero  <= '1' when cnt = to_unsigned(0, cnt'length) else '0';
  clear <= '1' when win_wr = '1' and win_addr = "0000010" else '0';

  win_rdata <= win_data;

  process (all)
  begin
    nx <= st;

    case st is
      when IDLE =>
        if cmd_valid = '1' then
          nx <= LOAD;
        end if;

      when LOAD =>
        nx <= REQ;

      when REQ =>
        if gnt = '1' then
          nx <= ADDR;
        end if;

      when ADDR =>
        nx <= DATA;

      when DATA =>
        if zero = '1' then
          nx <= TURN;
        end if;

      when TURN =>
        nx <= WACK;

      when WACK =>
        if ack = '1' then
          nx <= RESP;
        elsif nack = '1' then
          nx <= RETRY;
        elsif zero = '1' then
          nx <= ERR;
        end if;

      when RETRY =>
        nx <= REQ;

      when RESP =>
        if rsp_ready = '1' then
          nx <= COOL;
        end if;

      when ERR =>
        if rsp_ready = '1' then
          nx <= COOL;
        end if;

      when COOL =>
        if zero = '1' then
          nx <= IDLE;
        end if;

      when others =>
        nx <= IDLE;
    end case;
  end process;

  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        st  <= IDLE;
        cnt <= (others => '0');
      else
        st <= nx;

        if st = ADDR then
          cnt <= to_unsigned(3, cnt'length);
        elsif st = TURN then
          cnt <= to_unsigned(7, cnt'length);
        elsif (st = RESP or st = ERR) and rsp_ready = '1' then
          cnt <= to_unsigned(2, cnt'length);
        elsif st = DATA or st = WACK or st = COOL then
          cnt <= cnt - to_unsigned(1, cnt'length);
        end if;
      end if;
    end if;
  end process;

  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' or clear = '1' then
        bursts <= (others => '0');
        errs   <= (others => '0');
      else
        if st = RESP and rsp_ready = '1' then
          bursts <= bursts + to_unsigned(1, bursts'length);
        end if;

        if st = ERR and rsp_ready = '1' then
          errs <= errs + to_unsigned(1, errs'length);
        end if;
      end if;
    end if;
  end process;

  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        win_data <= (others => '0');
      elsif win_rd = '1' then
        case win_addr is
          when "0000000" =>
            win_data <= std_logic_vector(resize(bursts, win_data'length));
          when "0000001" =>
            win_data <= std_logic_vector(resize(errs, win_data'length));
          when others =>
            win_data <= (others => '0');
        end case;
      end if;
    end if;
  end process;

  -- Registered output decode: each bus output is driven directly by its
  -- output register, using the state and counter values before this clock edge.
  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        o_req       <= '0';
        o_addr_v    <= '0';
        o_valid     <= '0';
        o_last      <= '0';
        o_rsp_valid <= '0';
        o_rsp_err   <= '0';
        o_cmd_ready <= '1';
        o_cmd_ack   <= '0';
      else
        if st = REQ or st = ADDR or st = DATA then
          o_req <= '1';
        else
          o_req <= '0';
        end if;

        if st = ADDR then
          o_addr_v <= '1';
        else
          o_addr_v <= '0';
        end if;

        if st = DATA then
          o_valid <= '1';
        else
          o_valid <= '0';
        end if;

        if st = DATA and zero = '1' then
          o_last <= '1';
        else
          o_last <= '0';
        end if;

        if st = RESP or st = ERR then
          o_rsp_valid <= '1';
        else
          o_rsp_valid <= '0';
        end if;

        if st = ERR then
          o_rsp_err <= '1';
        else
          o_rsp_err <= '0';
        end if;

        if st = IDLE then
          o_cmd_ready <= '1';
        else
          o_cmd_ready <= '0';
        end if;

        if st = LOAD then
          o_cmd_ack <= '1';
        else
          o_cmd_ack <= '0';
        end if;
      end if;
    end if;
  end process;
end architecture rtl;

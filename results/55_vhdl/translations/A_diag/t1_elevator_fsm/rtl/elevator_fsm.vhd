library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity elevator_fsm is
  generic (
    FLOOR_CYCLES : integer := 150_000_000;
    DOOR_CYCLES  : integer := 200_000_000
  );
  port (
    clk       : in  std_logic;
    rst       : in  std_logic;
    sw_async  : in  std_logic_vector(3 downto 0);
    led       : out std_logic_vector(15 downto 0);
    win_addr  : in  std_logic_vector(6 downto 0);
    win_wr    : in  std_logic;
    win_rd    : in  std_logic;
    win_wdata : in  std_logic_vector(31 downto 0);
    win_rdata : out std_logic_vector(31 downto 0)
  );
end entity elevator_fsm;

architecture rtl of elevator_fsm is
  constant R_FLOOR : std_logic_vector(6 downto 0) := "0000000";
  constant R_DIR   : std_logic_vector(6 downto 0) := "0000001";
  constant R_PEND  : std_logic_vector(6 downto 0) := "0000010";
  constant R_STATE : std_logic_vector(6 downto 0) := "0000011";
  constant R_MOVES : std_logic_vector(6 downto 0) := "0000100";

  constant IDLE   : unsigned(1 downto 0) := "00";
  constant MOVING : unsigned(1 downto 0) := "01";
  constant DOOR   : unsigned(1 downto 0) := "10";

  constant FLOOR_LIMIT : unsigned(31 downto 0) :=
    unsigned(to_signed(FLOOR_CYCLES - 1, 32));
  constant DOOR_LIMIT : unsigned(31 downto 0) :=
    unsigned(to_signed(DOOR_CYCLES - 1, 32));

  signal sw       : std_logic_vector(3 downto 0);
  signal sw_q     : std_logic_vector(3 downto 0);
  signal pend     : std_logic_vector(3 downto 0);
  signal calls    : std_logic_vector(3 downto 0);
  signal p1       : std_logic_vector(3 downto 0);
  signal above    : std_logic_vector(3 downto 0);
  signal below    : std_logic_vector(3 downto 0);
  signal state    : unsigned(1 downto 0);
  signal floor    : unsigned(1 downto 0);
  signal nf       : unsigned(1 downto 0);
  signal dir      : std_logic;
  signal moves    : unsigned(15 downto 0);
  signal timer    : unsigned(31 downto 0);
  signal ahead_up : std_logic;
  signal ahead_dn : std_logic;
begin
  u_sw : entity work.sync2_vh
    generic map (
      WIDTH => 4
    )
    port map (
      clk => clk,
      rst => rst,
      d   => sw_async,
      q   => sw
    );

  process (all)
    variable calls_v : std_logic_vector(3 downto 0);
    variable floor_i : integer;
  begin
    calls_v := (sw and not sw_q);
    if win_wr = '1' and win_addr = R_PEND then
      calls_v := calls_v or win_wdata(3 downto 0);
    end if;

    if state = DOOR then
      calls_v(to_integer(floor)) := '0';
    end if;

    calls <= calls_v;
    p1    <= pend or calls_v;

    floor_i := to_integer(floor);
    for k in 0 to 3 loop
      if k > floor_i then
        above(k) <= '1';
      else
        above(k) <= '0';
      end if;

      if k < floor_i then
        below(k) <= '1';
      else
        below(k) <= '0';
      end if;
    end loop;
  end process;

  ahead_up <= '1' when (p1 and above) /= "0000" else '0';
  ahead_dn <= '1' when (p1 and below) /= "0000" else '0';

  nf <= floor - 1 when dir = '1' else floor + 1;

  process (clk)
    variable pend_v : std_logic_vector(3 downto 0);
  begin
    if rising_edge(clk) then
      if rst = '1' then
        sw_q  <= (others => '0');
        pend  <= (others => '0');
        state <= IDLE;
        floor <= (others => '0');
        dir   <= '0';
        moves <= (others => '0');
        timer <= (others => '0');
      else
        sw_q  <= sw;
        pend_v := p1;
        pend  <= pend_v;
        timer <= timer + 1;

        if state = MOVING and timer = FLOOR_LIMIT then
          floor <= nf;
          moves <= moves + 1;
          timer <= (others => '0');

          if p1(to_integer(nf)) = '1' then
            pend_v(to_integer(nf)) := '0';
            pend  <= pend_v;
            state <= DOOR;
          end if;
        elsif state = IDLE or
              (state = DOOR and timer = DOOR_LIMIT) then
          timer <= (others => '0');

          if p1(to_integer(floor)) = '1' then
            pend_v(to_integer(floor)) := '0';
            pend  <= pend_v;
            state <= DOOR;
          elsif (dir = '1' and ahead_dn = '1') or
                (dir = '0' and ahead_up = '1') then
            state <= MOVING;
          elsif (dir = '1' and ahead_up = '1') or
                (dir = '0' and ahead_dn = '1') then
            dir   <= not dir;
            state <= MOVING;
          else
            state <= IDLE;
          end if;
        end if;
      end if;
    end if;
  end process;

  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        led <= (others => '0');
      else
        if state = DOOR then
          led(15) <= '1';
        else
          led(15) <= '0';
        end if;

        if state = MOVING then
          led(14) <= '1';
        else
          led(14) <= '0';
        end if;

        led(13 downto 8) <= (others => '0');
        led(7 downto 4)  <= pend;
        led(3 downto 0)  <= std_logic_vector(
          shift_left(to_unsigned(1, 4), to_integer(floor))
        );
      end if;
    end if;
  end process;

  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        win_rdata <= (others => '0');
      elsif win_rd = '1' then
        case win_addr is
          when R_FLOOR =>
            win_rdata <= std_logic_vector(resize(floor, 32));
          when R_DIR =>
            win_rdata <= (31 downto 1 => '0') & dir;
          when R_PEND =>
            win_rdata <= (31 downto 4 => '0') & pend;
          when R_STATE =>
            win_rdata <= (31 downto 2 => '0') & std_logic_vector(state);
          when R_MOVES =>
            win_rdata <= (31 downto 16 => '0') & std_logic_vector(moves);
          when others =>
            win_rdata <= (others => '0');
        end case;
      end if;
    end if;
  end process;
end architecture rtl;

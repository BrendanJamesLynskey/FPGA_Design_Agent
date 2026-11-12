library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity gray_stepper is
    generic (
        DEBOUNCE_CYCLES : integer := 1_000_000;
        TICK_CYCLES     : integer := 100_000
    );
    port (
        clk       : in  std_logic;
        rst       : in  std_logic;
        btn       : in  std_logic;
        dir_async : in  std_logic;
        led       : out std_logic_vector(15 downto 0);
        win_addr  : in  std_logic_vector(6 downto 0);
        win_wr    : in  std_logic;
        win_rd    : in  std_logic;
        win_wdata : in  std_logic_vector(31 downto 0);
        win_rdata : out std_logic_vector(31 downto 0)
    );
end entity gray_stepper;

architecture rtl of gray_stepper is
    function clog2(n : positive) return positive is
        variable value  : natural := n - 1;
        variable result : natural := 0;
    begin
        while value > 0 loop
            value  := value / 2;
            result := result + 1;
        end loop;
        if result = 0 then
            return 1;
        else
            return result;
        end if;
    end function;

    constant PW : positive := clog2(TICK_CYCLES + 1);

    constant R_GRAY  : std_logic_vector(6 downto 0) := "0000000";
    constant R_BIN   : std_logic_vector(6 downto 0) := "0000001";
    constant R_CTRL  : std_logic_vector(6 downto 0) := "0000010";
    constant R_RATE  : std_logic_vector(6 downto 0) := "0000011";
    constant R_STEPS : std_logic_vector(6 downto 0) := "0000100";

    signal lvl       : std_logic;
    signal press     : std_logic;
    signal dir       : std_logic;
    signal auto_on   : std_logic;
    signal run       : std_logic;
    signal astep     : std_logic;
    signal step      : std_logic;

    signal bin       : unsigned(9 downto 0);
    signal gray      : unsigned(9 downto 0);
    signal bin_nx    : unsigned(9 downto 0);

    signal rate      : unsigned(15 downto 0);
    signal tk        : unsigned(15 downto 0);
    signal steps     : unsigned(15 downto 0);
    signal pre       : unsigned(PW - 1 downto 0);

    signal wr_bin    : std_logic;
    signal wr_ctrl   : std_logic;
    signal wr_rate   : std_logic;
begin
    u_db : entity work.bm_debounce
        generic map (
            CYCLES => DEBOUNCE_CYCLES
        )
        port map (
            clk     => clk,
            rst     => rst,
            d_async => btn,
            level   => lvl,
            rise    => press
        );

    u_dir : entity work.sync2_vh
        port map (
            clk => clk,
            rst => rst,
            d   => dir_async,
            q   => dir
        );

    wr_bin  <= '1' when win_wr = '1' and win_addr = R_BIN  else '0';
    wr_ctrl <= '1' when win_wr = '1' and win_addr = R_CTRL else '0';
    wr_rate <= '1' when win_wr = '1' and win_addr = R_RATE else '0';

    run <= '1' when auto_on = '1' and rate /= to_unsigned(0, 16) else '0';

    astep <= '1'
        when run = '1'
         and wr_ctrl = '0'
         and wr_rate = '0'
         and pre = to_unsigned(TICK_CYCLES - 1, PW)
         and tk = rate - to_unsigned(1, 16)
        else '0';

    step <= press or astep;

    bin_nx <= bin - to_unsigned(1, 10) when dir = '1'
              else bin + to_unsigned(1, 10);

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                pre     <= (others => '0');
                tk      <= (others => '0');
                auto_on <= '0';
                rate    <= to_unsigned(250, 16);
            else
                if wr_ctrl = '1' then
                    auto_on <= win_wdata(0);
                end if;

                if wr_rate = '1' then
                    rate <= unsigned(win_wdata(15 downto 0));
                end if;

                if wr_ctrl = '1' or wr_rate = '1' or run = '0' then
                    pre <= (others => '0');
                    tk  <= (others => '0');
                elsif pre = to_unsigned(TICK_CYCLES - 1, PW) then
                    pre <= (others => '0');
                    if tk = rate - to_unsigned(1, 16) then
                        tk <= (others => '0');
                    else
                        tk <= tk + 1;
                    end if;
                else
                    pre <= pre + 1;
                end if;
            end if;
        end if;
    end process;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                bin   <= (others => '0');
                gray  <= (others => '0');
                steps <= (others => '0');
            elsif wr_bin = '1' then
                bin  <= unsigned(win_wdata(9 downto 0));
                gray <= unsigned(win_wdata(9 downto 0))
                        xor shift_right(unsigned(win_wdata(9 downto 0)), 1);
            elsif step = '1' then
                bin   <= bin_nx;
                gray  <= bin_nx xor shift_right(bin_nx, 1);
                steps <= steps + 1;
            end if;
        end if;
    end process;

    led <= auto_on & "00000" & std_logic_vector(gray);

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                win_rdata <= (others => '0');
            elsif win_rd = '1' then
                case win_addr is
                    when R_GRAY =>
                        win_rdata <= std_logic_vector(resize(gray, 32));
                    when R_BIN =>
                        win_rdata <= std_logic_vector(resize(bin, 32));
                    when R_CTRL =>
                        win_rdata <= (31 downto 9 => '0') & dir & "0000000" & auto_on;
                    when R_RATE =>
                        win_rdata <= std_logic_vector(resize(rate, 32));
                    when R_STEPS =>
                        win_rdata <= std_logic_vector(resize(steps, 32));
                    when others =>
                        win_rdata <= (others => '0');
                end case;
            end if;
        end if;
    end process;
end architecture rtl;

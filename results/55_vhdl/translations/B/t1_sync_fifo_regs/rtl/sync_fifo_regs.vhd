library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sync_fifo_regs is
    port (
        clk       : in  std_logic;
        rst       : in  std_logic;
        led       : out std_logic_vector(15 downto 0);
        win_addr  : in  std_logic_vector(6 downto 0);
        win_wr    : in  std_logic;
        win_rd    : in  std_logic;
        win_wdata : in  std_logic_vector(31 downto 0);
        win_rdata : out std_logic_vector(31 downto 0)
    );
end entity sync_fifo_regs;

architecture rtl of sync_fifo_regs is
    constant R_PUSH  : std_logic_vector(6 downto 0) := "0000000";
    constant R_POP   : std_logic_vector(6 downto 0) := "0000001";
    constant R_HEAD  : std_logic_vector(6 downto 0) := "0000010";
    constant R_LEVEL : std_logic_vector(6 downto 0) := "0000011";
    constant R_FLAGS : std_logic_vector(6 downto 0) := "0000100";
    constant R_AF    : std_logic_vector(6 downto 0) := "0000101";

    constant LEVEL_FULL : unsigned(4 downto 0) := to_unsigned(16, 5);
    constant ZERO22     : std_logic_vector(21 downto 0) := (others => '0');
    constant ZERO27     : std_logic_vector(26 downto 0) := (others => '0');

    type memory_t is array (0 to 15) of std_logic_vector(7 downto 0);
    signal mem : memory_t;

    signal wp       : unsigned(3 downto 0) := (others => '0');
    signal rp       : unsigned(3 downto 0) := (others => '0');
    signal level    : unsigned(4 downto 0) := (others => '0');
    signal af_th    : unsigned(4 downto 0) := to_unsigned(12, 5);
    signal ovf      : std_logic := '0';
    signal unf      : std_logic := '0';
    signal led_reg  : std_logic_vector(15 downto 0) := (others => '0');
    signal rdata_reg : std_logic_vector(31 downto 0) := (others => '0');

    signal empty_i : std_logic;
    signal full_i  : std_logic;
    signal afull_i : std_logic;
    signal push_i  : std_logic;
    signal pop_i   : std_logic;
    signal head_i  : std_logic_vector(7 downto 0);
begin
    led <= led_reg;
    win_rdata <= rdata_reg;

    empty_i <= '1' when level = to_unsigned(0, level'length) else '0';
    full_i  <= '1' when level = LEVEL_FULL else '0';
    afull_i <= '1' when level >= af_th else '0';

    push_i <= '1' when win_wr = '1' and win_addr = R_PUSH else '0';
    pop_i  <= '1' when win_rd = '1' and win_addr = R_POP else '0';

    head_i <= (others => '0') when empty_i = '1' else mem(to_integer(rp));

    -- The memory write is independent of reset, as in the source design.
    process (clk)
    begin
        if rising_edge(clk) then
            if push_i = '1' and full_i = '0' then
                mem(to_integer(wp)) <= win_wdata(7 downto 0);
            end if;
        end if;
    end process;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                wp    <= (others => '0');
                rp    <= (others => '0');
                level <= (others => '0');
                ovf   <= '0';
                unf   <= '0';
                af_th <= to_unsigned(12, af_th'length);
            else
                if push_i = '1' then
                    if full_i = '1' then
                        ovf <= '1';
                    else
                        wp    <= wp + 1;
                        level <= level + 1;
                    end if;
                end if;

                if pop_i = '1' then
                    if empty_i = '1' then
                        unf <= '1';
                    else
                        rp    <= rp + 1;
                        level <= level - 1;
                    end if;
                end if;

                if win_wr = '1' and win_addr = R_FLAGS then
                    if win_wdata(8) = '1' then
                        ovf <= '0';
                    end if;
                    if win_wdata(9) = '1' then
                        unf <= '0';
                    end if;
                end if;

                if win_wr = '1' and win_addr = R_AF then
                    af_th <= unsigned(win_wdata(4 downto 0));
                end if;
            end if;
        end if;
    end process;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                led_reg <= (others => '0');
            else
                for k in 0 to 15 loop
                    if to_unsigned(k, level'length) < level then
                        led_reg(k) <= '1';
                    else
                        led_reg(k) <= '0';
                    end if;
                end loop;
            end if;
        end if;
    end process;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                rdata_reg <= (others => '0');
            elsif win_rd = '1' then
                case win_addr is
                    when R_POP =>
                        rdata_reg <= x"000000" & head_i;
                    when R_HEAD =>
                        rdata_reg <= x"000000" & head_i;
                    when R_LEVEL =>
                        rdata_reg <= ZERO27 & std_logic_vector(level);
                    when R_FLAGS =>
                        rdata_reg <= ZERO22 & unf & ovf & "00000" & afull_i & full_i & empty_i;
                    when R_AF =>
                        rdata_reg <= ZERO27 & std_logic_vector(af_th);
                    when others =>
                        rdata_reg <= (others => '0');
                end case;
            end if;
        end if;
    end process;
end architecture rtl;

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

    type mem_array_t is array (0 to 15) of std_logic_vector(7 downto 0);
    signal mem : mem_array_t;

    signal wp     : unsigned(3 downto 0);
    signal rp     : unsigned(3 downto 0);
    signal level  : unsigned(4 downto 0);
    signal af_th  : unsigned(4 downto 0);
    signal ovf    : std_logic;
    signal unf    : std_logic;
    signal head   : std_logic_vector(7 downto 0);

    signal empty  : std_logic;
    signal full   : std_logic;
    signal afull  : std_logic;
    signal push   : std_logic;
    signal pop    : std_logic;
begin
    empty <= '1' when level = to_unsigned(0, level'length) else '0';
    full  <= '1' when level = to_unsigned(16, level'length) else '0';
    afull <= '1' when level >= af_th else '0';

    push <= '1' when win_wr = '1' and win_addr = R_PUSH else '0';
    pop  <= '1' when win_rd = '1' and win_addr = R_POP else '0';

    head <= (others => '0') when empty = '1' else mem(to_integer(rp));

    process (clk)
    begin
        if rising_edge(clk) then
            if push = '1' and full = '0' then
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
                if push = '1' then
                    if full = '1' then
                        ovf <= '1';
                    else
                        wp    <= wp + to_unsigned(1, wp'length);
                        level <= level + to_unsigned(1, level'length);
                    end if;
                end if;

                if pop = '1' then
                    if empty = '1' then
                        unf <= '1';
                    else
                        rp    <= rp + to_unsigned(1, rp'length);
                        level <= level - to_unsigned(1, level'length);
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
                led <= (others => '0');
            else
                for k in 0 to 15 loop
                    if to_unsigned(k, level'length) < level then
                        led(k) <= '1';
                    else
                        led(k) <= '0';
                    end if;
                end loop;
            end if;
        end if;
    end process;

    process (clk)
        variable read_value : std_logic_vector(31 downto 0);
    begin
        if rising_edge(clk) then
            if rst = '1' then
                win_rdata <= (others => '0');
            elsif win_rd = '1' then
                read_value := (others => '0');

                case win_addr is
                    when R_POP | R_HEAD =>
                        read_value(7 downto 0) := head;
                    when R_LEVEL =>
                        read_value(4 downto 0) := std_logic_vector(level);
                    when R_FLAGS =>
                        read_value(9) := unf;
                        read_value(8) := ovf;
                        read_value(2) := afull;
                        read_value(1) := full;
                        read_value(0) := empty;
                    when R_AF =>
                        read_value(4 downto 0) := std_logic_vector(af_th);
                    when others =>
                        null;
                end case;

                win_rdata <= read_value;
            end if;
        end if;
    end process;
end architecture rtl;

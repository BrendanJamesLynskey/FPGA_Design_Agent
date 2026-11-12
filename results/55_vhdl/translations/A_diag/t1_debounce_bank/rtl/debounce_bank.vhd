library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity debounce_bank is
    generic (
        DEBOUNCE_CYCLES : integer := 2_000_000
    );
    port (
        clk       : in  std_logic;
        rst       : in  std_logic;
        sw_async  : in  std_logic_vector(15 downto 0);
        led       : out std_logic_vector(15 downto 0);
        win_addr  : in  std_logic_vector(6 downto 0);
        win_wr    : in  std_logic;
        win_rd    : in  std_logic;
        win_wdata : in  std_logic_vector(31 downto 0);
        win_rdata : out std_logic_vector(31 downto 0)
    );
end entity debounce_bank;

architecture rtl of debounce_bank is
    type count_array_t is array (0 to 15) of unsigned(7 downto 0);

    signal lvl     : std_logic_vector(15 downto 0);
    signal lvl_d   : std_logic_vector(15 downto 0);
    signal rise    : std_logic_vector(15 downto 0);
    signal fall    : std_logic_vector(15 downto 0);
    signal edges   : std_logic_vector(15 downto 0);
    signal rise_en : std_logic_vector(15 downto 0);
    signal fall_en : std_logic_vector(15 downto 0);
    signal unused  : std_logic_vector(15 downto 0);
    signal cnt     : count_array_t;
begin
    g_db : for k in 0 to 15 generate
        u_db : entity work.bm_debounce
            generic map (
                CYCLES => DEBOUNCE_CYCLES
            )
            port map (
                clk     => clk,
                rst     => rst,
                d_async => sw_async(k),
                level   => lvl(k),
                rise    => unused(k)
            );
    end generate;

    rise <= lvl and not lvl_d;
    fall <= (not lvl) and lvl_d;
    led  <= lvl_d;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                lvl_d   <= (others => '0');
                edges   <= (others => '0');
                rise_en <= (others => '1');
                fall_en <= (others => '0');

                for k in 0 to 15 loop
                    cnt(k) <= (others => '0');
                end loop;
            else
                lvl_d <= lvl;

                if win_wr = '1' and win_addr = "0000001" then
                    edges <= (edges and not win_wdata(15 downto 0)) or
                             (rise and rise_en) or (fall and fall_en);
                else
                    edges <= edges or (rise and rise_en) or (fall and fall_en);
                end if;

                if win_wr = '1' and win_addr = "0000010" then
                    rise_en <= win_wdata(15 downto 0);
                end if;

                if win_wr = '1' and win_addr = "0000011" then
                    fall_en <= win_wdata(15 downto 0);
                end if;

                for k in 0 to 15 loop
                    if win_wr = '1' and
                       win_addr = std_logic_vector(to_unsigned(4 + k / 4, 7)) then
                        cnt(k) <= (others => '0');
                    elsif lvl(k) /= lvl_d(k) then
                        cnt(k) <= cnt(k) + 1;
                    end if;
                end loop;
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
                    when "0000000" =>
                        win_rdata <= x"0000" & lvl_d;
                    when "0000001" =>
                        win_rdata <= x"0000" & edges;
                    when "0000010" =>
                        win_rdata <= x"0000" & rise_en;
                    when "0000011" =>
                        win_rdata <= x"0000" & fall_en;
                    when "0000100" =>
                        win_rdata <= std_logic_vector(cnt(3)) &
                                     std_logic_vector(cnt(2)) &
                                     std_logic_vector(cnt(1)) &
                                     std_logic_vector(cnt(0));
                    when "0000101" =>
                        win_rdata <= std_logic_vector(cnt(7)) &
                                     std_logic_vector(cnt(6)) &
                                     std_logic_vector(cnt(5)) &
                                     std_logic_vector(cnt(4));
                    when "0000110" =>
                        win_rdata <= std_logic_vector(cnt(11)) &
                                     std_logic_vector(cnt(10)) &
                                     std_logic_vector(cnt(9)) &
                                     std_logic_vector(cnt(8));
                    when "0000111" =>
                        win_rdata <= std_logic_vector(cnt(15)) &
                                     std_logic_vector(cnt(14)) &
                                     std_logic_vector(cnt(13)) &
                                     std_logic_vector(cnt(12));
                    when others =>
                        win_rdata <= (others => '0');
                end case;
            end if;
        end if;
    end process;
end architecture rtl;

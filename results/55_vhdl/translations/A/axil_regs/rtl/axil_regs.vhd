library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity axil_regs is
  generic (
    AW : integer := 6
  );
  port (
    clk     : in  std_logic;
    rst_n   : in  std_logic;
    awaddr  : in  std_logic_vector(AW-1 downto 0);
    awvalid : in  std_logic;
    awready : out std_logic;
    wdata   : in  std_logic_vector(31 downto 0);
    wstrb   : in  std_logic_vector(3 downto 0);
    wvalid  : in  std_logic;
    wready  : out std_logic;
    bresp   : out std_logic_vector(1 downto 0);
    bvalid  : out std_logic;
    bready  : in  std_logic;
    araddr  : in  std_logic_vector(AW-1 downto 0);
    arvalid : in  std_logic;
    arready : out std_logic;
    rdata   : out std_logic_vector(31 downto 0);
    rresp   : out std_logic_vector(1 downto 0);
    rvalid  : out std_logic;
    rready  : in  std_logic
  );
end entity axil_regs;

architecture rtl of axil_regs is
  signal r0, r1, r2 : std_logic_vector(31 downto 0);
  signal r3         : std_logic_vector(31 downto 0);

  signal aw_got : std_logic;
  signal w_got  : std_logic;
  signal a_q    : std_logic_vector(AW-1 downto 0);
  signal d_q    : std_logic_vector(31 downto 0);
  signal s_q    : std_logic_vector(3 downto 0);

  signal aw_hs : std_logic;
  signal w_hs  : std_logic;
  signal ar_hs : std_logic;
  signal do_wr : std_logic;
begin
  r3 <= r0 xor r1 xor r2;

  awready <= not (aw_got or bvalid);
  wready  <= not (w_got or bvalid);
  arready <= not rvalid;

  aw_hs <= awvalid and awready;
  w_hs  <= wvalid and wready;
  ar_hs <= arvalid and arready;
  do_wr <= aw_got and w_got and not bvalid;

  process (clk)
  begin
    if rising_edge(clk) then
      if rst_n = '0' then
        r0     <= (others => '0');
        r1     <= (others => '0');
        r2     <= (others => '0');
        aw_got <= '0';
        w_got  <= '0';
        bvalid <= '0';
        bresp  <= (others => '0');
        rvalid <= '0';
        rdata  <= (others => '0');
        rresp  <= (others => '0');
      else
        if aw_hs = '1' then
          aw_got <= '1';
          a_q    <= awaddr;
        end if;

        if w_hs = '1' then
          w_got <= '1';
          d_q   <= wdata;
          s_q   <= wstrb;
        end if;

        if do_wr = '1' then
          aw_got <= '0';
          w_got  <= '0';
          bvalid <= '1';

          if unsigned(a_q(AW-1 downto 2)) <= to_unsigned(3, AW-2) then
            bresp <= "00";
          else
            bresp <= "10";
          end if;

          for i in 0 to 3 loop
            if s_q(i) = '1' then
              if unsigned(a_q(AW-1 downto 2)) = to_unsigned(0, AW-2) then
                r0(8*i+7 downto 8*i) <= d_q(8*i+7 downto 8*i);
              elsif unsigned(a_q(AW-1 downto 2)) = to_unsigned(1, AW-2) then
                r1(8*i+7 downto 8*i) <= d_q(8*i+7 downto 8*i);
              elsif unsigned(a_q(AW-1 downto 2)) = to_unsigned(2, AW-2) then
                r2(8*i+7 downto 8*i) <= d_q(8*i+7 downto 8*i);
              end if;
            end if;
          end loop;
        end if;

        if bvalid = '1' and bready = '1' then
          bvalid <= '0';
        end if;

        if ar_hs = '1' then
          rvalid <= '1';
          if unsigned(araddr(AW-1 downto 2)) = to_unsigned(0, AW-2) then
            rdata <= r0;
            rresp <= "00";
          elsif unsigned(araddr(AW-1 downto 2)) = to_unsigned(1, AW-2) then
            rdata <= r1;
            rresp <= "00";
          elsif unsigned(araddr(AW-1 downto 2)) = to_unsigned(2, AW-2) then
            rdata <= r2;
            rresp <= "00";
          elsif unsigned(araddr(AW-1 downto 2)) = to_unsigned(3, AW-2) then
            rdata <= r3;
            rresp <= "00";
          else
            rdata <= x"DEADBEEF";
            rresp <= "10";
          end if;
        elsif rvalid = '1' and rready = '1' then
          rvalid <= '0';
        end if;
      end if;
    end if;
  end process;
end architecture rtl;

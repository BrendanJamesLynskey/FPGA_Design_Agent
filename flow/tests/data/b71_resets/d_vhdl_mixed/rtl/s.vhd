entity reset_sync is port(clk,rst_n,d: in bit; q: out bit); end;
architecture a of reset_sync is begin
process(clk,rst_n) begin if rst_n='0' then q<='0'; elsif clk'event and clk='1' then q<=d; end if; end process; end;

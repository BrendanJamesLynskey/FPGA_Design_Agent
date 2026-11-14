always_ff @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
/* trailing
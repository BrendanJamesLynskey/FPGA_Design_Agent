// t1_bind.sv: attach the checkers to the unmodified RTL. Compile it with the RTL and the checkers.
bind dimmer_counter counter_checker u_chk_counter (
    .clk(clk), .rst(rst), .count(count), .duty(duty), .ctrl(ctrl), .duty_eff(duty_eff), .led(led),
    .p_up(p_up), .p_down(p_down), .p_clear(p_clear), .n_up(n_up), .n_down(n_down), .n_clear(n_clear),
    .win_wr(win_wr), .win_addr(win_addr), .win_wdata(win_wdata));
bind debounce debounce_checker #(.CYCLES(CYCLES)) u_chk_db (
    .clk(clk), .rst(rst), .btn(btn), .level(level), .press(press));
bind sevenseg_scan scan_checker u_chk_scan (
    .clk(clk), .rst(rst), .enable(enable), .blank(blank), .an(an));

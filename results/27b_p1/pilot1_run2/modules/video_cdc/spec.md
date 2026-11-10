Synchronize pattern selection from clk_sys into clk_pix. Transfer the
changing frame count from clk_pix into clk_sys using a CDC scheme suitable
for a multi-bit counter, such as Gray-code synchronization.

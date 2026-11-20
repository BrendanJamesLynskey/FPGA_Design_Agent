"""Register map of rtl/tcp_fast.sv (word addresses on the software bus) and the control-register bits."""
CTRL, DMAC_HI, DMAC_LO, SMAC_HI, SMAC_LO, SIP, DIP, PORTS, TTL_MSS, SND_NXT, SND_UNA, SND_WND, RCV_NXT, RCV_WND, IP_ID, STALE_LIMIT = range(16)
CNT_BASE = 16           # counters 16..29, in the order of tcpref.COUNTERS
CLR_CNT = 31            # any write clears every counter
CTRL_ARM, CTRL_VALID, CTRL_BUSY = 1, 2, 4        # read bits of CTRL; a write's bit 0 is the new arm request (1 also rebuilds the template)

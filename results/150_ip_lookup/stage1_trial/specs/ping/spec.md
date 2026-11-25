# Ping responder

I want the Nexys A7-100T to answer ping. Connect to the board's Ethernet PHY, give the board a fixed IPv4 address
(192.168.1.50) and MAC address, and reply to ICMP echo requests sent to it by other machines on the same network.
Light an LED each time a reply is sent. Reset with the CPU reset button. The design ID reads "PING".

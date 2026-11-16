#!/bin/bash
d=$(dirname "$0")
$d/run.sh ipv4_udp_rx 6 xc7 1
$d/run.sh ipv4_udp_tx 4 xc7 1

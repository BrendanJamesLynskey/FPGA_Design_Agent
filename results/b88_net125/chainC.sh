#!/bin/bash
d=$(dirname "$0")
$d/run.sh igmp_join 4 xc7 1
$d/run.sh arp_responder 3 xc7 1 1

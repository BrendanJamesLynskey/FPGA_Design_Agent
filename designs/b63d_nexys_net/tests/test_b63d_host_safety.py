"""The link phase's network-safety checks (host/board_run.py), with stand-in command outputs: no traffic, no root.
Each refusal case is the passing baseline with one thing changed."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("board_run", Path(__file__).resolve().parents[1] / "host" / "board_run.py")
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

LINK = ("ip", "-d", "-o", "link", "show", "dev", "enx1")
ADDR4 = ("ip", "-4", "-o", "addr", "show", "dev", "enx1")
ADDR6 = ("ip", "-6", "-o", "addr", "show", "dev", "enx1")
ROUTES = ("ip", "-4", "-o", "route", "show", "table", "all")
DEFAULTS = ("ip", "-4", "route", "show", "table", "all", "default")
NEIGH = ("ip", "-4", "neigh", "show", "dev", "enx1")
GOOD = {
    LINK: "5: enx1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP mode DEFAULT group default "
          "qlen 1000\\    link/ether 02:12:34:56:78:9a brd ff:ff:ff:ff:ff:ff promiscuity 0 minmtu 68 maxmtu 1500 "
          "addrgenmode eui64 numtxqueues 1 numrxqueues 1 parentbus usb parentdev 2-1:1.0\n",
    ADDR4: "5: enx1    inet 192.168.63.1/24 brd 192.168.63.255 scope global enx1\\       valid_lft forever\n",
    ADDR6: "5: enx1    inet6 fe80::12:34ff:fe56:789a/64 scope link \\       valid_lft forever\n",
    ROUTES: "default via 192.168.1.1 dev eno1 proto dhcp metric 100\n"
            "192.168.1.0/24 dev eno1 proto kernel scope link src 192.168.1.20\n"
            "192.168.63.0/24 dev enx1 proto kernel scope link src 192.168.63.1\n"
            "local 192.168.63.1 dev enx1 table local proto kernel scope host src 192.168.63.1\n"
            "broadcast 192.168.63.255 dev enx1 table local proto kernel scope link src 192.168.63.1\n",
    ("cat", "/proc/sys/net/ipv4/conf/enx1/forwarding"): "0\n",
    ("cat", "/proc/sys/net/ipv4/conf/enx1/proxy_arp"): "0\n",
    DEFAULTS: "default via 192.168.1.1 dev eno1 proto dhcp metric 100\n",
    ("ip", "-4", "route", "get", "192.168.1.1"): "192.168.1.1 dev eno1 src 192.168.1.20\n",
    ("ip", "-4", "route", "get", "192.168.63.2", "oif", "enx1"): "192.168.63.2 dev enx1 src 192.168.63.1\n",
    ("ip", "-4", "route", "get", "239.63.0.1", "oif", "enx1"): "multicast 239.63.0.1 dev enx1 src 192.168.63.1\n",
    ("ip", "-4", "route", "get", "192.168.63.2"): "192.168.63.2 dev enx1 src 192.168.63.1\n",
    NEIGH: "192.168.63.2 lladdr 02:00:00:00:00:63 REACHABLE\n",
}


def runner(over=None):
    t = {**GOOD, **(over or {})}
    return lambda *cmd: t.get(tuple(cmd), "")


def refused(over, iface="enx1"):
    return br.isolation_check(iface, runner(over))


def test_isolated_link_passes():
    assert refused({}) == []


@pytest.mark.parametrize("case,over,word", [
    # the interface itself
    ("vlan on the home NIC", {LINK: "6: enx1@eno1: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\\    link/ether "
                                    "02:12:34:56:78:9a vlan protocol 802.1Q id 63 <REORDER_HDR>\n"}, "stacked"),
    ("macvlan on the home NIC", {LINK: "7: enx1@eno1: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\\    link/ether "
                                       "02:12:34:56:78:9b macvlan mode bridge\n"}, "macvlan"),
    ("ipvlan", {LINK: "8: enx1@eno1: <BROADCAST,MULTICAST,UP> mtu 1500\\    ipvlan mode l2\n"}, "ipvlan"),
    ("bridge port", {LINK: "5: enx1: <BROADCAST,MULTICAST,UP> mtu 1500 master br0 state UP\\    bridge_slave "
                           "state forwarding\n"}, "enslaved"),
    ("bond member", {LINK: "5: enx1: <BROADCAST,MULTICAST,SLAVE,UP> mtu 1500 master bond0\\    bond_slave state "
                           "ACTIVE\n"}, "enslaved"),
    ("a bridge itself", {LINK: "9: enx1: <BROADCAST,MULTICAST,UP> mtu 1500\\    bridge forward_delay 1500\n"}, "bridge"),
    ("missing interface", {LINK: ""}, "does not exist"),
    # IPv4 addresses
    ("address outside the subnet", {ADDR4: GOOD[ADDR4] + "5: enx1 inet 10.0.0.5/8 scope global enx1\n"}, "10.0.0.5"),
    ("peer-form address", {ADDR4: GOOD[ADDR4] + "5: enx1 inet 10.1.1.1 peer 10.1.1.2/32 scope global enx1\n"},
     "plain a.b.c.d/n"),
    ("wider prefix", {ADDR4: "5: enx1 inet 192.168.63.1/16 scope global enx1\n"}, "only 192.168.63.1/24"),
    # IPv6
    ("global IPv6 address", {ADDR6: GOOD[ADDR6] + "5: enx1 inet6 2001:db8::5/64 scope global dynamic\n"}, "IPv6"),
    ("unique-local IPv6 address", {ADDR6: GOOD[ADDR6] + "5: enx1 inet6 fd12:3456::5/64 scope global\n"}, "IPv6"),
    # routes
    ("default route via the link", {DEFAULTS: GOOD[DEFAULTS] + "default via 192.168.63.254 dev enx1 table 100\n",
                                    ROUTES: GOOD[ROUTES] + "default via 192.168.63.254 dev enx1 table 100\n"}, "default route"),
    ("split default 0/1 + 128/1", {ROUTES: GOOD[ROUTES] + "0.0.0.0/1 via 192.168.63.254 dev enx1 table 7\n"
                                                          "128.0.0.0/1 via 192.168.63.254 dev enx1 table 7\n"}, "0.0.0.0/1"),
    ("another prefix", {ROUTES: GOOD[ROUTES] + "10.20.0.0/16 via 192.168.63.254 dev enx1\n"}, "10.20.0.0/16"),
    ("route to the home gateway", {("ip", "-4", "route", "get", "192.168.1.1"): "192.168.1.1 dev enx1 src 192.168.63.1\n"},
     "gateway"),
    ("board routed elsewhere", {("ip", "-4", "route", "get", "192.168.63.2"): "192.168.63.2 via 192.168.1.1 dev eno1\n"},
     "not enx1"),
    ("multipath split default", {ROUTES: GOOD[ROUTES] + "0.0.0.0/1 proto static \\\tnexthop via 192.168.63.254 dev enx1 "
                                 "weight 1 \\\tnexthop via 192.168.1.1 dev eno1 weight 1\n"}, "0.0.0.0/1"),
    ("no carrier", {LINK: GOOD[LINK].replace("UP,LOWER_UP", "UP").replace("state UP", "state DOWN")}, "carrier"),
    # not a plain PCI/USB device
    ("Open vSwitch internal port", {LINK: GOOD[LINK].replace(" parentbus usb parentdev 2-1:1.0", "").replace(
        "addrgenmode", "\\    openvswitch addrgenmode")}, "parentbus"),
    ("HSR master", {LINK: GOOD[LINK].replace(" parentbus usb parentdev 2-1:1.0", "") + "\\    hsr slave1 eno1\n"},
     "parentbus"),
    # IPv6 on the wire, forwarding
    ("IPv6 router neighbour", {("ip", "-6", "neigh", "show", "dev", "enx1"): "fe80::1 lladdr 02:00:00:00:00:fe router STALE\n"},
     "IPv6 host"),
    ("IPv6 default route", {("ip", "-6", "-o", "route", "show", "table", "all", "default"):
                            "default via fe80::1 dev enx1 proto ra metric 1024 expires 1790sec\n"}, "IPv6 default"),
    ("forwarding on", {("cat", "/proc/sys/net/ipv4/conf/enx1/forwarding"): "1\n"}, "forwarding"),
    ("proxy ARP on", {("cat", "/proc/sys/net/ipv4/conf/enx1/proxy_arp"): "1\n"}, "proxy_arp"),
    ("forwarding unreadable", {("cat", "/proc/sys/net/ipv4/conf/enx1/forwarding"): ""}, "unreadable"),
    # neighbours
    ("another host on the subnet", {NEIGH: GOOD[NEIGH] + "192.168.63.77 lladdr 02:00:00:00:00:77 STALE\n"},
     "another host"),
    ("the board's address with another MAC", {NEIGH: "192.168.63.2 lladdr 02:00:00:00:00:99 REACHABLE\n"}, "not the board's"),
])
def test_refusals(case, over, word):
    why = refused(over)
    assert any(word in w for w in why), (case, why)


def test_the_home_interface_refused():
    """The interface that carries the default route can never pass."""
    eno = {("ip", "-d", "-o", "link", "show", "dev", "eno1"): GOOD[LINK].replace("enx1", "eno1"),
           ("ip", "-4", "-o", "addr", "show", "dev", "eno1"): "2: eno1 inet 192.168.1.20/24 scope global eno1\n"}
    why = br.isolation_check("eno1", runner(eno))
    assert any("default route" in w for w in why) and any("only 192.168.63.1/24" in w for w in why)


def test_ping_loss_parsed_numerically():
    assert br.ping_ok("5 packets transmitted, 5 received, 0% packet loss, time 4006ms", 5)
    assert not br.ping_ok("5 packets transmitted, 0 received, 100% packet loss, time 4093ms", 5)
    assert not br.ping_ok("5 packets transmitted, 4 received, 20% packet loss, time 4006ms", 5)
    assert not br.ping_ok("ping: connect: Network is unreachable", 5)


def test_a_failed_query_refuses():
    """A query that fails (the real runner raises on a non-zero exit) must stop the run, not read as 'nothing found'."""
    import subprocess

    def failing(*cmd):
        if cmd[:3] == ("ip", "-4", "-o") and "route" in cmd:
            raise subprocess.CalledProcessError(2, cmd)
        return runner()(*cmd)
    with pytest.raises(subprocess.CalledProcessError):
        br.isolation_check("enx1", failing)


def test_quiet_link_counts_frames(tmp_path, monkeypatch):
    """quiet_link reports the frames received during the window (0 on a cable to the idle board)."""
    f = tmp_path / "enx1" / "statistics" / "rx_packets"
    f.parent.mkdir(parents=True)
    f.write_text("100\n")
    assert br.quiet_link("enx1", 0, str(tmp_path)) == 0
    reads = iter(["100\n", "107\n"])
    monkeypatch.setattr(br.Path, "read_text", lambda self: next(reads))
    assert br.quiet_link("enx1", 0, str(tmp_path)) == 7

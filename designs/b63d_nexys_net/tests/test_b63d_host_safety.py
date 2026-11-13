"""The link phase's network-safety checks (host/board_run.py), with stand-in command outputs: no traffic, no root."""
from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("board_run", Path(__file__).resolve().parents[1] / "host" / "board_run.py")
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

GOOD = {
    ("ip", "-4", "-o", "addr", "show", "dev", "enx1"): "5: enx1    inet 192.168.63.1/24 scope global enx1\n",
    ("ip", "-4", "route", "show", "default"): "default via 192.168.1.1 dev eno1 proto dhcp metric 100\n",
    ("ip", "-4", "route", "show", "table", "all", "default"): "default via 192.168.1.1 dev eno1 proto dhcp\n",
    ("ip", "-4", "route", "get", "192.168.63.2", "oif", "enx1"): "192.168.63.2 dev enx1 src 192.168.63.1\n",
    ("ip", "-4", "route", "get", "239.63.0.1", "oif", "enx1"): "multicast 239.63.0.1 dev enx1 src 192.168.63.1\n",
    ("ip", "-4", "route", "get", "192.168.63.2"): "192.168.63.2 dev enx1 src 192.168.63.1\n",
    ("ip", "-4", "neigh", "show", "dev", "enx1"): "192.168.63.2 lladdr 02:00:00:00:00:63 REACHABLE\n",
}


def runner(over=None):
    t = {**GOOD, **(over or {})}
    return lambda *cmd: t.get(tuple(cmd), "")


def test_isolated_link_passes():
    assert br.isolation_check("enx1", runner()) == []


def test_default_route_on_the_interface_refused():
    why = br.isolation_check("enx1", runner({("ip", "-4", "route", "show", "default"):
                                             "default via 192.168.63.254 dev enx1\n"}))
    assert any("default route" in w for w in why)


def test_the_home_interface_refused():
    """The interface that carries the default route (the home LAN) can never pass: wrong address and default route."""
    t = {("ip", "-4", "-o", "addr", "show", "dev", "eno1"): "2: eno1    inet 192.168.1.20/24 scope global eno1\n"}
    why = br.isolation_check("eno1", runner(t))
    assert any("default route" in w for w in why) and any("only 192.168.63.1/24" in w for w in why)


def test_address_outside_the_subnet_refused():
    why = br.isolation_check("enx1", runner({("ip", "-4", "-o", "addr", "show", "dev", "enx1"):
                                             "5: enx1 inet 192.168.63.1/24 x\n5: enx1 inet 10.0.0.5/8 x\n"}))
    assert any("10.0.0.5" in w for w in why)


def test_route_to_the_board_by_another_interface_refused():
    why = br.isolation_check("enx1", runner({("ip", "-4", "route", "get", "192.168.63.2"):
                                             "192.168.63.2 via 192.168.1.1 dev eno1\n"}))
    assert any("not enx1" in w for w in why)


def test_another_host_on_the_subnet_refused():
    why = br.isolation_check("enx1", runner({("ip", "-4", "neigh", "show", "dev", "enx1"):
                                             "192.168.63.2 lladdr 02:00:00:00:00:63 REACHABLE\n"
                                             "192.168.63.77 lladdr 3c:22:fb:00:00:01 STALE\n"}))
    assert any("192.168.63.77" in w for w in why)


def test_ping_loss_parsed_numerically():
    ok = "5 packets transmitted, 5 received, 0% packet loss, time 4006ms"
    assert br.ping_ok(ok, 5)
    assert not br.ping_ok("5 packets transmitted, 0 received, 100% packet loss, time 4093ms", 5)
    assert not br.ping_ok("5 packets transmitted, 4 received, 20% packet loss, time 4006ms", 5)
    assert not br.ping_ok("ping: connect: Network is unreachable", 5)

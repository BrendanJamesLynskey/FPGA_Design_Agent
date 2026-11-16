"""Host client for the UDP endpoint: typed commands with sequence numbers, a dry-run transport against the reference model.

    python3 -m showcase.udp_endpoint.host.client --dry-run          (no board, no network)
    python3 -m showcase.udp_endpoint.host.client --host 192.168.1.50 --port 5005     (a real board; phase 3, not run)

A transport takes one datagram payload and returns the datagrams that came back within its timeout (a list: zero for a dropped
command, one for a reply). Telemetry frames arrive on their own and are collected with ``collect``.
"""

from __future__ import annotations

import argparse
import json
import socket
from typing import Protocol

from showcase.udp_endpoint.model import udp_ref as u


class Transport(Protocol):
    def exchange(self, payload: bytes) -> list[bytes]: ...


class SimTransport:
    """Dry run: the reference model stands in for the board."""

    def __init__(self, endpoint: u.Endpoint | None = None) -> None:
        self.ep = endpoint or u.Endpoint()

    def exchange(self, payload: bytes) -> list[bytes]:
        r = self.ep.datagram(payload)
        return [r] if r else []


class UdpTransport:
    def __init__(self, host: str, port: int, timeout: float = 0.2) -> None:
        self.addr = (host, port)
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.settimeout(timeout)

    def exchange(self, payload: bytes) -> list[bytes]:
        self.s.sendto(payload, self.addr)
        out = []
        try:
            while True:
                out.append(self.s.recvfrom(2048)[0])
        except socket.timeout:
            return out


class CommandError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(u.ERROR_NAMES.get(status, str(status)))
        self.status = status


class Client:
    def __init__(self, transport: Transport, first_seq: int = 0) -> None:
        self.t, self.seq = transport, first_seq

    def send(self, typ: int, payload: bytes = b"", seq: int | None = None) -> dict | None:
        """One command. Returns the decoded reply, or None if the endpoint dropped it. The next sequence number is used unless given."""
        s = self.seq if seq is None else seq
        got = self.t.exchange(u.build_command(typ, s, payload))
        if seq is None:
            self.seq = (self.seq + 1) & 0xFFFF
        if not got:
            return None
        r = u.parse_response(got[0])
        assert r["seq"] == s and r["type"] == typ, "reply does not match the command"
        return r

    def _ok(self, typ: int, payload: bytes = b"") -> dict:
        r = self.send(typ, payload)
        if r is None:
            raise TimeoutError("no reply")
        if r["status"] != u.OK:
            raise CommandError(r["status"])
        return r

    def read(self, addr: int) -> int:
        return int.from_bytes(self._ok(u.READ, addr.to_bytes(2, "big"))["payload"], "big")

    def write(self, addr: int, value: int) -> None:
        self._ok(u.WRITE, addr.to_bytes(2, "big") + (value & 0xFFFFFFFF).to_bytes(4, "big"))

    def status(self) -> dict:
        p = self._ok(u.STATUS)["payload"]
        d = {k: int.from_bytes(p[2 * i:2 * i + 2], "big") for i, k in enumerate(u.COUNTERS)}
        d["tlm_frames"], d["tlm_on"] = int.from_bytes(p[14:16], "big"), bool(p[16])
        return d

    def start_telemetry(self, period: int = 0) -> None:
        self._ok(u.TLM_START, period.to_bytes(2, "big"))

    def stop_telemetry(self) -> None:
        self._ok(u.TLM_STOP)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="talk to the reference model, not a board")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int, default=5005)
    a = ap.parse_args()
    if not a.dry_run and not a.host:
        ap.error("give --host (a board) or --dry-run")
    c = Client(SimTransport() if a.dry_run else UdpTransport(a.host, a.port))
    c.write(u.REG_S0, 0xCAFEF00D)
    print(json.dumps({"id": hex(c.read(u.REG_ID)), "scratch0": hex(c.read(u.REG_S0)), "status": c.status()}, indent=1))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Cloud burst runner for Vivado batches on AWS EC2 (brief 33). The owner runs every command that costs money.

    python3 cloud/fda_cloud.py <command> [--config cloud/cloud.yaml] [--dry-run]

Commands (thin wrappers: cloud/start.sh, sync.sh, run_batch.sh, fetch_results.sh, stop.sh):

    start          launch one instance from our Vivado AMI (Spot first, on-demand only if allowed), after the budget check
    status         the burst instances that exist, their state, age and the spend so far
    sync           copy the repository (git archive of HEAD) and the batch inputs to the instance (rsync over SSH)
    run-batch F    run the jobs of batch file F on the instance, several at once (cloud/instance/run_batch_remote.sh)
    fetch-results  copy the results back into cloud/results/<instance id>/
    stop           terminate every burst instance (tag fda:burst=1) and record the spend

Safety, so nothing runs up a bill:

- **Hard budget.** ``budget_usd`` in the config caps the month's spend. ``start`` refuses when the spend recorded in
  ``cloud/state/ledger.json`` plus the new instance's worst case (``max_hours`` at the on-demand price) would pass it.
  The ledger charges every instance at the on-demand price for its whole life, an upper bound on what AWS bills.
- **Auto-stop on the instance itself.** The user data (cloud/instance/user_data.sh) schedules a shutdown at
  ``max_hours`` and starts an idle watchdog (cloud/instance/idle_watchdog.sh) that shuts down after ``idle_minutes``
  with no Vivado process, no batch job and no SSH session. The instance is launched with shutdown behaviour
  *terminate* and a root volume deleted on termination, so a shutdown ends all billing. This works even if the
  owner's PC is off.
- **No keys in the repo.** boto3 uses the owner's own AWS login (``aws configure`` / ``aws sso login``, profile in
  the config); SSH uses the owner's key pair, whose private key stays in ~/.ssh.
- ``--dry-run`` prints every AWS request and every ssh/rsync command instead of running it, and needs no AWS login.

The tests (cloud/tests) run every command against moto's mocked EC2, never against AWS.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TAG = "fda:burst"
DEFAULTS: dict[str, Any] = {
    "profile": None,                  # the owner's AWS CLI profile (None: the default chain)
    "region": "eu-west-2",            # London
    "ami_id": None,                   # our AMI with Vivado 2026.1 (cloud/BUILD_AMI.md); start refuses without it
    "instance_type": "c7a.2xlarge",   # 8 vCPU = 8 physical cores (c7a has no SMT), 16 GiB, 3.7 GHz
    "spot": True,
    "allow_on_demand": False,         # fall back to on-demand when Spot has no capacity (owner's choice)
    "on_demand_usd_per_hour": 0.49,   # the ledger's price per hour (on-demand, an upper bound for Spot)
    "budget_usd": 20.0,               # hard cap per calendar month
    "max_hours": 4.0,                 # each instance shuts itself down (terminates) after this
    "idle_minutes": 20,               # ... or after this long idle
    "key_name": None,                 # the owner's EC2 key pair name
    "ssh_key": "~/.ssh/fda_burst.pem",
    "ssh_user": "ubuntu",
    "security_group_id": None,        # SSH from the owner's IP only (cloud/README.md)
    "subnet_id": None,
    "root_volume_gb": 160,            # the AMI's snapshot size or more: Vivado for our families was ~70-90 GB on the previous release; check the 2026.1 install
    "remote_dir": "/home/ubuntu/fda",
    "parallel_jobs": 2,               # Vivado jobs at once on the instance
    "threads_per_job": 4,             # FDA_VIVADO_THREADS for each
    "mem_max_per_job": "7G",
}


class Refused(SystemExit):
    """A safety rule stopped the command (budget, missing AMI, an instance already running)."""


def load_config(path: Path | None) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    if path and path.is_file():
        cfg.update(yaml.safe_load(path.read_text()) or {})
    return cfg


# --- ledger --------------------------------------------------------------------------------------------------------
def ledger_path() -> Path:
    return Path(os.environ.get("FDA_CLOUD_STATE", HERE / "state")) / "ledger.json"


def read_ledger() -> dict[str, Any]:
    p = ledger_path()
    return json.loads(p.read_text()) if p.is_file() else {"instances": {}}


def write_ledger(led: dict[str, Any]) -> None:
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led, indent=2, sort_keys=True) + "\n")


def _hours(start: str, end: str | None, now: dt.datetime) -> float:
    t0 = dt.datetime.fromisoformat(start)
    t1 = dt.datetime.fromisoformat(end) if end else now
    return max(0.0, (t1 - t0).total_seconds() / 3600.0)


def month_spend(led: dict[str, Any], now: dt.datetime) -> float:
    """Spend this calendar month, every instance charged at its recorded price for its whole life so far (a running
    instance counts up to now)."""
    total = 0.0
    for rec in led["instances"].values():
        if rec["launched"][:7] == now.strftime("%Y-%m"):
            total += _hours(rec["launched"], rec.get("ended"), now) * rec["usd_per_hour"]
    return round(total, 4)


def budget_check(cfg: dict[str, Any], led: dict[str, Any], now: dt.datetime) -> dict[str, float]:
    spent = month_spend(led, now)
    worst = cfg["max_hours"] * cfg["on_demand_usd_per_hour"]
    if spent + worst > cfg["budget_usd"]:
        raise Refused(f"budget: spent ${spent:.2f} this month; a new instance could cost up to ${worst:.2f} "
                      f"({cfg['max_hours']} h at ${cfg['on_demand_usd_per_hour']}/h); the cap is ${cfg['budget_usd']:.2f}")
    return {"spent_usd": spent, "worst_case_usd": round(worst, 4), "budget_usd": cfg["budget_usd"]}


# --- AWS -----------------------------------------------------------------------------------------------------------
class DryEC2:
    """Stands in for the boto3 client under --dry-run: prints each request and returns a plausible empty answer."""

    def __getattr__(self, name: str):
        def call(**kw):
            print(f"DRY-RUN ec2.{name}({json.dumps(kw, sort_keys=True, default=str)})")
            if name == "run_instances":
                return {"Instances": [{"InstanceId": "i-dryrun", "LaunchTime": dt.datetime.now(dt.timezone.utc)}]}
            if name == "describe_instances":
                return {"Reservations": []}
            return {}
        return call


def ec2_client(cfg: dict[str, Any], dry: bool):
    if dry:
        return DryEC2()
    import boto3                                                   # only for real (owner) runs and the moto tests
    sess = boto3.session.Session(profile_name=cfg["profile"]) if cfg["profile"] else boto3.session.Session()
    return sess.client("ec2", region_name=cfg["region"])


def user_data(cfg: dict[str, Any]) -> str:
    text = (HERE / "instance" / "user_data.sh").read_text()
    return (text.replace("@MAX_MINUTES@", str(int(cfg["max_hours"] * 60)))
                .replace("@IDLE_MINUTES@", str(int(cfg["idle_minutes"])))
                .replace("@WATCHDOG@", (HERE / "instance" / "idle_watchdog.sh").read_text()))


def burst_instances(ec2) -> list[dict[str, Any]]:
    r = ec2.describe_instances(Filters=[{"Name": f"tag:{TAG}", "Values": ["1"]},
                                        {"Name": "instance-state-name",
                                         "Values": ["pending", "running", "stopping", "stopped"]}])
    return [i for res in r.get("Reservations", []) for i in res.get("Instances", [])]


def launch_request(cfg: dict[str, Any], spot: bool) -> dict[str, Any]:
    req: dict[str, Any] = {
        "ImageId": cfg["ami_id"], "InstanceType": cfg["instance_type"], "MinCount": 1, "MaxCount": 1,
        "InstanceInitiatedShutdownBehavior": "terminate",
        "UserData": user_data(cfg),
        "BlockDeviceMappings": [{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": int(cfg["root_volume_gb"]),
                                                                    "VolumeType": "gp3", "DeleteOnTermination": True}}],
        "MetadataOptions": {"HttpTokens": "required"},
        "TagSpecifications": [{"ResourceType": "instance", "Tags": [
            {"Key": TAG, "Value": "1"}, {"Key": "Name", "Value": "fda-vivado-burst"},
            {"Key": "fda:max_hours", "Value": str(cfg["max_hours"])}]},
            {"ResourceType": "volume", "Tags": [{"Key": TAG, "Value": "1"}]}],
    }
    if cfg["key_name"]:
        req["KeyName"] = cfg["key_name"]
    if cfg["security_group_id"]:
        req["SecurityGroupIds"] = [cfg["security_group_id"]]
    if cfg["subnet_id"]:
        req["SubnetId"] = cfg["subnet_id"]
    if spot:
        # one-time Spot: AWS reclaims it with two minutes' notice; the batch then re-runs the unfinished jobs
        req["InstanceMarketOptions"] = {"MarketType": "spot", "SpotOptions": {
            "SpotInstanceType": "one-time", "InstanceInterruptionBehavior": "terminate"}}
    return req


SPOT_FULL = ("InsufficientInstanceCapacity", "SpotMaxPriceTooLow", "MaxSpotInstanceCountExceeded")


def start(cfg: dict[str, Any], dry: bool, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    if not cfg["ami_id"]:
        raise Refused("start: no ami_id in the config; build the AMI first (cloud/BUILD_AMI.md)")
    led = read_ledger()
    b = budget_check(cfg, led, now)
    ec2 = ec2_client(cfg, dry)
    running = burst_instances(ec2)
    if running:
        raise Refused(f"start: a burst instance already exists ({running[0]['InstanceId']}); stop it first")
    market = "spot" if cfg["spot"] else "on-demand"
    try:
        r = ec2.run_instances(**launch_request(cfg, cfg["spot"]))
    except Exception as e:                                         # botocore ClientError, without importing botocore
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        if not (cfg["spot"] and code in SPOT_FULL and cfg["allow_on_demand"]):
            raise
        print(f"start: Spot refused ({code}); falling back to on-demand (allow_on_demand is set)")
        market = "on-demand"
        r = ec2.run_instances(**launch_request(cfg, False))
    inst = r["Instances"][0]
    iid = inst["InstanceId"]
    if not dry:
        led["instances"][iid] = {"launched": now.isoformat(), "ended": None, "market": market,
                                 "instance_type": cfg["instance_type"], "usd_per_hour": cfg["on_demand_usd_per_hour"],
                                 "region": cfg["region"]}
        write_ledger(led)
    out = {"instance_id": iid, "market": market, **b}
    print(json.dumps(out))
    return out


def status(cfg: dict[str, Any], dry: bool, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    ec2 = ec2_client(cfg, dry)
    rows = [{"instance_id": i["InstanceId"], "state": i["State"]["Name"], "type": i["InstanceType"],
             "public_ip": i.get("PublicIpAddress"),
             "age_h": round((now - i["LaunchTime"]).total_seconds() / 3600.0, 2)} for i in burst_instances(ec2)]
    out = {"instances": rows, "month_spend_usd": month_spend(read_ledger(), now), "budget_usd": cfg["budget_usd"]}
    print(json.dumps(out, default=str))
    return out


def stop(cfg: dict[str, Any], dry: bool, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    ec2 = ec2_client(cfg, dry)
    ids = [i["InstanceId"] for i in burst_instances(ec2)]
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
    led = read_ledger()
    for iid, rec in led["instances"].items():
        if rec.get("ended") is None and (iid in ids or not dry):
            # an instance no longer listed has already ended (it shut itself down): close its record now, an upper bound
            rec["ended"] = now.isoformat()
    if not dry:
        write_ledger(led)
    out = {"terminated": ids, "month_spend_usd": month_spend(led, now)}
    print(json.dumps(out))
    return out


# --- SSH side ------------------------------------------------------------------------------------------------------
def _host(cfg: dict[str, Any], dry: bool, ip: str | None) -> str:
    if ip:
        return ip
    if dry:
        return "<instance ip>"
    rows = [i for i in burst_instances(ec2_client(cfg, False)) if i.get("PublicIpAddress")]
    if not rows:
        raise Refused("no running burst instance with a public IP (start one first)")
    return rows[0]["PublicIpAddress"]


def _ssh(cfg: dict[str, Any]) -> list[str]:
    return ["ssh", "-i", os.path.expanduser(cfg["ssh_key"]), "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ServerAliveInterval=30"]


def _run(cmd: list[str], dry: bool) -> int:
    print(("DRY-RUN " if dry else "") + " ".join(shlex.quote(c) for c in cmd))
    return 0 if dry else subprocess.run(cmd).returncode


def sync(cfg: dict[str, Any], dry: bool, ip: str | None = None, extra: list[str] | None = None) -> int:
    """The committed tree (git archive HEAD: no build outputs, no private files, nothing untracked) plus the named
    extra paths (for example a staged build/bench/<task> directory)."""
    host = f"{cfg['ssh_user']}@{_host(cfg, dry, ip)}"
    rd = cfg["remote_dir"]
    tar = Path(os.environ.get("FDA_CLOUD_STATE", HERE / "state")) / "repo.tar"
    if not dry:
        tar.parent.mkdir(parents=True, exist_ok=True)
    rc = _run(["git", "-C", str(ROOT), "archive", "--format=tar", "-o", str(tar), "HEAD"], dry)
    rc = rc or _run([*_ssh(cfg), host, f"mkdir -p {shlex.quote(rd)}"], dry)
    rc = rc or _run(["rsync", "-az", "-e", " ".join(_ssh(cfg)), str(tar), f"{host}:{rd}/repo.tar"], dry)
    rc = rc or _run([*_ssh(cfg), host, f"cd {shlex.quote(rd)} && tar -xf repo.tar && rm repo.tar"], dry)
    for p in extra or []:
        rel = Path(p).resolve().relative_to(ROOT)
        rc = rc or _run(["rsync", "-az", "--relative", "-e", " ".join(_ssh(cfg)), f"{ROOT}/./{rel}", f"{host}:{rd}/"],
                        dry)
    return rc


def run_batch(cfg: dict[str, Any], batch: Path, dry: bool, ip: str | None = None) -> int:
    host = f"{cfg['ssh_user']}@{_host(cfg, dry, ip)}"
    rd = cfg["remote_dir"]
    rc = _run(["rsync", "-az", "-e", " ".join(_ssh(cfg)), str(batch), f"{host}:{rd}/batch.txt"], dry)
    remote = (f"cd {shlex.quote(rd)} && PARALLEL={int(cfg['parallel_jobs'])} THREADS={int(cfg['threads_per_job'])} "
              f"MEM_MAX={shlex.quote(cfg['mem_max_per_job'])} bash cloud/instance/run_batch_remote.sh batch.txt")
    return rc or _run([*_ssh(cfg), host, remote], dry)


def fetch_results(cfg: dict[str, Any], dry: bool, ip: str | None = None, label: str = "latest") -> int:
    host = f"{cfg['ssh_user']}@{_host(cfg, dry, ip)}"
    dst = HERE / "results" / label
    if not dry:
        dst.mkdir(parents=True, exist_ok=True)
    return _run(["rsync", "-az", "-e", " ".join(_ssh(cfg)), f"{host}:{cfg['remote_dir']}/cloud_results/", f"{dst}/"],
                dry)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["start", "status", "sync", "run-batch", "fetch-results", "stop"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--config", type=Path, default=HERE / "cloud.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ip", help="the instance's address (default: look it up by tag)")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    try:
        if a.command == "start":
            start(cfg, a.dry_run)
        elif a.command == "status":
            status(cfg, a.dry_run)
        elif a.command == "stop":
            stop(cfg, a.dry_run)
        elif a.command == "sync":
            return sync(cfg, a.dry_run, a.ip, a.args)
        elif a.command == "run-batch":
            if not a.args:
                raise Refused("run-batch needs a batch file (cloud/batch.example.txt)")
            return run_batch(cfg, Path(a.args[0]), a.dry_run, a.ip)
        elif a.command == "fetch-results":
            return fetch_results(cfg, a.dry_run, a.ip, a.args[0] if a.args else "latest")
    except Refused as e:
        print(f"REFUSED: {e.code}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

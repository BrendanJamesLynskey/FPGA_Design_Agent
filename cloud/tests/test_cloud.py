"""Brief 33: the cloud burst runner against moto's mocked EC2 (never real AWS), its dry run, its budget and the
instance-side idle watchdog. Skipped where boto3/moto are not installed."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
from botocore.exceptions import ClientError  # noqa: E402

from cloud import fda_cloud as fc  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 11, 11, 3, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def no_real_aws(tmp_path, monkeypatch):
    """Fake credentials and no config files: nothing here can reach the owner's account."""
    for k, v in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_SESSION_TOKEN": "testing",
                 "AWS_DEFAULT_REGION": "eu-west-2", "AWS_CONFIG_FILE": str(tmp_path / "none"),
                 "AWS_SHARED_CREDENTIALS_FILE": str(tmp_path / "none"), "FDA_CLOUD_STATE": str(tmp_path / "state")}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with moto.mock_aws():
        yield


def _cfg(**kw):
    ec2 = boto3.client("ec2", region_name="eu-west-2")
    ami = ec2.describe_images(Owners=["amazon"])["Images"][0]["ImageId"]
    return {**fc.DEFAULTS, "ami_id": ami, **kw}


def test_start_launches_one_spot_instance_with_the_safety_settings():
    cfg = _cfg()
    out = fc.start(cfg, dry=False, now=NOW)
    assert out["market"] == "spot" and out["spent_usd"] == 0
    ec2 = boto3.client("ec2", region_name="eu-west-2")
    inst = fc.burst_instances(ec2)
    assert [i["InstanceId"] for i in inst] == [out["instance_id"]]
    i = inst[0]
    assert i["InstanceType"] == "c7a.2xlarge" and i.get("InstanceLifecycle") == "spot"
    attr = ec2.describe_instance_attribute(InstanceId=i["InstanceId"], Attribute="instanceInitiatedShutdownBehavior")
    assert attr["InstanceInitiatedShutdownBehavior"]["Value"] == "terminate"
    tags = {t["Key"]: t["Value"] for t in i["Tags"]}
    assert tags[fc.TAG] == "1"
    led = fc.read_ledger()
    assert led["instances"][i["InstanceId"]]["usd_per_hour"] == cfg["on_demand_usd_per_hour"]
    # a second start is refused while one exists
    with pytest.raises(fc.Refused):
        fc.start(cfg, dry=False, now=NOW)


def test_user_data_carries_the_hard_stop_and_the_watchdog():
    ud = fc.user_data({**fc.DEFAULTS, "max_hours": 3, "idle_minutes": 15})
    assert "shutdown -h +180" in ud and "IDLE_MINUTES=15" in ud and "pgrep -x vivado" in ud and "@" not in ud


def test_stop_terminates_and_closes_the_ledger():
    cfg = _cfg()
    iid = fc.start(cfg, dry=False, now=NOW)["instance_id"]
    later = NOW + dt.timedelta(hours=2)
    out = fc.stop(cfg, dry=False, now=later)
    assert out["terminated"] == [iid]
    assert out["month_spend_usd"] == pytest.approx(2 * cfg["on_demand_usd_per_hour"])
    assert fc.burst_instances(boto3.client("ec2", region_name="eu-west-2")) == []


def test_budget_refuses_a_start_that_could_pass_the_cap():
    cfg = _cfg(budget_usd=5.0, max_hours=4.0, on_demand_usd_per_hour=0.5)
    led = {"instances": {"i-old": {"launched": (NOW - dt.timedelta(hours=8)).isoformat(),
                                   "ended": (NOW - dt.timedelta(hours=1)).isoformat(), "usd_per_hour": 0.5}}}
    fc.write_ledger(led)                                    # $3.50 spent; a new one could add $2.00: refused at $5.00
    with pytest.raises(fc.Refused, match="budget"):
        fc.start(cfg, dry=False, now=NOW)
    assert fc.burst_instances(boto3.client("ec2", region_name="eu-west-2")) == []
    # last month's spend does not count
    led["instances"]["i-old"]["launched"] = "2026-10-01T00:00:00+00:00"
    led["instances"]["i-old"]["ended"] = "2026-10-01T06:00:00+00:00"
    fc.write_ledger(led)
    assert fc.start(cfg, dry=False, now=NOW)["spent_usd"] == 0


def test_no_ami_is_refused():
    with pytest.raises(fc.Refused, match="ami_id"):
        fc.start({**fc.DEFAULTS}, dry=False, now=NOW)


def test_spot_without_capacity_falls_back_only_when_allowed(monkeypatch):
    calls = []
    real = fc.ec2_client

    def client(cfg, dry):
        c = real(cfg, dry)
        orig = c.run_instances

        def run_instances(**kw):
            calls.append("spot" if "InstanceMarketOptions" in kw else "on-demand")
            if "InstanceMarketOptions" in kw:
                raise ClientError({"Error": {"Code": "InsufficientInstanceCapacity", "Message": "none"}}, "RunInstances")
            return orig(**kw)
        c.run_instances = run_instances
        return c
    monkeypatch.setattr(fc, "ec2_client", client)
    with pytest.raises(ClientError):
        fc.start(_cfg(), dry=False, now=NOW)
    assert calls == ["spot"]
    out = fc.start(_cfg(allow_on_demand=True), dry=False, now=NOW)
    assert out["market"] == "on-demand" and calls == ["spot", "spot", "on-demand"]


def test_dry_run_calls_nothing_and_records_nothing(capsys):
    cfg = {**fc.DEFAULTS, "ami_id": "ami-0123456789abcdef0"}
    fc.start(cfg, dry=True, now=NOW)
    assert fc.sync(cfg, dry=True) == 0
    batch = HERE / "batch.example.txt"
    assert fc.run_batch(cfg, batch, dry=True) == 0
    assert fc.fetch_results(cfg, dry=True) == 0
    fc.stop(cfg, dry=True, now=NOW)
    out = capsys.readouterr().out
    assert "DRY-RUN ec2.run_instances(" in out and '"InstanceInitiatedShutdownBehavior": "terminate"' in out
    assert "DRY-RUN git -C" in out and "DRY-RUN rsync" in out and "run_batch_remote.sh batch.txt" in out
    assert not fc.ledger_path().exists()


def test_cli_status_and_refusal(capsys, tmp_path):
    assert fc.main(["status", "--config", str(tmp_path / "none.yaml")]) == 0
    assert json.loads(capsys.readouterr().out.strip())["instances"] == []
    assert fc.main(["start", "--config", str(tmp_path / "none.yaml")]) == 2       # no AMI configured


def _watchdog(tmp_path, busy_file: bool, idle_since_min: int | None, idle_minutes: int = 20) -> str:
    st = tmp_path / "idle_since"
    if idle_since_min is not None:
        st.write_text(str(int(dt.datetime.now().timestamp()) - idle_since_min * 60))
    bf = tmp_path / "busy"
    if busy_file:
        bf.write_text("")
    env = dict(os.environ, FDA_WATCHDOG_ONCE="1", FDA_WATCHDOG_STATE=str(st), FDA_BUSY_FILE=str(bf),
               IDLE_MINUTES=str(idle_minutes), PATH="/usr/bin:/bin")
    # `who` lists the build PC's own logins; a stand-in that lists nobody makes the test about the watchdog's logic
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "who").write_text("#!/bin/sh\nexit 0\n")
    (fake / "who").chmod(0o755)
    (fake / "pgrep").write_text("#!/bin/sh\nexit 1\n")
    (fake / "pgrep").chmod(0o755)
    env["PATH"] = f"{fake}:/usr/bin:/bin"
    return subprocess.run(["bash", str(HERE / "instance" / "idle_watchdog.sh")], env=env, capture_output=True,
                          text=True).stdout.strip()


def test_idle_watchdog(tmp_path):
    assert _watchdog(tmp_path, busy_file=True, idle_since_min=60) == "busy"
    assert not (tmp_path / "idle_since").exists()                  # busy resets the idle clock
    (tmp_path / "busy").unlink()
    assert _watchdog(tmp_path, busy_file=False, idle_since_min=None) == "idle for 0 min"
    assert _watchdog(tmp_path, busy_file=False, idle_since_min=25).endswith("shutting down")

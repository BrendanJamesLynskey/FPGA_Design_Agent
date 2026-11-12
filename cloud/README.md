# Cloud burst runner (AWS EC2, brief 33)

Runs batches of Vivado builds on one AWS EC2 instance in London (eu-west-2) when the build PC is the bottleneck. It is
for **throughput**: parameter and strategy sweeps, seed runs, and many agent builds at once. It is not for making one
build faster: a cloud core is only somewhat faster than the build PC's (below), and a single build uses at most four
threads well.

Nothing here has been run against AWS. The scripts were tested against [moto](https://github.com/getmoto/moto)'s
mocked EC2 (`cloud/tests/test_cloud.py`) and in `--dry-run` mode. **The owner runs every command that can cost money**
(`start`, `stop`, the AMI build, the trial), with their own AWS login. No keys are stored in this repository.

## Design

| Choice | What | Why |
|---|---|---|
| Provider | AWS EC2, region eu-west-2 | the owner's account; Google Compute Engine is the fallback if AWS fails a requirement |
| Instance | `c7a.2xlarge` (8 vCPU, 16 GiB; configurable) | c7a vCPUs are whole cores (no SMT), AMD EPYC 9R14 at 3.7 GHz; two 4-thread Vivado jobs fit |
| Image | our own EBS-backed AMI with Vivado **2026.1** installed in `/tools/Xilinx/2026.1` | the same version as the build PC, so results compare; a VM starts in minutes with nothing to download. Not AMD's FPGA Developer AMI, whose Vivado version follows the F2 tools |
| Market | Spot (one-time), on-demand only if `allow_on_demand: true` | batch work survives an interruption: `run-batch` skips finished jobs, so re-running the same batch finishes the rest |
| Data | `sync`: `git archive HEAD` plus named extra paths over rsync/SSH; `fetch-results`: rsync back | only committed files leave the PC: no private knowledge packs, no held-out tasks, no keys |
| Access | the owner's EC2 key pair; a security group that allows SSH from the owner's IP only | no open ports, no VPN, no link from the instance to the home network |
| Licence | none needed for our parts (below) | the owner's node-locked licence is tied to the build PC's MAC address and does not move |

### What stops the bill

1. **Hard monthly budget** (`budget_usd`, default $20). `start` refuses when this month's recorded spend plus the new
   instance's worst case (`max_hours` x the on-demand price) would pass it. The ledger (`cloud/state/ledger.json`, not
   committed) charges every instance at the on-demand price for its whole life, so it overstates a Spot bill.
2. **A hard stop on the instance.** Its user data schedules `shutdown` at `max_hours` (default 4 h). Instances launch
   with shutdown behaviour *terminate* and a root volume deleted on termination, so shutting down ends all charges.
3. **An idle watchdog on the instance** (`instance/idle_watchdog.sh`, a systemd service): it shuts the instance down
   after `idle_minutes` (default 20) with no Vivado process, no running batch and no SSH login. Items 2 and 3 work
   even if the owner's PC is switched off.
4. **`stop`** terminates every instance tagged `fda:burst=1`.
5. Recommended, owner action: an AWS Budgets alert on the account (for example $25/month, email at 80%), as a check
   that does not depend on these scripts.

What still costs money when nothing runs: the AMI's EBS snapshot (about 60-90 GB of Vivado for our families, roughly
$3-5 a month at London snapshot prices; to be read from the owner's bill).

### Licence and devices

The build PC uses the owner's node-locked licence, which is tied to its MAC address. The parts this project builds
for, xc7a100t (Nexys A7), xc7z020 (ZedBoard) and xck26 (KV260), are in the no-cost edition of Vivado. Brief 33
checked this on the build PC with the licence hidden from Vivado: see `results/33_vivado_speed/README.md`. The
cloud image therefore needs no licence file. Anything that needs a paid licence (a larger device, a licensed IP core)
stays on the build PC.

## Use (owner)

One-off setup: `cloud/BUILD_AMI.md` (key pair, security group, AMI). Copy `cloud/cloud.example.yaml` to
`cloud/cloud.yaml` (not committed) and fill in `ami_id`, `key_name`, `security_group_id`.

```
cloud/start.sh                      # Spot instance; prints its id, the month's spend and the worst case
cloud/status.sh                     # instances, age, spend so far
cloud/sync.sh build/bench/c13_nexys_harris_vga      # the repo at HEAD plus the named staged designs
cloud/run_batch.sh cloud/batch.example.txt           # runs the jobs, 2 at a time, 4 threads each
cloud/fetch_results.sh trial1        # results into cloud/results/trial1/
cloud/stop.sh                       # terminate; also happens on its own when idle or at max_hours
```

Every command takes `--dry-run`, which prints the AWS requests and the ssh/rsync commands without running them.

Batch file lines: `<label> <design dir> <stop stage> [VAR=value ...]` (`batch.example.txt`). Each job runs in its own
copy of the repository through `flow/run_vivado.sh`, so the build cache, the thread pins, the memory cap and the
gates are the same as on the build PC.

## Trial (owner, one instance, about one hour)

`_handoff/fpga_agent/cloud_trial_33.sh` (in the owner's hand-off folder) starts one instance, syncs, runs
`cloud/trial_batch.txt` (the brief 33 small and mid designs at 1, 4 and 8 threads), fetches the results and stops.
The cost per build hour then comes from the instance's billed hours and the measured build times, compared with the
build PC's numbers in `results/33_vivado_speed/`.

## Dependencies and licences

| Package | Use | Licence |
|---|---|---|
| boto3 1.44.0 (with botocore) | the EC2 calls in `fda_cloud.py` (imported only for real runs and the tests) | Apache-2.0 |
| moto 5.2.5 | `cloud/tests`: a mocked EC2, so no test touches AWS | Apache-2.0 |
| PyYAML | the config file | MIT |
| rsync, OpenSSH, git | `sync` and `fetch-results` (system tools) | GPL-3.0 / BSD / GPL-2.0, used as programs, not linked |

Vivado itself is not redistributed: the owner installs it on the builder instance with their own AMD account.

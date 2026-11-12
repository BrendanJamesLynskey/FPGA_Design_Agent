# Building the Vivado AMI (owner, once; brief 33)

Every step here is an owner action: it uses the owner's AWS login and AMD account and some of it costs money (one
builder instance for about two hours, then the AMI's snapshot storage). Region eu-west-2 throughout.

1. **Log in and set the region:** `aws configure` (or `aws sso login --profile <p>`), region `eu-west-2`.
2. **Key pair and security group** (SSH from your own address only):

   ```
   aws ec2 create-key-pair --key-name fda-burst --key-type ed25519 --query KeyMaterial --output text > ~/.ssh/fda_burst.pem
   chmod 600 ~/.ssh/fda_burst.pem
   aws ec2 create-security-group --group-name fda-burst-ssh --description "FDA burst: SSH from owner"
   aws ec2 authorize-security-group-ingress --group-name fda-burst-ssh --protocol tcp --port 22 --cidr "$(curl -s https://checkip.amazonaws.com)/32"
   ```

3. **Builder instance:** Ubuntu 24.04 LTS (x86_64), `c7a.2xlarge`, on-demand, 200 GB gp3 root volume, the key pair
   and security group above. Find the current Ubuntu AMI id in the EC2 console's launch wizard (Canonical, owner
   099720109477).
4. **Install Vivado 2026.1** on the builder, the same version as the build PC (`/opt/Xilinx/2026.1`):
   - `sudo apt-get update && sudo apt-get install -y rsync git python3-yaml python3-pip libtinfo6 libncurses6 libx11-6 libxext6 libxrender1 libxtst6 libxi6 locales && sudo locale-gen en_US.UTF-8`
   - download AMD's Linux self-extracting web installer for 2026.1 (it needs your AMD account), then in batch mode:
     `./FPGAs_AdaptiveSoCs_Unified_SDI_2026.1_*_Lin64.bin --keep --noexec --target installer`,
     `installer/xsetup -b AuthTokenGen` (your AMD login), `installer/xsetup -b ConfigGen` (choose **Vivado** and its no-cost
     edition; the build PC runs 2026.1 on the free Basic licence tier, so check the edition names the installer offers), edit the generated `install_config.txt` so that only the families we use are selected
     (7 Series, Zynq-7000, Zynq UltraScale+ MPSoC / Kria), `Destination=/tools/Xilinx`, then
     `sudo installer/xsetup -b Install -a XilinxEULA,3rdPartyEULA -c install_config.txt`.
   - check: `/tools/Xilinx/2026.1/Vivado/bin/vivado -version` prints `v2026.1`. No licence file is installed.
   - remove the installer files and `~/.Xilinx` login tokens before imaging.
5. **Make the AMI:** stop the builder, then
   `aws ec2 create-image --instance-id <id> --name fda-vivado-2026.1-<date> --description "Vivado 2026.1 no-cost edition, 7 series + Zynq + ZU+"`;
   when it is `available`, terminate the builder and put the AMI id in `cloud/cloud.yaml`.
6. **Budget alert (recommended):** AWS Budgets, a monthly cost budget of about $25 with an email at 80%.

Read AMD's licence agreement for the edition you install before running it on a cloud instance; the no-cost edition
is what this project uses.

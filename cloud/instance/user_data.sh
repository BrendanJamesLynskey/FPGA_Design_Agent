#!/bin/bash
# user_data.sh: runs once as root when a burst instance boots (cloud/fda_cloud.py fills in the marked values).
# 1. A hard stop: shut down after @MAX_MINUTES@ minutes whatever happens. The instance is launched with shutdown
#    behaviour "terminate" and a root volume deleted on termination, so a shutdown ends all billing.
# 2. The idle watchdog (cloud/instance/idle_watchdog.sh): shut down after @IDLE_MINUTES@ idle minutes.
set -eu
shutdown -h +@MAX_MINUTES@ "fda burst: max_hours reached" || true
cat >/usr/local/sbin/fda_idle_watchdog.sh <<'WATCHDOG'
@WATCHDOG@
WATCHDOG
chmod 755 /usr/local/sbin/fda_idle_watchdog.sh
cat >/etc/systemd/system/fda-idle-watchdog.service <<'UNIT'
[Unit]
Description=FDA burst: shut down when idle
[Service]
Environment=IDLE_MINUTES=@IDLE_MINUTES@
ExecStart=/usr/local/sbin/fda_idle_watchdog.sh
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now fda-idle-watchdog.service

#!/bin/bash

# Run this script with sudo to set up the systemd services for PaperMC and playit.gg
# Usage: sudo bash setup_services.sh

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo)"
  exit 1
fi

cat <<EOF > /etc/systemd/system/papermc.service
[Unit]
Description=PaperMC Minecraft Server
After=network.target

[Service]
User=root
WorkingDirectory=/wdc/PaperMC
# We read the max RAM setting dynamically from a config or just use the default.
# The Django app should rewrite this ExecStart line when RAM changes, or we use a start script.
# For simplicity, we call a start.sh script that Django updates, or Django updates this unit file.
ExecStart=/bin/bash /wdc/PaperMC/start.sh
Restart=on-failure
SuccessExitStatus=143

[Install]
WantedBy=multi-user.target
EOF

# Create a default start.sh in /wdc/PaperMC
mkdir -p /wdc/PaperMC
if [ ! -f /wdc/PaperMC/start.sh ]; then
    echo "java -Xms1024M -Xmx4096M -jar paper.jar --nogui" > /wdc/PaperMC/start.sh
    chmod +x /wdc/PaperMC/start.sh
fi

cat <<EOF > /etc/systemd/system/playit.service
[Unit]
Description=Playit.gg Tunnel
After=network.target

[Service]
User=root
ExecStart=/usr/bin/playit
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "Systemd services for papermc and playit have been installed."
echo "You can now control them via the web app."

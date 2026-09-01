#!/bin/bash
# Setup passwordless sudo for systemctl commands needed by mcmanager

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (using sudo)"
  exit 1
fi

# Detect the real user who invoked sudo
REAL_USER=${SUDO_USER:-$(whoami)}

SUDOERS_FILE="/etc/sudoers.d/mcmanager_services"

echo "Granting passwordless sudo for $REAL_USER to control papermc and playit..."

cat <<EOF > $SUDOERS_FILE
$REAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl start papermc, /bin/systemctl stop papermc, /bin/systemctl restart papermc, /bin/systemctl is-active papermc
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start papermc, /usr/bin/systemctl stop papermc, /usr/bin/systemctl restart papermc, /usr/bin/systemctl is-active papermc
$REAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl start playit, /bin/systemctl stop playit, /bin/systemctl restart playit, /bin/systemctl is-active playit
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start playit, /usr/bin/systemctl stop playit, /usr/bin/systemctl restart playit, /usr/bin/systemctl is-active playit
EOF

chmod 0440 $SUDOERS_FILE

echo "Successfully configured sudoers in $SUDOERS_FILE"

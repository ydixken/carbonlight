#!/usr/bin/env bash
# carbonlight uninstall. Removes binary and service unit; preserves /etc/carbonlight.toml.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  exec sudo "$0" "$@"
fi

systemctl disable --now carbonlight.service 2>/dev/null || true
rm -f /etc/systemd/system/carbonlight.service
rm -f /usr/local/bin/carbonlight
systemctl daemon-reload

echo "Removed /usr/local/bin/carbonlight and /etc/systemd/system/carbonlight.service."
echo "/etc/carbonlight.toml left in place (delete manually if desired)."

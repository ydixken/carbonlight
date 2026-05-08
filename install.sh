#!/usr/bin/env bash
# carbonlight system install. Idempotent. Requires root.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "run as root: sudo $0" >&2
  exit 1
fi

cd "$(dirname "$(readlink -f "$0")")"

# 1. Dependency check ---------------------------------------------------------
if ! /usr/bin/python3 -c 'import evdev' 2>/dev/null; then
  echo "ERROR: python3-evdev is required but not installed for /usr/bin/python3."
  echo "Install with one of:"
  if   command -v apt    >/dev/null 2>&1; then echo "  sudo apt install python3-evdev"
  elif command -v dnf    >/dev/null 2>&1; then echo "  sudo dnf install python3-evdev"
  elif command -v pacman >/dev/null 2>&1; then echo "  sudo pacman -S python-evdev"
  elif command -v zypper >/dev/null 2>&1; then echo "  sudo zypper install python3-evdev"
  else echo "  pip install evdev   # in a venv, or your distro's package manager"; fi
  exit 1
fi

# 2. Detect a backlight LED ---------------------------------------------------
LED="/sys/class/leds/tpacpi::kbd_backlight"
if [[ ! -e "$LED" ]]; then
  shopt -s nullglob
  cand=( /sys/class/leds/*kbd_backlight* )
  if (( ${#cand[@]} == 0 )); then
    echo "ERROR: no keyboard backlight LED found under /sys/class/leds/" >&2
    echo "If your laptop has one under a different name, set led_path in" >&2
    echo "/etc/carbonlight.toml after install." >&2
    exit 1
  fi
  LED="${cand[0]}"
  echo "WARN: tpacpi::kbd_backlight not found; using $LED."
  echo "      If wrong, edit /etc/carbonlight.toml and set led_path explicitly."
fi
echo "Detected LED: $LED  (max=$(cat "$LED/max_brightness" 2>/dev/null || echo "?"))"

# 3. Install files ------------------------------------------------------------
install -m 0755 carbonlight.py /usr/local/bin/carbonlight
install -m 0644 carbonlight.service /etc/systemd/system/carbonlight.service
if [[ ! -f /etc/carbonlight.toml ]]; then
  install -m 0644 carbonlight.toml /etc/carbonlight.toml
  echo "Wrote default config to /etc/carbonlight.toml"
else
  echo "Keeping existing /etc/carbonlight.toml"
fi

# 4. Enable and start ---------------------------------------------------------
systemctl daemon-reload
systemctl enable --now carbonlight.service

# 5. Verify -------------------------------------------------------------------
sleep 1
if systemctl is-active --quiet carbonlight.service; then
  echo
  echo "carbonlight is installed and running."
  echo "Press a key on your keyboard. The backlight should illuminate."
  echo "Logs:    journalctl -u carbonlight.service -f"
  echo "Tweak:   sudo \$EDITOR /etc/carbonlight.toml && sudo systemctl restart carbonlight"
else
  echo "ERROR: service failed to start."
  echo "Check:   journalctl -u carbonlight.service -n 50" >&2
  exit 1
fi

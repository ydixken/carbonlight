# carbonlight

> Mac-like activity-driven keyboard backlight for ThinkPad laptops on Linux.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org)

A small system daemon that lights up your ThinkPad's keyboard the way macOS
does: any keypress, mouse move, or trackpad touch turns it on; a few seconds of
inactivity fade it off again. Manual `Fn+Space` cycles are honored as the new
target level.

No background polling, no GUI, no DBus. Just an `evdev` epoll loop and one
`/sys` write per state change.

---

## Why?

Out of the box on Linux the ThinkPad keyboard backlight is a manual toggle
(`Fn+Space` cycles off → low → high → off). That's fine, but if you've used a
MacBook you know the convenience of having it react to your hands without
thought. carbonlight does the activity-driven half of that experience.

What carbonlight does **not** do (yet, by design):

- **No ambient-light gating.** Most laptops — including the X1 Carbon Gen 13
  this was developed on — don't expose an ALS to Linux. Adding a webcam-
  luminance or time-of-day substitute is on the roadmap.
- **No smooth fade.** ThinkPad backlights have only 0/1/2 levels in hardware.
  The "fade" is one or two stepped transitions, not a continuous ramp.

---

## Compatibility

| Status | Hardware / Software |
| --- | --- |
| Tested | ThinkPad X1 Carbon Gen 13, Ubuntu 25.10, kernel 6.17, Python 3.13 |
| Should work | Any ThinkPad with `tpacpi::kbd_backlight` (most of them); other vendors that expose a `*kbd_backlight*` LED under `/sys/class/leds/` |
| Won't work | Hardware where the backlight isn't a Linux LED class device |

If `cat /sys/class/leds/*kbd_backlight*/max_brightness` prints a number, you're
in business.

---

## Install

```bash
git clone https://github.com/ydixken/carbonlight.git
cd carbonlight
sudo make install
```

The installer checks for `python3-evdev`, autodetects the LED, drops the binary
to `/usr/local/bin/`, the config to `/etc/carbonlight.toml`, the systemd unit
to `/etc/systemd/system/`, and enables the service.

If `python3-evdev` is missing, install it first:

| Distro | Command |
| --- | --- |
| Debian / Ubuntu | `sudo apt install python3-evdev` |
| Fedora | `sudo dnf install python3-evdev` |
| Arch | `sudo pacman -S python-evdev` |
| openSUSE | `sudo zypper install python3-evdev` |

---

## Configure

Edit `/etc/carbonlight.toml`:

```toml
target_level   = 1     # 0..max_brightness; ThinkPads cap at 2
idle_timeout_s = 5.0   # seconds of inactivity before fade-off
fade_step_s    = 0.12  # dwell per level during fade (only visible if target >= 2)
# led_path     = "/sys/class/leds/tpacpi::kbd_backlight"   # optional override
```

Apply:

```bash
sudo systemctl restart carbonlight
```

---

## Verify

```bash
sudo systemctl status carbonlight       # should be 'active (running)'
journalctl -u carbonlight -n 20         # should list watched devices
carbonlight --list-devices              # quick read-only sanity check
```

Then press a key. Backlight should light up. Stop touching the laptop for
`idle_timeout_s` seconds — backlight should fade.

If something's off, run `carbonlight --debug` directly to see per-event logs:

```bash
sudo systemctl stop carbonlight
sudo /usr/local/bin/carbonlight --debug
```

---

## Uninstall

```bash
sudo make uninstall
```

`/etc/carbonlight.toml` is left in place so a re-install picks up your
settings. Remove it manually if you want a clean slate.

---

## How it works

- A single Python process registers each watched input device's fd with `epoll`.
- On any input → snap LED to `target_level`, reset the idle timer.
- After `idle_timeout_s` → fade `current → 0` with `fade_step_s` per step.
- A self-pipe via `signal.set_wakeup_fd` makes `epoll.poll()` signal-aware
  (PEP 475 otherwise auto-restarts blocking syscalls).
- The LED's `brightness_hw_changed` sysfs file is polled by mtime so manual
  `Fn+Space` cycles snapshot a new target instead of being clobbered.

See [`docs/DESIGN.md`](docs/DESIGN.md) for more.

---

## Caveats

- **No ambient light gating.** Not enough laptops expose ALS to Linux. See the
  roadmap.
- **Fade granularity is hardware-bound.** ThinkPads have 3 levels (0/1/2).
  Fade-out from `target_level=1` is a single step; from `target_level=2` you'll
  see one intermediate dwell.
- **Hot-plugged USB keyboards aren't auto-discovered.** The daemon enumerates
  devices at startup. After plugging an external keyboard, run
  `sudo systemctl restart carbonlight` to pick it up.
- **Suspend/resume.** The kernel resets the LED on resume; the daemon
  reconverges on the next event.

---

## Roadmap

- Hot-plug discovery via `pyudev`.
- Optional ALS substitutes:
  - Time-of-day gating (sunrise/sunset)
  - Webcam-frame luminance probe (privacy trade-off documented)
- D-Bus interface for live-reload and external controls.
- Verified vendor coverage: Dell, Asus, MSI, MacBook (Linux).
- Distro packages (`.deb`, AUR `PKGBUILD`).

---

## Contributing

PRs welcome. To work on this:

```bash
git clone https://github.com/ydixken/carbonlight.git
cd carbonlight
make lint                 # ruff + py_compile
make test                 # unit tests, no hardware required
sudo make test-smoke      # end-to-end via uinput, root + python3-evdev
```

Smoke tests can't run in CI because they need `/dev/uinput`. CI runs lint and
unit tests only.

For substantive changes, please open an issue first to discuss the design.

---

## License

MIT — see [LICENSE](LICENSE).

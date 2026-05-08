# Hardware notes

## Supported LEDs

carbonlight talks to a kernel LED class device — anything matching the glob
`/sys/class/leds/*kbd_backlight*`. Common naming by vendor:

| Vendor | LED name | Notes |
| --- | --- | --- |
| Lenovo / ThinkPad | `tpacpi::kbd_backlight` | Provided by the `thinkpad_acpi` module. Default for carbonlight. |
| Dell | `dell::kbd_backlight` | Provided by `dell-laptop`. Often supports more levels (0..3). |
| Asus | `asus::kbd_backlight` | Provided by `asus-wmi` / `asus-nb-wmi`. |
| Apple (running Linux) | `smc::kbd_backlight` | Provided by `applesmc`. Many discrete levels. |
| Generic | `platform::kbd_backlight` | Generic platform driver fallback. |

If your laptop is in this list, carbonlight should autodetect the LED and just
work. If not, find the right path under `/sys/class/leds/`, set it explicitly
in `/etc/carbonlight.toml`:

```toml
led_path = "/sys/class/leds/your::kbd_backlight"
```

## Probing your hardware

```bash
# Does a kbd backlight exist?
ls /sys/class/leds/ | grep -i kbd

# How many levels?
cat /sys/class/leds/*kbd_backlight*/max_brightness

# Try setting it manually
echo 1 | sudo tee /sys/class/leds/*kbd_backlight*/brightness
```

If `max_brightness` is `2`, fades will be coarse — the daemon can only do
0→1→2 transitions. If it's `4` or higher, fades look noticeably smoother with
`target_level >= 2`.

## Why no ambient-light sensor?

The macOS implementation of "Mac-like" keyboard backlight uses an ALS (ambient
light sensor) to skip activation entirely in bright rooms. On Linux, ALS
support is patchy. To check your machine:

```bash
ls /sys/bus/iio/devices/
for d in /sys/bus/iio/devices/iio:device*; do
  echo "$d: $(cat "$d/name" 2>/dev/null)"
  ls "$d" 2>/dev/null | grep -i illumin
done
```

You're looking for a device named `als` or attributes like `in_illuminance_*`.
On the development hardware (ThinkPad X1 Carbon Gen 13, Ubuntu 25.10) the only
HID sensors enumerated are `hinge` (lid angle) and `accel_3d` (3D
accelerometer) — no ALS.

If yours has one, that's good news for a future version. carbonlight v0.1
deliberately ignores ambient light to keep the dependency surface small.

## Input device coverage

carbonlight watches every device under `/dev/input/event*` that looks like an
intentional input source:

- **Typing keyboards** (have `KEY_A` in their `EV_KEY` capabilities).
- **Mice / trackpoints** (have `REL_X` / `REL_Y` axes).
- **Touchpads / touchscreens** (have `ABS_X` / `ABS_Y` axes).

It explicitly skips:

- **Bluetooth devices** (BUS_BLUETOOTH) so headset media keys don't wake
  the LED.
- **Buttons / switches** without typing keys (power button, lid switch,
  sleep button, video bus).

Hot-plugged USB keyboards/mice are **not** picked up automatically — discovery
runs once at startup. After plugging an external device, run
`sudo systemctl restart carbonlight`.

## Troubleshooting

```bash
# What devices is the daemon watching?
journalctl -u carbonlight -n 30

# Quick read-only check from the CLI
carbonlight --list-devices

# Verbose per-event logs (run in foreground, stop the service first)
sudo systemctl stop carbonlight
sudo /usr/local/bin/carbonlight --debug
```

If `--list-devices` prints fewer than expected, you may have a permission
problem. The daemon runs as root via the systemd unit, so it always has the
right access — but invoking it manually as your user requires membership in
the `input` group (which doesn't take effect until you re-login).

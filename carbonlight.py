#!/usr/bin/python3
"""carbonlight: Mac-like activity-driven keyboard backlight for ThinkPad laptops.

Watches keyboards/touchpads/trackpoints via evdev. On any input the LED snaps to
the configured target level. After idle_timeout_s of inactivity it fades down by
one level per fade_step_s. Manual brightness changes (Fn+Space on ThinkPads)
are detected via the LED's brightness_hw_changed sysfs attribute and become the
new target.

Project: https://github.com/ydixken/carbonlight
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import os
import select
import signal
import sys
import time
import tomllib
from pathlib import Path

import evdev
from evdev import ecodes

__version__ = "0.1.0"

DEFAULT_LED_PATH = "/sys/class/leds/tpacpi::kbd_backlight"
LED_GLOB = "/sys/class/leds/*kbd_backlight*"

DEFAULTS: dict[str, object] = {
    "target_level": 1,
    "idle_timeout_s": 5.0,
    "fade_step_s": 0.12,
    "led_path": "",
}

_DEFAULT_CONFIG_PATHS = [
    Path("/etc/carbonlight.toml"),
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def debug_enabled() -> bool:
    return bool(os.environ.get("CARBONLIGHT_DEBUG"))


def clamp_level(level: int | float, max_level: int) -> int:
    return max(0, min(max_level, int(level)))


def load_config(custom_paths: list[Path] | None = None) -> dict:
    """Load the first existing TOML config, falling back to DEFAULTS.

    Search order: explicit custom_paths if provided; otherwise /etc/carbonlight.toml
    then $XDG_CONFIG_HOME/carbonlight.toml (or ~/.config/carbonlight.toml).
    Unknown keys in the TOML are ignored. Malformed TOML is logged and skipped.
    """
    cfg = DEFAULTS.copy()
    if custom_paths is not None:
        candidates = list(custom_paths)
    else:
        candidates = list(_DEFAULT_CONFIG_PATHS)
        xdg = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        candidates.append(xdg / "carbonlight.toml")

    for p in candidates:
        if not p.exists():
            continue
        try:
            with p.open("rb") as f:
                user_cfg = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            log(f"config load failed ({p}): {e}; trying next")
            continue
        for k in DEFAULTS:
            if k in user_cfg:
                cfg[k] = user_cfg[k]
        log(f"loaded config from {p}")
        return cfg
    return cfg


def find_led_dir(config: dict) -> Path:
    """Locate the keyboard backlight LED directory under /sys/class/leds.

    Preference order:
      1. config["led_path"] if set (caller's explicit override).
      2. /sys/class/leds/tpacpi::kbd_backlight (ThinkPad default).
      3. First glob match for /sys/class/leds/*kbd_backlight*.
    """
    explicit = config.get("led_path") or ""
    if explicit:
        return Path(explicit)
    default = Path(DEFAULT_LED_PATH)
    if default.exists():
        return default
    matches = sorted(glob.glob(LED_GLOB))
    if matches:
        return Path(matches[0])
    raise RuntimeError(
        f"no keyboard backlight LED found under {LED_GLOB}. "
        "Set 'led_path' in /etc/carbonlight.toml."
    )


def write_brightness(level: int, max_level: int, brightness_path: Path) -> None:
    try:
        brightness_path.write_text(str(clamp_level(level, max_level)))
    except OSError as e:
        log(f"backlight write failed: {e}")


def read_brightness(brightness_path: Path) -> int:
    try:
        return int(brightness_path.read_text().strip() or "0")
    except OSError:
        return 0


def has_abs_xy(caps: dict) -> bool:
    """True if EV_ABS capabilities include ABS_X or ABS_Y.

    evdev returns ABS caps as a list of (code, AbsInfo) tuples or bare ints
    depending on call style; handle both.
    """
    for entry in caps.get(ecodes.EV_ABS, []):
        code = entry[0] if isinstance(entry, tuple) else entry
        if code in (ecodes.ABS_X, ecodes.ABS_Y):
            return True
    return False


def is_relevant(dev: evdev.InputDevice) -> bool:
    """True if dev is a keyboard, mouse, trackpoint, or touchpad we should watch."""
    # Bluetooth AVRCP "keyboards" (e.g., headphone media keys) shouldn't wake the LED.
    if dev.info.bustype == ecodes.BUS_BLUETOOTH:
        return False
    caps = dev.capabilities(verbose=False)
    keys = caps.get(ecodes.EV_KEY, [])
    if ecodes.KEY_A in keys:
        return True
    rel = caps.get(ecodes.EV_REL, [])
    if ecodes.REL_X in rel or ecodes.REL_Y in rel:
        return True
    return has_abs_xy(caps)


def discover_devices() -> list[evdev.InputDevice]:
    devices: list[evdev.InputDevice] = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except (PermissionError, OSError) as e:
            log(f"skip {path}: {e}")
            continue
        if is_relevant(d):
            devices.append(d)
        else:
            d.close()
    return devices


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="carbonlight",
        description="Mac-like activity-driven keyboard backlight for ThinkPads.",
    )
    p.add_argument("--version", action="version", version=f"carbonlight {__version__}")
    p.add_argument(
        "--config", metavar="PATH",
        help="path to a TOML config file (overrides default search)",
    )
    p.add_argument("--debug", action="store_true", help="verbose logging")
    p.add_argument(
        "--list-devices", action="store_true",
        help="print the input devices that would be watched, then exit",
    )
    return p.parse_args(argv)


def run_daemon(cfg: dict) -> int:
    led_dir = find_led_dir(cfg)
    led_brightness = led_dir / "brightness"
    led_max = led_dir / "max_brightness"
    led_hw_changed = led_dir / "brightness_hw_changed"

    try:
        max_level = int(led_max.read_text().strip())
    except OSError as e:
        log(f"cannot read {led_max}: {e}")
        return 1

    target = clamp_level(int(cfg["target_level"]), max_level)
    idle = float(cfg["idle_timeout_s"])
    step = float(cfg["fade_step_s"])

    if not os.access(led_brightness, os.W_OK):
        log(
            f"no write access to {led_brightness}; "
            "service must run as root, or grant the user write access via tmpfiles.d"
        )
        return 1

    devices = discover_devices()
    if not devices:
        log("no input devices accessible; check permissions on /dev/input/event*")
        return 1
    log(
        f"watching {len(devices)} devices, target={target}/{max_level}, "
        f"idle={idle}s, step={step}s, led={led_dir}"
    )
    for d in devices:
        log(f"  - {d.path}: {d.name}")

    fd_to_dev = {d.fd: d for d in devices}
    poller = select.epoll()
    for fd in fd_to_dev:
        poller.register(fd, select.EPOLLIN)

    # Self-pipe so signals wake epoll.poll() (PEP 475 otherwise auto-restarts it).
    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_r, False)
    os.set_blocking(wake_w, False)
    signal.set_wakeup_fd(wake_w)
    poller.register(wake_r, select.EPOLLIN)

    hw_mtime = led_hw_changed.stat().st_mtime if led_hw_changed.exists() else 0.0

    current = read_brightness(led_brightness)
    awake = current > 0
    last_event = time.monotonic() if awake else 0.0
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)

    try:
        while running:
            timeout = max(0.0, last_event + idle - time.monotonic()) if awake else -1.0
            events = poller.poll(timeout if timeout >= 0 else None)

            # Detect manual override via hw_changed mtime advancing.
            if led_hw_changed.exists():
                try:
                    m = led_hw_changed.stat().st_mtime
                except OSError:
                    m = hw_mtime
                if m > hw_mtime:
                    hw_mtime = m
                    new_level = read_brightness(led_brightness)
                    if new_level > 0:
                        target = new_level
                        log(f"manual override -> target={target}")
                    current = new_level
                    awake = new_level > 0
                    last_event = time.monotonic()

            if events:
                input_event_seen = False
                event_sources: set[str] = set()
                for fd, _ in events:
                    if fd == wake_r:
                        with contextlib.suppress(BlockingIOError):
                            os.read(wake_r, 64)
                        continue
                    input_event_seen = True
                    event_sources.add(fd_to_dev[fd].name)
                    try:
                        for _ in fd_to_dev[fd].read():
                            pass
                    except (BlockingIOError, OSError):
                        pass
                if input_event_seen:
                    if debug_enabled():
                        log(f"event from: {sorted(event_sources)}")
                    last_event = time.monotonic()
                    if not awake or current != target:
                        write_brightness(target, max_level, led_brightness)
                        current = target
                        awake = True
            elif awake and time.monotonic() - last_event >= idle:
                while current > 0 and running:
                    current -= 1
                    write_brightness(current, max_level, led_brightness)
                    if current > 0:
                        time.sleep(step)
                awake = False
    finally:
        write_brightness(0, max_level, led_brightness)
        for d in devices:
            with contextlib.suppress(Exception):
                d.close()

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.debug:
        os.environ["CARBONLIGHT_DEBUG"] = "1"

    custom_paths = [Path(args.config)] if args.config else None
    cfg = load_config(custom_paths)

    if args.list_devices:
        devices = discover_devices()
        if not devices:
            log("no input devices accessible (try running as root)")
            return 1
        for d in devices:
            print(f"{d.path}\t{d.name}")
            d.close()
        return 0

    return run_daemon(cfg)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)

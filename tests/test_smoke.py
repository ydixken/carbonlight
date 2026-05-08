"""End-to-end smoke test using a synthetic uinput keyboard.

Requires: root privileges and python3-evdev. Skipped automatically otherwise.

The test drives a real running carbonlight binary from the repo (not the
installed copy at /usr/local/bin/) so changes can be tested before install.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DAEMON = REPO / "carbonlight.py"

requires_root = pytest.mark.skipif(
    os.geteuid() != 0,
    reason="needs root to access /dev/uinput and write to /sys/class/leds",
)


def _have_uinput() -> bool:
    return Path("/dev/uinput").exists()


def _have_kbd_backlight() -> Path | None:
    import glob as _glob
    matches = sorted(_glob.glob("/sys/class/leds/*kbd_backlight*"))
    return Path(matches[0]) if matches else None


@requires_root
def test_press_then_idle_then_wake():
    if not _have_uinput():
        pytest.skip("/dev/uinput not available")
    led_dir = _have_kbd_backlight()
    if led_dir is None:
        pytest.skip("no kbd_backlight LED on this host")

    import evdev
    from evdev import ecodes

    led = led_dir / "brightness"
    saved = led.read_text().strip()
    led.write_text("0")

    cfg_dir = Path(tempfile.mkdtemp(prefix="carbonlight-smoketest-"))
    cfg_path = cfg_dir / "carbonlight.toml"
    cfg_path.write_text(
        f'target_level = 1\nidle_timeout_s = 1.5\nfade_step_s = 0.05\n'
        f'led_path = "{led_dir}"\n'
    )

    ui = evdev.UInput({ecodes.EV_KEY: [ecodes.KEY_A]}, name="carbonlight-smoketest")
    time.sleep(0.4)

    try:
        proc = subprocess.Popen(
            [sys.executable, str(DAEMON), "--config", str(cfg_path)],
            stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
        )
        try:
            time.sleep(1.0)
            assert proc.poll() is None, (
                f"daemon exited prematurely (rc={proc.returncode}): "
                f"{proc.stderr.read().decode() if proc.stderr else ''}"
            )

            ui.write(ecodes.EV_KEY, ecodes.KEY_A, 1)
            ui.syn()
            time.sleep(0.05)
            ui.write(ecodes.EV_KEY, ecodes.KEY_A, 0)
            ui.syn()
            time.sleep(0.3)
            after_press = int(led.read_text().strip() or "0")

            time.sleep(2.0)  # idle 1.5s + safety
            after_idle = int(led.read_text().strip() or "0")

            ui.write(ecodes.EV_KEY, ecodes.KEY_A, 1)
            ui.syn()
            time.sleep(0.05)
            ui.write(ecodes.EV_KEY, ecodes.KEY_A, 0)
            ui.syn()
            time.sleep(0.3)
            after_wake = int(led.read_text().strip() or "0")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    finally:
        ui.close()
        led.write_text(saved)

    assert after_press == 1, f"expected LED=1 after keypress, got {after_press}"
    assert after_idle == 0, f"expected LED=0 after idle, got {after_idle}"
    assert after_wake == 1, f"expected LED=1 after wake-from-idle, got {after_wake}"

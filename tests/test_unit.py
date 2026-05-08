"""Unit tests that don't require any hardware or root privileges."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from evdev import ecodes

import carbonlight
from carbonlight import (
    DEFAULTS,
    clamp_level,
    find_led_dir,
    has_abs_xy,
    is_relevant,
    load_config,
)

# ---- clamp_level -----------------------------------------------------------

def test_clamp_level_inside_range_unchanged():
    assert clamp_level(1, 2) == 1


def test_clamp_level_caps_to_max():
    assert clamp_level(5, 2) == 2


def test_clamp_level_floors_at_zero():
    assert clamp_level(-3, 2) == 0


def test_clamp_level_coerces_floats():
    assert clamp_level(1.7, 2) == 1


# ---- load_config -----------------------------------------------------------

def test_load_config_returns_defaults_when_no_files(tmp_path):
    cfg = load_config(custom_paths=[tmp_path / "nope.toml"])
    assert cfg["target_level"] == DEFAULTS["target_level"]
    assert cfg["idle_timeout_s"] == DEFAULTS["idle_timeout_s"]
    assert cfg["fade_step_s"] == DEFAULTS["fade_step_s"]
    assert cfg["led_path"] == DEFAULTS["led_path"]


def test_load_config_user_override_wins(tmp_path):
    p = tmp_path / "carbonlight.toml"
    p.write_text("target_level = 2\nidle_timeout_s = 10.0\n")
    cfg = load_config(custom_paths=[p])
    assert cfg["target_level"] == 2
    assert cfg["idle_timeout_s"] == 10.0
    # untouched keys keep defaults
    assert cfg["fade_step_s"] == DEFAULTS["fade_step_s"]


def test_load_config_invalid_toml_falls_back_to_defaults(tmp_path):
    p = tmp_path / "carbonlight.toml"
    p.write_text("not valid = toml = at all = {")
    cfg = load_config(custom_paths=[p])
    assert cfg == DEFAULTS


def test_load_config_unknown_keys_ignored(tmp_path):
    p = tmp_path / "carbonlight.toml"
    p.write_text('target_level = 1\nbogus_key = "hello"\n')
    cfg = load_config(custom_paths=[p])
    assert "bogus_key" not in cfg


def test_load_config_first_existing_wins(tmp_path):
    a = tmp_path / "a.toml"
    b = tmp_path / "b.toml"
    a.write_text("target_level = 2\n")
    b.write_text("target_level = 0\n")
    cfg = load_config(custom_paths=[a, b])
    assert cfg["target_level"] == 2


# ---- has_abs_xy ------------------------------------------------------------

def test_has_abs_xy_finds_x_in_tuple_caps():
    caps = {ecodes.EV_ABS: [(ecodes.ABS_X, object())]}
    assert has_abs_xy(caps) is True


def test_has_abs_xy_finds_y_in_int_caps():
    caps = {ecodes.EV_ABS: [ecodes.ABS_Y]}
    assert has_abs_xy(caps) is True


def test_has_abs_xy_returns_false_when_no_xy():
    caps = {ecodes.EV_ABS: [(ecodes.ABS_PRESSURE, object())]}
    assert has_abs_xy(caps) is False


def test_has_abs_xy_handles_missing_ev_abs():
    assert has_abs_xy({}) is False


# ---- is_relevant -----------------------------------------------------------

def _fake_dev(bustype: int, caps: dict):
    """Fake evdev.InputDevice for filter tests."""
    return SimpleNamespace(
        info=SimpleNamespace(bustype=bustype),
        capabilities=lambda verbose=False: caps,
    )


def test_is_relevant_typing_keyboard():
    dev = _fake_dev(ecodes.BUS_I8042, {ecodes.EV_KEY: [ecodes.KEY_A, ecodes.KEY_B]})
    assert is_relevant(dev) is True


def test_is_relevant_pointer_with_rel_x():
    dev = _fake_dev(ecodes.BUS_I2C, {ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y]})
    assert is_relevant(dev) is True


def test_is_relevant_touchpad_with_abs_xy():
    dev = _fake_dev(ecodes.BUS_I2C, {ecodes.EV_ABS: [(ecodes.ABS_X, object())]})
    assert is_relevant(dev) is True


def test_is_relevant_filters_bluetooth_avrcp():
    # A Bluetooth headset reporting media keys shouldn't wake the LED.
    dev = _fake_dev(
        ecodes.BUS_BLUETOOTH,
        {ecodes.EV_KEY: [ecodes.KEY_PLAYPAUSE, ecodes.KEY_NEXTSONG]},
    )
    assert is_relevant(dev) is False


def test_is_relevant_filters_power_button():
    # Power button has KEY_POWER but no KEY_A — not a typing keyboard.
    dev = _fake_dev(0, {ecodes.EV_KEY: [ecodes.KEY_POWER]})
    assert is_relevant(dev) is False


def test_is_relevant_filters_lid_switch():
    # Lid switches have EV_SW only.
    dev = _fake_dev(0, {ecodes.EV_SW: [ecodes.SW_LID]})
    assert is_relevant(dev) is False


# ---- find_led_dir ----------------------------------------------------------

def test_find_led_dir_uses_explicit_override():
    assert find_led_dir({"led_path": "/sys/class/leds/foo::kbd_backlight"}) == Path(
        "/sys/class/leds/foo::kbd_backlight"
    )


def test_find_led_dir_returns_default_when_present(monkeypatch, tmp_path):
    fake_default = tmp_path / "tpacpi::kbd_backlight"
    fake_default.mkdir()
    monkeypatch.setattr(carbonlight, "DEFAULT_LED_PATH", str(fake_default))
    monkeypatch.setattr(carbonlight, "LED_GLOB", str(tmp_path / "*kbd_backlight*"))
    assert find_led_dir({"led_path": ""}) == fake_default


def test_find_led_dir_falls_back_to_glob(monkeypatch, tmp_path):
    monkeypatch.setattr(
        carbonlight, "DEFAULT_LED_PATH", str(tmp_path / "missing")
    )
    other = tmp_path / "asus::kbd_backlight"
    other.mkdir()
    monkeypatch.setattr(carbonlight, "LED_GLOB", str(tmp_path / "*kbd_backlight*"))
    assert find_led_dir({"led_path": ""}) == other


def test_find_led_dir_raises_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.setattr(carbonlight, "DEFAULT_LED_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(carbonlight, "LED_GLOB", str(tmp_path / "*kbd_backlight*"))
    with pytest.raises(RuntimeError):
        find_led_dir({"led_path": ""})


# ---- CLI sanity ------------------------------------------------------------

def test_parse_args_version(capsys):
    with pytest.raises(SystemExit) as exc:
        carbonlight.parse_args(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "carbonlight" in out and carbonlight.__version__ in out


def test_parse_args_defaults():
    args = carbonlight.parse_args([])
    assert args.config is None
    assert args.debug is False
    assert args.list_devices is False


def test_parse_args_flags():
    args = carbonlight.parse_args(["--config", "/tmp/x.toml", "--debug", "--list-devices"])
    assert args.config == "/tmp/x.toml"
    assert args.debug is True
    assert args.list_devices is True

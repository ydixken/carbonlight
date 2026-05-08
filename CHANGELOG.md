# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-08

### Added
- Initial release. Activity-driven keyboard backlight daemon for ThinkPads
  with `tpacpi::kbd_backlight`.
- Autodetection of `*kbd_backlight*` LEDs on other vendors (Dell, Asus, …).
- Configurable target level, idle timeout, and fade step via
  `/etc/carbonlight.toml`.
- Manual brightness override (Fn+Space on ThinkPads) honored as the new
  target via `brightness_hw_changed` mtime detection.
- CLI: `--config`, `--debug`, `--list-devices`, `--version`.
- Hardened systemd system service.
- Smoke test using a virtual `uinput` keyboard.

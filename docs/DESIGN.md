# Design

A short tour of why carbonlight is shaped the way it is. Useful if you're
considering a contribution.

## Control flow

```
                  ┌──────────────────────────────┐
                  │   epoll.poll(timeout=remaining_idle)
                  └──────┬───────────────────────┘
                         ▼
            ┌─────────────────────────────┐
            │   any input event?          │
            └────────┬────────────────────┘
                  yes │           no │ (timeout)
                     ▼              ▼
        ┌──────────────────┐    ┌────────────────────┐
        │ drain reads;     │    │ awake && idle      │
        │ LED ← target;    │    │ exceeded?          │
        │ reset last_event │    └────┬───────────────┘
        └──────────────────┘         ▼
                                ┌─────────────────────┐
                                │ fade: current--     │
                                │ until 0, sleeping   │
                                │ fade_step_s between │
                                └─────────────────────┘
```

Each iteration also checks `brightness_hw_changed`'s mtime. If it advanced,
some other process (most likely the user pressing Fn+Space) changed the LED;
we snapshot the new value and use it as the new `target` for subsequent
activity-driven cycles.

## Why `signal.set_wakeup_fd`

[PEP 475](https://peps.python.org/pep-0475/) says CPython auto-restarts
`epoll.poll()` after a signal, which means SIGTERM doesn't return from the
syscall. The daemon would hang on shutdown until the next input event.

The fix is to register a side-channel pipe:

```python
wake_r, wake_w = os.pipe()
os.set_blocking(wake_r, False)
os.set_blocking(wake_w, False)
signal.set_wakeup_fd(wake_w)
poller.register(wake_r, select.EPOLLIN)
```

When a signal arrives, Python writes the signal number to `wake_w`, which
makes `poll()` return immediately with `wake_r` ready. The handler has run by
then, set `running = False`, and the next loop check exits.

## Why `/usr/bin/python3` (not `/usr/bin/env python3`)

Many Linux setups (Linuxbrew, conda, pyenv, asdf) put a different Python
ahead of `/usr/bin/python3` in `PATH`. Those Pythons typically don't have
`python3-evdev` (a system package) installed.

We pin the system interpreter so the system-installed module is always found.

## Why a system service (not a user service)

The daemon needs to read `/dev/input/event*` (group `input`) and write to
`/sys/class/leds/*/brightness` (root or a permission rule). Two paths:

1. **System service** (current): runs as root, no permission ceremony, works
   immediately. The trade-off is a root-owned daemon — but it's hardened
   (`ProtectSystem=strict`, `NoNewPrivileges`, `RestrictAddressFamilies=AF_UNIX`,
   …) and reads ~250 lines of Python.
2. **User service**: runs as the logged-in user, needs `input` group
   membership and a writable LED. The blocker is that adding a user to a
   group via `gpasswd` doesn't propagate to the already-running
   `systemd --user` manager — a full re-login is required. That's a hostile
   onboarding experience for a small tool.

System service won.

## Why direct sysfs (not DBus / UPower)

GNOME's `org.gnome.SettingsDaemon.Power.Keyboard` interface exists but is
empty on the development hardware. `upowerd` doesn't manage keyboard
backlights generically. Going through DBus would mean reimplementing what
sysfs already does — at the cost of an extra dependency that may or may not
be running on a given setup.

Sysfs is universal, fast, and obvious.

## Why no ambient-light gating

The Mac behavior the user remembers has two parts: activity-driven on/off
*and* ambient-gated suppression in bright rooms. On Linux, ALS exposure is
spotty. Many laptops (including the X1 Carbon Gen 13 this was developed on)
expose only hinge and accelerometer sensors — no illuminance.

Three substitutes that may land in a future version:

- **Time-of-day gate.** Coarsest. ~15 LoC. No new dependencies.
- **Webcam luminance probe.** Closest to true ALS, but uses the camera every
  ~30 s with the indicator LED behavior that implies. Privacy trade-off.
- **`hinge` sensor heuristic.** If the lid is barely open (laptop closed-ish),
  skip activation. Available on this hardware. Low signal-to-noise for the
  use case.

For v0.1, none of these. The activity half is the bulk of the perceived
benefit anyway, and a "no ALS" daemon is more portable.

## Code organization

A single Python file. The whole daemon fits in ~280 lines; splitting it into
modules adds friction for readers and contributors without a payoff. If the
project grows past ~600 lines, that calculus changes.

Key functions are pure and individually testable:

- `clamp_level(level, max_level)` — bounds-check helper.
- `load_config(custom_paths=None)` — TOML loader with explicit-paths override.
- `find_led_dir(config)` — LED autodetection with override.
- `is_relevant(dev)` / `has_abs_xy(caps)` — device filter.

The main loop in `run_daemon(cfg)` is sequential and side-effecting, with
test coverage via the uinput-based smoke test.

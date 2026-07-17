# Rigol Oscilloscope Controller

A Tkinter-based GUI for controlling Rigol digital oscilloscopes over USB via SCPI/VISA. Provides channel configuration, trigger setup, horizontal/vertical scaling, live waveform preview, and screenshot capture — without needing to type raw SCPI commands.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Auto-discovery** — scans connected USB VISA resources and identifies a Rigol scope automatically (no manual VISA address entry required)
- **Channel control** — per-channel coupling (AC/DC/GND), probe attenuation (0.1x–10x), vertical scale (V/div), and signal invert
- **Trigger control** — edge trigger source, slope, coupling, level, and sweep mode (AUTO/NORMAL/SINGLE)
- **Horizontal control** — time/div configuration
- **Live view** — polls the scope display every 500ms and renders it inline in the GUI
- **Screenshot capture** — saves PNG snapshots to disk with timestamped filenames
- **Raw SCPI console** — send arbitrary SCPI write/query commands for anything not covered by the UI
- **Event log** — timestamped terminal-style log of every action and error

## Supported Hardware

Built and tested against the **Rigol DHO800 series** (DHO802 / DHO804 / DHO812 / DHO814).

The connection logic currently identifies any instrument whose `*IDN?` response contains `"RIGOL"` — this means other Rigol product lines (signal generators, power supplies) could technically be picked up if connected, since the check does not confirm the device is an oscilloscope. If you're running this against hardware other than a DHO800-series scope, verify the SCPI commands in `Scope` against your model's programming manual before use — command syntax (e.g. `:DISPlay:SNAP?`, `:TRIGger:EDGe:...`) can vary between Rigol product families and firmware versions.

### Extending to newer models

To add support for a new Rigol scope model:

1. Confirm the model's SCPI command set matches (or update) the commands in the `Scope` class — check the manufacturer's programming guide for differences, especially around trigger subsystems and screenshot commands.
2. Update the model-matching logic in `find_rigol_instrument` to include the new model string.
3. Test `capture_screenshot` separately first — binary block transfer commands are the most likely to differ between firmware versions.

## Requirements

- Python 3.9+
- A Rigol oscilloscope connected via USB, with the instrument in USBTMC mode

### Dependencies

```
pyvisa
pyvisa-py
Pillow
```

Install with:

```bash
pip install pyvisa pyvisa-py Pillow
```

> **Note:** This project uses the pure-Python VISA backend (`pyvisa-py`), so no separate NI-VISA driver installation is required. On Linux, you may need USB permissions (e.g. a udev rule) to access the instrument without root.

## Usage

```bash
python scope_gui.py
```

1. Click **CONNECT** — the app scans USB VISA resources and connects to the first Rigol scope found.
2. Select a channel via the **Configure CH1–CH4** radio buttons, then adjust coupling, probe attenuation, or vertical scale from the dropdowns.
3. Configure trigger source, slope, coupling, and level in the **Trigger Configure** panel.
4. Use **RUN** / **STOP** to control acquisition, or select a sweep mode (AUTO/NORMAL/SINGLE).
5. Click **CAPTURE SCREENSHOT** to save the current display as a PNG (saved to `./screenshots/`), or **START LIVE VIEW** for a continuously refreshing preview.
6. Use the **SCPI COMMANDS** field to send raw commands directly — append `?` to send a query instead of a write.

## Project Structure

The code is split into two layers:

| Class | Responsibility |
|---|---|
| `Scope` | All hardware I/O — VISA connection, SCPI writes/queries, screenshot capture, file saving. No GUI dependencies. |
| `ScopeApp` | All Tkinter widgets and event handlers. Never talks to `pyvisa` directly — always goes through a `Scope` instance. |

This separation means `Scope` can be reused independently of the GUI (e.g. in a script or test harness).

## Known Limitations

- `trigger_level()` writes to the `:TRIGger:PULSe:LEVel` SCPI subsystem, while trigger source/slope/coupling all use `:TRIGger:EDGe:...`. If you're using edge triggering (the default), verify this matches your firmware's expected command — some Rigol models expect `:TRIGger:EDGe:LEVel` instead.
- Screenshot filenames are timestamped to the second; two captures within the same second will overwrite each other.
- The `./screenshots` save directory is hardcoded (not configurable from the UI).
- `find_rigol_instrument` connects to the *first* Rigol device found on USB; if multiple Rigol instruments are connected, which one gets selected is not deterministic.

## License

MIT

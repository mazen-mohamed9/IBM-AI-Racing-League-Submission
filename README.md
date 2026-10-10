# AI Racing Submission — TORCS Python Client

**Script:** `finale.py`
**Dependency:** `race_analyzer.py` (optional live telemetry logger, imported at runtime)
**Evidence:** `telemetry_20261010_161003.csv` (per-step telemetry from a recorded run)

---

## Setup Requirements

- **Python 3.6+** — no additional packages required for the base client
- **TORCS** with the **SCR (Simulated Car Racing)** patch installed
  - Platform: **Linux recommended** (auto-relaunch uses `pkill torcs`)
  - On Windows/macOS the client connects and drives normally; auto-relaunch on connection failure is disabled (a human-readable message is printed instead)
- **`xte`** (X11 tool-emulator) — used by `autostart.sh` to navigate the TORCS GUI and start the race; not required if the race is started manually
- `matplotlib` — **optional**; if installed, `race_analyzer.py` saves a telemetry PNG alongside the CSV on shutdown; silently skipped if absent

---

## Run Command

```bash
# 1. Start TORCS in SCR mode (Linux)
torcs -nofuel -nodamage -nolaptime &
sh autostart.sh          # navigates the TORCS GUI to start the practice race

# 2. In a separate terminal, run the client
python finale.py

# With explicit port (required in race / competition mode)
python finale.py --port 3001

# With debug telemetry printed each tick
python finale.py --debug

# Limit to ~1 lap on Corkscrew (~1 600 steps)
python finale.py --steps 2000
```

TORCS listens on **UDP port 3001** by default.  
The port must be passed via `--port` / `-p`; it is **never hardcoded** (competition rule).

---

## Results

| Metric | Value |
|---|---|
| Track | Corkscrew (est. 3 608 m) |
| Total steps recorded | 500 000 |
| Run duration | 149.7 s |
| Top speed | 228.7 km/h |
| Average speed | 203.0 km/h |
| Total damage | 0 |
| Turns detected | 8 |
| Laps completed (via lastLapTime) | 1 |
| Telemetry CSV | `telemetry_20261010_161003.csv` |
| Demonstration video | `Demonstration viddeo.mp4` |

> **Note on lap count:** The `race_study.json` reports 1 completed lap via `lastLapTime`
> (1.464 s, 121 steps — this is the warm-up/identification phase lap registered by the SCR
> server before the car was fully rolling). The `distFromStart` wrap-around lap timer built
> into `finale.py` detects full 3 600 m laps; no full wrap-around lap was captured
> in the recorded CSV run, which started mid-track at `distFromStart ≈ 3 598 m`.
> The telemetry CSV covers the full 500 000-step run at ~50 Hz.

---

## File List

| File | Role |
|---|---|
| `finale.py` | Main racing client — run this to race |
| `race_analyzer.py` | Optional live telemetry recorder; auto-imported by `finale.py` |
| `autostart.sh` | Shell script to navigate the TORCS GUI and start the SCR race |
| `telemetry_20261010_161003.csv` | Real per-step telemetry CSV from a recorded run |
| `Lap report capstone.jpeg` | Lap report screenshot |
| `Demonstration viddeo.mp4` | Demonstration video |
| `README.md` | This file |
| `SUBMISSION.md` | Description, enhancements and Bob-use notes |

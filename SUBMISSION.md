# SUBMISSION.md

## Project Description

A hand-crafted, sensor-based Python driving agent for the TORCS racing simulator,
communicating over the SCR (Simulated Car Racing) UDP protocol.  The agent reads
19 track-edge distance sensors, vehicle speed, heading angle, and wheel-spin
velocities every ~20 ms (~50 Hz) and outputs throttle, brake, steering, gear, and
clutch commands.

**Base code:** `snakeoil3_gym(baseline).py` — the public SnakeOil3 reference client by Chris X Edwards (2013).
**Submission file:** `finale.py` — the racing-optimised build derived from that baseline.

---

## Enhancements Over Baseline

All changes are documented in `CHANGELOG.md` (in the parent repository).
The four classes of improvement are:

### FIX 1 — Dead return in `DriverAction.__repr__`
Removed an unreachable second `return out+'\n'` that followed the real `return out`.
No runtime impact, but eliminates a misleading line implying the server received a
trailing newline.

### FIX 2 — Dead block in `ServerState.__repr__`
Removed a raw-output block that was positioned after an unconditional
`return self.fancyout()`. It could never execute; removed for clarity.

### FIX 3 — Cross-platform auto-relaunch guard
`setup_connection()` previously called `os.system('pkill torcs')` unconditionally.
Now gated behind `sys.platform.startswith('linux')` — Windows/macOS get a
human-readable message instead of a silent OS error.

### FIX 4 — Straight-road swerving (four sub-fixes)

| Sub-fix | Change | Reason |
|---|---|---|
| 4a | Steering gain halved: `angle * 15/PI` → `angle * 7.5/PI` | Small heading-noise (~0.05 rad) was amplified to ±0.24 steer, causing swerve on straights |
| 4b | `sensor_asymmetry` term removed entirely | `max(track[0:5])` swings 0–200 m on straights, generating ~390 steer sign-flips per lap |
| 4c | `R['steer'] * 50` coupling removed from throttle comparison | Noisy steering was directly modulating engine output, causing surging in sync with swerve |
| 4d | Braking dead-band widened (+5 → +30 km/h) and divisor softened (70 → 120) | Earlier, harder braking was triggering 30+ m before corners; revised profile is later and gentler |

### NEW — Blind-apex speed floor
When `track_ahead ≤ 0` (sensor reads −1.0 at hairpin wall), `target_speed` is set to
55 km/h instead of computing `−1 × 2 = −2 km/h`. Validated: only 2 zones affected on
Corkscrew (152 total steps); max measured speed in those zones = 67.4 km/h.

### NEW — Gear threshold optimisation
Upshifts moved 10 km/h earlier (e.g. 2nd gear at >40 vs >50) to keep the engine
closer to peak power band through acceleration zones.

### NEW — Lap timing via `distFromStart` wrap detection
The SCR server's `lastLapTime` broadcast is unreliable. `finale.py` detects
lap completions by watching `distFromStart` drop from >85% to <15% of track length,
and records `curLapTime` at that moment.

### NEW — Optional `RaceAnalyzer` integration
`race_analyzer.py` is imported at startup (graceful fallback if absent).  It logs
every step to a timestamped CSV, detects incidents (off-track, damage spikes, near-edge),
identifies corners, builds a 50 m speed-zone map, and prints a full race report on exit.

### NEW — Robust main loop
The bare `for` loop is wrapped in `try / except KeyboardInterrupt / finally` to guarantee
socket shutdown and lap/analyzer summary output even on Ctrl-C.

---

## Bob Use

IBM Bob was used throughout this project for:

1. **Code investigation** — reading `snakeoil3_gym.py` and all intermediate
   scripts to identify the exact lines causing the swerve and throttle oscillation.

2. **Bug diagnosis** — Bob traced the swerve root cause to three coupled factors:
   the high `angle * 15/PI` gain, the `sensor_asymmetry` max() term, and the
   `R['steer'] * 50` throttle coupling. Each was isolated and fixed in sequence.

3. **Race-report generation** — Bob drafted `race_report.txt` from the code analysis
   and the `race_study.json` data produced by `race_analyzer.py`.

4. **CHANGELOG authoring** — Bob generated the full `CHANGELOG.md` diff table and
   per-fix explanations by comparing `snakeoil3_gym(baseline).py` against
   `finale.py`.

5. **Submission packaging** — Bob created this `ai-racing-submission/` folder,
   inspected all imports to identify required local dependencies, copied only the
   needed files, and drafted this `README.md` and `SUBMISSION.md`.

---

## Evidence

| Evidence item | File |
|---|---|
| Per-step telemetry CSV (real run, 500 000 steps) | `telemetry_20261010_161003.csv` |
| Lap report (screenshot) | `Lap report capstone.jpeg` |
| Demonstration video | `Demonstration viddeo.mp4` |

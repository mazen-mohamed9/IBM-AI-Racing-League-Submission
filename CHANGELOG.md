# CHANGELOG — `finale.py` vs `snakeoil3_gym.py`

> **Base file:** `snakeoil3_gym.py` (original SnakeOil3 library, version `20130505-2`)
> **New file:**  `finale.py` (racing-optimised build, same version string)

---

## Summary of Changes

| Area | `snakeoil3_gym.py` | `finale.py` |
|---|---|---|
| Max simulation steps | `100 000` | `500 000` |
| Track sensor angles | Narrow forward cone (`±45°` max) | Same narrow cone (unchanged) |
| Auto-relaunch guard | Runs `pkill torcs` on **all** platforms | Linux-only guard (`sys.platform`) |
| `ServerState.__repr__` | Dead code block after `return` | Dead code removed (FIX 2) |
| `DriverAction.__repr__` | Unreachable second `return out+'\n'` | Removed (FIX 1) |
| Steering gain | `angle * 15 / PI` (~4.77) | `angle * 7.5 / PI` (~2.39) — halved |
| Steer → throttle coupling | `target_speed - R['steer'] * 50` | Coupling removed entirely |
| Throttle accumulation step | `±0.01` per tick | `+0.03 / −0.01` (faster build-up) |
| Braking dead-band | `+5 km/h` over target | `+30 km/h` over target |
| Braking divisor | `70` | `120` (softer brake force) |
| Blind-apex handling | Falls through to negative `target_speed` | Hard floor `55 km/h` when `track_ahead ≤ 0` |
| Gear thresholds | 50 / 80 / 110 / 140 / 170 km/h | 40 / 70 / 100 / 130 / 160 km/h |
| Sensor-asymmetry steer hint | Present (added noise) | Removed |
| Lap timing | Not present | Added (distFromStart wrap detection) |
| Race analyzer integration | Not present | Optional `RaceAnalyzer` integration |
| Main loop structure | Bare `for` loop | `try/except KeyboardInterrupt / finally` |

---

## Detailed Change Log

### FIX 1 — Removed unreachable `return` in `DriverAction.__repr__`

**File:** `DriverAction.__repr__` (line ~496 in original)

```python
# snakeoil3_gym.py (before)
        return out
        return out+'\n'     # ← DEAD CODE — never reached

# finale.py (after)
        return out
        # FIX 1: Removed unreachable `return out+'\n'` that was here.
```

**Impact:** No runtime impact — the second `return` was unreachable — but removes
a misleading line that implied the server received a trailing newline.

---

### FIX 2 — Removed dead raw-output block in `ServerState.__repr__`

**File:** `ServerState.__repr__` (lines ~308–319 in original)

```python
# snakeoil3_gym.py (before)
    def __repr__(self):
        return self.fancyout()     # unconditional return
        out= str()                 # ← DEAD CODE — lines 312–319 never execute
        for k in sorted(self.d):
            ...

# finale.py (after)
    def __repr__(self):
        # FIX 2: Removed the unreachable raw-output block.
        return self.fancyout()
```

**Impact:** None at runtime. Removes ~8 lines of unreachable code.

---

### FIX 3 — Cross-platform auto-relaunch guard

**File:** `Client.setup_connection`

```python
# snakeoil3_gym.py (before)
    os.system('pkill torcs')          # crashes silently on Windows / macOS

# finale.py (after)
    if sys.platform.startswith('linux'):
        os.system('pkill torcs')
        ...
    else:
        print("Auto-relaunch is only supported on Linux. "
              "Please restart TORCS manually.")
```

**Impact:** Prevents a confusing silent failure when running on Windows or macOS.

---

### FIX 4a — Steering gain halved

**File:** `drive_example`

```python
# snakeoil3_gym.py
R['steer'] = S['angle'] * 15 / PI       # gain ≈ 4.77

# finale.py
R['steer'] = S['angle'] * 7.5 / PI      # gain ≈ 2.39
```

**Reason:** Small sensor-noise `angle` values (~0.05 rad) were amplified to
`±0.24` steer units by the high gain, causing the car to swerve on straights.
Halving the gain reduces this to `±0.12`.

---

### FIX 4b — Sensor-asymmetry steer hint removed

**File:** `drive_example`

A `(track_left - track_right) * factor` steer hint was introduced during
development of `finale.py` to lean toward the longer side sensor. With TORCS's
narrow forward-cone sensor layout this generated erratic `±1.0` steer spikes
(~390 sign flips per lap measured) because `max(track[0:5])` and
`max(track[14:19])` swing between near-zero and 200 m on every straight.
It was removed before final submission — it was never present in the baseline.

---

### FIX 4c — Steer → throttle coupling removed

**File:** `drive_example`

```python
# snakeoil3_gym.py
if S['speedX'] < target_speed - (R['steer'] * 50):
    R['accel'] += .01

# finale.py
if S['speedX'] < target_speed:
    R['accel'] += .03
```

**Reason:** `R['steer'] * 50` fed raw noisy steering directly into the throttle
comparison, causing the engine to surge and dip in sync with every steer twitch.
Removing this decouples throttle from steering entirely.

---

### FIX 4d — Braking: wider dead-band and softer force

**File:** `drive_example`

```python
# snakeoil3_gym.py — brake fires 5 km/h over target, hard force
if S['speedX'] > target_speed + 5:
    R['brake'] = clip((S['speedX'] - target_speed) / 70.0, 0, 1)

# finale.py — brake fires 30 km/h over target, softer
if S['speedX'] > target_speed + 30:
    R['brake'] = clip((S['speedX'] - target_speed) / 120.0, 0, 1)
```

**Reason:** The narrow dead-band caused the car to brake far too early on corner
approach (30+ metres early). Widening to +30 km/h and increasing the divisor
produces a later, gentler braking profile that preserves more entry speed.

---

### NEW — Dynamic `target_speed` formula

**File:** `drive_example`

```python
# snakeoil3_gym.py — flat constant
target_speed = 300

# finale.py — sensor-driven, with straight bonus and blind-apex floor
flank_max      = max(track_left, track_right)
if track_ahead > 0:
    straight_bonus = clip((flank_max - track_ahead) * 0.5, 0, 80)
    target_speed   = clip(track_ahead * 2.0 + straight_bonus, 40, 300)
else:
    target_speed   = 55   # blind-apex floor (see next entry)
```

**Reason:** A flat 300 km/h target meant the car never braked for corners —
braking was driven entirely by the dead-band (`speedX > target + 30`), making
corner speed wholly dependent on how fast the car happened to be travelling.
The new formula sets `target_speed` proportional to `track_ahead` (the centre
sensor distance), so the car automatically slows when the track shortens ahead.
`straight_bonus` adds up to 80 km/h when the flank sensors are longer than the
centre sensor, rewarding genuine straights with a higher ceiling. The result is
clipped to 40–300 km/h to prevent runaway values.

---

### NEW — Blind-apex speed floor

**File:** `drive_example`

```python
# finale.py only
if track_ahead > 0:
    target_speed = clip(track_ahead * 2.0 + straight_bonus, 40, 300)
else:
    target_speed = 55   # sensor reads -1 at hairpin apex → hold 55 km/h
```

**Reason:** The track-ahead sensor can return `−1.0` when the apex sensor ray hits
a wall behind the car in a tight hairpin. Without this guard `target_speed` became
`−2.0`, causing `accel -= 0.01` for ~10 seconds and a 15–20 s performance loss.

---

### NEW — Gear threshold optimisation

**File:** `drive_example`

| Gear | `snakeoil3_gym.py` | `finale.py` |
|---|---|---|
| 2 | > 50 km/h | > 40 km/h |
| 3 | > 80 km/h | > 70 km/h |
| 4 | > 110 km/h | > 100 km/h |
| 5 | > 140 km/h | > 130 km/h |
| 6 | > 170 km/h | > 160 km/h |

Shifts happen 10 km/h earlier to keep the engine closer to peak power band.

---

### NEW — `maxSteps` raised from 100 000 to 500 000

Allows the car to complete ~5 full laps on the Corkscrew circuit
(~3 600 m, ~1 600 steps/lap) without hitting the step limit mid-race.

---

### NEW — Lap timing system

Detects lap completions by watching `distFromStart` wrap from near the track end
(> 85 % of track length) back to near zero (< 15 %). At each wrap, `curLapTime`
is recorded and printed with a running best-lap display.

---

### NEW — Optional `RaceAnalyzer` integration

If `race_analyzer.py` is present in the same directory, `finale.py`
imports and uses `RaceAnalyzer` to record per-step telemetry, detect turns,
build a speed-zone map, and write `race_study.json` + `race_report.txt`
on shutdown.

---

### NEW — Robust main loop (`try/finally`)

```python
# snakeoil3_gym.py — bare loop, no cleanup on Ctrl-C
for step in range(C.maxSteps, 0, -1):
    ...

# finale.py — guaranteed shutdown + lap summary
try:
    for step in range(C.maxSteps, 0, -1):
        ...
except KeyboardInterrupt:
    print('\n[Analyzer] Interrupted.')
finally:
    C.shutdown()
    # print lap summary
    # save analyzer
```

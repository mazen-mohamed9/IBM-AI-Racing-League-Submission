#!/usr/bin/python
"""
race_analyzer.py
----------------
Live telemetry logger and post-run analyzer for snakeoiltestingv1.py.

USAGE (two ways):

  1. Wrap your existing drive loop:

        import snakeoiltestingv1 as snakeoil
        from race_analyzer import RaceAnalyzer

        C = snakeoil.Client()
        analyzer = RaceAnalyzer()
        for step in range(C.maxSteps, 0, -1):
            C.get_servers_input()
            snakeoil.drive_example(C)
            analyzer.record(C)          # <-- one line added
            C.respond_to_server()
        C.shutdown()
        analyzer.save()                 # writes CSV + prints summary
        analyzer.report()

  2. Run this file directly to drive AND analyze in one shot:

        python race_analyzer.py [same flags as snakeoiltestingv1.py]

WHAT IT RECORDS (every step, ~50 Hz):
  step, time, distRaced, distFromStart, lapTime,
  speedX, speedY, speedZ,
  angle, trackPos,
  accel, brake, steer, gear,
  track_min (nearest wall), track_ahead,
  rpm, fuel, damage,
  wheelSpinVel_0..3,
  corner_sharpness (derived),
  off_track (bool: track_min < 0)

OUTPUT:
  telemetry_<timestamp>.csv  — full per-step log
  summary printed to stdout  — key stats per incident, lap stats,
                               worst corners, off-track events
"""

import csv
import sys
import os
import time
import math
from datetime import datetime

# ── optional: matplotlib for live plot (warns if not installed) ─────────────
try:
    import matplotlib
    matplotlib.use('Agg')   # non-interactive backend; safe on headless machines
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print('[Analyzer] WARNING: matplotlib not installed — PNG capstone will not be generated.')
    print('[Analyzer]          Install it with:  pip install matplotlib')

PI = 3.14159265359

# ── helpers ─────────────────────────────────────────────────────────────────

def _clip(v, lo, hi):
    return max(lo, min(hi, v))

def _corner_sharpness(track):
    """Mirror of the formula in snakeoiltestingv1 so the log matches."""
    near_left  = max(track[5:9])
    near_right = max(track[10:14])
    near_min   = min(near_left, near_right)
    return _clip(1.0 - near_min / 80.0, 0.0, 1.0)


# ── main class ───────────────────────────────────────────────────────────────

class RaceAnalyzer:
    """
    Records live telemetry from a running snakeoiltestingv1 Client,
    writes a CSV log, and prints a human-readable race summary.
    """

    FIELDS = [
        'step', 'elapsed_s',
        'distRaced', 'distFromStart', 'curLapTime', 'lastLapTime',
        'speedX', 'speedY', 'speedZ',
        'angle', 'trackPos',
        'accel', 'brake', 'steer', 'gear',
        'track_min', 'track_ahead',
        'corner_sharpness',
        'rpm', 'fuel', 'damage',
        'wSpin0', 'wSpin1', 'wSpin2', 'wSpin3',
        'off_track',
    ]

    def __init__(self, output_dir='.', live_print=True, print_every=50):
        """
        output_dir   — where to write the CSV (default: current dir)
        live_print   — print a one-line summary to stdout every `print_every` steps
        print_every  — interval for live console output
        """
        self.output_dir  = output_dir
        self.live_print  = live_print
        self.print_every = print_every

        self._rows        = []          # list of dicts, one per step
        self._step        = 0
        self._start_time  = time.time()
        self._incidents   = []          # list of (step, reason, snapshot)
        self._lap_times   = []          # completed lap times
        self._last_lap    = None        # last seen lastLapTime value
        self._prev_damage = 0.0         # to detect new damage events

    # ── public API ──────────────────────────────────────────────────────────

    def record(self, client):
        """Call once per step, after drive_example() and before respond_to_server()."""
        S = client.S.d
        R = client.R.d

        track = S.get('track', [200.0] * 19)
        wspin = S.get('wheelSpinVel', [0.0, 0.0, 0.0, 0.0])

        track_min    = min(track)
        track_ahead  = track[9]
        cs           = _corner_sharpness(track)
        off_track    = track_min < 0
        elapsed      = time.time() - self._start_time
        damage       = S.get('damage', 0.0)
        last_lap     = S.get('lastLapTime', 0.0)

        row = {
            'step'           : self._step,
            'elapsed_s'      : round(elapsed, 3),
            'distRaced'      : S.get('distRaced', 0.0),
            'distFromStart'  : S.get('distFromStart', 0.0),
            'curLapTime'     : S.get('curLapTime', 0.0),
            'lastLapTime'    : last_lap,
            'speedX'         : S.get('speedX', 0.0),
            'speedY'         : S.get('speedY', 0.0),
            'speedZ'         : S.get('speedZ', 0.0),
            'angle'          : S.get('angle', 0.0),
            'trackPos'       : S.get('trackPos', 0.0),
            'accel'          : R.get('accel', 0.0),
            'brake'          : R.get('brake', 0.0),
            'steer'          : R.get('steer', 0.0),
            'gear'           : R.get('gear', 1),
            'track_min'      : track_min,
            'track_ahead'    : track_ahead,
            'corner_sharpness': round(cs, 3),
            'rpm'            : S.get('rpm', 0.0),
            'fuel'           : S.get('fuel', 0.0),
            'damage'         : damage,
            'wSpin0'         : wspin[0],
            'wSpin1'         : wspin[1],
            'wSpin2'         : wspin[2],
            'wSpin3'         : wspin[3],
            'off_track'      : int(off_track),
        }
        self._rows.append(row)

        # ── incident detection ──────────────────────────────────────────
        if off_track:
            self._flag_incident('OFF_TRACK', row)
        elif abs(S.get('trackPos', 0.0)) > 0.85:
            self._flag_incident('NEAR_EDGE (trackPos={:.2f})'.format(S['trackPos']), row)
        if damage - self._prev_damage > 10:
            self._flag_incident('DAMAGE +{:.0f}'.format(damage - self._prev_damage), row)
        self._prev_damage = damage

        # ── lap completion ──────────────────────────────────────────────
        if last_lap and last_lap != self._last_lap and last_lap > 0:
            self._lap_times.append(last_lap)
            self._last_lap = last_lap

        # ── live console line ───────────────────────────────────────────
        if self.live_print and self._step % self.print_every == 0:
            self._print_live(row, cs)

        self._step += 1

    def save(self, filename=None):
        """Write the full telemetry log to CSV."""
        if not self._rows:
            print('[Analyzer] No data recorded.')
            return None

        if filename is None:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.output_dir,
                                    'telemetry_{}.csv'.format(ts))

        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            writer.writeheader()
            writer.writerows(self._rows)

        print('\n[Analyzer] Telemetry saved → {}'.format(filename))
        self._last_csv = filename
        return filename

    def report(self):
        """Print a human-readable race summary to stdout."""
        if not self._rows:
            print('[Analyzer] No data to report.')
            return

        rows = self._rows
        n    = len(rows)

        speeds  = [r['speedX'] for r in rows]
        steers  = [r['steer']  for r in rows]
        accels  = [r['accel']  for r in rows]
        brakes  = [r['brake']  for r in rows]
        damages = [r['damage'] for r in rows]

        off_steps = [r for r in rows if r['off_track']]
        dist      = rows[-1]['distRaced']
        duration  = rows[-1]['elapsed_s']

        sep = '─' * 62

        print('\n' + sep)
        print('  RACE ANALYZER REPORT')
        print(sep)

        # ── general ────────────────────────────────────────────────────
        print('\n── General ─────────────────────────────────────────────')
        print('  Steps recorded   : {:,}'.format(n))
        print('  Duration         : {:.1f} s  ({:.1f} min)'.format(
              duration, duration / 60))
        print('  Distance raced   : {:.0f} m  ({:.2f} km)'.format(
              dist, dist / 1000))

        # ── speed ──────────────────────────────────────────────────────
        print('\n── Speed (km/h) ────────────────────────────────────────')
        print('  Max              : {:.1f}'.format(max(speeds)))
        print('  Avg              : {:.1f}'.format(_mean(speeds)))
        print('  Min (moving)     : {:.1f}'.format(
              min(s for s in speeds if s > 5) if any(s > 5 for s in speeds) else 0))

        # ── steering ───────────────────────────────────────────────────
        steer_abs = [abs(s) for s in steers]
        print('\n── Steering ────────────────────────────────────────────')
        print('  Max abs steer    : {:.3f}'.format(max(steer_abs)))
        print('  Avg abs steer    : {:.3f}'.format(_mean(steer_abs)))
        # oscillation proxy: how often steer changes sign
        sign_changes = sum(
            1 for i in range(1, len(steers))
            if steers[i] * steers[i-1] < 0
        )
        print('  Sign changes     : {:,}  ({:.1f}/s)'.format(
              sign_changes, sign_changes / max(duration, 1)))

        # ── braking ────────────────────────────────────────────────────
        brake_events = sum(1 for b in brakes if b > 0.05)
        print('\n── Braking ─────────────────────────────────────────────')
        print('  Steps braking    : {:,}  ({:.1f}%)'.format(
              brake_events, 100 * brake_events / n))
        print('  Max brake        : {:.3f}'.format(max(brakes)))
        print('  Avg brake (when active): {:.3f}'.format(
              _mean([b for b in brakes if b > 0.05]) or 0))

        # ── damage ─────────────────────────────────────────────────────
        print('\n── Damage ──────────────────────────────────────────────')
        print('  Total damage     : {:.0f}'.format(damages[-1]))
        print('  Damage events    : {:,}'.format(
              sum(1 for i in range(1, len(damages))
                  if damages[i] - damages[i-1] > 10)))

        # ── off-track ──────────────────────────────────────────────────
        print('\n── Off-Track Events ────────────────────────────────────')
        if off_steps:
            print('  Total off-track steps : {:,}'.format(len(off_steps)))
            # group into contiguous runs
            runs = _group_runs([r['step'] for r in off_steps])
            print('  Distinct incidents    : {:,}'.format(len(runs)))
            for idx, (start, end) in enumerate(runs[:10]):  # show first 10
                snap = rows[start]
                print('  [{:2d}] step {:,}–{:,}  '
                      'speed={:.1f}  trackPos={:.2f}  '
                      'distFromStart={:.0f} m'.format(
                      idx + 1, start, end,
                      snap['speedX'], snap['trackPos'],
                      snap['distFromStart']))
            if len(runs) > 10:
                print('       ... and {:d} more'.format(len(runs) - 10))
        else:
            print('  None! Clean run.')

        # ── all flagged incidents ───────────────────────────────────────
        if self._incidents:
            print('\n── Flagged Incidents ───────────────────────────────────')
            seen = set()
            for step, reason, snap in self._incidents:
                key = reason.split(' ')[0] + str(step // 10)  # de-dup nearby
                if key in seen:
                    continue
                seen.add(key)
                print('  step {:,}  {}  '
                      '| speed={:.1f}  cs={:.2f}  '
                      'dist={:.0f} m'.format(
                      step, reason,
                      snap['speedX'], snap['corner_sharpness'],
                      snap['distFromStart']))

        # ── laps ───────────────────────────────────────────────────────
        if self._lap_times:
            print('\n── Lap Times ───────────────────────────────────────────')
            for i, t in enumerate(self._lap_times):
                print('  Lap {:2d} : {}'.format(i + 1, _fmt_laptime(t)))
            print('  Best   : {}'.format(_fmt_laptime(min(self._lap_times))))
            if len(self._lap_times) > 1:
                print('  Avg    : {}'.format(
                      _fmt_laptime(_mean(self._lap_times))))

        # ── worst corners ──────────────────────────────────────────────
        sharp = sorted(rows, key=lambda r: r['corner_sharpness'], reverse=True)
        worst = []
        seen_dist = []
        for r in sharp:
            # deduplicate corners within 100 m of each other
            if all(abs(r['distFromStart'] - d) > 100 for d in seen_dist):
                worst.append(r)
                seen_dist.append(r['distFromStart'])
            if len(worst) == 5:
                break

        if worst:
            print('\n── Hardest Corners (by sensor sharpness) ───────────────')
            print('  {:>6}  {:>8}  {:>7}  {:>7}  {:>7}  {:>6}'.format(
                  'dist', 'sharp', 'speed', 'brake', 'steer', 'off?'))
            for r in worst:
                print('  {:>6.0f}m {:>8.3f}  {:>7.1f}  {:>7.3f}  {:>7.3f}  {:>6}'.format(
                      r['distFromStart'], r['corner_sharpness'],
                      r['speedX'], r['brake'], r['steer'],
                      'YES' if r['off_track'] else 'no'))

        print('\n' + sep + '\n')

        # ── optional: save plots ────────────────────────────────────────
        if HAS_MPL:
            self._save_plots()

    # ── private ─────────────────────────────────────────────────────────────

    def _flag_incident(self, reason, row):
        """Record an incident only if not already flagged in the last 25 steps."""
        if self._incidents and self._step - self._incidents[-1][0] < 25:
            return
        self._incidents.append((self._step, reason, dict(row)))

    def _print_live(self, row, cs):
        bar_speed = int(row['speedX'] / 6)
        bar_cs    = int(cs * 10)
        flag = ' !!OFF!!' if row['off_track'] else ''
        print('[{:>6}] {:.0f}km/h |{:<50}| '
              'cs={:.2f} |{:<10}| '
              'steer={:+.3f} brake={:.2f}{}'.format(
              row['step'],
              row['speedX'],
              'X' * bar_speed,
              cs,
              '#' * bar_cs,
              row['steer'],
              row['brake'],
              flag))

    def _save_plots(self):
        """Save a multi-panel PNG next to the CSV."""
        if not hasattr(self, '_last_csv'):
            print('[Analyzer] WARNING: PNG not saved — save() was never called or produced no data.')
            return
        rows = self._rows
        dist = [r['distFromStart'] for r in rows]

        fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
        fig.suptitle('Race Telemetry', fontsize=13)

        axes[0].plot(dist, [r['speedX'] for r in rows], color='steelblue', lw=0.8)
        axes[0].set_ylabel('Speed (km/h)')

        axes[1].plot(dist, [r['steer'] for r in rows], color='darkorange', lw=0.8)
        axes[1].axhline(0, color='gray', lw=0.4, ls='--')
        axes[1].set_ylabel('Steer')

        axes[2].plot(dist, [r['accel'] for r in rows], color='green', lw=0.8, label='accel')
        axes[2].plot(dist, [-r['brake'] for r in rows], color='red',   lw=0.8, label='brake')
        axes[2].legend(loc='upper right', fontsize=8)
        axes[2].set_ylabel('Throttle / Brake')

        axes[3].plot(dist, [r['trackPos'] for r in rows], color='purple', lw=0.8)
        axes[3].axhline( 1, color='red', lw=0.5, ls='--')
        axes[3].axhline(-1, color='red', lw=0.5, ls='--')
        axes[3].set_ylabel('trackPos')
        axes[3].set_xlabel('Distance from start (m)')

        # mark off-track regions
        off = [r['distFromStart'] for r in rows if r['off_track']]
        for ax in axes:
            for d in off:
                ax.axvline(d, color='red', alpha=0.15, lw=0.6)

        plt.tight_layout()
        plot_path = self._last_csv.replace('.csv', '.png')
        plt.savefig(plot_path, dpi=120)
        plt.close()
        print('[Analyzer] Plot saved → {}'.format(plot_path))


# ── pure helpers (no dependencies) ──────────────────────────────────────────

def _mean(lst):
    return sum(lst) / len(lst) if lst else 0.0

def _fmt_laptime(seconds):
    if not seconds:
        return '--:--.---'
    m  = int(seconds // 60)
    s  = seconds - m * 60
    return '{:02d}:{:06.3f}'.format(m, s)

def _group_runs(steps):
    """Group a sorted list of step numbers into contiguous (start, end) runs."""
    if not steps:
        return []
    runs = []
    start = prev = steps[0]
    for s in steps[1:]:
        if s == prev + 1:
            prev = s
        else:
            runs.append((start, prev))
            start = prev = s
    runs.append((start, prev))
    return runs


# ── standalone entry point ───────────────────────────────────────────────────

if __name__ == '__main__':
    # Import the driver from the same directory.
    sys.path.insert(0, os.path.dirname(__file__))
    import snakeoiltestingv1 as snakeoil

    print('[Analyzer] Starting race with live telemetry...')
    print('[Analyzer] Press Ctrl+C to stop early and still get the report.\n')

    C        = snakeoil.Client()
    analyzer = RaceAnalyzer(live_print=True, print_every=50)

    try:
        for step in range(C.maxSteps, 0, -1):
            C.get_servers_input()
            snakeoil.drive_example(C)
            analyzer.record(C)
            C.respond_to_server()
    except KeyboardInterrupt:
        print('\n[Analyzer] Interrupted by user.')
    finally:
        C.shutdown()
        analyzer.save()
        analyzer.report()

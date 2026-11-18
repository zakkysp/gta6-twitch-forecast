#!/usr/bin/env python3
"""Hour-by-hour Twitch viewer forecast for a big game launch day.

Reads one case file per run (schema makefun/twitch-ccu-case/v1) from the
input directory and writes a five-quantile forecast for hours 2..24 of the
launch day to the output directory.

How it forecasts
----------------
Every past launch in the case's ``comparables`` has a full release-day
hourly curve.  For each comparable we take the curve's ratio to its own
hour-1 print, so every launch speaks in the same units: "how many times
hour 1's audience is watching in hour h".  Two kinds of comparable are
left out of that pool, because their curves do not describe a normal
launch day: the target game's own pre-release history (it is not a
launch at all), and launches whose notes flag early-access contamination
(their peak happened days before release day).

A second filter keeps only launches whose hour-1 print already carried a
real audience: when a launch's peak is more than twenty times its hour-1
print, hour 1 was nearly empty and every ratio built on it is noise from
a tiny denominator, so those launches are dropped.  The launches that
remain are the ones whose first hour looks like the case at hand.

For each forecast hour the program then takes the median of the surviving
log-ratios as the centre of the forecast and the interquartile range of
the same log-ratios (converted to a normal scale) as its log-spread, and
writes the five quantiles as

    q_tau = hour1_print * exp(median + z_tau * spread)

with z the standard-normal quantiles at 0.05, 0.25, 0.5, 0.75 and 0.95.
The median is the honest centre for the pinball loss, and the spread is
the dispersion actually seen across past launches, so the band is as
wide as the evidence says and no wider.

If too few comparables survive the filters, the program falls back to
the unfiltered pool, and if even that is too thin it falls back to a
flat forecast at the hour-1 print with a spread that widens over the
day.  Every output is clamped to (0, 1e9] and made non-decreasing, so
the forecast is always a valid one.

The program is deterministic: it reads only its case files, uses no
randomness, no clock and no network, and the same input always yields
the same output bytes.
"""

import json
import math
import os
import statistics

# Standard-normal quantiles at the five scored levels.
Z_SCORES = (-1.6448536269514722, -0.6744897501960817, 0.0,
            0.6744897501960817, 1.6448536269514722)

# A launch is dropped from the ratio pool when its peak is more than
# this many times its hour-1 print: its first hour was nearly empty.
PEAK_RATIO_CAP = 20.0

# A comparable needs at least this many hourly points on its release
# day to join the pool, and the pool needs at least this many launches
# before we trust its median and spread.
MIN_DAY_POINTS = 12
MIN_POOL_SIZE = 5

# Smallest log-spread we will report, so an hour where every past
# launch agreed exactly still carries a little honest uncertainty.
SPREAD_FLOOR = 0.05

MAX_VIEWERS = 1.0e9


def quantile(sorted_values, tau):
    """Linear-interpolation quantile of an already sorted list."""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return sorted_values[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def day_curve(comp):
    """Hourly viewers {1..24: viewers} on a comparable's release day.

    Returns None when the comparable has no usable hour-1 print.
    """
    day = (comp.get("day_start") or "")[:10]
    if not day:
        return None
    curve = {}
    for point in comp.get("hourly") or []:
        stamp = point.get("from") or ""
        if not stamp.startswith(day):
            continue
        try:
            hour = int(stamp[11:13]) + 1
            viewers = point.get("viewers")
        except (ValueError, TypeError):
            continue
        if 1 <= hour <= 24 and isinstance(viewers, (int, float)):
            curve[hour] = float(viewers)
    first = curve.get(1)
    if first is None or first <= 0:
        return None
    return curve


def is_launch_curve(comp):
    """True when a comparable describes a real launch day.

    The target game's own pre-release history and early-access
    contaminated launches are not launch days and are left out.
    """
    name = comp.get("name") or ""
    notes = comp.get("unlock") or ""
    if "Grand Theft Auto VI category before release" in name:
        return False
    if "target-history" in notes:
        return False
    if "early-access-contaminated" in notes:
        return False
    return True


def build_pool(case):
    """Surviving comparables as (hour-1 print, day curve) pairs.

    First the filtered pool (peak no more than PEAK_RATIO_CAP times the
    hour-1 print); if that is too small, the unfiltered pool of clean
    launch curves, so the program always has something to forecast
    from when the case carries any comparables at all.
    """
    clean = []
    for comp in case.get("comparables") or []:
        if not is_launch_curve(comp):
            continue
        curve = day_curve(comp)
        if curve is None or len(curve) < MIN_DAY_POINTS:
            continue
        clean.append((curve[1], curve))
    filtered = []
    for first, curve in clean:
        peak = max(curve.values())
        if peak / first <= PEAK_RATIO_CAP:
            filtered.append((first, curve))
    if len(filtered) >= MIN_POOL_SIZE:
        return filtered
    return clean


def hour_stats(pool, hour):
    """Median log-ratio and IQR-based log-spread for one hour.

    Returns (median, spread) or None when no comparable has that hour.
    """
    ratios = sorted(
        math.log(curve[hour] / first)
        for first, curve in pool
        if curve.get(hour) is not None and curve[hour] > 0
    )
    if not ratios:
        return None
    centre = statistics.median(ratios)
    lower = quantile(ratios, 0.25)
    upper = quantile(ratios, 0.75)
    spread = max((upper - lower) / 1.349, SPREAD_FLOOR)
    return centre, spread


def forecast_case(case):
    """Forecast rows for hours 2..24 of one case.

    Returns a list of {"hour": h, "q": [q05, q25, q50, q75, q95]}.
    """
    known = case.get("known") or []
    hour1 = 1.0
    if known:
        try:
            hour1 = float(known[0].get("viewers") or 0) or 1.0
        except (TypeError, ValueError):
            hour1 = 1.0
    hour1 = max(hour1, 1.0)

    wanted = []
    for row in case.get("forecast") or []:
        try:
            wanted.append(int(row["hour"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not wanted:
        wanted = list(range(2, 25))

    pool = build_pool(case)
    stats_by_hour = {}
    for hour in wanted:
        stats = hour_stats(pool, hour) if pool else None
        if stats is not None:
            stats_by_hour[hour] = stats
    # A past launch is sampled about once an hour, so some hour of
    # some case can have no comparable at all.  Fill such a hole by
    # interpolating the centre and the spread in log space from the
    # nearest hours that do have past launches, instead of dropping
    # back to a flat forecast for that one hour.
    known_hours = sorted(stats_by_hour)
    for hour in wanted:
        if hour in stats_by_hour or not known_hours:
            continue
        before = [h for h in known_hours if h < hour]
        after = [h for h in known_hours if h > hour]
        if before and after:
            lo, hi = before[-1], after[0]
            frac = (hour - lo) / (hi - lo)
            c_lo, s_lo = stats_by_hour[lo]
            c_hi, s_hi = stats_by_hour[hi]
            stats_by_hour[hour] = (
                c_lo + frac * (c_hi - c_lo),
                s_lo + frac * (s_hi - s_lo),
            )
        elif before:
            stats_by_hour[hour] = stats_by_hour[before[-1]]
        else:
            stats_by_hour[hour] = stats_by_hour[after[0]]
    rows = []
    for hour in wanted:
        stats = stats_by_hour.get(hour)
        if stats is None:
            # No past launch speaks for this hour: stay flat at the
            # hour-1 print with a spread that widens over the day.
            spread = 0.15 * math.sqrt(max(hour - 1, 1))
            centre = 0.0
        else:
            centre, spread = stats
        quantiles = []
        for z in Z_SCORES:
            value = hour1 * math.exp(centre + z * spread)
            quantiles.append(round(min(max(value, 1.0), MAX_VIEWERS), 2))
        for i in range(1, len(quantiles)):
            if quantiles[i] < quantiles[i - 1]:
                quantiles[i] = quantiles[i - 1]
        rows.append({"hour": hour, "q": quantiles})
    return rows


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    names = sorted(
        name for name in os.listdir(in_dir) if name.endswith(".in")
    )
    for name in names:
        case_id = name[: -len(".in")]
        with open(os.path.join(in_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        payload = {"hours": forecast_case(case)}
        out_path = os.path.join(out_dir, case_id + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
            fh.write("\n")


if __name__ == "__main__":
    main()

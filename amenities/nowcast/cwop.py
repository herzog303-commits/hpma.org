"""CWOP observations for GW2160 (Grapeview / Fair Harbor Marina).

GW2160 is the station the study used via Synoptic until that trial contract
lapsed on 2026-09-07. It is an APRSWXNET/CWOP site: the observations are
contributed by a volunteer into NOAA MADIS and travel over APRS-IS, so
Synoptic was selling convenient access, not the data.

Backend history, because the first answer was wrong:

  1. findu.com scraping -- REMOVED. Their front page forbids exactly this:
     "no screen scrapers" and "any repetitive access by a program is NOT
     ALLOWED". The data is public; that service is a volunteer's limited
     resource and its owner said no.
  2. aprs.fi API -- REJECTED. Forbids preloading, pre-caching and collecting
     for archival purposes, and requires requests be driven by an end-user
     action. Our cycle is scheduled and archives.
  3. Our own APRS-IS archive -- CURRENT. Both of the above independently
     point here: findu says "create your own database by parsing the APRS
     data stream", aprs.fi says "collect your data directly from the
     APRS-IS". aprsis.py holds a receive-only connection and appends to
     cwop_obs.jsonl; this module just reads that file. No web service is
     asked for anything, on any schedule.

Reading a local file means series() is cheap and has no failure mode worth
retrying -- an empty archive simply reads as "could not verify", which
score.py and cove_obs.py already handle.

  series(call, hours)  -> list of obs dicts, newest first
  at(vt, call)         -> the observation nearest a past time vt, or None
  latest(call)         -> most recent observation if fresh, else None
  rain_in_hour(vt)     -> 1/0/None for measurable precip in [vt-60m, vt]
"""
import json
import os
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# Overridable for the same reason wu.py's cache is: this file exists in BOTH
# repos, HERE resolves differently in each, and the archive itself is study
# data that lives only in the private repo. Without this the board's copy reads
# a path that does not exist and silently reports no CWOP gauge at all.
ARCHIVE = os.environ.get("CWOP_ARCHIVE") or os.path.join(HERE, "cwop_obs.jsonl")

DEFAULT_CALL = "GW2160"          # Grapeview / Fair Harbor Marina, 2.81 mi from the cove

# Positions are fixed station metadata and never move; a constant avoids
# needing a lookup service just to learn a lat/lon.
SITES = {"GW2160": {"name": "Grapeview (GW2160) @ Fair Harbor Marina",
                    "lat": 47.33033, "lon": -122.82967}}

CACHE_S = 60                     # the archive only grows every ~5 min
_CACHE = {}                      # (call, hours) -> (fetched_monotonic, rows)


def _dt(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _fetch(call, hours):
    """Rows from our own APRS-IS archive, written by aprsis.py."""
    if not os.path.exists(ARCHIVE):
        return []
    cutoff = time.time() - hours * 3600
    out = []
    with open(ARCHIVE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue                      # a torn final line while appending
            if o.get("call") != call:
                continue
            try:
                ts = _dt(o["ts"])
            except (KeyError, ValueError):
                continue
            if ts.timestamp() < cutoff:
                continue
            o["ts"] = ts
            out.append(o)
    out.sort(key=lambda o: o["ts"], reverse=True)
    return out


def series(call=DEFAULT_CALL, hours=72):
    """Observations newest-first, briefly cached so one cycle reads once."""
    key = (call, hours)
    hit = _CACHE.get(key)
    if hit and (time.monotonic() - hit[0]) < CACHE_S:
        return hit[1]
    rows = _fetch(call, hours)
    _CACHE[key] = (time.monotonic(), rows)
    return rows


def at(vt, call=DEFAULT_CALL, tol_min=30, hours=72):
    """The observation nearest vt, or None if nothing lands within tol_min."""
    rows = series(call, hours)
    if not rows:
        return None
    best = min(rows, key=lambda o: abs((o["ts"] - vt).total_seconds()))
    return best if abs((best["ts"] - vt).total_seconds()) <= tol_min * 60 else None


def latest(call=DEFAULT_CALL, max_age_min=60):
    """Most recent observation if it is fresh enough, else None."""
    rows = series(call, 6)
    if not rows:
        return None
    age = (datetime.now(timezone.utc) - rows[0]["ts"]).total_seconds() / 60
    return rows[0] if age <= max_age_min else None


def rain_in_hour(vt, call=DEFAULT_CALL):
    """Did measurable precip fall in [vt-60min, vt]? 1/0/None.

    Uses the station's own 1-hour accumulator (APRS 'r' field) rather than
    differencing a running total, so a midnight reset cannot read as negative.
    """
    rows = [o for o in series(call, 72)
            if 0 <= (vt - o["ts"]).total_seconds() <= 3600
            and o.get("rain_1h_in") is not None]
    if not rows:
        return None
    return 1 if max(o["rain_1h_in"] for o in rows) > 0.005 else 0


if __name__ == "__main__":
    s = series()
    print("%s: %d obs in archive, newest %s"
          % (DEFAULT_CALL, len(s), s[0]["ts"] if s else "none"))
    for o in s[:3]:
        print("  ", {k: v for k, v in o.items() if k != "raw"})

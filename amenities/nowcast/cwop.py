"""CWOP observations for GW2160 (Grapeview / Fair Harbor Marina), keyless.

GW2160 is the station the study used via Synoptic until the trial contract
lapsed on 2026-09-07. It is an APRSWXNET/CWOP station: the observations are
contributed by a volunteer into NOAA MADIS and are public at the source, so
Synoptic was selling convenient access, not the data. This reads the same
observations with no credential at all -- nothing to expire, nothing to
rotate, no entitlement to lose mid-season.

Carries every variable the scorecard verified against Synoptic, at ~5-minute
cadence (finer than the hourly windows we were requesting):

    temp F | wind dir | wind mph | gust mph | rain 1h/24h in | RH % | mb

One fetch covers 72 hours, so a whole cycle's verifications -- including a
large backlog -- are served from a single request. The Synoptic path made one
request per pending entry per variable (~512/day healthy, ~128k/day when it
started failing). This is 1 per cycle.

  series(call, hours)  -> list of obs dicts, newest first (process-cached)
  at(vt, call)         -> the observation nearest a past time vt, or None

Source: findu.com, a long-running volunteer APRS service. For anything the
board depends on long-term, prefer MADIS (the NOAA upstream; free but needs
an account via madis.ncep.noaa.gov/data_application.shtml) or the aprs.fi
JSON API (free key). _fetch() is the only function that knows about findu,
so swapping the backend touches one place.
"""
import re
import time
import urllib.request
from datetime import datetime, timezone

DEFAULT_CALL = "GW2160"          # Grapeview / Fair Harbor Marina, 2.81 mi from the cove

# Positions are fixed station metadata; findu carries them in the page header but
# a constant avoids a second request just to learn a lat/lon that never moves.
SITES = {"GW2160": {"name": "Grapeview (GW2160) @ Fair Harbor Marina",
                    "lat": 47.33033, "lon": -122.82967}}
MPH_KT = 0.868976
UA = {"User-Agent": "indian-cove-microclimate/1.0 (Indian Cove marina microclimate study)"}
CACHE_S = 600                    # a 15-min cycle refetches at most once

# time, tempF, dir, speed, gust, rain1h, rain24h, rainMidnight, RH, mb
_ROW = re.compile(
    r"\b(20\d{12})\s+(-?\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+"
    r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)")

_CACHE = {}                      # (call, hours) -> (fetched_monotonic, rows)


def _fetch(call, hours):
    """Raw observation rows from findu. The only findu-specific code here."""
    url = "http://www.findu.com/cgi-bin/wx.cgi?call=%s&last=%d" % (call, hours)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode(errors="replace")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    out = []
    for m in _ROW.finditer(text):
        g = m.groups()
        try:
            ts = datetime.strptime(g[0], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append({
            "ts": ts,
            "temp_f": float(g[1]),
            "wind_dir": int(g[2]),
            "wind_kt": round(float(g[3]) * MPH_KT, 1),
            "gust_kt": round(float(g[4]) * MPH_KT, 1),
            "rain_1h_in": float(g[5]),
            "rain_24h_in": float(g[6]),
            "rh": int(g[8]),
            "pressure_mb": float(g[9]),
        })
    out.sort(key=lambda o: o["ts"], reverse=True)
    return out


def series(call=DEFAULT_CALL, hours=72):
    """Observations newest-first, cached for CACHE_S so one cycle fetches once.

    Returns [] on failure rather than raising -- callers treat a missing
    observation as 'could not verify', exactly as the Synoptic path did.
    """
    key = (call, hours)
    hit = _CACHE.get(key)
    if hit and (time.monotonic() - hit[0]) < CACHE_S:
        return hit[1]
    try:
        rows = _fetch(call, hours)
    except Exception as exc:  # noqa: BLE001
        print("cwop: %s fetch failed (%s)" % (call, exc))
        return hit[1] if hit else []
    if rows:
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

    Uses the station's own 1-hour accumulator rather than differencing a
    running total, so a midnight reset cannot read as negative rainfall.
    """
    rows = [o for o in series(call, 72)
            if 0 <= (vt - o["ts"]).total_seconds() <= 3600]
    if not rows:
        return None
    return 1 if max(o["rain_1h_in"] for o in rows) > 0.005 else 0


if __name__ == "__main__":
    s = series()
    print("%s: %d obs, newest %s" % (DEFAULT_CALL, len(s), s[0]["ts"] if s else "none"))
    for o in s[:3]:
        print("  ", o)

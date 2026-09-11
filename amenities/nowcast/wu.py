"""Weather Underground PWS fetch — KWASHELT285 (Tomas's station, Harstine Pointe).

The closest station to the cove by far: 47.295,-122.854, elev 12 ft, ON Case Inlet,
0.35 mi from the gangway. WU-only (not on Synoptic), so its own small client. This
is the hyper-local ground truth the study always lacked -- use it for "rain now",
cove verification of the scorecard, and (eventually) checking the shelter model.

Key from env WUNDERGROUND_KEY, else secrets.json (git-ignored). Units imperial (units=e):
temp F, wind mph->kt, pressure inHg, precip inches.

  wu_current()      -> dict of the latest obs (or None)
  wu_hourly_at(vt)  -> the hourly obs nearest a past time vt (for verification), or None
"""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MPH_KT = 0.868976
BASE = "https://api.weather.com/v2/pws"

def _key():
    k = os.environ.get("WUNDERGROUND_KEY")
    if k:
        return k
    try:
        return json.load(open(os.path.join(HERE, "secrets.json")))["wunderground_key"]
    except Exception:  # noqa: BLE001
        return None

def _get(path, station, **params):
    key = _key()
    if not key:
        return None
    params.update(stationId=station, format="json", units="e", apiKey=key)
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as exc:  # noqa: BLE001
        print(f"wu: {station} {path} failed ({exc})")
        return None

def _pick(d, *names):
    """First non-None of several field names -- the current and hourly/7day endpoints
    spell the same quantity differently (temp vs tempAvg, windSpeed vs windspeedAvg).
    Plain dict.get(a, b) is not enough: WU sends the key with a null value."""
    for n in names:
        v = d.get(n)
        if v is not None:
            return v
    return None

def _norm(o):
    """WU observation dict -> normalized fields (kt, F, in, inHg). Handles both the
    current endpoint (instantaneous) and hourly/7day (per-hour aggregates): sustained
    wind takes the hourly MEAN, gust takes the hourly PEAK -- which is what a gust
    forecast is actually predicting."""
    im = o.get("imperial", {})
    ws = _pick(im, "windSpeed", "windspeedAvg")
    wg = _pick(im, "windGust", "windgustHigh", "windgustAvg")
    return {
        "ts": o.get("obsTimeUtc"),
        "lat": o.get("lat"), "lon": o.get("lon"),
        "temp_f": _pick(im, "temp", "tempAvg"),
        "dewpt_f": _pick(im, "dewpt", "dewptAvg"),
        "humidity": _pick(o, "humidity", "humidityAvg"),
        "wind_kt": round(ws * MPH_KT, 1) if ws is not None else None,
        "gust_kt": round(wg * MPH_KT, 1) if wg is not None else None,
        "wind_dir": _pick(o, "winddir", "winddirAvg"),
        "pressure_inhg": _pick(im, "pressure", "pressureMax"),
        "precip_rate_in": _pick(im, "precipRate"),
        "precip_total_in": _pick(im, "precipTotal"),
    }

DEFAULT_STATION = "KWASHELT285"

def wu_current(station=DEFAULT_STATION):
    d = _get("observations/current", station)
    obs = (d or {}).get("observations") or []
    return _norm(obs[0]) if obs else None

def wu_hourly_at(vt, station=DEFAULT_STATION, tol_min=45):
    """Nearest hourly obs to vt (UTC) from the last 7 days -- for scorecard verification."""
    d = _get("observations/hourly/7day", station)
    obs = (d or {}).get("observations") or []
    if not obs:
        return None
    def t(o):
        return datetime.fromisoformat(o["obsTimeUtc"].replace("Z", "+00:00"))
    best = min(obs, key=lambda o: abs((t(o) - vt).total_seconds()))
    return _norm(best) if abs((t(best) - vt).total_seconds()) <= tol_min * 60 else None

def wu_rain_1h(station=DEFAULT_STATION):
    """Accumulation over the last hour, in inches, or None.

    WU reports precipTotal as a running total that resets at LOCAL midnight, so
    differencing two hourly records can go negative across the reset. A negative
    difference means the reset fell inside the window, in which case the newer
    value is itself the post-reset accumulation.
    """
    d = _get("observations/hourly/7day", station)
    obs = (d or {}).get("observations") or []
    if len(obs) < 2:
        return None
    prev, cur = _norm(obs[-2]), _norm(obs[-1])
    if prev["precip_total_in"] is None or cur["precip_total_in"] is None:
        return None
    diff = cur["precip_total_in"] - prev["precip_total_in"]
    return round(cur["precip_total_in"] if diff < 0 else diff, 2)


def wu_nearest_current(stations):
    """First station in the list that returns data (list is closest-first in config)."""
    for s in stations:
        c = wu_current(s)
        if c and c.get("temp_f") is not None:
            return s, c
    return None, None

if __name__ == "__main__":
    for st in ("KWASHELT285", "KWASHELT12"):
        print(st, "->", json.dumps(wu_current(st)) if wu_current(st) else "none")

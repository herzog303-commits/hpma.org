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
import json, os, time, urllib.request, urllib.parse
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

# Disk cache, because mini_cycle runs nowcast / score / cove_obs as SEPARATE
# PROCESSES and each of them wants the same station in the same cycle. With 10
# registered stations the uncached load is ~41 calls/cycle (~3,900/day), which
# is over what a free PWS key should be asked for. Caching on disk collapses
# the duplicates across processes: ~10-12 calls/cycle (~1,150/day).
#
# TTLs are set below the update rate of the thing being cached -- PWS report
# roughly every 5 min, and the hourly endpoint only changes once an hour.
# Overridable, and it MUST be, because there are two copies of this file --
# one in the study repo and one in the board repo -- and HERE resolves
# differently in each. Left to default they keep SEPARATE caches and every
# station gets fetched twice per cycle, which is worse than no cache at all.
# mini_cycle sets WU_CACHE_DIR so both copies share one directory.
CACHE_DIR = os.environ.get("WU_CACHE_DIR") or os.path.join(HERE, ".wu-cache")
# The hourly endpoint only changes once an hour, so a 900 s TTL against a 900 s
# cycle meant it expired exactly at every cycle boundary and refetched all ten
# stations every time. 3000 s refetches roughly every third cycle instead, which
# is still fresher than the data. Measured effect: ~20 -> ~13 calls/cycle,
# ~1,900 -> ~1,250 per day.
CACHE_TTL = {"observations/current": 240, "observations/hourly/7day": 3000}


def _cache_file(path, station):
    safe = path.replace("/", "_")
    return os.path.join(CACHE_DIR, "%s__%s.json" % (safe, station))


def _get(path, station, **params):
    key = _key()
    if not key:
        return None
    cf = _cache_file(path, station)
    ttl = CACHE_TTL.get(path, 240)
    try:
        age = time.time() - os.path.getmtime(cf)
        if age < ttl:
            with open(cf) as f:
                return json.load(f)
    except (OSError, ValueError):
        pass

    params.update(stationId=station, format="json", units="e", apiKey=key)
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
    except Exception as exc:  # noqa: BLE001
        print(f"wu: {station} {path} failed ({exc})")
        # a stale cache entry beats nothing when the API is unreachable
        try:
            with open(cf) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = cf + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, cf)          # atomic: concurrent readers never see half a file
    except OSError:
        pass
    return data

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
        # Kept deliberately. RESEARCH_NOTES.md names shortwave radiation as a
        # top-tier predictor AND as the driver of the citizen-station warm bias
        # -- and Tomas's Ecowitt GW3000 MEASURES it 0.56 km from the gangway,
        # while predictors.jsonl was feeding the corrector Open-Meteo's MODELLED
        # value. A measured local value beats a modelled one from a 1-2 km grid.
        "solar_w_m2": _pick(o, "solarRadiation", "solarRadiationHigh"),
        "uv": _pick(o, "uv", "uvHigh"),
        "qc_status": o.get("qcStatus"),        # WU's own QC verdict, 1 = passed
        "elev_ft": _pick(im, "elev"),
    }

DEFAULT_STATION = "KWASHELT285"

def independent_stations(mc):
    """The station list with non-independent duplicates removed.

    Two registrations can share one outdoor sensor array -- an Ambient console
    will happily receive a neighbour's 915 MHz transmitter -- and when that
    happens the pair reports byte-identical temperature, humidity, wind and
    solar while remaining two entries in the roster. Counting both gives one
    sensor two votes in every median and silently overstates how many
    independent observations the network has.

    Pressure is NOT identical in such a pair, because each console derives it
    from its own configured elevation. That makes pressure exactly the wrong
    field to check for this, and it is the field that let KWAGRAPE6 pass an
    earlier check. See stations.wu_duplicates in microclimate.json.

    HARVEST DELIBERATELY IGNORES THIS: history from before the duplication
    began is real, independent data and is worth collecting.
    """
    st = mc.get("stations") or {}
    dupes = set((st.get("wu_duplicates") or {}).keys())
    return [s for s in (st.get("wu_stations") or []) if s not in dupes]


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

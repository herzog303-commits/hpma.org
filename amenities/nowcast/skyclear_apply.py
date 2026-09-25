"""Evaluate skyclear.json live. Stdlib + one Open-Meteo call per model.

The features are exactly what train_skyclear.py fitted, requested in the same
units and never converted on the way in. `persist` -- the observed cloud
fraction three hours ago -- is passed IN by the caller rather than fetched here,
because score.py already holds obs_cloud() and a second METAR path would be a
second thing to keep in step.

MODEL PATH resolves to ../skyclear.json first, so the copy under amenities/ is
the single file whether this runs from the study repo or from the board
checkout. Same rule as tempfix_apply, and for the same reason.
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = (os.environ.get("SKYCLEAR_MODEL")
         or next((p for p in (os.path.join(HERE, os.pardir, "skyclear.json"),
                              os.path.join(HERE, "skyclear.json"))
                  if os.path.exists(p)), os.path.join(HERE, "skyclear.json")))
CACHE = os.path.join(HERE, ".skyclear-feed-cache.json")
TTL_S = 900
MODELS = ["gfs_hrrr", "ecmwf_ifs025", "icon_seamless"]
_model = None


def model():
    global _model
    if _model is None:
        try:
            with open(MODEL) as f:
                _model = json.load(f)
        except (OSError, ValueError):
            _model = {}
    return _model


def _cove():
    for p in (os.path.join(HERE, "microclimate.json"),
              os.path.join(HERE, os.pardir, os.pardir, "microclimate.json")):
        try:
            with open(p) as f:
                c = json.load(f)["cove"]
            return c["lat"], c["lon"]
        except Exception:  # noqa: BLE001
            continue
    return 47.2959, -122.8614


def _get(q):
    return json.load(urllib.request.urlopen(
        "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=25))["hourly"]


def _feed():
    try:
        c = json.load(open(CACHE))
        if time.time() - c.get("at", 0) < TTL_S:
            return c.get("d") or {}
    except (OSError, ValueError):
        pass
    lat, lon = _cove()
    base = {"latitude": lat, "longitude": lon, "timezone": "GMT", "forecast_days": 2}
    out = {}
    try:
        h = _get(dict(base, hourly="cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
                                   "wind_direction_10m,wind_speed_10m,surface_pressure"))
        out["base"] = h
        for m in MODELS:
            out[m] = _get(dict(base, hourly="cloud_cover", models=m))
    except Exception:  # noqa: BLE001
        return {}
    try:
        json.dump({"d": out, "at": time.time()}, open(CACHE, "w"))
    except OSError:
        pass
    return out


def _walk(vec):
    m = model().get("model") or {}
    out = m.get("base")
    if out is None:
        return None
    for t in m.get("trees") or []:
        nd = t
        while isinstance(nd, list):
            nd = nd[2] if vec[nd[0]] <= nd[1] else nd[3]
        out += m["lr"] * nd
    return out


def predict(valid_utc, persist_frac):
    """P(sky clear at valid_utc), or None. persist_frac is observed cloud 0-1."""
    md = model()
    feats = md.get("features")
    if not feats or persist_frac is None:
        return None
    d = _feed()
    if not d or "base" not in d:
        return None
    key = valid_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")
    b = d["base"]
    try:
        i = b["time"].index(key)
    except (ValueError, KeyError):
        return None
    cc = []
    for m in MODELS:
        h = d.get(m) or {}
        try:
            j = h["time"].index(key)
        except (ValueError, KeyError):
            continue
        v = (h.get("cloud_cover") or [None])[j]
        if v is not None:
            cc.append(float(v))
    if len(cc) < 2:                     # the ensemble is the point; two is the floor
        return None
    g = lambda k: (b.get(k) or [None] * (i + 1))[i]
    dr = g("wind_direction_10m")
    doy = valid_utc.timetuple().tm_yday
    parts = {"ens_mean": sum(cc)/len(cc), "ens_max": max(cc), "ens_min": min(cc),
             "ens_spread": max(cc)-min(cc), "persist": persist_frac,
             "low": g("cloud_cover_low"), "mid": g("cloud_cover_mid"),
             "high": g("cloud_cover_high"),
             "wdir_sin": math.sin(math.radians(dr)) if dr is not None else 0.0,
             "wdir_cos": math.cos(math.radians(dr)) if dr is not None else 0.0,
             "wspd": g("wind_speed_10m") or 0.0,
             "mslp": g("surface_pressure") or 1013.0,
             "doy_sin": math.sin(2*math.pi*doy/365.25),
             "doy_cos": math.cos(2*math.pi*doy/365.25),
             "hour": valid_utc.astimezone(timezone.utc).hour}
    if any(parts.get(k) is None for k in feats):
        return None
    p = _walk([float(parts[k]) for k in feats])
    if p is None or not math.isfinite(p):
        return None
    return round(min(max(p, 0.01), 0.99), 3)


if __name__ == "__main__":
    t = datetime.now(timezone.utc) + timedelta(hours=3)
    for pf in (0.0, 0.5, 1.0):
        print("persist %.1f -> P(clear in 3h) = %s" % (pf, predict(t, pf)))

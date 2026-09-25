"""Apply tempfix.json server-side, so the scorecard measures what members see.

WHY THIS EXISTS. The board has applied the gradient-boosted temperature
correction in the browser since 2026-09-23, but score.py logs the RAW forecast:
`temp_f` src="live" carries bias +1.57 and MAE 2.08 while the number on the
screen is the corrected one. So the project ships a correction claiming MAE
1.09, shows it to members, and verifies something else entirely.

The failure that hides in that gap is total. A wrong feature ORDER, a stale
model file, the millimetre/inch mix-up that nearly shipped the same morning --
any of them would leave the scorecard looking perfectly healthy while the board
displayed nonsense. A correction nobody scores is a correction nobody can trust.

This records a second row, src="live-tempfix", from the same model the board
runs. The two are then directly comparable in the same scorecard, over the same
hours, against the same observation.

UNITS ARE REQUESTED, NOT CONVERTED, and as of 2026-09-24 there is nothing left
to convert. The model was fitted on Fahrenheit and KNOTS, which this asks for
directly. Precipitation used to be a feature and was the one input needing
arithmetic -- the board displays inches and had to multiply by 25.4 to reach the
archive's millimetres. It was worth 0.0000 F of MAE, so it was removed from the
model rather than defended: a feature worth nothing that carries a silent 25x
failure mode is a liability. No model input is now touched between the API and
the trees, on either side.

nowcast.py's own call is left alone: it does not set wind_speed_unit, so it
receives km/h, and changing that to serve this would move numbers the wind
logic already depends on.
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# ONE MODEL FILE, NOT THREE. The browser loads amenities/tempfix.json; in
# production this module runs from amenities/nowcast/, so it looks one level up
# and reads the SAME file the board is serving. A second copy beside this script
# would drift, and a correction that differs between the page and the scorecard
# is worse than no scorecard at all -- see the two-copy rule in CLAUDE.md.
MODEL = (os.environ.get("TEMPFIX_MODEL")
         or next((p for p in (os.path.join(HERE, os.pardir, "tempfix.json"),
                              os.path.join(HERE, "tempfix.json"))
                  if os.path.exists(p)), os.path.join(HERE, "tempfix.json")))
CACHE = os.path.join(HERE, ".tempfix-feed-cache.json")
TTL_S = 900
SOLAR_OFF_H = 8          # fixed UTC-8: the trainer's clock, not civil time

_model = None


def _cove():
    """(lat, lon), without importing marine.

    In production this file runs from hpma.org/amenities/nowcast/, where marine
    is not present -- `import marine` there returns None from every call and the
    correction silently never records. That is the two-copy trap CLAUDE.md
    warns about, found by actually running this from the board checkout rather
    than from the study repo where the import happens to succeed.
    """
    for p in (os.path.join(HERE, "microclimate.json"),
              os.path.join(HERE, os.pardir, os.pardir, "microclimate.json")):
        try:
            with open(p) as f:
                c = json.load(f)["cove"]
            return c["lat"], c["lon"]
        except Exception:  # noqa: BLE001
            continue
    return 47.2959, -122.8614      # the cove, from microclimate.json


def model():
    global _model
    if _model is None:
        try:
            with open(MODEL) as f:
                _model = json.load(f)
        except (OSError, ValueError):
            _model = {}
    return _model


def _feed():
    try:
        c = json.load(open(CACHE))
        if time.time() - c.get("at", 0) < TTL_S:
            return c.get("h") or {}
    except (OSError, ValueError):
        pass
    try:
        lat, lon = _cove()
        q = {"latitude": lat, "longitude": lon, "timezone": "GMT",
             "temperature_unit": "fahrenheit", "wind_speed_unit": "kn",
             "hourly": ("temperature_2m,dew_point_2m,relative_humidity_2m,"
                        "cloud_cover,shortwave_radiation,"
                        "wind_speed_10m,wind_gusts_10m"),
             "past_days": 1, "forecast_days": 2}
        h = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=25))["hourly"]
    except Exception:  # noqa: BLE001
        return {}
    try:
        json.dump({"h": h, "at": time.time()}, open(CACHE, "w"))
    except OSError:
        pass
    return h


def _predict(vec):
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


def corrected(when=None):
    """(raw_f, corrected_f) for the hour containing `when`, or (None, None).

    None rather than a guess whenever anything is missing: a correction applied
    to an incomplete feature row is worse than no correction, and the fallback
    everywhere else in this project is the uncorrected value.
    """
    md = model()
    feats = md.get("features")
    if not feats:
        return None, None
    h = _feed()
    if not h or "time" not in h:
        return None, None
    now = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    key = now.strftime("%Y-%m-%dT%H:00")
    try:
        i = h["time"].index(key)
    except (ValueError, KeyError):
        return None, None
    g = lambda k: (h.get(k) or [None] * (i + 1))[i]
    raw = g("temperature_2m")
    parts = {"f_temp": raw, "f_dewp": g("dew_point_2m"), "f_rh": g("relative_humidity_2m"),
             "f_cloud": g("cloud_cover"), "f_swr": g("shortwave_radiation"),
             "f_wind": g("wind_speed_10m"), "f_gust": g("wind_gusts_10m")}
    if any(v is None for v in parts.values()):
        return raw, None
    d = now - timedelta(hours=SOLAR_OFF_H)
    parts["hr"] = d.hour
    parts["doy"] = (d - datetime(d.year, 1, 1, tzinfo=timezone.utc)).days + 1
    parts["dpd"] = parts["f_temp"] - parts["f_dewp"]
    try:
        vec = [float(parts[k]) for k in feats]
    except (KeyError, TypeError):
        return raw, None
    delta = _predict(vec)
    if delta is None or not math.isfinite(delta):
        return raw, None
    return raw, round(raw - delta, 2)


if __name__ == "__main__":
    r, c = corrected()
    print("raw %s F   corrected %s F   delta %s"
          % (r, c, None if (r is None or c is None) else round(c - r, 2)))

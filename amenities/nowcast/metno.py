"""MET Norway locationforecast — a fifth forecast source, keyless.

Suggested by Dan via the Home Assistant met.no integration, which is a thin
wrapper over this API. We do not need Home Assistant; the API is public.

Worth having for a reason beyond "one more model": MET Norway is the institution
behind TITAN/titanlib and gridpp, both of which came up repeatedly in the
research spikes. Their locationforecast is ECMWF-derived with their own
post-processing, so it is genuinely independent of the Open-Meteo family — and
our five-year backfill already showed ECMWF beating HRRR at this site.

Carries three of the four variables we score: air_temperature, wind_speed and
precipitation_amount. NO GUST at this location (wind_speed_of_gust is absent
from both compact and complete here), so wind_gust_kt cannot be bake-off scored
against it.

THEIR TERMS ARE STRICT AND ENFORCED. Verbatim from the Terms of Service:

    "Do not ask too often, and don't repeat requests until the time indicated
     in the Expires response header. Cache data locally and use the
     If-Modified-Since request header to avoid repeatedly downloading the same
     data."
    "You must identify yourself"

So this module:
  * sends a User-Agent naming the project and its repository
  * refuses to refetch before the Expires timestamp it was given
  * sends If-Modified-Since and handles 304 by serving the cache
  * caches on disk, because mini_cycle runs board steps as separate processes

Expires runs ~30 min ahead and our cycle is 15 min, so in practice this fetches
every other cycle at most. Anything that returns 403 is almost always the
User-Agent -- their FAQ says so on the front page.

  series()  -> {hour_utc: (temp_f, wind_kt)} for the bake-off
  latest()  -> the current instant as a normalised dict
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MC = json.load(open(os.path.join(HERE, "microclimate.json")))
LAT, LON = MC["cove"]["lat"], MC["cove"]["lon"]

BASE = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
UA = {"User-Agent": "indian-cove-microclimate/1.0 "
                    "github.com/herzog303-commits/indian-cove-microclimate"}
CACHE = os.environ.get("METNO_CACHE") or os.path.join(HERE, ".metno-cache.json")

MS_KT = 1.943844
C_F = lambda c: c * 9.0 / 5.0 + 32.0


def _load_cache():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(c):
    try:
        tmp = CACHE + ".%d.tmp" % os.getpid()
        with open(tmp, "w") as f:
            json.dump(c, f)
        os.replace(tmp, CACHE)
    except OSError:
        pass


def fetch():
    """The forecast document, honouring Expires and If-Modified-Since."""
    c = _load_cache()
    now = time.time()
    # Their first rule: do not repeat the request before Expires.
    if c.get("body") and now < float(c.get("expires_epoch") or 0):
        return c["body"]

    req = urllib.request.Request(
        BASE + "?" + urllib.parse.urlencode({"lat": round(LAT, 4), "lon": round(LON, 4)}),
        headers=dict(UA))
    if c.get("last_modified"):
        req.add_header("If-Modified-Since", c["last_modified"])
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
            hdr = dict(r.headers)
    except urllib.error.HTTPError as e:
        if e.code == 304 and c.get("body"):
            # unchanged: extend our own cooldown and reuse what we hold
            c["expires_epoch"] = now + 1800
            _save_cache(c)
            return c["body"]
        print("metno: HTTP %d%s" % (e.code, " (check the User-Agent)" if e.code == 403 else ""))
        return c.get("body")
    except Exception as exc:  # noqa: BLE001
        print("metno: fetch failed (%s)" % exc)
        return c.get("body")

    exp = hdr.get("Expires")
    try:
        exp_epoch = datetime.strptime(exp, "%a, %d %b %Y %H:%M:%S %Z").replace(
            tzinfo=timezone.utc).timestamp() if exp else now + 1800
    except ValueError:
        exp_epoch = now + 1800
    _save_cache({"body": body, "expires_epoch": exp_epoch,
                 "last_modified": hdr.get("Last-Modified")})
    return body


def _rows(doc):
    for t in ((doc or {}).get("properties") or {}).get("timeseries") or []:
        try:
            when = datetime.fromisoformat(t["time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        yield when, t.get("data") or {}


def series():
    """{hour_utc: (temp_f, wind_kt)} — the shape record_bakeoff expects."""
    out = {}
    for when, data in _rows(fetch()):
        d = (data.get("instant") or {}).get("details") or {}
        t, w = d.get("air_temperature"), d.get("wind_speed")
        if t is None or w is None:
            continue
        out[when.replace(minute=0, second=0, microsecond=0)] = (
            round(C_F(t), 1), round(w * MS_KT, 1))
    return out


def precip_series():
    """{hour_utc: mm in the following hour} — met.no gives precip per interval."""
    out = {}
    for when, data in _rows(fetch()):
        n1 = (data.get("next_1_hours") or {}).get("details") or {}
        if "precipitation_amount" in n1:
            out[when.replace(minute=0, second=0, microsecond=0)] = n1["precipitation_amount"]
    return out


def latest():
    """Current instant, normalised to our units."""
    for when, data in _rows(fetch()):
        d = (data.get("instant") or {}).get("details") or {}
        if not d:
            continue
        return {
            "ts": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "temp_f": round(C_F(d["air_temperature"]), 1) if "air_temperature" in d else None,
            "wind_kt": round(d["wind_speed"] * MS_KT, 1) if "wind_speed" in d else None,
            "wind_dir": d.get("wind_from_direction"),
            "rh": d.get("relative_humidity"),
            "pressure_hpa": d.get("air_pressure_at_sea_level"),
            "cloud_pct": d.get("cloud_area_fraction"),
        }
    return None


if __name__ == "__main__":
    s = series()
    print("metno: %d hourly steps" % len(s))
    print("  latest:", latest())
    for k in sorted(s)[:4]:
        print("   %s  %5.1f F  %4.1f kt" % (k.strftime("%m-%d %Hz"), *s[k]))

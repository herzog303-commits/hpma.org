"""GOES-18 cloud mask over Indian Cove, straight from the satellite.

Gives the one thing nothing else in this pipeline provides: a LOCAL cloud
observation that works at night. The nine pyranometers are blind after sunset,
and METAR sky condition is regional (nearest airfield 23 km) and categorical.
GOES ABI band 13 is thermal IR, so the cloud mask is produced around the clock.

GEOMETRY. GOES-18 sits at 0N 137W. From the cove the satellite zenith angle is
56.1 degrees, giving a 1.79x pixel stretch, so the 2 km L2 products land at
about 2.0 x 3.6 km ON the cove. Verified by round-tripping the cove's lat/lon
through the fixed-grid projection and back: 2.10 km error, i.e. sub-pixel.

PRODUCT. ABI-L2-ACMC -- Clear Sky Mask, CONUS sector, every 5 minutes. BCM is
binary per pixel (0 clear_or_probably_clear, 1 cloudy_or_probably_cloudy), so a
single pixel is only ever 0% or 100%. Averaging a box around the cove turns it
into a usable fraction; 5x5 (~10 x 18 km) is the default.

BANDWIDTH, and why it is what it is. Files are 4.22 MB. Partial reads were
tried and rejected: fsspec + h5netcdf fetched 3,445 KB in 7.7 s against 4,220 KB
in 0.9 s for the whole file, because the HDF5 chunk layout means a windowed read
pulls most of the file anyway. netCDF4's "#mode=bytes" is not compiled into this
build. So: download the whole file, but only ONCE PER HOUR rather than per
cycle. ~101 MB/day, versus ~405 MB/day at cycle cadence, for data that does not
change meaningfully inside an hour at this resolution.

Needs xarray/netCDF4, so it runs under .venv-sscofs like sscofs.py does, and is
best-effort everywhere -- a satellite problem must never affect the board.

    .venv-sscofs/bin/python goes.py          # write goes_cloud.json
    .venv-sscofs/bin/python goes.py --box 9  # wider averaging box
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("GOES_OUT") or os.path.join(HERE, "goes_cloud.json")
BUCKET = "https://noaa-goes18.s3.amazonaws.com"
PRODUCT = "ABI-L2-ACMC"
UA = {"User-Agent": "indian-cove-microclimate/1.0 (marina microclimate study)"}
MIN_INTERVAL_S = 3300          # never resample inside ~55 min

MC = json.load(open(os.path.join(HERE, "microclimate.json")))
LAT, LON = MC["cove"]["lat"], MC["cove"]["lon"]


def newest_key(back_hours=3):
    """Newest ACMC object key, walking back an hour at a time if needed."""
    now = datetime.now(timezone.utc)
    for h in range(back_hours):
        t = now - timedelta(hours=h)
        prefix = "%s/%s/%s/%s/" % (PRODUCT, t.year, t.strftime("%j"), t.strftime("%H"))
        url = "%s/?list-type=2&prefix=%s&max-keys=60" % (BUCKET, prefix)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                body = r.read().decode(errors="replace")
        except Exception as exc:  # noqa: BLE001
            print("goes: listing failed (%s)" % exc)
            continue
        keys = re.findall(r"<Key>([^<]+)</Key>", body)
        if keys:
            return sorted(keys)[-1]
    return None


def _stat(a, how):
    """mean/max over the finite pixels, or None."""
    import numpy as np
    if a is None:
        return None
    v = a[np.isfinite(a)]
    if v.size == 0:
        return None
    return round(float(v.mean() if how == "mean" else v.max()), 3)


def _sza(ts):
    """Solar zenith angle at the scan. Recorded because the GOES-R ATBD and the
    peer-reviewed literature both document that the 3.9 um tests are erratic or
    inapplicable between 70 and 90 degrees -- and BOTH daytime scans of our one
    confirmed fog event (84.8 and 73.9 deg) fell inside that terminator band.
    Our "daytime detection fails" conclusion was drawn where the method is
    documented not to apply."""
    if ts is None:
        return None
    try:
        import marine
        return round(90.0 - marine.solar_elevation(ts), 1)
    except Exception:  # noqa: BLE001
        return None


def _projection(ds):
    """lat/lon -> fixed-grid scan angles, per the GOES-R Product User Guide."""
    p = ds["goes_imager_projection"].attrs
    H = p["perspective_point_height"] + p["semi_major_axis"]
    req, rpol = p["semi_major_axis"], p["semi_minor_axis"]
    lam0 = math.radians(p["longitude_of_projection_origin"])
    e2 = (req ** 2 - rpol ** 2) / req ** 2

    def to_xy(lat, lon):
        phi, lam = math.radians(lat), math.radians(lon)
        phic = math.atan((rpol ** 2 / req ** 2) * math.tan(phi))
        rc = rpol / math.sqrt(1 - e2 * math.cos(phic) ** 2)
        sx = H - rc * math.cos(phic) * math.cos(lam - lam0)
        sy = -rc * math.cos(phic) * math.sin(lam - lam0)
        sz = rc * math.sin(phic)
        # PUG visibility test: the point must lie on the visible disk
        if H * (H - sx) < sy * sy + (req ** 2 / rpol ** 2) * sz * sz:
            return None
        return (math.asin(-sy / math.sqrt(sx * sx + sy * sy + sz * sz)),
                math.atan(sz / sx))
    return to_xy


def _at_bearing(lat, lon, brg_deg, km):
    """Point km along a great-circle bearing from lat/lon."""
    R = 6371.0
    b = math.radians(brg_deg); d = km / R
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


RANGES_KM = (0, 20, 40, 60, 80, 120, 160)


def _upwind_profile(bcm, idx, wind_from_deg):
    """Cloud fraction along the upwind bearing, out to 160 km.

    We already download the whole CONUS array -- 3.8 million pixels -- and use
    25 of them. Reading a profile out to 160 km costs nothing extra, and it is
    the difference between "it is clear now" and "it will stay clear".
    """
    import numpy as np
    out = []
    for km in RANGES_KM:
        la, lo = _at_bearing(LAT, LON, wind_from_deg, km)
        r = idx(la, lo)
        if r is None:
            out.append({"km": km, "cloud_pct": None})
            continue
        jy, jx = r
        w = bcm[max(0, jy - 3):jy + 4, max(0, jx - 3):jx + 4].astype("float64")
        w = w[np.isfinite(w)]
        out.append({"km": km, "cloud_pct": round(100.0 * float(w.mean()), 1) if w.size else None})
    return out


def steering_wind():
    """Wind at cloud level, not at the dock.

    The first version of this used the 10 m wind and warned that it would
    overestimate lead time. Measured, that warning was an understatement: at
    one sample the surface read 1.8 kt while 850 hPa read 10.6 kt -- 5.9x --
    which turned a real ~6 h cloud arrival into a claimed 12.5 h.

    850 hPa (~1500 m) is the steering level for the low marine stratus that
    actually matters here; 700 hPa is recorded alongside for mid cloud. Both
    are free and keyless from Open-Meteo.
    """
    q = {"latitude": LAT, "longitude": LON, "timezone": "GMT", "forecast_days": 1,
         "hourly": ("wind_speed_10m,wind_direction_10m,"
                    "wind_speed_850hPa,wind_direction_850hPa,"
                    "wind_speed_700hPa,wind_direction_700hPa"),
         "wind_speed_unit": "kn"}
    try:
        h = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q),
            timeout=30))["hourly"]
    except Exception:  # noqa: BLE001
        return None
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    try:
        i = h["time"].index(now.strftime("%Y-%m-%dT%H:%M"))
    except (ValueError, KeyError):
        i = 0
    def g(k):
        v = h.get(k)
        return v[i] if v and i < len(v) else None
    return {"surface_kt": g("wind_speed_10m"), "surface_deg": g("wind_direction_10m"),
            "steer_kt": g("wind_speed_850hPa"), "steer_deg": g("wind_direction_850hPa"),
            "mid_kt": g("wind_speed_700hPa"), "mid_deg": g("wind_direction_700hPa"),
            "level": "850hPa"}


def _clear_outlook(profile, wind_kt, threshold=50.0):
    """How long until cloud arrives, from the upwind profile and the wind.

    CAVEAT worth carrying into anything that displays this: cloud is steered by
    flow well above the surface, typically faster than the 10 m wind and often
    veered from it. Using surface wind therefore OVERESTIMATES the lead time --
    cloud usually arrives sooner than this says. Treat it as an optimistic
    bound, not a promise.
    """
    first = next((p for p in profile if p["cloud_pct"] is not None
                  and p["cloud_pct"] >= threshold), None)
    if first is None:
        return {"clear_now": profile[0]["cloud_pct"] is not None and profile[0]["cloud_pct"] < 25,
                "cloud_km": None, "lead_h": None,
                "note": "no cloud >=%.0f%% within %d mi upwind" % (threshold, round(RANGES_KM[-1]*0.621371))}
    if not wind_kt or wind_kt < 1:
        return {"clear_now": profile[0]["cloud_pct"] < 25, "cloud_km": first["km"],
                "lead_h": None, "note": "wind too light to estimate arrival"}
    kmh = wind_kt * 1.852
    return {"clear_now": profile[0]["cloud_pct"] < 25,
            "cloud_km": first["km"], "cloud_mi": round(first["km"] * 0.621371),
            "lead_h": round(first["km"] / kmh, 1) if first["km"] else 0.0,
            "note": "850 hPa steering wind; partial cloud arrives before the "
                    "50%% solid-cloud threshold used here"}


def sample(box=5, key=None):
    """Download the newest cloud mask and average a box around the cove."""
    import numpy as np
    import xarray as xr

    key = key or newest_key()
    if not key:
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(BUCKET + "/" + key, headers=UA),
                                    timeout=180) as r:
            raw = r.read()
    except Exception as exc:  # noqa: BLE001
        print("goes: download failed (%s)" % exc)
        return None

    tmp = os.path.join(HERE, ".goes-tmp-%d.nc" % os.getpid())
    try:
        with open(tmp, "wb") as f:
            f.write(raw)
        ds = xr.open_dataset(tmp)
        xy = _projection(ds)(LAT, LON)
        if xy is None:
            return None
        ix = int(np.abs(ds.x.values - xy[0]).argmin())
        iy = int(np.abs(ds.y.values - xy[1]).argmin())
        bcm = ds["BCM"].values
        # The binary mask is not all this file carries. A deep-research spike
        # (2026-09-17) established that ACMC also holds a CONTINUOUS
        # Cloud_Probabilities field and the four-level ACM, and that we had
        # been discarding both. It matters: over a confirmed fog event BCM
        # reported 1-4% while Cloud_Probabilities ran 0.23-0.27 mean with a box
        # maximum of 0.82, against 0.003 mean / 0.023 max on a clear afternoon.
        # The binarisation threshold was flattening a real signal to a null.
        prob = ds["Cloud_Probabilities"].values if "Cloud_Probabilities" in ds else None
        acm = ds["ACM"].values if "ACM" in ds else None
        h = box // 2
        sl = (slice(max(0, iy - h), iy + h + 1), slice(max(0, ix - h), ix + h + 1))
        win = bcm[sl].astype("float64")
        pwin = prob[sl].astype("float64") if prob is not None else None
        awin = acm[sl].astype("float64") if acm is not None else None
        win = win[np.isfinite(win)]
        if win.size == 0:
            return None
        # scan start time is encoded in the filename: ...._sYYYYDDDHHMMSSs_...
        m = re.search(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})", key)
        ts = None
        if m:
            y, doy, hh, mm, ss = (int(g) for g in m.groups())
            ts = (datetime(y, 1, 1, tzinfo=timezone.utc)
                  + timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss))
        # upwind profile, using the regional wind direction the nowcast already
        # computed. Free -- the array is already in memory.
        prof = None; outlook = None
        try:
            sw = steering_wind() or {}
            wd = sw.get("steer_deg"); wk = sw.get("steer_kt")
            if wd is None:      # fall back to the surface wind the nowcast has
                nc_path = os.environ.get("NOWCAST_FOR_GOES") or os.path.join(HERE, "nowcast.json")
                with open(nc_path) as f:
                    w = (json.load(f).get("wind") or {})
                wd, wk = w.get("regional_dir_deg"), w.get("regional_kt")
            if wd is not None:
                def _idx(la, lo):
                    xy = _projection(ds)(la, lo)
                    if xy is None:
                        return None
                    return (int(np.abs(ds.y.values - xy[1]).argmin()),
                            int(np.abs(ds.x.values - xy[0]).argmin()))
                prof = _upwind_profile(bcm, _idx, wd)
                outlook = _clear_outlook(prof, wk)
                outlook["wind_from_deg"] = wd
                outlook["wind_kt"] = wk
                outlook["wind"] = sw
        except Exception:  # noqa: BLE001
            pass

        out = {
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scan_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None,
            "source": "GOES-18 ABI-L2-ACMC",
            "file": key.split("/")[-1],
            "box_px": box,
            "box_km": [round(box * 2.0, 1), round(box * 3.6, 1)],
            "n_px": int(win.size),
            "cloud_pct": round(100.0 * float(win.mean()), 1),
            # Continuous probability is the more honest number when the fog is
            # thin: the mask says yes/no, this says how sure it is. The MAX over
            # the box separates our cases where the mean does not -- 0.82 on a
            # fog night against 0.37 on a clear one.
            "cloud_prob_mean": _stat(pwin, "mean"),
            "cloud_prob_max": _stat(pwin, "max"),
            "acm_mean": _stat(awin, "mean"),
            "solar_zenith_deg": _sza(ts),
            "centre_cloudy": bool(bcm[iy, ix] >= 0.5),
            "pixel_km": [2.0, 3.6],
            "bytes": len(raw),
            "upwind": prof,
            "outlook": outlook,
        }
        ds.close()
        return out
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", type=int, default=5)
    ap.add_argument("--force", action="store_true", help="ignore the hourly interval")
    a = ap.parse_args()

    # Hourly is deliberate: 4.22 MB a file, and cloud at 2 km does not change
    # meaningfully inside an hour. Per-cycle sampling would be ~405 MB/day.
    if not a.force and os.path.exists(OUT):
        try:
            age = time.time() - os.path.getmtime(OUT)
            if age < MIN_INTERVAL_S:
                print("goes: last sample %.0f min ago, skipping" % (age / 60))
                return 0
        except OSError:
            pass

    r = sample(box=a.box)
    if not r:
        print("goes: no sample")
        return 1
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(r, f, indent=2)
    os.replace(tmp, OUT)
    # History, so the outlook can be VERIFIED. goes_cloud.json is overwritten
    # each hour; without this log there is no record of what the sky actually
    # did, and "cloud in 6 h" is an unfalsifiable claim.
    try:
        log = os.environ.get("GOES_LOG") or os.path.join(HERE, "goes_log.jsonl")
        o = r.get("outlook") or {}
        with open(log, "a") as f:
            f.write(json.dumps({
                "scan_utc": r.get("scan_utc"), "cloud_pct": r.get("cloud_pct"),
                "clear_now": o.get("clear_now"), "next_cloud_km": o.get("cloud_km"),
                "lead_h": o.get("lead_h"), "wind": o.get("wind"),
                "upwind": r.get("upwind")}) + "\n")
    except OSError:
        pass
    o = r.get("outlook") or {}
    tail = ""
    if o.get("cloud_km") is not None:
        tail = " | cloud %d mi upwind" % round(o["cloud_km"] * 0.621371) + (
            ", ~%.1fh out" % o["lead_h"] if o.get("lead_h") is not None else "")
    elif o:
        tail = " | clear to %d mi upwind" % round(RANGES_KM[-1] * 0.621371)
    print("goes: %s cloud %.0f%% over %.0fx%.0f km (%.1f MB)%s"
          % (r["file"][:28], r["cloud_pct"], r["box_km"][0], r["box_km"][1],
             r["bytes"] / 1e6, tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Morning marine layer, measured with the pyranometers we already read.

WHY THIS EXISTS. The scorecard showed Open-Meteo over-forecasting shortwave by
+114 W/m2, concentrated in the morning. The first explanation offered was
terrain or tree shading, and it was WRONG: fixed obstruction repeats at the
same sun angle every day, and these stations swing from 8% to 87% of
clear-sky at the same hour on different days. A tree does not move. A member
who looks out of the window in the morning had the right answer first --
marine layer.

WHY NOT THE SATELLITE. goes.py reads ABI-L2-ACMC, the Clear Sky Mask, and it
reported 0.0% cloud on exactly the mornings our pyranometers measured Kt 0.08.
Every station sits INSIDE the 10 x 18 km box GOES averages, so this is not a
sampling miss. It is the known weakness of IR cloud masking over water: a
shallow marine layer whose top is nearly the temperature of the sea beneath it
produces almost no thermal contrast, and the mask calls it clear. Detecting it
from space needs a different product -- the 3.9/11 um brightness-temperature
difference, or cloud-top height -- not a different box.

WHAT THIS MEASURES. The clear-sky index

    Kt = observed GHI / theoretical clear-sky GHI

per station, using Haurwitz for the clear-sky reference (a function of solar
elevation alone, good to ~10%, and no tuning to argue about). Kt near 1 is an
unobstructed sky; Kt below 0.4 is thick cloud overhead. Because we have eight
pyranometers inside 5 km, the SPREAD across them maps the cloud edge at a
resolution the satellite product does not deliver here: on 2026-09-16 at
09:00, 0.87 at one station and 0.08 at another 4.6 km away.

Daylight only, obviously. At night this is blind and GOES is what we have --
which is worth remembering when reading fire_clear_night, because night is
when an IR mask has the least contrast to work with.
"""
import json
import math
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MC = json.load(open(os.path.join(HERE, "microclimate.json")))
LAT, LON = MC["cove"]["lat"], MC["cove"]["lon"]
OUT = os.environ.get("MARINE_LOG") or os.path.join(HERE, "marine_log.jsonl")

# Kt thresholds. Deliberately wide in the middle: thin high cloud and a hazy
# sky both land there and we do not claim to tell them apart.
KT_CLEAR, KT_CLOUD = 0.75, 0.40
MIN_ELEV_DEG = 10.0          # below this the clear-sky reference is unreliable

# QC. Broken cloud really can push GHI above the clear-sky value -- edge
# reflection is a genuine effect worth perhaps 20-25%. Anything beyond this is
# not weather. Measured against the archive with the sun above 25 degrees,
# IWASHING2 exceeds it in 7% of hours, KWALAKEB35 in 6% and KWAALLYN13 in 4%,
# with worst cases near 3,000 W/m2 -- roughly twice the solar constant at the
# top of the atmosphere, so the sensor or its scaling is wrong, not the sky.
# These are the same stations whose low readings drove an earlier and overly
# confident "patchy marine layer" conclusion, which is why this guard exists.
KT_IMPOSSIBLE = 1.35
QC_MIN_ELEV_DEG = 25.0

_D2R = math.pi / 180.0


def _jd(dt):
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + (2 - a + a // 4) - 1524.5


def solar_elevation(dt_utc, lat=LAT, lon=LON):
    """Sun elevation in degrees. Same abbreviated series fire.py uses."""
    jd = _jd(dt_utc)
    T = (jd - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * T
    m = (357.52911 + 35999.05029 * T) * _D2R
    lam = (l0 + 1.914602 * math.sin(m) + 0.019993 * math.sin(2 * m)
           + 0.000289 * math.sin(3 * m)) % 360.0
    e = (23.439291 - 0.0130042 * T) * _D2R
    lo = lam * _D2R
    ra = math.atan2(math.sin(lo) * math.cos(e), math.cos(lo)) / _D2R % 360.0
    dec = math.asin(math.sin(e) * math.sin(lo)) / _D2R
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360.0
    h = ((gmst + lon - ra) % 360.0) * _D2R
    p, dc = lat * _D2R, dec * _D2R
    return math.asin(math.sin(p) * math.sin(dc) + math.cos(p) * math.cos(dc) * math.cos(h)) / _D2R


def solar_azimuth(dt_utc, lat=LAT, lon=LON):
    """Sun azimuth in degrees from north. Needed to tell a fixed obstruction
    (which sits at a BEARING) from cloud (which does not care)."""
    jd = _jd(dt_utc)
    T = (jd - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * T
    m = (357.52911 + 35999.05029 * T) * _D2R
    lam = (l0 + 1.914602 * math.sin(m) + 0.019993 * math.sin(2 * m)
           + 0.000289 * math.sin(3 * m)) % 360.0
    e = (23.439291 - 0.0130042 * T) * _D2R
    lo = lam * _D2R
    ra = math.atan2(math.sin(lo) * math.cos(e), math.cos(lo)) / _D2R % 360.0
    dec = math.asin(math.sin(e) * math.sin(lo)) / _D2R
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360.0
    h = ((gmst + lon - ra) % 360.0) * _D2R
    p, dc = lat * _D2R, dec * _D2R
    y = -math.sin(h)
    x = math.tan(dc) * math.cos(p) - math.sin(p) * math.cos(h)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def clearsky_ghi(dt_utc, lat=LAT, lon=LON):
    """Haurwitz clear-sky global horizontal irradiance, W/m2."""
    el = solar_elevation(dt_utc, lat, lon)
    if el <= 0:
        return 0.0, el
    cz = math.cos(math.radians(90.0 - el))
    return 1098.0 * cz * math.exp(-0.059 / cz), el


def kt(observed_w_m2, dt_utc, lat=LAT, lon=LON):
    """Clear-sky index, or None when the sun is too low to judge."""
    cs, el = clearsky_ghi(dt_utc, lat, lon)
    if el < MIN_ELEV_DEG or cs <= 0:
        return None
    return round(observed_w_m2 / cs, 3)


def survey(when=None):
    """Kt at every station that reports solar, right now.

    Returns None outside usable daylight rather than a page of zeroes.
    """
    try:
        import wu
    except Exception:  # noqa: BLE001
        return None
    when = when or datetime.now(timezone.utc)
    cs, el = clearsky_ghi(when)
    if el < MIN_ELEV_DEG:
        return None
    per, rejected = {}, {}
    for st in wu.independent_stations(MC):
        try:
            o = wu.wu_current(st) if hasattr(wu, "wu_current") else None
            v = (o or {}).get("solar_w_m2")
        except Exception:  # noqa: BLE001
            v = None
        if v is None:
            continue
        k = round(float(v) / cs, 3)
        if el >= QC_MIN_ELEV_DEG and k > KT_IMPOSSIBLE:
            rejected[st] = k          # not weather; do not let it vote
            continue
        per[st] = k
    if len(per) < 3:
        return None
    vals = sorted(per.values())
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    clouded = [s for s, k in per.items() if k < KT_CLOUD]
    clear = [s for s, k in per.items() if k >= KT_CLEAR]
    return {
        "t": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sun_elev_deg": round(el, 1), "clearsky_ghi": round(cs),
        "kt_median": round(med, 3), "kt_min": vals[0], "kt_max": vals[-1],
        "kt_spread": round(vals[-1] - vals[0], 3),
        "n": n, "n_clouded": len(clouded), "n_clear": len(clear),
        "per_station": per, "rejected": rejected,
        # A wide spread means the sky is not uniform across 5 km, which is the
        # signature worth recording: a cloud EDGE sitting over the cove.
        "patchy": (vals[-1] - vals[0]) >= 0.35,
        "state": ("clouded" if med < KT_CLOUD else
                  "clear" if med >= KT_CLEAR else "partial"),
    }


def main():
    s = survey()
    if not s:
        print("marine: sun too low (or too few solar stations) -- nothing to measure")
        return 0
    print("marine: %s | Kt med %.2f (min %.2f max %.2f, spread %.2f)%s"
          % (s["state"], s["kt_median"], s["kt_min"], s["kt_max"], s["kt_spread"],
             "  PATCHY -- cloud edge over the cove" if s["patchy"] else ""))
    print("  sun %.1f deg, clear-sky %d W/m2, %d/%d stations under cloud"
          % (s["sun_elev_deg"], s["clearsky_ghi"], s["n_clouded"], s["n"]))
    for st, k in sorted(s["per_station"].items(), key=lambda kv: -kv[1]):
        print("    %-14s Kt %.2f  %s" % (st, k, "clear" if k >= KT_CLEAR else
                                         "CLOUD" if k < KT_CLOUD else "partial"))
    try:
        with open(OUT, "a") as f:
            f.write(json.dumps(s) + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

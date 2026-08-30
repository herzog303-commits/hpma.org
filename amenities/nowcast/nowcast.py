"""Phase 2 -- the Indian Cove nowcast engine.

Consumes microclimate.json + live feeds and emits nowcast.json: a 1-4h
rain outlook with a confidence, built the microclimate-aware way --

  * radar is DOWN-WEIGHTED (it overshoots the cove; can't see low rain here),
  * model precip (Open-Meteo, which blends HRRR) carries the horizon,
  * wind-regime + barometric tendency supply the local correction,
  * a crossfade leans on the near-term nowcast early and the model later.

Stdlib only. Meant to run on a schedule and drop nowcast.json where the board
reads it -- same cron->JSON pattern as the surge feed.

  python nowcast.py            # print + write nowcast.json
"""
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = os.path.join(HERE, "microclimate.json")
OUT = os.environ.get("NOWCAST_OUT") or os.path.join(HERE, "nowcast.json")


def load_params():
    with open(PARAMS) as f:
        return json.load(f)


def fetch(cove):
    lat, lon = cove["lat"], cove["lon"]
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "precipitation,temperature_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m,pressure_msl,cloud_cover,is_day",
        "minutely_15": "precipitation",
        "hourly": "precipitation,precipitation_probability,pressure_msl,temperature_2m",
        "temperature_unit": "fahrenheit",
        "timezone": "America/Los_Angeles",
        "forecast_hours": 6, "forecast_minutely_15": 12,
    })
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


# present-weather tokens that mean precipitation is falling (mist/fog/haze excluded)
_PRECIP_WX = ("RA", "DZ", "SN", "SG", "GR", "GS", "PL", "IC", "UP", "SH", "TS")


def _haversine_mi(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, asin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 3958.8 * 2 * asin(sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2):
    """Compass bearing FROM point 1 TO point 2 (deg). For an upwind station this
    is the direction the weather is coming from."""
    from math import radians, degrees, sin, cos, atan2
    dl = radians(lon2 - lon1)
    y = sin(dl) * cos(radians(lat2))
    x = cos(radians(lat1))*sin(radians(lat2)) - sin(radians(lat1))*cos(radians(lat2))*cos(dl)
    return (degrees(atan2(y, x)) + 360) % 360


_COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _compass(deg):
    return _COMPASS[round(deg / 22.5) % 16]


def fetch_synoptic_rain(params, series=None):
    """Closest-gauge rain check via Synoptic (needs SYNOPTIC_TOKEN env -- a GitHub
    secret in the Action; absent -> skipped, METAR still runs). G2160 Grapeview
    (~4.5 mi up Case Inlet) is the nearest gauge; it reports a running daily
    accumulation, so a RISE over the last hour means rain is falling now. Pass
    `series` ({stid: [(lat,lon,accum), ...]}) to bypass the network for testing."""
    tok = os.environ.get("SYNOPTIC_TOKEN")
    gauges = params["stations"].get("precip_gauges") or []
    if (not tok and series is None) or not gauges:
        return []
    cove = params["cove"]
    if series is None:
        q = urllib.parse.urlencode({"stid": ",".join(gauges), "recent": 90,
                                    "vars": "precip_accum_since_local_midnight",
                                    "units": "precip|in", "token": tok, "obtimezone": "utc"})
        try:
            with urllib.request.urlopen("https://api.synopticdata.com/v2/stations/timeseries?" + q, timeout=45) as r:
                data = json.load(r)
        except Exception as exc:  # noqa: BLE001
            print(f"nowcast: Synoptic fetch failed ({exc})")
            return []
        series = {}
        for s in data.get("STATION", []):
            vals = [v for v in s["OBSERVATIONS"].get("precip_accum_since_local_midnight_set_1", []) if v is not None]
            series[s["STID"]] = (float(s["LATITUDE"]), float(s["LONGITUDE"]), vals)
    wet = []
    for sid, val in series.items():
        lat, lon, vals = val
        if len(vals) < 2:
            continue
        delta = vals[-1] - vals[0] if vals[-1] >= vals[0] else vals[-1]   # guard midnight reset
        if delta > 0.001:
            wet.append({"station": sid, "wx": "rain (gauge)", "precip_in": round(delta, 2),
                        "dist_mi": round(_haversine_mi(cove["lat"], cove["lon"], lat, lon), 1),
                        "bearing_deg": round(_bearing_deg(cove["lat"], cove["lon"], lat, lon)),
                        "age_min": 0, "source": "synoptic"})
    return wet


NOW_MI = 8            # a wet station this close = rain AT the cove (vs upwind = inbound)


def observe_precip(params, regime=None, regional_kt=0, reports=None):
    """Is precipitation being OBSERVED near the cove, and is more inbound? Merges the
    closest Synoptic gauge (G2160 Grapeview) with keyless METAR stations, then splits
    the signal: 'now' = a wet station within NOW_MI (rain at the cove); 'inbound' = a
    wet station UPWIND for the current regime (weather advecting toward us), with a
    lead-time estimate from the regional wind. Catches the light marine rain the model
    misses. Returns an 'observed' dict or None on failure. Pass `reports` for tests."""
    cove = params["cove"]
    st = params["stations"]
    ids = list(dict.fromkeys([st.get("primary_obs"), st.get("primary_taf"),
                              *st.get("fallback_obs", [])]))
    ids = [i for i in ids if i]
    if reports is None:
        url = "https://aviationweather.gov/api/data/metar?" + urllib.parse.urlencode(
            {"ids": ",".join(ids), "format": "json", "hours": 2})
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hpma-marina-board"})
            with urllib.request.urlopen(req, timeout=30) as r:
                reports = json.load(r)
        except Exception as exc:  # noqa: BLE001
            print(f"nowcast: METAR fetch failed ({exc})")
            return None
    latest = {}
    for m in reports:                                   # keep the most recent per station
        sid = m.get("icaoId")
        if sid and (sid not in latest or m.get("reportTime", "") > latest[sid].get("reportTime", "")):
            latest[sid] = m
    now = datetime.now(timezone.utc)
    wet = []
    for sid, m in latest.items():
        wx = (m.get("wxString") or "").upper()
        pr = m.get("precip")
        if not (any(tok in wx for tok in _PRECIP_WX) or (pr and pr > 0)):
            continue
        try:
            rt = datetime.fromisoformat(m["reportTime"].replace("Z", "+00:00"))
            age = round((now - rt).total_seconds() / 60)
        except Exception:  # noqa: BLE001
            age = None
        if age is not None and age > 75:                # stale -> not "now"
            continue
        wet.append({"station": sid, "wx": wx or None, "precip_in": pr,
                    "dist_mi": round(_haversine_mi(cove["lat"], cove["lon"], m["lat"], m["lon"]), 1),
                    "bearing_deg": round(_bearing_deg(cove["lat"], cove["lon"], m["lat"], m["lon"])),
                    "age_min": age, "source": "metar"})
    wet = fetch_synoptic_rain(params) + wet         # closest gauge (Grapeview) first
    wet.sort(key=lambda w: w["dist_mi"])

    # 'now' = wet at/near the cove; 'inbound' = wet UPWIND for this regime, advecting in
    upwind = set()
    for r in params.get("wind_regimes", []):
        if regime and r["name"] == regime:
            upwind = set(r.get("upwind", []))
    now = next((w for w in wet if w["dist_mi"] <= NOW_MI), None)
    inbound = None
    for w in wet:
        if w["dist_mi"] > NOW_MI and w["station"] in upwind:
            adv_mph = max(15.0, regional_kt * 1.15)          # advection speed (>= a floor)
            lead = w["dist_mi"] / adv_mph
            inbound = {**w, "from_dir": _compass(w["bearing_deg"]),
                       "lead_h": round(lead * 2) / 2 or 0.5}  # nearest 0.5 h, min 0.5
            break

    if now:
        note = (f"rain now near cove: {now['station']} {now['dist_mi']:.0f} mi "
                f"({now['wx'] or 'gauge'})")
    elif inbound:
        note = (f"rain inbound from {inbound['from_dir']}: {inbound['station']} "
                f"{inbound['dist_mi']:.0f} mi, ~{inbound['lead_h']:g} h out")
    else:
        note = "no precip observed near or upwind of the cove"
    return {
        "raining_nearby": bool(now),
        "now": now,
        "inbound": inbound,
        "checked": ids + (params["stations"].get("precip_gauges") or []),
        "wet_stations": wet,
        "note": note,
    }


def classify_regime(params, wind_dir, wind_kt):
    if wind_dir is None or (wind_kt is not None and wind_kt < 3):
        return next(r for r in params["wind_regimes"] if r["name"] == "slack")
    d = wind_dir % 360
    for reg in params["wind_regimes"]:
        if reg["name"] == "slack":
            continue
        if reg["dir_min"] <= d <= reg["dir_max"]:
            return reg
    return next(r for r in params["wind_regimes"] if r["name"] == "slack")


def marina_wind(params, regime, wkt, wdir, cur):
    """Downscale the regional (free-stream) forecast wind to the marina using the
    WindNinja wind_shelter table. On light, clear nights, fall through to the
    stable cold-air-drainage estimate (near-calm) instead of the mechanical factor.
    Returns None if no wind_shelter table is present."""
    ws = params.get("wind_shelter")
    if not ws:
        return None
    reg = ws["by_regime"].get(regime["name"]) or ws["by_regime"].get("slack")
    m = reg["marina"]
    factor, shift = m["factor"], m.get("dir_shift", 0)
    rgust = round((cur.get("wind_gusts_10m") or 0) * 0.539957, 1)   # km/h -> kt
    local_kt = round(wkt * factor, 1)
    local_gust = round(rgust * factor, 1)
    local_dir = round((wdir + shift) % 360) if wdir is not None else None
    mode = "mechanical"
    # stable drainage: light regional wind + night + clear sky -> cove pools near-calm
    clear = (cur.get("cloud_cover") if cur.get("cloud_cover") is not None else 100) < 40
    night = cur.get("is_day") == 0
    if wkt < 6 and night and clear:
        drain = ws.get("stable_night", {}).get("by_point", {}).get("marina", {})
        stable_kt = drain.get("stable_kt")
        if stable_kt is not None:
            local_kt = round(min(local_kt, stable_kt), 1)
            local_gust = local_kt                       # calm drainage night: no gusts
            local_dir = drain.get("stable_dir", local_dir)
            mode = "drainage"
    # exposed-point wind: Dougall Point (the headland people actually stand on) --
    # the marina number badly understates it. Sustained + gust via its shelter factor.
    ex_f = reg.get("DougallPt", {}).get("factor", 1.0)
    exposed = None if mode == "drainage" else {
        "point": "Dougall Pt", "factor": ex_f,
        "kt": round(wkt * ex_f, 1), "gust_kt": round(rgust * ex_f, 1)}
    return {
        "regional_kt": round(wkt, 1),
        "regional_gust_kt": rgust,
        "regional_dir_deg": wdir,
        "marina_kt": local_kt,
        "marina_gust_kt": local_gust,
        "marina_dir_deg": local_dir,
        "shelter_factor": factor,
        "mode": mode,
        "exposed": exposed,
        "note": ("cold-air drainage: cove near-calm on this clear light night"
                 if mode == "drainage" else
                 f"marina {local_kt:g} kt (x{factor}), exposed pts ~{exposed['kt']:g} "
                 f"gusting {exposed['gust_kt']:g} ({regime['name']})"),
    }


def baro_tendency(data):
    """Pressure change (hPa) over the last 3h, from hourly pressure_msl."""
    h = data.get("hourly", {})
    times, p = h.get("time", []), h.get("pressure_msl", [])
    now = data.get("current", {}).get("time", "")[:13]  # yyyy-mm-ddThh
    k = next((i for i, t in enumerate(times) if t[:13] == now), None)
    if k is None or not p:
        return 0.0
    j = max(0, k - 3)
    if p[k] is None or p[j] is None:
        return 0.0
    return p[k] - p[j]


def _amount_to_risk(mm):
    if mm >= 0.3:
        return 0.85
    if mm >= 0.1:
        return 0.5
    if mm > 0.0:
        return 0.25
    return 0.05


def minutely_risk(data, upto_min, ratio=1.0):
    m = data.get("minutely_15", {})
    vals = m.get("precipitation", []) or []
    n = max(1, upto_min // 15)
    window = [v for v in vals[:n] if v is not None]
    return _amount_to_risk((max(window) if window else 0.0) * ratio)


def hourly_risk(data, upto_min, ratio=1.0):
    h = data.get("hourly", {})
    prob = h.get("precipitation_probability", []) or []
    amt = h.get("precipitation", []) or []
    n = max(1, upto_min // 60)
    p = [x for x in prob[:n] if x is not None]
    a = [x for x in amt[:n] if x is not None]
    prisk = (max(p) / 100.0) if p else 0.0
    arisk = _amount_to_risk((max(a) if a else 0.0) * ratio)  # rain-shadow scaled
    return max(prisk, arisk)


def regime_risk(regime, tend, params):
    b = params["baro"]
    r = regime["wet_prior"]
    if tend <= b["falling_fast_hpa_3h"]:
        r += b["wet_nudge"]
    elif tend >= b["rising_fast_hpa_3h"]:
        r += b["dry_nudge"]
    return max(0.0, min(1.0, r))


def confidence(components):
    """High when the independent signals agree; low when they diverge."""
    spread = max(components) - min(components)
    if spread < 0.25:
        return "high"
    if spread < 0.5:
        return "moderate"
    return "low"


def main():
    params = load_params()
    cove = params["cove"]
    try:
        data = fetch(cove)
    except Exception as exc:  # noqa: BLE001
        print(f"nowcast: live fetch failed ({exc})")
        return

    cur = data.get("current", {})
    wdir = cur.get("wind_direction_10m")
    wkt = (cur.get("wind_speed_10m") or 0) * 0.539957  # km/h -> kt
    regime = classify_regime(params, wdir, wkt)
    wind = marina_wind(params, regime, wkt, wdir, cur)
    obs = observe_precip(params, regime["name"], wkt)   # now (closest gauge) + inbound (upwind)
    tend = baro_tendency(data)
    baro_word = ("falling" if tend <= params["baro"]["falling_fast_hpa_3h"]
                 else "rising" if tend >= params["baro"]["rising_fast_hpa_3h"]
                 else "steady")

    # 4-year calibration: rain-shadow ratio + seasonal temp offset
    cal = params.get("model_calibration", {})
    ratio = cal.get("precip_ratio") or 1.0
    SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
              6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
    month = int((cur.get("time") or "2000-01")[5:7])
    toff = (cal.get("temp_offset_by_season_f") or {}).get(
        SEASON[month], cal.get("temp_offset_f") or 0)
    tnow = cur.get("temperature_2m")
    temp_cove = round(tnow + toff, 1) if tnow is not None else None

    buckets = []
    for band in params["blend"]["crossfade"]:
        w = band["weights"]
        comp = {
            "minutely": minutely_risk(data, band["upto_min"], ratio),
            "hourly": hourly_risk(data, band["upto_min"], ratio),
            "regime": regime_risk(regime, tend, params),
        }
        risk = sum(w[k] * comp[k] for k in w)
        buckets.append({"label": band["label"], "risk": round(risk, 2),
                        "components": {k: round(v, 2) for k, v in comp.items()}})

    thr = params["blend"]["rain_threshold"]
    onset = next((b for b in buckets if b["risk"] >= thr), None)
    driver = onset or max(buckets, key=lambda b: b["risk"])
    conf = confidence(list(driver["components"].values()))

    if onset:
        headline = f"Rain likely {onset['label']}"
    elif max(b["risk"] for b in buckets) >= thr * 0.6:
        headline = "Showers possible within 4h"
    else:
        headline = "Dry through 4h"
    detail = f"{regime['name']} flow, baro {baro_word}"

    # OBSERVED precip overrides the model headline (model/radar miss light marine
    # rain -- a real gauge report is ground truth). 'now' = at the cove; else 'inbound'
    # = rain upwind, advecting toward us with a lead-time estimate.
    def _wxword(wx):
        wx = wx or ""
        return ("Showers" if "SH" in wx else "Drizzle" if "DZ" in wx
                else "Light rain" if ("-" in wx and "RA" in wx) else "Rain" if "RA" in wx
                else "Snow" if "SN" in wx else "Precip")
    if obs and obs.get("now"):
        nw = obs["now"]
        headline = f"{_wxword(nw['wx'])} observed nearby"
        detail = f"{nw['station']} {nw['wx'] or 'precip'} {nw['dist_mi']:.0f} mi · forecast: {detail}"
    elif obs and obs.get("inbound"):
        ib = obs["inbound"]
        headline = f"Rain inbound from {ib['from_dir']} (~{ib['lead_h']:g}h)"
        detail = f"upwind {ib['station']} {ib['wx'] or 'precip'} {ib['dist_mi']:.0f} mi · forecast: {detail}"

    nowcast = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cove": cove["name"],
        "headline": headline,
        "detail": detail,
        "confidence": conf,
        "regime": regime["name"],
        "baro_hpa_3h": round(tend, 1),
        "wind_dir_deg": wdir,
        "wind_kt": round(wkt, 1),
        "wind": wind,
        "observed": obs,
        "radar_note": "radar excluded: overshoots the cove (see microclimate.json)",
        "precip_ratio": ratio,
        "temp_model_f": tnow,
        "temp_cove_f": temp_cove,
        "temp_offset_f": round(toff, 2),
        "timeline": buckets,
    }
    with open(OUT, "w") as f:
        json.dump(nowcast, f, indent=2)

    print("=" * 60)
    print(f" INDIAN COVE NOWCAST   ({nowcast['generated_utc']})")
    print("=" * 60)
    print(f"  {headline.upper()}   [{conf} confidence]")
    print(f"  {detail}  (wind {wdir}deg {wkt:.0f} kt, dP/3h {tend:+.1f} hPa)")
    if wind:
        ex = wind.get("exposed")
        exs = f" | exposed {ex['kt']:.0f} gusting {ex['gust_kt']:.0f}" if ex else ""
        print(f"  MARINA WIND {wind['marina_kt']:.0f} kt "
              f"(regional {wind['regional_kt']:.0f} kt, x{wind['shelter_factor']:.2f}, {wind['mode']}){exs}")
    if obs:
        print(f"  OBSERVED: {obs['note']}")
    print("  " + "-" * 46)
    for b in buckets:
        bar = "#" * int(b["risk"] * 20)
        print(f"  {b['label']:10} risk {b['risk']:.2f} |{bar:<20}| "
              f"m{b['components']['minutely']:.2f} h{b['components']['hourly']:.2f} "
              f"r{b['components']['regime']:.2f}")
    print(f"\n  wrote -> {os.path.relpath(OUT, HERE)}")


if __name__ == "__main__":
    main()

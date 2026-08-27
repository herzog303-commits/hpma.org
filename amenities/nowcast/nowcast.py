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
        "current": "precipitation,temperature_2m,wind_speed_10m,wind_direction_10m,pressure_msl,cloud_cover,is_day",
        "minutely_15": "precipitation",
        "hourly": "precipitation,precipitation_probability,pressure_msl,temperature_2m",
        "temperature_unit": "fahrenheit",
        "timezone": "America/Los_Angeles",
        "forecast_hours": 6, "forecast_minutely_15": 12,
    })
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


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
    local_kt = round(wkt * factor, 1)
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
            local_dir = drain.get("stable_dir", local_dir)
            mode = "drainage"
    return {
        "regional_kt": round(wkt, 1),
        "regional_dir_deg": wdir,
        "marina_kt": local_kt,
        "marina_dir_deg": local_dir,
        "shelter_factor": factor,
        "mode": mode,
        "note": ("cold-air drainage: cove near-calm on this clear light night"
                 if mode == "drainage" else
                 f"marina sheltered to {int(round(factor*100))}% of open-water wind ({regime['name']})"),
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
        print(f"  MARINA WIND {wind['marina_kt']:.0f} kt "
              f"(regional {wind['regional_kt']:.0f} kt, x{wind['shelter_factor']:.2f}, {wind['mode']})")
    print("  " + "-" * 46)
    for b in buckets:
        bar = "#" * int(b["risk"] * 20)
        print(f"  {b['label']:10} risk {b['risk']:.2f} |{bar:<20}| "
              f"m{b['components']['minutely']:.2f} h{b['components']['hourly']:.2f} "
              f"r{b['components']['regime']:.2f}")
    print(f"\n  wrote -> {os.path.relpath(OUT, HERE)}")


if __name__ == "__main__":
    main()

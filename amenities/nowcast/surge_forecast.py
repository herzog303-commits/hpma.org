"""Publish a multi-day SURGE forecast (surge_forecast.json) for the board + alert.

Turns the calibrated surge_model (microclimate.json) + the Open-Meteo pressure/wind
FORECAST into a surge-vs-time series, anchored to the live Tacoma residual so it
matches reality now and evolves with the forecast out ~5 days. This is what gives
the board's tide curve and the email alert their multi-day lead time (vs the old
hours-only persistence).

  surge_ft(t) = model(P,W,t) + (live_residual - model_now) * fade(t)

Output (JSON, the board's SURGE_FORECAST_URL format): [{"t": iso, "ft": x.xx}, ...]
Env: SURGE_FORECAST_OUT (default ./surge_forecast.json).  python surge_forecast.py
"""
import json, os, urllib.request, urllib.parse
from math import sin, cos, radians
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
MC = json.load(open(os.path.join(HERE, "microclimate.json")))
OUT = os.environ.get("SURGE_FORECAST_OUT") or os.path.join(HERE, "surge_forecast.json")
TAC = "9446484"
NOAA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

def model_surge(P, ws, wd, m):
    return (m["a_press_ft_per_hpa"] * (m["p0_hpa"] - P)
            + m["bu_wind_ft_per_kt"] * ws * sin(radians(wd))
            + m["bv_wind_ft_per_kt"] * ws * cos(radians(wd))
            + m["offset_ft"])

def live_residual():
    """Latest Tacoma observed - predicted (ft), or None."""
    def g(**kw):
        kw.setdefault("application", "hpma_marina_board"); kw.setdefault("format", "json")
        kw.setdefault("units", "english"); kw.setdefault("time_zone", "gmt"); kw.setdefault("datum", "MLLW")
        with urllib.request.urlopen(NOAA + "?" + urllib.parse.urlencode(kw), timeout=30) as r:
            return json.load(r)
    try:
        obs = g(product="water_level", station=TAC, date="latest")["data"]
        if not obs:
            return None
        last = obs[-1]; ot = datetime.strptime(last["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        day = ot.strftime("%Y%m%d")
        pr = g(product="predictions", station=TAC, begin_date=day, end_date=day, interval="6")["predictions"]
        near = min(pr, key=lambda p: abs((datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) - ot).total_seconds()))
        return float(last["v"]) - float(near["v"])
    except Exception as exc:  # noqa: BLE001
        print(f"surge_forecast: live residual failed ({exc})")
        return None

def main():
    m = MC.get("surge_model")
    if not m:
        print("surge_forecast: no surge_model in microclimate.json"); return
    cove = MC["cove"]
    q = urllib.parse.urlencode({"latitude": cove["lat"], "longitude": cove["lon"], "timezone": "GMT",
                                "forecast_days": 6, "wind_speed_unit": "kn",
                                "hourly": "pressure_msl,wind_speed_10m,wind_direction_10m"})
    h = json.load(urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?" + q, timeout=30))["hourly"]
    times = [datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) for t in h["time"]]
    now = datetime.now(timezone.utc)

    # anchor the model to the live residual, fading the correction over anchor_hours
    resid = live_residual()
    anchor_h = m.get("anchor_hours", 18)
    i_now = min(range(len(times)), key=lambda i: abs((times[i] - now).total_seconds()))
    model_now = model_surge(h["pressure_msl"][i_now], h["wind_speed_10m"][i_now], h["wind_direction_10m"][i_now], m)
    corr = (resid - model_now) if resid is not None else 0.0

    series = []
    for t, P, ws, wd in zip(times, h["pressure_msl"], h["wind_speed_10m"], h["wind_direction_10m"]):
        if t < now - timedelta(hours=1) or None in (P, ws, wd):
            continue
        fade = max(0.0, 1 - max(0.0, (t - now).total_seconds() / 3600) / anchor_h)
        ft = model_surge(P, ws, wd, m) + corr * fade
        series.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "ft": round(ft, 2)})

    with open(OUT, "w") as f:
        json.dump(series, f, indent=2)
    peak = max(series, key=lambda s: s["ft"]) if series else None
    print(f"wrote {os.path.relpath(OUT, HERE)}: {len(series)} hrs | live resid "
          f"{('%.2f' % resid) if resid is not None else 'n/a'} ft | "
          f"peak {peak['ft']:.2f} ft @ {peak['t']}" if peak else "no series")

if __name__ == "__main__":
    main()

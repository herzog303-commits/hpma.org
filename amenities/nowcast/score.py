"""Forecast verification + scoring loop -- closes the "predict, observe, score,
refine" cycle the calibration was always meant to feed.

Each cycle it (1) LOGS the current forecasts with their valid times, (2) VERIFIES
any past-valid forecasts against what was actually observed, and (3) rolls up a
scorecard.json with skill per variable + the bias correction each one suggests.

Variables scored:
  surge_ft       surge_forecast.json at +6/+12/+24 h   vs Tacoma residual        -> bias/MAE/RMSE
  rain_next_hr   nowcast next-hour rain probability     vs observed precip (0/1)  -> Brier
  wind_kt        nowcast regional wind (0-lead)         vs Grapeview wind         -> bias/MAE/RMSE
  temp_f         nowcast cove temp (0-lead)             vs Grapeview temp         -> bias/MAE/RMSE

Obs: NOAA Tacoma (keyless, surge); Synoptic G2160 (wind/temp/rain, needs
SYNOPTIC_TOKEN); METAR (keyless rain fallback). Persisted in forecast_log.jsonl
(committed); publishes scorecard.json.  python score.py
"""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
MC = json.load(open(os.path.join(HERE, "microclimate.json")))
LOG = os.path.join(HERE, "forecast_log.jsonl")
CARD = os.environ.get("SCORECARD_OUT") or os.path.join(HERE, "scorecard.json")
NOWCAST = os.environ.get("NOWCAST_FILE") or os.path.join(HERE, "..", "nowcast.json")
SURGE_FC = os.environ.get("SURGE_FORECAST_FILE") or os.path.join(HERE, "..", "surge_forecast.json")
for cand in (NOWCAST, os.path.join(HERE, "nowcast.json")):   # study/local fallback
    if os.path.exists(cand):
        NOWCAST = cand; break
if not os.path.exists(SURGE_FC):
    SURGE_FC = os.path.join(HERE, "surge_forecast.json")
TAC = "9446484"
NOAA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
PRUNE_DAYS = 60
RIPE_MIN = 20          # wait this long past valid time before verifying (obs settle)

def _load(path):
    try: return json.load(open(path))
    except Exception: return None  # noqa: BLE001

def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

# ---------------------------------------------------------------- record
def interp(series, t):
    pts = sorted((_dt(x["t"]), x["ft"]) for x in series)
    if not pts or t < pts[0][0] or t > pts[-1][0]:
        return None
    for i in range(len(pts) - 1):
        if pts[i][0] <= t <= pts[i + 1][0]:
            (a, va), (b, vb) = pts[i], pts[i + 1]
            return va + (vb - va) * (t - a).total_seconds() / (b - a).total_seconds()
    return pts[-1][1]

def record(now):
    recs = []
    nc = _load(NOWCAST)
    if nc:
        tl = nc.get("timeline", [])
        if len(tl) >= 2:
            recs.append(("rain_next_hr", now + timedelta(minutes=60), 60, round(max(tl[0]["risk"], tl[1]["risk"]), 3)))
        w = nc.get("wind") or {}
        if w.get("regional_kt") is not None:
            recs.append(("wind_kt", now, 0, round(w["regional_kt"], 1)))
        if nc.get("temp_cove_f") is not None:
            recs.append(("temp_f", now, 0, round(nc["temp_cove_f"], 1)))
    sf = _load(SURGE_FC)
    if sf:
        for lead in (6, 12, 24):
            v = interp(sf, now + timedelta(hours=lead))
            if v is not None:
                recs.append(("surge_ft", now + timedelta(hours=lead), lead * 60, round(v, 2)))
    return [{"var": var, "valid": vt.strftime("%Y-%m-%dT%H:%M:%SZ"), "lead_min": lm, "fcst": f,
             "obs": None} for var, vt, lm, f in recs]

# ---------------------------------------------------------------- observations
def _noaa(**kw):
    kw.setdefault("application", "hpma_marina_board"); kw.setdefault("format", "json")
    kw.setdefault("units", "english"); kw.setdefault("time_zone", "gmt"); kw.setdefault("datum", "MLLW")
    with urllib.request.urlopen(NOAA + "?" + urllib.parse.urlencode(kw), timeout=30) as r:
        return json.load(r)

def obs_surge(vt):
    """Tacoma residual (observed - predicted) at vt."""
    day = vt.strftime("%Y%m%d")
    try:
        obs = {_dt2(x["t"]): float(x["v"]) for x in _noaa(product="water_level", station=TAC, begin_date=day, end_date=day)["data"] if x["v"] not in ("", None)}
        prd = {_dt2(x["t"]): float(x["v"]) for x in _noaa(product="predictions", station=TAC, begin_date=day, end_date=day, interval="6")["predictions"]}
    except Exception:  # noqa: BLE001
        return None
    ot = min(obs, key=lambda t: abs((t - vt).total_seconds()), default=None)
    if ot is None or abs((ot - vt).total_seconds()) > 1800:
        return None
    pt = min(prd, key=lambda t: abs((t - ot).total_seconds()), default=None)
    return round(obs[ot] - prd[pt], 2) if pt is not None else None

def _dt2(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)

def _synoptic(vt, extravars):
    tok = os.environ.get("SYNOPTIC_TOKEN")
    if not tok:
        return None
    q = urllib.parse.urlencode({"stid": "G2160", "vars": extravars, "units": "speed|kts,temp|F,precip|in",
                                "start": (vt - timedelta(minutes=40)).strftime("%Y%m%d%H%M"),
                                "end": (vt + timedelta(minutes=10)).strftime("%Y%m%d%H%M"),
                                "token": tok, "obtimezone": "utc"})
    try:
        with urllib.request.urlopen("https://api.synopticdata.com/v2/stations/timeseries?" + q, timeout=30) as r:
            return json.load(r)["STATION"][0]["OBSERVATIONS"]
    except Exception:  # noqa: BLE001
        return None

def _nearest(ob, key, vt):
    ts = ob.get("date_time", []); vs = ob.get(key, [])
    best = None
    for t, v in zip(ts, vs):
        if v is None: continue
        dt = abs((_dt(t) - vt).total_seconds())
        if best is None or dt < best[0]:
            best = (dt, v)
    return best[1] if best and best[0] <= 1800 else None

def obs_wind(vt):
    ob = _synoptic(vt, "wind_speed")
    return round(_nearest(ob, "wind_speed_set_1", vt), 1) if ob and _nearest(ob, "wind_speed_set_1", vt) is not None else None

def obs_temp(vt):
    ob = _synoptic(vt, "air_temp")
    return round(_nearest(ob, "air_temp_set_1", vt), 1) if ob and _nearest(ob, "air_temp_set_1", vt) is not None else None

def obs_rain(vt):
    """Did measurable precip fall near the cove in [vt-60min, vt]?  1/0/None."""
    ob = _synoptic(vt, "precip_accum_since_local_midnight")   # Grapeview accum delta over the hour
    if ob:
        vs = [(_dt(t), v) for t, v in zip(ob.get("date_time", []), ob.get("precip_accum_since_local_midnight_set_1", [])) if v is not None]
        win = [v for t, v in vs if vt - timedelta(minutes=70) <= t <= vt + timedelta(minutes=10)]
        if len(win) >= 2:
            return 1 if (win[-1] - win[0]) > 0.005 else 0
    # keyless METAR fallback: any precip token at KSHN/KOLM in the window
    try:
        ids = ",".join([MC["stations"]["primary_obs"], MC["stations"]["primary_taf"]])
        u = "https://aviationweather.gov/api/data/metar?" + urllib.parse.urlencode({"ids": ids, "format": "json", "hours": 4})
        rep = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "hpma"}), timeout=30))
    except Exception:  # noqa: BLE001
        return None
    toks = ("RA", "DZ", "SN", "SH", "GR", "GS", "PL", "TS")
    hit = False
    for m in rep:
        try: rt = _dt(m["reportTime"])
        except Exception: continue  # noqa: BLE001
        if vt - timedelta(minutes=60) <= rt <= vt + timedelta(minutes=5):
            wx = (m.get("wxString") or "").upper()
            if any(k in wx for k in toks) or (m.get("precip") and m["precip"] > 0):
                hit = True
    return 1 if hit else 0

OBS = {"surge_ft": obs_surge, "wind_kt": obs_wind, "temp_f": obs_temp, "rain_next_hr": obs_rain}

# ---------------------------------------------------------------- scorecard
def scorecard(entries):
    import math
    done = [e for e in entries if e.get("obs") is not None]
    card = {"generated_utc": None, "n_verified": len(done), "n_pending": len(entries) - len(done), "variables": {}}
    for var in ("surge_ft", "wind_kt", "temp_f", "rain_next_hr"):
        v = [e for e in done if e["var"] == var]
        if not v:
            continue
        if var == "rain_next_hr":
            p = [e["fcst"] for e in v]; o = [e["obs"] for e in v]
            brier = sum((pi - oi) ** 2 for pi, oi in zip(p, o)) / len(v)
            base = sum(o) / len(o)
            brier_clim = sum((base - oi) ** 2 for oi in o) / len(v)
            skill = 1 - brier / brier_clim if brier_clim > 0 else 0.0
            card["variables"][var] = {"n": len(v), "brier": round(brier, 3), "base_rate": round(base, 3),
                                      "brier_skill_vs_climo": round(skill, 3),
                                      "note": "lower Brier better; skill>0 beats always-forecasting-climatology"}
        else:
            errs = [e["fcst"] - e["obs"] for e in v]
            bias = sum(errs) / len(errs)
            mae = sum(abs(x) for x in errs) / len(errs)
            rmse = math.sqrt(sum(x * x for x in errs) / len(errs))
            card["variables"][var] = {"n": len(v), "bias": round(bias, 2), "mae": round(mae, 2), "rmse": round(rmse, 2),
                                      "suggested_adjustment": round(-bias, 2),
                                      "note": "bias = forecast - observed; add suggested_adjustment to de-bias"}
    return card

def main():
    now = datetime.now(timezone.utc)
    entries = []
    if os.path.exists(LOG):
        for ln in open(LOG):
            ln = ln.strip()
            if ln:
                try: entries.append(json.loads(ln))
                except Exception: pass  # noqa: BLE001

    # 1. record current forecasts (dedup by var + valid rounded to 15 min)
    seen = {(e["var"], e["valid"][:15]) for e in entries}
    added = 0
    for r in record(now):
        if (r["var"], r["valid"][:15]) not in seen:
            entries.append(r); seen.add((r["var"], r["valid"][:15])); added += 1

    # 2. verify ripe, unverified forecasts
    verified = 0
    for e in entries:
        if e.get("obs") is not None:
            continue
        vt = _dt(e["valid"])
        if vt > now - timedelta(minutes=RIPE_MIN) or vt < now - timedelta(days=PRUNE_DAYS):
            continue
        try:
            o = OBS[e["var"]](vt)
        except Exception:  # noqa: BLE001
            o = None
        if o is not None:
            e["obs"] = o
            e["err"] = None if e["var"] == "rain_next_hr" else round(e["fcst"] - o, 2)
            verified += 1

    # 3. prune + persist + scorecard
    entries = [e for e in entries if _dt(e["valid"]) > now - timedelta(days=PRUNE_DAYS)]
    with open(LOG, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    card = scorecard(entries)
    card["generated_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(card, open(CARD, "w"), indent=2)
    print(f"score: +{added} logged, {verified} verified, {card['n_verified']} total verified / {card['n_pending']} pending")
    for var, s in card["variables"].items():
        print(f"  {var:14} {s}")

if __name__ == "__main__":
    main()

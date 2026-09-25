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
import json, os, urllib.request, urllib.parse, urllib.error

# GW2160 (Grapeview) read straight from CWOP -- the same station Synoptic
# served, but keyless and public at source. Primary since the Synoptic
# contract lapsed 2026-09-07; Synoptic stays wired as a fallback.
try:
    import cwop
except Exception:  # noqa: BLE001
    cwop = None
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
MC = json.load(open(os.path.join(HERE, "microclimate.json")))
# The forecast log holds raw observed values (the `obs` field) and therefore
# lives in the PRIVATE study repo, not the public board repo. mini_cycle points
# FORECAST_LOG there; the default keeps standalone runs self-contained.
LOG = os.environ.get("FORECAST_LOG") or os.path.join(HERE, "forecast_log.jsonl")

# Predictors for a future statistical corrector, one row per CYCLE (not per
# forecast row -- that would duplicate ~180 bytes across ~800 rows/day).
# Join to forecast_log on issue time: issue = valid - lead_min.
#
# Rationale (RESEARCH_NOTES.md finding 3): the largest documented lever in
# forecast post-processing is the PREDICTOR SET, not the algorithm -- feeding
# non-target meteorological fields plus station bias, hour-of-day, day-of-year
# and shortwave radiation gave significant gains at >97% of station/lead-time
# combinations. We cannot fit anything on a two-week archive, but a corrector
# fitted in 2027 can only use predictors recorded in 2026. The cost of not
# logging these today is permanent.
PRED_LOG = os.environ.get("PREDICTOR_LOG") or os.path.join(HERE, "predictors.jsonl")
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
# sky_clear_3h was WORSE THAN CLIMATOLOGY (Brier 0.197 against 0.136, skill
# -0.446) and the cause was not the predictor -- it was the framing. The
# forecast was emitted as a deterministic 0/1 while Brier, a proper scoring
# rule, lets the climatological baseline hedge at the 0.837 base rate. A 0/1
# forecast is therefore penalised even when it is informative, and this one is
# informative: over 467 verified rows the GOES outlook separated cleanly,
#
#     P(clear | outlook said clear) = 0.897      n = 377
#     P(clear | outlook said cloud) = 0.589      n =  90
#
# a separation of +0.308. Emitting that as an honest probability instead of a
# hard call moves the SAME predictor from -0.446 skill to positive, verified
# out of sample: 5-fold gives +0.087, and a chronological split (fit on the
# first 280 rows, score the next 187 -- the way it will actually be used)
# gives +0.115.
#
# Self-calibrating rather than hard-coded, because the hit rate is a property
# of this site and this satellite geometry and will drift; a constant fitted
# today would quietly go stale. Smoothed toward the base rate so a thin record
# cannot produce a confident number.
SKY_CAL_PRIOR = 10.0     # pseudo-observations pulling each class to the base rate
SKY_CAL_MIN_N = 30       # below this, make no calibration claim
SKY_REFIT_UTC = "2026-09-25T02:10:00Z"   # when the fitted model actually went live.
                                         # A date-only cutover counted 116 rows of which
                                         # only 2 were model-sourced, and reported their
                                         # score as the model's.
SKY_CAL_DAYS = 7         # recency window; pooling regimes is what broke this.
                         # Measured over the calibrated era, shorter is
                         # monotonically better -- all/21/14/10 days all score
                         # -0.089, 7 days -0.087, 5 days -0.050 -- which says the
                         # base rate DRIFTS rather than stepping once, so a long
                         # window is always averaging over a sky that has moved.
                         # 5 scored best and is not chosen: on a 25-day record
                         # that is fitting noise, and 7 days still leaves ~100
                         # rows to estimate two classes from.


def _sky_raw(e):
    """The 0/1 outlook behind a logged row.

    Rows written from 2026-09-21 carry it explicitly; earlier rows stored the
    raw call in `fcst` itself, and smoothing guarantees a calibrated value is
    never exactly 0 or 1, so the two are distinguishable.
    """
    r = e.get("raw")
    if r is not None:
        try: return float(r)
        except (TypeError, ValueError): return None
    f = e.get("fcst")
    return float(f) if f in (0.0, 1.0) else None


def _apply_wind_correction(kt, when):
    """The board's displayed wind, computed here so it can be scored.

    Mirrors marina-board.html exactly: subtract bias_by_hour_local for the local
    hour, then rescale to the observed spread, then clamp at zero. Reads the
    PUBLISHED scorecard rather than recomputing, because the board reads that
    file too and a second derivation is a second thing to keep in step.

    Returns None whenever the board would also decline -- missing table, too few
    samples per hour -- so the pair only exists on hours the correction actually
    applied to.
    """
    if kt is None:
        return None
    try:
        with open(CARD) as f:
            cv = (json.load(f).get("cove_verification") or {}).get("wind_kt") or {}
    except (OSError, ValueError):
        return None
    tbl = cv.get("bias_by_hour_local") or {}
    if len(tbl) < 20 or (cv.get("min_n_per_hour") or 0) < 15:
        return None                      # the board's own BIAS_MIN_HOURS / BIAS_MIN_N
    b = tbl.get(str(local_hour(when)))
    if b is None:
        return None
    v = kt - b
    m = cv.get("variance_match") or {}
    if m.get("scale"):
        v = m["mean_observed"] + (v - m["mean_corrected"]) * m["scale"]
    return max(0.0, v)


def _sky_calibration(entries, now=None):
    """{1.0: P(clear|said clear), 0.0: P(clear|said cloud)} or None if too thin.

    RECENCY-LIMITED, because this pooled two incompatible regimes. Verified rows
    before 2026-09-21 carry a clear-sky base rate of 0.824; rows after carry
    0.260 -- autumn arriving. A calibration fitted across both emits ~0.85 for
    "clear" into a world where clear happens a quarter of the time, and the
    published skill went to -0.165 as a result.

    HONEST LIMITS, because this does not rescue the variable. Measured over the
    calibrated era: as emitted -0.165, recency-windowed about -0.05 to -0.09,
    and PURE CLIMATOLOGY -0.028. No window beats climatology, and the -0.028
    floor is not zero because the base rate drifts faster than any trailing
    estimate tracks it -- a real-time forecast is scored against a climatology
    that knows the future. So the window recovers most of the self-inflicted
    loss and none of the skill.

    THE PREDICTOR ITSELF HAS DECAYED. The separation this variable was built on
    was P(clear|outlook clear) 0.897 against P(clear|cloud) 0.589. Over the last
    307 verified rows it is 0.243 against 0.144 -- a gap of 0.10 where there was
    0.31. The GOES outlook is not currently telling us much about this sky.

    WHAT LOOKS BETTER, recorded rather than shipped: the continuous `lead_h`
    behind the binary separates 0.000 / 0.029 / 0.437 by tercile against the
    binary's 0.099, exactly as the note at the emission site predicted. A
    threshold at 12 h scores +0.017 against the shipped 3 h at -0.018 -- but on
    EIGHT rows, and a day-blocked bootstrap prefers it in only 87.7% of
    resamples, below this project's bar. It needs a season, not a fortnight.
    """
    v = [e for e in (entries or [])
         if e.get("var") == "sky_clear_3h" and e.get("obs") is not None
         and e.get("src", "live") == "live" and _sky_raw(e) is not None]
    if now is not None and SKY_CAL_DAYS:
        cut = now - timedelta(days=SKY_CAL_DAYS)
        recent = [e for e in v if _dt(e["valid"]) >= cut]
        # Fall back to the full record rather than make no claim at all: a stale
        # calibration still beats the 0/1 this replaced.
        if len(recent) >= SKY_CAL_MIN_N:
            v = recent
    if len(v) < SKY_CAL_MIN_N:
        return None
    base = sum(e["obs"] for e in v) / len(v)
    out = {}
    for cls in (0.0, 1.0):
        g = [e["obs"] for e in v if _sky_raw(e) == cls]
        out[cls] = round((sum(g) + SKY_CAL_PRIOR * base) / (len(g) + SKY_CAL_PRIOR), 3)
    return out


def interp(series, t):
    pts = sorted((_dt(x["t"]), x["ft"]) for x in series)
    if not pts or t < pts[0][0] or t > pts[-1][0]:
        return None
    for i in range(len(pts) - 1):
        if pts[i][0] <= t <= pts[i + 1][0]:
            (a, va), (b, vb) = pts[i], pts[i + 1]
            return va + (vb - va) * (t - a).total_seconds() / (b - a).total_seconds()
    return pts[-1][1]

def record(now, entries=None):
    recs = []
    extra = {}          # per-variable fields carried onto the logged row
    # Declared up front: the wind block below runs before the temperature one
    # and referenced windfix_rows before assignment, which crashed the cycle's
    # score step outright. Caught by running score.py from the BOARD checkout
    # the way mini_cycle does -- from the study repo the crash never appeared,
    # because the board's copy was a version behind.
    tempfix_rows, windfix_rows = [], []
    nc = _load(NOWCAST)
    if nc:
        tl = nc.get("timeline", [])
        if len(tl) >= 2:
            recs.append(("rain_next_hr", now + timedelta(minutes=60), 60, round(max(tl[0]["risk"], tl[1]["risk"]), 3)))
        w = nc.get("wind") or {}
        if w.get("regional_kt") is not None:
            recs.append(("wind_kt", now, 0, round(w["regional_kt"], 1)))
            # AND THE CORRECTED WIND, for the same reason temperature got one.
            # The board de-biases the displayed wind by hour and then rescales it
            # to the observed spread; neither step was logged, so the scorecard
            # measured the raw forecast at bias +2.90 while the screen showed
            # something else. This applies the SAME table from the SAME file the
            # board fetches -- the published scorecard, not a freshly computed
            # one -- so the two cannot drift apart.
            #
            # Applied to regional_kt, the identical quantity logged above as
            # src="live", so the pair is like-for-like. Pairing a correction
            # against a differently-corrected forecast is the error that made
            # the temperature comparison read +113% yesterday.
            cw = _apply_wind_correction(w["regional_kt"], now)
            if cw is not None:
                windfix_rows.append({"var": "wind_kt", "src": "live-windfix",
                                     "valid": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "lead_min": 0, "fcst": round(cw, 1), "obs": None})
        # Gusts are what a boater actually reads before going out, and they were
        # computed, sheltered and shown on the board but never verified.
        # REGIONAL gust is scored because G2160 (Fair Harbor, Grapeview) is a
        # regional station ~5 mi NNE -- apples to apples with wind_kt above.
        # NOTE: marina_gust_kt / marina_kt (regional x shelter_factor) remain
        # UNVERIFIABLE until a sensor exists at the cove itself. That gap is the
        # whole point of the study; do not mistake wind_kt's score for evidence
        # about the shelter model.
        if w.get("regional_gust_kt") is not None:
            recs.append(("wind_gust_kt", now, 0, round(w["regional_gust_kt"], 1)))
        if nc.get("temp_cove_f") is not None:
            recs.append(("temp_f", now, 0, round(nc["temp_cove_f"], 1)))
    # SCORE WHAT MEMBERS ACTUALLY SEE. The board has applied tempfix.json in the
    # browser since 2026-09-23 while this logged only the raw forecast, so the
    # scorecard measured a number nobody was shown. A wrong feature order, a
    # stale model file or a unit slip would all have left these figures looking
    # perfectly healthy. Logged as a separate src so the two sit side by side in
    # the same scorecard, over the same hours, against the same observation.
    try:
        import tempfix_apply
        raw_f, corr_f = tempfix_apply.corrected()
        if corr_f is not None and raw_f is not None:
            # BOTH SIDES OF THE PAIR, and that is the whole point. The first
            # version logged only the corrected value and let it be compared
            # against src="live", which is nc["temp_cove_f"] -- a DIFFERENT
            # forecast that already carries its own cove offset. The pair read
            # raw MAE 0.68 against corrected 1.45 and looked like the correction
            # had made things twice as bad; it was measuring two unrelated
            # quantities. tempfix corrects Open-Meteo's temperature_2m, so the
            # baseline has to be Open-Meteo's temperature_2m.
            for src, val in (("live-om-raw", raw_f), ("live-tempfix", corr_f)):
                tempfix_rows.append({"var": "temp_f", "src": src,
                                     "valid": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "lead_min": 0, "fcst": round(val, 1), "obs": None})
    except Exception:  # noqa: BLE001
        pass          # the correction is an improvement, never a dependency
    # Cloud/radiation skill. Recorded only when the forecast expects meaningful
    # daylight -- scoring hours where both sides are zero would manufacture
    # skill out of darkness.
    try:
        solar = _openmeteo_solar()
        for lead in (60, 180):
            vt = (now + timedelta(minutes=lead)).replace(minute=0, second=0, microsecond=0)
            v = solar.get(vt)
            if v is not None and v > 20:
                recs.append(("solar_w_m2", vt, lead, round(v, 1)))
    except Exception:  # noqa: BLE001
        pass

    try:
        cld = _openmeteo_cloud()
        for lead in (60, 180):
            vt = (now + timedelta(minutes=lead)).replace(minute=0, second=0, microsecond=0)
            if vt in cld:
                recs.append(("cloud_pct", vt, lead, round(cld[vt], 1)))
    except Exception:  # noqa: BLE001
        pass

    # Will the sky still be clear in 3 hours? Deterministic 0/1, so the Brier
    # score reads as a miss rate. Only recorded when GOES actually produced an
    # outlook -- no outlook, no claim, nothing to score.
    try:
        gp = os.environ.get("GOES_OUT") or os.path.join(HERE, "goes_cloud.json")
        with open(gp) as f:
            g = json.load(f)
        o = g.get("outlook") or {}
        scan = _dt(g["scan_utc"])
        if o and (now - scan).total_seconds() <= 7200:
            lead = o.get("lead_h")
            raw = 1.0 if (o.get("clear_now") and (lead is None or lead > 3)) else 0.0
            # PRIMARY: the fitted model. The GOES binary above is kept only as a
            # logged field and a fallback -- it scored -0.83 skill because its
            # TRUTH lives in goes_log.jsonl, eight days deep, so it could never
            # be fitted, only hedged on a rolling base rate. skyclear.json is
            # fitted on 33,310 hours across five years and scores +0.655.
            #
            # persist is the observed cloud fraction NOW, verified three hours
            # out -- the single strongest feature, worth +0.549 skill on its own,
            # and the old version did not use it at all.
            clear3 = None
            try:
                import skyclear_apply
                pc = obs_cloud(now)
                if pc is not None:
                    clear3 = skyclear_apply.predict(now + timedelta(minutes=180), pc / 100.0)
            except Exception:  # noqa: BLE001
                clear3 = None
            _used_model = clear3 is not None
            if clear3 is None:
                cal = _sky_calibration(entries, now)
                # Fallback only. Hedge at the base rate rather than ship a 0/1.
                clear3 = cal[raw] if cal else (0.90 if raw else 0.60)
            # Log the CONTINUOUS state behind the binary too. `lead > 3` throws
            # away the difference between cloud arriving in 3.5 h and in 11.5 h,
            # which is most of the information the outlook actually has. These
            # cost nothing now and make a better predictor fittable in a month;
            # nothing reads them yet, deliberately.
            extra["sky_clear_3h"] = {"raw": raw, "model": bool(_used_model),
                                     "lead_h": lead, "cloud_km": o.get("cloud_km"),
                                     "cloud_pct_now": g.get("cloud_pct")}
            recs.append(("sky_clear_3h", now + timedelta(minutes=180), 180, clear3))
    except Exception:  # noqa: BLE001
        pass

    sf = _load(SURGE_FC)
    if sf:
        for lead in (6, 12, 24):
            v = interp(sf, now + timedelta(hours=lead))
            if v is not None:
                recs.append(("surge_ft", now + timedelta(hours=lead), lead * 60, round(v, 2)))
    base = [{"var": var, "src": "live", "valid": vt.strftime("%Y-%m-%dT%H:%M:%SZ"), "lead_min": lm, "fcst": f,
             "obs": None, **extra.get(var, {})} for var, vt, lm, f in recs]
    # shadow the 0-lead wind/temp as "cove" -- same forecast, verified at the cove (WU)
    cove = [{**r, "src": "cove"} for r in base if r["var"] in ("wind_kt", "temp_f") and r["lead_min"] == 0]
    return base + cove + tempfix_rows + windfix_rows

# ---------------------------------------------------------------- bake-off (shadow forecast sources)
NWS_HOURLY = "https://api.weather.gov/gridpoints/SEW/105,57/forecast/hourly"   # cove gridpoint (api.weather.gov/points)

def _openmeteo_series(model=None):
    """{hour_utc: (temp_f, wind_kt)} for the next day from Open-Meteo (best_match or a named model)."""
    q = {"latitude": MC["cove"]["lat"], "longitude": MC["cove"]["lon"], "timezone": "GMT",
         "hourly": "temperature_2m,wind_speed_10m", "forecast_days": 1,
         "wind_speed_unit": "kn", "temperature_unit": "fahrenheit"}
    if model:
        q["models"] = model
    h = json.load(urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=30))["hourly"]
    out = {}
    for t, tp, ws in zip(h["time"], h["temperature_2m"], h["wind_speed_10m"]):
        if None not in (tp, ws):
            out[datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)] = (round(tp, 1), round(ws, 1))
    return out

def _openmeteo_extra():
    """Current-hour non-target fields from Open-Meteo, for the predictor log.

    Shortwave radiation is called out explicitly in the post-processing
    literature as a useful predictor (it proxies the daytime heating that
    drives both the warm bias and citizen-station sun exposure). The rest are
    the cheap "other meteorological fields" the same finding recommends.
    Keyless and free, so one extra request per cycle is acceptable.
    """
    q = {"latitude": MC["cove"]["lat"], "longitude": MC["cove"]["lon"], "timezone": "GMT",
         "hourly": ("shortwave_radiation,cloud_cover,relative_humidity_2m,"
                    "surface_pressure,dew_point_2m,precipitation,wind_gusts_10m"),
         "forecast_days": 1, "wind_speed_unit": "kn", "temperature_unit": "fahrenheit"}
    try:
        h = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=30))["hourly"]
    except Exception:  # noqa: BLE001
        return {}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    try:
        i = h["time"].index(now.strftime("%Y-%m-%dT%H:%M"))
    except (ValueError, KeyError):
        return {}
    out = {}
    for k in ("shortwave_radiation", "cloud_cover", "relative_humidity_2m",
              "surface_pressure", "dew_point_2m", "precipitation", "wind_gusts_10m"):
        v = h.get(k)
        if v and i < len(v):
            out[k] = v[i]
    return out


def log_predictors(now):
    """One row per cycle: the forecast-time state a corrector could condition on."""
    nc = _load(NOWCAST) or {}
    w = nc.get("wind") or {}
    obs = nc.get("observed") or {}
    # Solar-ish local hour from longitude, so the diurnal predictor does not
    # depend on the DST rules of a timezone database.
    solar_h = (now.hour + now.minute / 60.0 + MC["cove"]["lon"] / 15.0) % 24
    row = {
        "t": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hour_utc": now.hour,
        "solar_hour": round(solar_h, 2),
        "doy": int(now.strftime("%j")),
        "regime": nc.get("regime"),
        "confidence": nc.get("confidence"),
        "baro_hpa_3h": nc.get("baro_hpa_3h"),
        "precip_ratio": nc.get("precip_ratio"),
        "temp_model_f": nc.get("temp_model_f"),
        "temp_cove_f": nc.get("temp_cove_f"),
        "temp_offset_f": nc.get("temp_offset_f"),
        "regional_kt": w.get("regional_kt"),
        "regional_gust_kt": w.get("regional_gust_kt"),
        "regional_dir_deg": w.get("regional_dir_deg"),
        "marina_kt": w.get("marina_kt"),
        "shelter_factor": w.get("shelter_factor"),
        "shelter_mode": w.get("mode"),
        "raining_nearby": obs.get("raining_nearby"),
    }
    # The gauge consensus is the board's headline claim ("RAINING NOW, 4 of 11
    # gauges") and it was being computed, displayed, and then thrown away. Log
    # it so the claim can be verified later against what the gauges actually
    # recorded -- otherwise the one number a member reads is the one number we
    # have no history for.
    rn = nc.get("rain_now") or {}
    if rn:
        row.update({"rain_gauges_wet": rn.get("wet"), "rain_gauges_total": rn.get("total"),
                    "rain_observed": rn.get("observed"), "rain_confident": rn.get("confident"),
                    "rain_nearest_rate_in_hr": rn.get("nearest_rate_in_hr"),
                    "rain_max_rate_in_hr": rn.get("max_rate_in_hr")})
    row.update(_openmeteo_extra())

    # GOES-18 cloud mask -- a LOCAL satellite cloud observation, recorded next to
    # the regional METAR one so the two can be compared. Whether METAR's 23 km
    # sky is good enough for this site is exactly the question that justifies
    # carrying GOES at all, and it is only answerable if both are logged.
    try:
        gp = os.environ.get("GOES_OUT") or os.path.join(HERE, "goes_cloud.json")
        with open(gp) as f:
            g = json.load(f)
        age = (datetime.now(timezone.utc)
               - datetime.strptime(g["scan_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
               ).total_seconds() / 60
        if age <= 120:
            row["goes_cloud_pct"] = g.get("cloud_pct")
            row["goes_centre_cloudy"] = g.get("centre_cloudy")
            row["goes_scan_age_min"] = round(age, 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        row["metar_cloud_pct"] = obs_cloud(datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0))
    except Exception:  # noqa: BLE001
        pass

    # MEASURED insolation beats modelled. Tomas's Ecowitt GW3000 reports
    # solarRadiation and UV 0.56 km from the gangway; _openmeteo_extra above
    # supplies a MODELLED shortwave value off a 1-2 km grid. Record both --
    # RESEARCH_NOTES.md names shortwave as a top predictor AND as the driver of
    # the citizen-station warm bias, so the measured/modelled gap is itself
    # diagnostic. pws_temp_f is here so the forecast-minus-observation error can
    # be computed from a single predictor row without a join.
    try:
        import wu as _wu
        sts = _wu.independent_stations(MC)
        c = _wu.wu_current(sts[0]) if sts else None
        if c:
            row["pws_station"] = sts[0]
            row["pws_solar_w_m2"] = c.get("solar_w_m2")
            row["pws_uv"] = c.get("uv")
            row["pws_temp_f"] = c.get("temp_f")
            row["pws_rh"] = c.get("humidity")
            row["pws_qc"] = c.get("qc_status")
    except Exception:  # noqa: BLE001
        pass
    try:
        with open(PRED_LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:  # noqa: BLE001
        pass
    return row


def _openmeteo_solar():
    """{hour_utc: W/m2} forecast shortwave radiation, for cloud-skill scoring."""
    q = {"latitude": MC["cove"]["lat"], "longitude": MC["cove"]["lon"], "timezone": "GMT",
         "hourly": "shortwave_radiation,cloud_cover", "forecast_days": 2}
    try:
        h = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=30))["hourly"]
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for t, sw in zip(h["time"], h["shortwave_radiation"]):
        if sw is None:
            continue
        out[datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)] = sw
    return out


def obs_solar(vt):
    """Measured shortwave, median across the stations that carry a solar sensor.

    Nine of ten registered PWS report solarRadiation. A median across them is
    far more robust than any single pyranometer, which can be shaded by a tree,
    fouled, or tilted.

    SEMANTICS, and this matters for reading the bias: the forecast side is
    Open-Meteo's shortwave_radiation, an AVERAGE over the preceding hour, while
    WU's hourly archive exposes solarRadiationHigh, the PEAK within the hour.
    Peak exceeds mean whenever cloud is broken and equals it under clear sky,
    so the scored bias carries a systematic negative component that is an
    artefact of the units, NOT forecast error. Comparisons BETWEEN models remain
    valid because every model is scored against the same truth.

    THAT CAVEAT DOES NOT EXPLAIN THE BIAS WE ACTUALLY SEE, and reading it as
    though it did was a mistake. The artefact above pushes the bias NEGATIVE.
    Measured, it is +114 W/m2, concentrated in the morning -- so the true error
    is LARGER than scored, not smaller. The cause is a morning marine layer
    that the models forecast through: see marine.py, which measures clear-sky
    index at every pyranometer and routinely finds Kt near 0.1 on mornings when
    both Open-Meteo and the GOES cloud mask call the sky clear.
    """
    try:
        import wu
    except Exception:  # noqa: BLE001
        return None
    vals = []
    for st in wu.independent_stations(MC):
        try:
            o = wu.wu_hourly_at(vt, station=st)
        except Exception:  # noqa: BLE001
            continue
        if o and o.get("solar_w_m2") is not None:
            vals.append(float(o["solar_w_m2"]))
    if len(vals) < 3:
        return None
    vals.sort()
    n = len(vals)
    return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 1)


# METAR sky cover -> fraction, using the mid-point of each okta range.
# RADAR CANNOT DO THIS. Weather radar detects hydrometeors -- rain, snow, hail.
# Cloud droplets are far too small to return usable S-band signal, so a solid
# overcast produces zero echo. That is our most common sky here, and it is why
# microclimate.json already excludes radar. METAR sky condition is an actual
# human/ceilometer cloud observation and we were already fetching it for rain.
_metar_cache = {}

_SKY = {"SKC": 0.0, "CLR": 0.0, "NCD": 0.0, "NSC": 0.0,
        "FEW": 1.5 / 8, "SCT": 3.5 / 8, "BKN": 6.0 / 8, "OVC": 1.0,
        "OVX": 1.0, "VV": 1.0}


def _openmeteo_cloud():
    """{hour_utc: cloud %} forecast total cloud cover."""
    q = {"latitude": MC["cove"]["lat"], "longitude": MC["cove"]["lon"], "timezone": "GMT",
         "hourly": "cloud_cover", "forecast_days": 2}
    try:
        h = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=30))["hourly"]
    except Exception:  # noqa: BLE001
        return {}
    return {datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc): c
            for t, c in zip(h["time"], h["cloud_cover"]) if c is not None}


def obs_cloud(vt):
    """Observed total cloud %, median across the nearby airfields' METARs.

    METAR reports sky cover CUMULATIVELY from the lowest layer up, so the
    greatest reported cover in a report IS the total sky covered. An empty
    clouds array means CLR/SKC -- genuinely zero, not missing.

    Airfields are 23 km and further, so this is REGIONAL cloud, not cove cloud.
    That is a much weaker objection for cloud than it would be for rain: cloud
    fields are synoptic-scale where our rain is manifestly not, which is the
    whole reason the rain gauges had to be local.
    """
    # ONE fetch serves every pending verification in this run. Each METAR
    # response already covers 4 hours, so calling per entry would re-request the
    # same window repeatedly -- precisely the retry storm that turned the
    # Synoptic outage into ~128k requests/day (see RESEARCH_NOTES / score.py's
    # circuit breaker). Process-scoped: a fresh cycle fetches once.
    rep = _metar_cache.get("rep")
    if rep is None:
        try:
            ids = ",".join([MC["stations"]["primary_obs"], MC["stations"]["primary_taf"],
                            "KTCM", "KPWT"])
            u = "https://aviationweather.gov/api/data/metar?" + urllib.parse.urlencode(
                {"ids": ids, "format": "json", "hours": 6})
            rep = json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers={"User-Agent": "hpma-marina-board"}), timeout=30))
        except Exception:  # noqa: BLE001
            _metar_cache["rep"] = []      # do not retry all run
            return None
        _metar_cache["rep"] = rep
    if not rep:
        return None
    best = {}
    for m in rep:
        try:
            rt = _dt(m["reportTime"])
        except Exception:  # noqa: BLE001
            continue
        if abs((rt - vt).total_seconds()) > 2400:      # within 40 min of the valid hour
            continue
        sid = m.get("icaoId")
        gap = abs((rt - vt).total_seconds())
        if sid in best and best[sid][0] <= gap:
            continue
        layers = m.get("clouds") or []
        # .strip() because an unrecognised code falls to 0.0 -- "clear" -- which
        # is the wrong direction to fail in. The IEM archive writes vertical
        # visibility as "VV " with a trailing space; this reads the live feed,
        # which does not, but a silent default of 0.0 is not worth the bet.
        frac = max((_SKY.get((l.get("cover") or "").strip().upper(), 0.0) for l in layers), default=0.0)
        best[sid] = (gap, frac)
    vals = sorted(v[1] for v in best.values())
    if len(vals) < 2:
        return None
    n = len(vals)
    return round(100 * (vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2), 1)


def obs_sky_clear(vt):
    """Was the sky clear at vt? 1/0/None, from the SAME truth the model was fitted on.

    TRUTH MOVED FROM GOES TO METAR ON 2026-09-24, and the move is what made the
    variable fixable. The old truth came from goes_log.jsonl -- the same
    instrument that made the prediction, which was deliberate, because
    goes_cloud.json is overwritten hourly and without a log "cloud in 3 hours"
    is unfalsifiable. But that log holds EIGHT DAYS. A target with eight days of
    history cannot be fitted, only hedged, which is why this variable sat at
    -0.83 skill on a rolling base rate.

    The median METAR cloud fraction across four airfields has FIVE YEARS. It is
    regional rather than over-the-cove, which score.py already accepts for
    cloud_pct on the grounds that cloud is synoptic-scale where our rain is not.
    Fitted on it, the model scores +0.655.

    Train and verify now use the same quantity. Scoring a METAR-fitted model
    against a GOES target would be the exact mismatch that made burnoff_clears
    unreadable, and it is not repeated here.
    """
    fr = obs_cloud(vt)
    if fr is not None:
        try:
            import skyclear_apply
            cut = 100.0 * (skyclear_apply.model().get("clear_max") or 0.25)
        except Exception:  # noqa: BLE001
            cut = 25.0
        return 1.0 if fr <= cut else 0.0
    return _obs_sky_clear_goes(vt)


def _obs_sky_clear_goes(vt):
    """The retired GOES-based truth, kept as a fallback when METAR is missing."""
    path = os.environ.get("GOES_LOG") or os.path.join(HERE, "goes_log.jsonl")
    best = None
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    t = _dt(r["scan_utc"])
                except Exception:  # noqa: BLE001
                    continue
                gap = abs((t - vt).total_seconds())
                if gap <= 2700 and (best is None or gap < best[0]):   # within 45 min
                    best = (gap, r)
    except OSError:
        return None
    if not best or best[1].get("cloud_pct") is None:
        return None
    return 1 if best[1]["cloud_pct"] < 25 else 0


def _nws_series():
    """{hour_utc: (temp_f, wind_kt)} from the NWS gridpoint hourly forecast (NBM)."""
    req = urllib.request.Request(NWS_HOURLY, headers={"User-Agent": "hpma-marina-board", "Accept": "application/geo+json"})
    periods = json.load(urllib.request.urlopen(req, timeout=30))["properties"]["periods"]
    out = {}
    for p in periods:
        try:
            t = datetime.fromisoformat(p["startTime"]).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
            tp = float(p["temperature"])                                   # already F
            ws = float(str(p["windSpeed"]).split()[0]) * 0.868976          # mph -> kt
            out[t] = (round(tp, 1), round(ws, 1))
        except Exception:  # noqa: BLE001
            continue
    return out

def record_bakeoff(now):
    """Log temp/wind at +1h and +3h from each shadow source, scored against the same
    Grapeview obs -- a head-to-head of forecast sources at the cove."""
    # "openmeteo" (best_match) was REMOVED 2026-09-14: at this location
    # Open-Meteo serves gfs_hrrr AS best_match, so the bake-off was scoring the
    # same model twice and calling it a comparison. Verified two ways -- 279 of
    # 279 live temp_f pairs identical, and 46,414 of 46,414 backfilled hours
    # identical to 1e-9.
    #
    # Replaced with models that are genuinely different, and which the five-year
    # backfill shows are BETTER here (matched sample n=20,444, MAE):
    #     ecmwf_ifs025  1.71   <- 25 km, beats HRRR
    #     icon_seamless 1.90
    #     gfs_hrrr      2.07   <- 3 km, loses despite the resolution
    # Historical rows tagged "openmeteo" stay in the log and remain honest; they
    # are simply HRRR under an older label.
    def _metno():
        try:
            import metno
            return metno.series()
        except Exception:  # noqa: BLE001
            return {}

    srcs = {"hrrr": lambda: _openmeteo_series("gfs_hrrr"),
            "ecmwf": lambda: _openmeteo_series("ecmwf_ifs025"),
            "icon": lambda: _openmeteo_series("icon_seamless"),
            "nws": _nws_series,
            # MET Norway -- ECMWF-derived with their own post-processing, so
            # genuinely independent of the Open-Meteo family above. Keyless.
            # Carries temp and wind but NOT gust at this location.
            "metno": _metno}
    recs = []
    for src, fn in srcs.items():
        try:
            series = fn()
        except Exception as exc:  # noqa: BLE001
            print(f"score bakeoff: {src} failed ({exc})"); continue
        for lead in (60, 180):
            vt = (now + timedelta(minutes=lead)).replace(minute=0, second=0, microsecond=0)
            key = min(series, key=lambda t: abs((t - vt).total_seconds()), default=None)
            if key is None or abs((key - vt).total_seconds()) > 3600:
                continue
            tp, ws = series[key]
            vs = key.strftime("%Y-%m-%dT%H:%M:%SZ")
            recs.append({"var": "temp_f", "src": src, "valid": vs, "lead_min": lead, "fcst": tp, "obs": None})
            recs.append({"var": "wind_kt", "src": src, "valid": vs, "lead_min": lead, "fcst": ws, "obs": None})
    return recs

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

# Circuit breaker. Verification calls Synoptic once PER PENDING ENTRY, and an entry
# that fails to verify stays pending and is retried every cycle for PRUNE_DAYS. So a
# credential/quota failure does not degrade gracefully -- it amplifies: ~1,300 failed
# requests per cycle, ~128k/day, which burns the very quota that may have caused it.
# On the first 401/403/429 we stop calling Synoptic for the rest of this run. The flag
# is process-local, so the next cycle retries once and recovers on its own.
_SYNOPTIC_DOWN = False

def _synoptic(vt, extravars):
    global _SYNOPTIC_DOWN
    tok = os.environ.get("SYNOPTIC_TOKEN")
    if not tok or _SYNOPTIC_DOWN:
        return None
    q = urllib.parse.urlencode({"stid": "G2160", "vars": extravars, "units": "speed|kts,temp|F,precip|in",
                                "start": (vt - timedelta(minutes=40)).strftime("%Y%m%d%H%M"),
                                "end": (vt + timedelta(minutes=10)).strftime("%Y%m%d%H%M"),
                                "token": tok, "obtimezone": "utc"})
    try:
        with urllib.request.urlopen("https://api.synopticdata.com/v2/stations/timeseries?" + q, timeout=30) as r:
            return json.load(r)["STATION"][0]["OBSERVATIONS"]
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            _SYNOPTIC_DOWN = True
            print("score: synoptic HTTP %d -- account denied or throttled; "
                  "skipping synoptic verification for the rest of this run" % e.code)
        return None
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

# REFERENCE STATION SWITCHED 2026-09-21. wind_kt, temp_f and wind_gust_kt --
# and with them the entire six-way model bake-off -- were verified against
# Grapeview GW2160 over CWOP. That gauge went off the air on 2026-09-16 and
# took five days to notice (see aprsis.py), during which nothing verified at
# all. The Synoptic fallback had already expired on 2026-09-07, so there was no
# second source: one station's failure silently froze the scorecard.
#
# The reference is now KWASHELT285 -- 0.56 km, Ecowitt GW3000 on roof fascia
# ~20 ft up in clean air, the best-exposed PWS in the network and already the
# primary for wind. It is a fair substitute rather than a convenient one: over
# the historical record the +3 kt wind bias measured +3.64 here against +3.27
# at Grapeview, which is why the README calls that bias confirmed at two sites
# rather than a siting artifact.
#
# GW2160 is kept as a FALLBACK, not restored as primary, deliberately: a
# reference that flaps between two stations mixes two different sitings inside
# one bias number, and WU gives us ten stations where CWOP gave us one.
#
# THE DISCONTINUITY IS REAL AND MUST NOT BE READ THROUGH. Rows verified before
# this date used Grapeview; rows after use the cove. Absolute bias and rmse in
# variables{} therefore step on this date. The BAKE-OFF ranking is unaffected,
# because every model at a given timestamp is scored against the same
# observation whichever station supplied it -- only the absolute numbers move.
REFERENCE_SWITCHED_UTC = "2026-09-21T10:00:00Z"
REFERENCE_STATION = "KWASHELT285"


def _primary(vt):
    """The live reference observation for wind/temp/gust at `vt`.

    Cove WU first, Grapeview CWOP only if WU has nothing for that hour.
    """
    o = _cove_hourly(vt)
    if o:
        return o, "wu"
    c = cwop.at(vt) if cwop else None
    return (c, "cwop") if c is not None else (None, None)


def obs_wind(vt):
    o, src = _primary(vt)
    if o is not None and o.get("wind_kt") is not None:
        return o["wind_kt"]
    ob = _synoptic(vt, "wind_speed")
    return round(_nearest(ob, "wind_speed_set_1", vt), 1) if ob and _nearest(ob, "wind_speed_set_1", vt) is not None else None

def obs_gust(vt):
    o, src = _primary(vt)
    if o is not None and o.get("gust_kt") is not None:
        return o["gust_kt"]
    ob = _synoptic(vt, "wind_gust")
    v = _nearest(ob, "wind_gust_set_1", vt) if ob else None
    return round(v, 1) if v is not None else None

def obs_temp(vt):
    o, src = _primary(vt)
    if o is not None and o.get("temp_f") is not None:
        return o["temp_f"]
    ob = _synoptic(vt, "air_temp")
    return round(_nearest(ob, "air_temp_set_1", vt), 1) if ob and _nearest(ob, "air_temp_set_1", vt) is not None else None

def obs_rain(vt):
    """Did measurable precip fall near the cove in [vt-60min, vt]?  1/0/None."""
    if cwop:
        r = cwop.rain_in_hour(vt)          # station's own 1h accumulator, no midnight-reset artifact
        if r is not None:
            return r
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

def _night_depression(vt):
    """Network dewpoint depression by hour across the fire window ending at vt.

    Truth for the fog-formation call. Read from data_log.jsonl, which carries
    the QC'd cove consensus every cycle.
    """
    import collections, json as _j, math as _m, statistics
    end = vt
    start = end - timedelta(hours=7)
    hrs = collections.defaultdict(list)
    path = os.environ.get("DATA_LOG") or os.path.join(HERE, "data_log.jsonl")
    try:
        with open(path) as f:
            for ln in f:
                try:
                    d = _j.loads(ln)
                    o = d.get("obs") or {}
                    if o.get("cove_temp_f") is None or o.get("cove_rh") is None:
                        continue
                    t = _dt(d["t"].replace("+00:00", "Z"))
                except Exception:  # noqa: BLE001
                    continue
                if not (start <= t <= end):
                    continue
                tf, rh = o["cove_temp_f"], o["cove_rh"]
                tc = (tf - 32) / 1.8
                a, b = 17.625, 243.04
                g = _m.log(max(rh, 1) / 100.0) + a * tc / (b + tc)
                hrs[local_hour(t)].append(tf - ((b * g / (a - g)) * 1.8 + 32))
    except OSError:
        return {}
    return {h: statistics.median(v) for h, v in hrs.items()}


def obs_fog_forms(vt):
    """1.0 if the surface saturated at any point in the window."""
    d = _night_depression(vt)
    if len(d) < 4:
        return None
    return 1.0 if any(v <= 1.0 for v in d.values()) else 0.0


def obs_fog_onset(vt):
    """The hour it actually fogged in, 24+ for after midnight, else None."""
    d = _night_depression(vt)
    if len(d) < 4:
        return None
    hit = [h if h >= 19 else h + 24 for h, v in d.items() if v <= 1.0]
    return float(min(hit)) if hit else None


# WHICH Kt THE BURN-OFF VERIFIER USES, and why it changed on 2026-09-24.
#
# This read marine_log.jsonl, which records marine.survey() -> wu_current ->
# "solarRadiation": an INSTANTANEOUS sample taken whenever the cycle happened to
# run. burnoff.py was fitted on backfill/obs_hourly_extra.jsonl -> "solar_hi" ->
# "solarRadiationHigh": the hourly PEAK. Both arrive through the same
# wu._norm line, `_pick(o, "solarRadiation", "solarRadiationHigh")`, because the
# current endpoint carries the first field and the hourly endpoint only the
# second. Neither call site looks wrong.
#
# They are not close. Over 58 overlapping hours the peak exceeds the
# instantaneous value by a median of +0.33 Kt, and 36 hours clear the 0.65 bar
# by peak against 7 by instantaneous. So the model learned a 61% clearing base
# rate and was scored where clearing is five times rarer -- it over-forecast by
# construction, and the duel was measuring that mismatch rather than the model.
#
# Verifying on the PEAK makes the two agree, so the duel measures the model
# rather than the mismatch. That is the whole reason for it, and the cost is
# stated plainly here because it is not small.
#
# A PEAK OF 0.65 IS A SUNBREAK, NOT A CLEARED SKY, and no threshold fixes that.
# Calibrated against 68 live hours where the instantaneous median is available:
#
#     peak >= 0.65   catches 7/7 sustained-clear hours, 35 FALSE ALARMS
#     peak >= 0.85   catches 7/7                        27 false alarms
#     peak >= 1.00   catches 2/7                        12 false alarms
#
# There is no cutoff that separates them, because one bright break drives the
# hourly maximum arbitrarily high whatever the rest of the hour did -- peak Kt
# above 1.0 appears in this data, which is cloud-edge enhancement. Sustained
# clearing is simply not recoverable from an hourly maximum.
#
# SO burnoff_clears NOW MEASURES "did the sun break through at all", and the
# board's wording -- "84% chance it clears by 3pm" -- promises more than that.
# The honest fixes are to refit the model on a sustained measure once enough
# live instantaneous history exists (68 hours today, growing every cycle), or
# to change the board's wording to match. Both are open; neither is this line.
_upper_cache = {}


def _upper_by_hour(day):
    """Over-cove mid/high cloud %, by UTC hour, for a recent day. {} on failure."""
    key = str(day)
    if key in _upper_cache:
        return _upper_cache[key]
    out = {}
    try:
        q = {"latitude": MC["cove"]["lat"], "longitude": MC["cove"]["lon"],
             "timezone": "GMT", "hourly": "cloud_cover_mid,cloud_cover_high",
             "past_days": 7, "forecast_days": 1}
        h = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=30))["hourly"]
        for i, t in enumerate(h["time"]):
            out[t] = max(h["cloud_cover_mid"][i] or 0, h["cloud_cover_high"][i] or 0)
    except Exception:  # noqa: BLE001
        pass
    _upper_cache[key] = out
    return out


def _kt_day(vt):
    """Deck transmission by local hour -- Kt as a fraction of what the sun angle
    and today's upper cloud ALLOW, which is the target burnoff.py is fitted on.

    Hours below skyref's elevation floor are omitted entirely rather than
    reported as a very thick deck, because at this site a cloudless sky reads
    Kt 0.19 at 10-15 degrees and the number means nothing.
    """
    import marine, skyref, collections, statistics
    day = (vt - timedelta(hours=7)).date()
    try:
        import wu as _wu
        stations = _wu.independent_stations(MC)
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for h in range(6, 19):
        # Local -> UTC with the same fixed offset the day boundary above uses.
        # The valid times are mid-afternoon local, so the date is unambiguous.
        when = datetime(day.year, day.month, day.day, h, tzinfo=timezone.utc) + timedelta(hours=7)
        elev = marine.solar_elevation(when)
        if not skyref.usable(elev):
            continue
        ks = []
        for st in stations:
            try:
                o = _wu.wu_hourly_at(when, station=st)
            except Exception:  # noqa: BLE001
                continue
            v = (o or {}).get("solar_w_m2")
            if v is None:
                continue
            k = marine.kt(float(v), when)
            if k is not None:
                ks.append(k)
        if len(ks) >= 3:
            upper = _upper_by_hour(day).get(when.strftime("%Y-%m-%dT%H:00"))
            t = skyref.deck_transmission(statistics.median(ks), elev, upper or 0.0)
            if t is not None:
                out[h] = t
    return out


def _kt_day_sustained(vt):
    """Median clear-sky index by local hour from INSTANTANEOUS samples.

    marine_log.jsonl records marine.survey() every cycle, so each hour holds
    roughly four point samples and their median describes what the hour was
    actually like -- as opposed to _kt_day above, which reports the brightest
    instant in the hour. This is the measure that means CLEAR rather than
    CLEARING, and it is scored from today so that a refit onto it becomes
    possible: burnoff.py cannot be fitted to a target with no history.
    """
    import collections, statistics, json as _j
    day = (vt - timedelta(hours=7)).date()
    hrs = collections.defaultdict(list)
    try:
        with open(os.path.join(HERE, "marine_log.jsonl")) as f:
            for ln in f:
                try:
                    d = _j.loads(ln)
                    t = _dt(d["t"]) - timedelta(hours=7)
                except Exception:  # noqa: BLE001
                    continue
                if t.date() == day and d.get("kt_median") is not None:
                    hrs[t.hour].append(d["kt_median"])
    except OSError:
        return {}
    return {h: statistics.median(v) for h, v in hrs.items() if len(v) >= 2}


def obs_burnoff_sustained(vt):
    """1.0 if the deck was actually CLEAR -- hourly median Kt >= 0.65, not a peak."""
    med = _kt_day_sustained(vt)
    if len(med) < 4:
        return None
    return 1.0 if any(k >= 0.65 for h, k in med.items() if 9 <= h <= 15) else 0.0


def obs_burnoff_clears(vt):
    """1.0 if the DECK went away -- transmission 0.65 of what the sky allowed."""
    med = _kt_day(vt)
    if len(med) < 4:
        return None
    return 1.0 if any(k >= 0.65 for h, k in med.items() if 9 <= h <= 15) else 0.0


def obs_burnoff_hour(vt):
    """The hour it actually broke, or None if it never did."""
    med = _kt_day(vt)
    if len(med) < 4:
        return None
    hit = [h for h in sorted(med) if 9 <= h <= 15 and med[h] >= 0.65]
    return float(hit[0]) if hit else None


# ------------------------------------------------- fire-window verification
# The fire page makes claims about a WINDOW (7pm-2am), not an instant: the
# overnight low, the peak gust, whether it stayed dry, whether it stayed clear.
# The existing verifier signature fn(valid_time) fits these exactly, because
# the window is always the FIRE_WINDOW_H hours ENDING at the valid time.
#
# Truth comes from our own 15-minute cycle record (data_log.jsonl, ~12 rows an
# hour) and, for cloud after dark, from the GOES-18 mask -- the pyranometers
# are blind at night and METAR is 23 km away, so satellite is the only way to
# score "clear skies till 2am" at all.
FIRE_WINDOW_H = 7
FIRE_CLEAR_PCT = 30      # window mean cloud below this counts as "a clear night"
FIRE_MIN_HOURS = 5       # need this many distinct hours covered, or decline to score
DATA_LOG = os.environ.get("DATA_LOG") or os.path.join(HERE, "data_log.jsonl")

_datalog_cache = None


def _datalog():
    """data_log.jsonl parsed once per run."""
    global _datalog_cache
    if _datalog_cache is None:
        rows = []
        try:
            with open(DATA_LOG) as f:
                for ln in f:
                    try:
                        d = json.loads(ln)
                        d["_t"] = _dt(d["t"].replace("+00:00", "Z"))
                    except Exception:  # noqa: BLE001
                        continue
                    rows.append(d)
        except OSError:
            pass
        _datalog_cache = rows
    return _datalog_cache


def _window(vt, rows, tkey="_t"):
    t0 = vt - timedelta(hours=FIRE_WINDOW_H)
    return [r for r in rows if t0 <= r[tkey] <= vt]


def _covered(rows):
    """Distinct hours present. A night the Mini slept through must not verify
    as a calm clear one just because the few rows that exist happen to agree."""
    return len({r["_t"].hour for r in rows})


def _fire_vals(vt, pick):
    rows = _window(vt, _datalog())
    if _covered(rows) < FIRE_MIN_HOURS:
        return None
    vals = [v for v in (pick(r) for r in rows) if v is not None]
    return vals or None


def obs_fire_low(vt):
    v = _fire_vals(vt, lambda r: (r.get("obs") or {}).get("cove_temp_f"))
    return round(min(v), 1) if v else None


def obs_fire_gust(vt):
    v = _fire_vals(vt, lambda r: (r.get("wind") or {}).get("regional_gust_kt"))
    return round(max(v), 1) if v else None


def obs_fire_dry(vt):
    """1.0 if no gauge measured rain anywhere in the window."""
    v = _fire_vals(vt, lambda r: (r.get("obs") or {}).get("rain_in"))
    return None if v is None else (1.0 if max(v) <= 0 else 0.0)


def obs_fire_clear(vt):
    """1.0 if the GOES cloud mask averaged under FIRE_CLEAR_PCT across the window."""
    path = os.environ.get("GOES_LOG") or os.path.join(HERE, "goes_log.jsonl")
    rows = []
    try:
        with open(path) as f:
            for ln in f:
                try:
                    d = json.loads(ln)
                    d["_t"] = _dt(d["scan_utc"])
                except Exception:  # noqa: BLE001
                    continue
                rows.append(d)
    except OSError:
        return None
    w = [r for r in _window(vt, rows) if r.get("cloud_pct") is not None]
    if len(w) < 3:                      # too few scans to characterise a night
        return None
    return 1.0 if sum(r["cloud_pct"] for r in w) / len(w) < FIRE_CLEAR_PCT else 0.0


OBS = {"surge_ft": obs_surge, "wind_kt": obs_wind, "wind_gust_kt": obs_gust,
       "temp_f": obs_temp, "rain_next_hr": obs_rain, "solar_w_m2": obs_solar,
       "cloud_pct": obs_cloud,
       "sky_clear_3h": obs_sky_clear,
       # burnoff_clears verifies on the hourly PEAK, matching what burnoff.py
       # was fitted on. It means "the sun broke through", not "the deck cleared
       # and stayed cleared" -- see the note above _kt_day.
       "burnoff_clears": obs_burnoff_clears, "burnoff_hour": obs_burnoff_hour,
       # Same forecast, stricter target. The gap between these two IS the
       # recalibration the model needs, measured rather than guessed.
       "burnoff_sustained": obs_burnoff_sustained,
       "fog_forms": obs_fog_forms, "fog_onset_hour": obs_fog_onset,
       "fire_low_f": obs_fire_low, "fire_max_gust_kt": obs_fire_gust,
       "fire_dry_night": obs_fire_dry, "fire_clear_night": obs_fire_clear}

# Cove verification: the SAME live forecasts, verified against the Weather Underground
# station AT the cove (KWASHELT285, 0.35 mi) instead of Grapeview (5 mi) -- so we can
# see whether the wind/temp biases are real at the marina or partly a Grapeview artifact.
try:
    import wu
except Exception:  # noqa: BLE001
    wu = None

def _cove_hourly(vt):
    """The cove observation for verification -- nearest station the rest of the
    network does not contradict.

    This took the FIRST station with data, which meant a single broken reading
    became the observed truth and the forecast was scored against it. KWASHELT67
    published 117 F on a 35 F afternoon and -18 F on a 65 F evening; 2% of its
    readings were like that for two years, and every one of them would have been
    booked here as forecast error.
    """
    if wu is None:
        return None
    stations = wu.independent_stations(MC)
    try:
        ok = wu.wu_hourly_consensus(vt, stations, field="temp_f")
    except Exception:  # noqa: BLE001
        ok = None
    if ok:
        for st, o in ok:
            if o.get("temp_f") is not None or o.get("wind_kt") is not None:
                return o
    # No temperature anywhere, or too few peers to judge: fall back to the old
    # behaviour rather than return nothing. A wind-only hour is still verifiable.
    for st in stations:
        o = wu.wu_hourly_at(vt, station=st)
        if o and (o.get("temp_f") is not None or o.get("wind_kt") is not None):
            return o
    return None

def obs_cove_wind(vt):
    o = _cove_hourly(vt); return o.get("wind_kt") if o else None

def obs_cove_temp(vt):
    o = _cove_hourly(vt); return o.get("temp_f") if o else None

COVE_OBS = {"wind_kt": obs_cove_wind, "temp_f": obs_cove_temp}


def obs_temp_network(vt):
    """Median temperature across >=3 stations -- the quantity tempfix was FITTED on.

    train_tempfix.py targets the median of at least three PWS, deliberately:
    a headline finding in this project was once wrong because three models were
    scored against a single station and their agreement mistaken for
    corroboration. Verifying the resulting model against ONE station therefore
    measures something it was never asked to predict -- KWASHELT285 sits 0.56 km
    from the gangway and carries its own microclimate, which is the whole
    subject of the study rather than an error to be corrected away.

    Spike-filtered by the same consensus rule the rest of the pipeline uses, so
    a broken sensor cannot become the truth.
    """
    if wu is None:
        return None
    try:
        ok = wu.wu_hourly_consensus(vt, wu.independent_stations(MC), field="temp_f")
    except Exception:  # noqa: BLE001
        return None
    vals = sorted(float(o["temp_f"]) for _, o in (ok or []) if o.get("temp_f") is not None)
    if len(vals) < 3:
        return None
    n = len(vals)
    return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 1)


# Rows whose forecast is Open-Meteo's raw 2 m temperature or the tempfix
# correction of it are verified against the NETWORK, not the primary station.
NETWORK_OBS = {"temp_f": obs_temp_network}
NETWORK_SRCS = ("live-om-raw", "live-tempfix")

# ---------------------------------------------------------------- scorecard
SCORED_VARS = ("surge_ft", "wind_kt", "temp_f", "rain_next_hr", "solar_w_m2",
               "cloud_pct", "sky_clear_3h",
               "fire_low_f", "fire_max_gust_kt", "fire_dry_night", "fire_clear_night",
               "burnoff_clears", "burnoff_sustained", "burnoff_hour",
               "fog_forms", "fog_onset_hour")
# Probabilities, scored with Brier rather than bias/MAE.
MIN_HOUR_N = 8          # hours with fewer verified pairs are not reported

# Local hour, properly. This was written as `- timedelta(hours=7)`, which is
# PDT and only PDT: Pacific time is -8 from early November to mid March. The
# board derives its local hour from a real timezone, so from the DST switch
# onward the two would have disagreed by an hour -- score.py filing an
# observation under 14:00 that the board would look up as 13:00. For a wind
# correction whose value swings 4 kt across the day, a one-hour misalignment is
# not cosmetic.
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # noqa: BLE001
    _TZ = None


def local_hour(dt):
    """Hour of day at the cove, DST included."""
    if _TZ is not None:
        return dt.astimezone(_TZ).hour
    return (dt - timedelta(hours=7)).hour          # last resort, PDT only
PROB_VARS = {"rain_next_hr", "sky_clear_3h", "fire_dry_night", "fire_clear_night",
             "burnoff_clears", "burnoff_sustained", "fog_forms"}


def scorecard(entries):
    import math
    done = [e for e in entries if e.get("obs") is not None]
    card = {"generated_utc": None, "n_verified": len(done), "n_pending": len(entries) - len(done), "variables": {}}
    for var in SCORED_VARS:
        v = [e for e in done if e["var"] == var and e.get("src", "live") == "live"]   # production only
        if not v:
            continue
        if var in PROB_VARS:
            p = [e["fcst"] for e in v]; o = [e["obs"] for e in v]
            brier = sum((pi - oi) ** 2 for pi, oi in zip(p, o)) / len(v)
            base = sum(o) / len(o)
            brier_clim = sum((base - oi) ** 2 for oi in o) / len(v)
            skill = 1 - brier / brier_clim if brier_clim > 0 else 0.0
            card["variables"][var] = {"n": len(v), "brier": round(brier, 3), "base_rate": round(base, 3),
                                      "brier_skill_vs_climo": round(skill, 3),
                                      "note": "lower Brier better; skill>0 beats always-forecasting-climatology"}
            if var == "sky_clear_3h":
                # Same recency window the emission site uses, so the map the
                # scorecard reports is the map that is actually being shipped.
                cal = _sky_calibration(done, datetime.now(timezone.utc))
                card["variables"][var]["calibration"] = cal
                card["variables"][var]["_note"] = (
                    "P(sky clear in 3 h). Fitted, not calibrated: an ensemble of three "
                    "NWP cloud forecasts plus the observed sky three hours earlier, the "
                    "layered low/mid/high cloud over the cove, wind regime, pressure, "
                    "season and hour. Truth is the median METAR cloud fraction across "
                    "KSHN/KOLM/KTCM/KPWT -- regional, which is acceptable because cloud "
                    "is synoptic-scale where our rain is not. This is NOT the fog-on-the-"
                    "water question; that is burnoff.py's, and it uses different "
                    "instruments for good reason.")
                card["variables"][var]["_health"] = (
                    "REPLACED 2026-09-24. Rows up to that date came from a GOES binary "
                    "mapped through a rolling calibration and scored -0.83 in the "
                    "calibrated era; they are pooled here and drag the number down. The "
                    "cause was never the calibration -- the TRUTH lived in "
                    "goes_log.jsonl, eight days deep, so the predictor could be hedged "
                    "but never fitted. Truth now comes from the median METAR cloud "
                    "fraction across four airfields, which has five years, and the "
                    "forecast comes from skyclear.json: 33,310 hours, leave-one-year-out "
                    "Brier 0.0825, AUC 0.953, skill +0.655. Persistence alone -- the "
                    "observed sky three hours earlier -- is worth +0.549 of that and the "
                    "old version did not use it. Read the post-2026-09-24 rows; the "
                    "pooled figure is two different variables added together.")
                # The variable changed instrument on 2026-09-24, so the pooled
                # figure above adds two different things together. This is the
                # one to read: rows forecast by skyclear.json against a METAR
                # target. Self-contained on purpose -- it used to depend on
                # locals computed elsewhere in this branch.
                nr = [e for e in v if e["valid"] >= SKY_REFIT_UTC]
                if len(nr) >= 20:
                    b2 = sum((e["fcst"] - e["obs"]) ** 2 for e in nr) / len(nr)
                    bb2 = sum(e["obs"] for e in nr) / len(nr)
                    c2 = sum((bb2 - e["obs"]) ** 2 for e in nr) / len(nr)
                    card["variables"][var]["since_refit"] = {
                        "n": len(nr), "base_rate": round(bb2, 3), "brier": round(b2, 4),
                        "brier_skill_vs_climo": round(1 - b2 / c2, 3) if c2 > 0 else None,
                        "_note": "fitted model against a METAR target, from %s. "
                                 "The pooled number above still carries the retired "
                                 "GOES-based rows." % SKY_REFIT_UTC[:10]}
        else:
            errs = [e["fcst"] - e["obs"] for e in v]
            bias = sum(errs) / len(errs)
            mae = sum(abs(x) for x in errs) / len(errs)
            rmse = math.sqrt(sum(x * x for x in errs) / len(errs))
            # A SINGLE bias number is misleading here, and measurably so. Both
            # wind and temperature biases carry strong diurnal structure --
            # wind swings 3.65 kt between its best hour (+1.25 at 15:00) and
            # its worst (+4.90 at 22:00), which is LARGER than the overall
            # +3.26 bias; temperature swings 2.87 F the other way, nearly
            # right at dawn and 3 F too warm mid-afternoon. Applying the flat
            # suggested_adjustment would over-correct afternoons and
            # under-correct nights.
            #
            # Mass's chapter on sea breezes, land breezes and slope winds is
            # the explanation: these are diurnal circulations, land cools far
            # faster than water, and the cove decouples at night while the
            # model keeps forecasting regional flow.
            byh = {}
            for e in v:
                h = local_hour(_dt(e["valid"]))
                byh.setdefault(h, []).append(e["fcst"] - e["obs"])
            hourly = {str(h): round(sum(x) / len(x), 2)
                      for h, x in sorted(byh.items()) if len(x) >= MIN_HOUR_N}
            card["variables"][var] = {"n": len(v), "bias": round(bias, 2), "mae": round(mae, 2), "rmse": round(rmse, 2),
                                      "suggested_adjustment": round(-bias, 2),
                                      "bias_by_hour_local": hourly,
                                      "diurnal_range": round(max(hourly.values()) - min(hourly.values()), 2) if hourly else None,
                                      "note": "bias = forecast - observed; add suggested_adjustment to de-bias",
                                      "_diurnal": ("bias_by_hour_local is the SAME bias split by local hour. Where "
                                                   "diurnal_range approaches or exceeds the overall bias, a flat "
                                                   "correction is the wrong instrument and an hour-of-day correction "
                                                   "is warranted.")}

    # DOES THE SHIPPED CORRECTION ACTUALLY HELP? The board applies tempfix.json
    # in the browser; src="live-tempfix" is the same model evaluated here. Both
    # are scored over the same hours against the same observation, so this is a
    # paired comparison of what members see against what the model said before
    # correction. Until this existed the project shipped a correction claiming
    # MAE 1.09 and verified the raw forecast at MAE 2.08 -- a stale model file
    # or a wrong feature order would not have moved a single published number.
    tf = {}
    _paired = {}
    for src in ("live-om-raw", "live-tempfix"):
        for e in done:
            if e["var"] == "temp_f" and e.get("src") == src and e.get("lead_min") == 0:
                # Bucket on valid[:15], the SAME key the dedup uses. Pairing on
                # the exact string fails whenever the raw row deduped from an
                # earlier cycle and the corrected one is new: their timestamps
                # then differ by seconds and the pair silently never forms.
                _paired.setdefault(e["valid"][:15], {})[src] = e
    both = [p for p in _paired.values() if len(p) == 2]
    if len(both) >= 10:
        def _stat(src):        # noqa: E306
            errs = [p[src]["fcst"] - p[src]["obs"] for p in both]
            n = len(errs)
            return {"n": n, "bias": round(sum(errs) / n, 2),
                    "mae": round(sum(abs(x) for x in errs) / n, 2),
                    "rmse": round((sum(x * x for x in errs) / n) ** 0.5, 2)}
        tf = {"raw": _stat("live-om-raw"), "corrected": _stat("live-tempfix"),
              "_note": ("paired on identical valid hours, against the MEDIAN OF >=3 "
                        "STATIONS -- the quantity train_tempfix.py was fitted on. "
                        "'raw' is Open-Meteo temperature_2m, the exact input tempfix "
                        "corrects; it is NOT nc['temp_cove_f'], which already carries "
                        "its own cove offset and briefly stood in here, making the "
                        "correction look twice as bad as the forecast it was not "
                        "correcting. Verifying against the primary station alone would "
                        "be the same category of error: KWASHELT285 has its own "
                        "microclimate, about 1 F from the network at any hour, and that "
                        "microclimate is this project's subject rather than model error. "
                        "If corrected is not better here, the correction is not working "
                        "in production whatever the backtest said.")}
        tf["mae_change_pct"] = round(100 * (tf["corrected"]["mae"] - tf["raw"]["mae"])
                                     / max(tf["raw"]["mae"], 1e-9), 1)

    # Does the shipped WIND correction help? Same construction as
    # tempfix_verification: identical valid hours, identical truth, one side
    # corrected. Until this existed the board de-biased and rescaled the wind
    # and nothing measured the result.
    wf = {}
    _wp = {}
    for src in ("live", "live-windfix"):
        for e in done:
            if e["var"] == "wind_kt" and e.get("src") == src and e.get("lead_min") == 0:
                _wp.setdefault(e["valid"][:15], {})[src] = e
    wboth = [q for q in _wp.values() if len(q) == 2]
    if len(wboth) >= 10:
        def _wstat(src):
            er = [q[src]["fcst"] - q[src]["obs"] for q in wboth]
            n = len(er)
            sd = (sum((x - sum(er)/n) ** 2 for x in er) / n) ** 0.5
            return {"n": n, "bias": round(sum(er)/n, 2),
                    "mae": round(sum(abs(x) for x in er)/n, 2),
                    "rmse": round((sum(x*x for x in er)/n) ** 0.5, 2),
                    "sd_of_error": round(sd, 2)}
        obs_sd = None
        ov = [q["live"]["obs"] for q in wboth]
        if len(ov) > 1:
            mo = sum(ov)/len(ov)
            obs_sd = (sum((x-mo)**2 for x in ov)/len(ov)) ** 0.5
        fv = [q["live-windfix"]["fcst"] for q in wboth]
        mf = sum(fv)/len(fv)
        f_sd = (sum((x-mf)**2 for x in fv)/len(fv)) ** 0.5
        wf = {"raw": _wstat("live"), "corrected": _wstat("live-windfix"),
              "sharpness_pct": round(100 * f_sd / obs_sd, 1) if obs_sd else None,
              "_note": ("paired on identical valid hours. 'corrected' is what the board "
                        "displays -- hour-of-day de-bias then rescaled to the observed "
                        "spread -- applied to regional_kt, the same quantity 'raw' logs. "
                        "sharpness_pct is the corrected forecast's spread against the "
                        "observed; the point of the rescale was that the hour-corrected "
                        "wind carried ~158% of it, unbiased on average and still too "
                        "windy at the top. Near 100 is the target; well under is the "
                        "shrinkage trap that killed the gradient-boosted attempt.")}
        wf["mae_change_pct"] = round(100 * (wf["corrected"]["mae"] - wf["raw"]["mae"])
                                     / max(wf["raw"]["mae"], 1e-9), 1)

    # cove verification: the SAME live wind/temp forecasts scored at the cove (WU) --
    # compare bias/rmse here against the Grapeview-verified numbers in variables{} above.
    cove = {}
    for var in ("wind_kt", "temp_f"):
        v = [e for e in done if e["var"] == var and e.get("src") == "cove"]
        if not v:
            continue
        errs = [e["fcst"] - e["obs"] for e in v]
        # Hourly structure, verified at the COVE rather than at Grapeview --
        # this is the table the board corrects its displayed forecast with, so
        # it must be scored against the station 0.56 km away, not the one 5 km
        # away across the peninsula. The structure is larger here than at
        # Grapeview (temperature +0.15 F at 02:00 against +4.82 F at 16:00)
        # because the cove decouples harder overnight.
        #
        # Verified real, not sampling noise: median standard error per hour is
        # 0.28, the diurnal ranges are 10-13x that, and a permutation test over
        # 4,000 shuffles never once reproduced the observed range (p < 0.00025).
        byh = {}
        for e in v:
            h = local_hour(_dt(e["valid"]))
            byh.setdefault(h, []).append(e["fcst"] - e["obs"])
        hourly = {str(h): round(sum(x) / len(x), 2)
                  for h, x in sorted(byh.items()) if len(x) >= MIN_HOUR_N}
        cove[var] = {"n": len(v), "bias": round(sum(errs) / len(errs), 2),
                     "mae": round(sum(abs(x) for x in errs) / len(errs), 2),
                     "rmse": round(math.sqrt(sum(x * x for x in errs) / len(errs)), 2),
                     "bias_by_hour_local": hourly,
                     "hours_covered": len(hourly),
                     "min_n_per_hour": min((len(x) for x in byh.values()), default=0),
                     "diurnal_range": round(max(hourly.values()) - min(hourly.values()), 2) if hourly else None}
        # VARIANCE MATCH, for wind only and for a measured reason. Subtracting
        # the hour-of-day bias fixes the MEAN and leaves the spread alone, and
        # the spread is wrong: the hour-corrected forecast carries 128% of the
        # observed standard deviation. So it is unbiased on average while still
        # calling 8 kt on a day the anemometer never passed 6.
        #
        # Rescaling to the observed spread is the classic inflation step, run
        # in the SHRINKING direction here. On a chronological split -- fit on
        # the first half of the verified rows, scored on the second -- it beat
        # the shipped hour-of-day correction on every measure that matters:
        #
        #     raw                     MAE 3.031  RMSE 3.525  bias +2.68  sharp 123%
        #     hour-of-day [shipped]   MAE 1.521  RMSE 1.981  bias -0.43  sharp 128%
        #     + variance match        MAE 1.375  RMSE 1.784  bias +0.04  sharp 113%
        #
        # Quantile mapping reached a marginally better MAE (1.371) and a worse
        # everything else -- it under-disperses to 88% and drops recall of the
        # few hours above 6 kt from 0.36 to 0.29. This is NOT the shrinkage trap
        # that killed the gradient-boosted wind correction: that one flattened
        # an already-underdispersed series, this one trims an overdispersed one.
        if var == "wind_kt" and len(v) >= 200:
            corr = [e["fcst"] - hourly.get(str(local_hour(_dt(e["valid"]))),
                                           sum(errs) / len(errs)) for e in v]
            obs = [e["obs"] for e in v]
            mc, mo = sum(corr) / len(corr), sum(obs) / len(obs)
            sc = (sum((x - mc) ** 2 for x in corr) / len(corr)) ** 0.5
            so = (sum((x - mo) ** 2 for x in obs) / len(obs)) ** 0.5
            if sc > 1e-6:
                cove[var]["variance_match"] = {
                    "mean_corrected": round(mc, 3), "mean_observed": round(mo, 3),
                    "sd_corrected": round(sc, 3), "sd_observed": round(so, 3),
                    "scale": round(so / sc, 4),
                    "_apply": ("after subtracting bias_by_hour_local: "
                               "v = mean_observed + (v - mean_corrected) * scale"),
                    "_why": ("the hour-corrected forecast carries %.0f%% of the observed "
                             "spread, so it is unbiased on average and still too windy "
                             "at the top. Shrinking, not inflating." % (100 * sc / max(so, 1e-9)))}
    if card["variables"].get("cloud_pct"):
        card["variables"]["cloud_pct"]["_note"] = (
            "Cloud-cover skill. Forecast Open-Meteo cloud_cover vs the median METAR sky "
            "condition at KSHN/KOLM/KTCM/KPWT, mapped from okta mid-points "
            "(FEW 19%, SCT 44%, BKN 75%, OVC 100%). Airfields are 23 km+, so this is "
            "REGIONAL cloud -- acceptable because cloud is synoptic-scale where our rain "
            "is not. Radar cannot supply this: it detects hydrometeors, not cloud "
            "droplets, so an overcast sky returns no echo.")

    if card["variables"].get("solar_w_m2"):
        card["variables"]["solar_w_m2"]["_note"] = (
            "Cloud/radiation skill. Forecast is Open-Meteo shortwave_radiation, an "
            "AVERAGE over the preceding hour; observation is the median "
            "solarRadiationHigh across 9 PWS, a PEAK within the hour. Peak exceeds "
            "mean under broken cloud, so the bias carries a negative artefact that is "
            "NOT forecast error. Model-to-model comparison is unaffected. Daytime only "
            "(forecast > 20 W/m2).")

    card["windfix_verification"] = wf or {
        "_note": "no paired hours yet; starts accumulating from 2026-09-25"}
    card["tempfix_verification"] = tf or {
        "_note": "no paired hours yet; the like-for-like pairing "
                 "(live-om-raw vs live-tempfix, network-median truth) starts "
                 "accumulating from 2026-09-25"}

    if cove:
        card["cove_verification"] = {"_note": "same forecast verified at the cove (WU KWASHELT285/12, ~0.35 mi). "
                                     "This USED to be the contrast against Grapeview in variables{}, but GW2160 "
                                     "went off the air on 2026-09-16 and the live reference moved to the same cove "
                                     "station on 2026-09-21, so the two now share a SOURCE -- though not a SAMPLE, "
                                     "since cove rows shadow only the 0-lead forecasts, which is why the two "
                                     "still differ (1.42 vs 1.77 F when switched). "
                                     "The board corrects its displayed forecast from THIS table, so it is kept "
                                     "as the stable, board-facing contract. Restoring a genuine second site means "
                                     "adding a Grapeview WU station (KWAGRAPE21); it is not free, because the "
                                     "two-site agreement is what makes the +3 kt wind bias a finding rather than "
                                     "a siting artifact.", **cove}

    # bake-off: forecast sources head-to-head (same var, same lead, same obs)
    bake = {}
    for var in ("temp_f", "wind_kt"):
        for lead in (60, 180):
            per = {}
            for src in ("hrrr", "ecmwf", "icon", "nws", "metno", "openmeteo"):
                s = [e for e in done if e["var"] == var and e.get("src") == src and e.get("lead_min") == lead]
                if not s:
                    continue
                errs = [e["fcst"] - e["obs"] for e in s]
                per[src] = {"n": len(s), "bias": round(sum(errs) / len(errs), 2),
                            "rmse": round(math.sqrt(sum(x * x for x in errs) / len(errs)), 2)}
            if len(per) >= 2:
                per["_best_rmse"] = min(per, key=lambda k: per[k]["rmse"])
                bake[f"{var}_+{lead // 60}h"] = per
    if bake:
        card["bakeoff"] = {"_note": "same variable, lead, and obs across sources; lowest rmse wins", **bake}

    # Model head-to-head: when a forecast module is replaced, the retired model
    # keeps forecasting under its own src so the replacement has to win on the
    # board's own record, not only in cross-validation. Both see the SAME
    # inputs at the same instant, which is the whole point of logging the
    # shadow rather than recomputing it from an archive later.
    duel = {}
    for var, srcs in (("burnoff_clears", ("live", "v1-climatology")),
                      ("burnoff_hour", ("live", "v1-climatology"))):
        # PAIRED: only mornings where both models have a verified forecast, so
        # neither is credited for a day the other never called. Rows from
        # before the replacement carry src "live-v1-climatology" and are
        # excluded by construction -- the new model never forecast those days.
        got = {src: {e["valid"]: e for e in done
                     if e["var"] == var and e.get("src") == src} for src in srcs}
        both = set.intersection(*(set(g) for g in got.values())) if got else set()
        per = {}
        for src in srcs:
            s = [got[src][v] for v in sorted(both)]
            if not s:
                continue
            if var in PROB_VARS:
                per[src] = {"n": len(s),
                            "brier": round(sum((e["fcst"] - e["obs"]) ** 2 for e in s) / len(s), 4)}
            else:
                per[src] = {"n": len(s),
                            "mae": round(sum(abs(e["fcst"] - e["obs"]) for e in s) / len(s), 2)}
        if len(per) >= 2:
            k = "brier" if var in PROB_VARS else "mae"
            per["_best"] = min((x for x in per if not x.startswith("_")), key=lambda x: per[x][k])
            duel[var] = per
    if duel:
        card["model_duel"] = {
            "_note": "current model (live) vs the retired one it replaced (v1-climatology), "
                     "same inputs, same observation. The archive says stull-6.12 should win "
                     "burnoff_clears by about 0.064 Brier; ~50 clouded mornings settles it.",
            **duel}
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

    # 1. record current forecasts + bake-off shadow sources (dedup by var+src+valid[15min])
    key = lambda e: (e["var"], e.get("src", "live"), e["valid"][:15])
    seen = {key(e) for e in entries}
    added = 0
    for r in record(now, entries) + record_bakeoff(now):
        if key(r) not in seen:
            entries.append(r); seen.add(key(r)); added += 1

    log_predictors(now)          # forecast-time state, for a future corrector

    # 2. verify ripe, unverified forecasts
    verified = 0
    for e in entries:
        if e.get("obs") is not None:
            continue
        vt = _dt(e["valid"])
        if vt > now - timedelta(minutes=RIPE_MIN) or vt < now - timedelta(days=PRUNE_DAYS):
            continue
        try:
            src = e.get("src")
            if src in NETWORK_SRCS:
                fn = NETWORK_OBS.get(e["var"])
            elif src == "cove":
                fn = COVE_OBS.get(e["var"])
            else:
                fn = OBS.get(e["var"])
            o = fn(vt) if fn else None
        except Exception:  # noqa: BLE001
            o = None
        if o is not None:
            e["obs"] = o
            e["err"] = None if e["var"] in PROB_VARS else round(e["fcst"] - o, 2)
            verified += 1

    # 3. prune + persist + scorecard
    entries = [e for e in entries if _dt(e["valid"]) > now - timedelta(days=PRUNE_DAYS)]
    with open(LOG, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    card = scorecard(entries)
    # Regime table travels with the scorecard: the board already fetches this
    # file for bias_by_hour_local and should not need a second calibration feed.
    try:
        card["drainage_temp_adjust_f"] = (MC.get("model_calibration") or {}).get("drainage_temp_adjust_f")
    except Exception:  # noqa: BLE001
        pass
    card["reference_station"] = {
        "station": REFERENCE_STATION,
        "switched_utc": REFERENCE_SWITCHED_UTC,
        "previous": "GW2160 (Grapeview, CWOP) -- off the air since 2026-09-16T21:00Z",
        "_note": "wind_kt, temp_f, wind_gust_kt and the bake-off are verified against this "
                 "station. Rows verified BEFORE switched_utc used Grapeview, so absolute bias "
                 "and rmse in variables{} step on that date and must not be read as a trend. "
                 "Bake-off RANKING is unaffected: at any timestamp every model is scored "
                 "against the same observation, whichever station supplied it."}
    card["generated_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(card, open(CARD, "w"), indent=2)
    print(f"score: +{added} logged, {verified} verified, {card['n_verified']} total verified / {card['n_pending']} pending")
    for var, s in card["variables"].items():
        print(f"  {var:14} {s}")

if __name__ == "__main__":
    main()

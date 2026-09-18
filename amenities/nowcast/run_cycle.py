"""One capture cycle -- the complete data record for Indian Cove.

Runs the QC observation + the nowcast, then appends ONE comprehensive record to
data_log.jsonl (append-only master dataset). Each record holds everything needed
to score forecasts and re-calibrate later, captured RAW so nothing needs tuning
after the fact:

  forecast : what we predicted (nowcast.json)
  obs      : the QC'd cove observation (cove_obs.json)
  stations : raw readings from the key sensors (Grapeview, dock PurpleAir, buoy)
  metar    : airfield present-weather rain flags + cove model precip

Also refreshes the latest snapshots: cove_obs.json, nowcast.json, stations_snapshot.json.

Cross-platform (stdlib). This is what the always-on host (Mac Mini) runs on a
schedule -- copy the folder + secrets.json, point launchd at `python3 run_cycle.py`,
and it captures the full dataset with no further tuning.
"""
import json
import os
import urllib.parse
import urllib.request
import sys
import traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import cove_obs   # noqa: E402  (Synoptic + PurpleAir QC obs; needs secrets.json)
import nowcast    # noqa: E402  (Open-Meteo prediction; keyless)
import phase1     # noqa: E402  (airfield METAR flags; keyless)

DATA_LOG = os.path.join(HERE, "data_log.jsonl")

# A cycle that cannot refresh a snapshot (no secrets.json, or the fetch failed)
# leaves the PREVIOUS snapshot sitting on disk. Reading it blindly stamps stale
# observations with a fresh timestamp -- silent corruption of the very dataset
# this file exists to build. Anything older than this is dropped instead.
STALE_S = int(os.environ.get("OBS_MAX_AGE_S", "1800"))

# key raw stations to log each cycle, by Synoptic STID / PurpleAir index
KEY_STATIONS = {"G2160": "grapeview", "208423": "pickering_estate",
                "74361": "harstine_pointe", "46121": "carr_inlet_buoy"}
FORECAST_KEYS = ["headline", "confidence", "regime", "precip_ratio", "temp_cove_f",
                 "temp_model_f", "temp_offset_f", "wind_dir_deg", "wind_kt",
                 "baro_hpa_3h", "timeline"]
OBS_KEYS = ["cove_temp_f", "cove_rh", "n_used", "n_rejected", "rejected",
            "rain_in", "rain_window", "rain_gauge", "rain_gauge_km",
            "wind_kt", "wind_dir", "wind_from"]


def load(name, default):
    try:
        with open(os.path.join(HERE, name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def fresh(d, stamp, what):
    """Return d only if its generated_utc is recent; otherwise {} (all-null record).

    Same shape either way, so downstream consumers keep the schema -- but a stale
    snapshot becomes explicit nulls rather than plausible-looking wrong numbers.
    """
    g = d.get("generated_utc")
    if not g:
        return d                       # nothing to judge it by; leave as-is
    try:
        age = (datetime.fromisoformat(stamp) - datetime.fromisoformat(g)).total_seconds()
    except ValueError:
        return d
    if age > STALE_S:
        print(f"  {what}: STALE by {age/60:.0f} min -- omitted (recorded as null)")
        return {}
    return d


COCO_LOG = os.path.join(HERE, "cocorahs_daily.jsonl")


def capture_cocorahs(days_back=3):
    """Append any CoCoRaHS daily reports we do not already hold.

    Observers file late and amend, so re-check the last few days rather than
    only yesterday -- but key on (station, date) so nothing is stored twice.
    """
    import cocorahs
    from datetime import date, timedelta

    have = set()
    if os.path.exists(COCO_LOG):
        with open(COCO_LOG) as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                    have.add((r.get("id"), r.get("date")))
                except ValueError:
                    continue
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days_back)
    # cheap guard: if we already hold every gauge for the end date, do nothing
    ids = {s["id"] for s in cocorahs.stations()}
    if ids and all((i, end.isoformat()) in have for i in ids):
        return 0
    new = [r for r in cocorahs.reports(start, end) if (r["id"], r["date"]) not in have]
    if new:
        with open(COCO_LOG, "a") as f:
            for r in new:
                f.write(json.dumps(r) + "\n")
        near = min(new, key=lambda r: r["dist_km"])
        print("    cocorahs: +%d report(s), nearest %s %s %.2f in"
              % (len(new), near["id"], near["date"], near["precip_in"] or 0.0))
    return len(new)


WATER_STATION = "9446484"          # Tacoma PORTS, the board's met station


def water_temperature():
    """Sea-surface temperature, and its difference from our air temperature.

    Returns None rather than raising: this is a new field and nothing upstream
    should break if NOAA is unavailable.
    """
    q = {"product": "water_temperature", "station": WATER_STATION, "date": "latest",
         "units": "english", "time_zone": "gmt", "format": "json",
         "application": "indian_cove_microclimate"}
    try:
        d = json.load(urllib.request.urlopen(
            "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
            + urllib.parse.urlencode(q), timeout=30))
        row = (d.get("data") or [None])[0]
        return {"water_f": float(row["v"]), "t": row["t"], "station": WATER_STATION}
    except Exception:  # noqa: BLE001
        return None


def main():
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"\n===== capture {stamp} =====")

    # 1. QC observation (Synoptic + PurpleAir) -> cove_obs.json + stations_snapshot.json
    if os.path.exists(os.path.join(HERE, "secrets.json")):
        try:
            cove_obs.main()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    else:
        print("  (no secrets.json -- skipping QC obs; nowcast still runs keyless)")

    # 2. Prediction (Open-Meteo, keyless) -> nowcast.json
    try:
        nowcast.main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()

    # 2b. CoCoRaHS daily gauges -- ONCE PER DAY, not once per cycle.
    #     Seven hand-read gauges within 10 km, public and keyless. Jarrell Cove
    #     (1.88 km) is on Pickering Passage like the cove; the Lakebay cluster
    #     (4.7-9.3 km) is on the Case Inlet side, so the spread measures the
    #     cross-peninsula rain-shadow gradient. Daily manual reads -- useless for
    #     live timing, gold standard for totals and calibration.
    #     The have-we-already-got-it guard IS the rate limit: at 96 cycles/day
    #     this fetches at most once.
    try:
        capture_cocorahs()
    except Exception:  # noqa: BLE001
        traceback.print_exc()

    # 3. Airfield METAR rain flags (keyless)
    try:
        metar = phase1.join_snapshot()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        metar = {}

    # 4. Assemble + append the comprehensive record
    nc = load("nowcast.json", {})
    obs = fresh(load("cove_obs.json", {}), stamp, "cove_obs")
    snap = fresh(load("stations_snapshot.json", {"stations": []}), stamp, "stations_snapshot")
    key = {}
    for s in snap.get("stations", []):
        label = KEY_STATIONS.get(str(s.get("id")))
        if label:
            key[label] = {k: s.get(k) for k in ("temp_f", "rh", "wind", "wind_dir", "rain_24h")}

    # The full wind block, not just the top-level scalars. It carries the
    # REGIONAL values, the SHELTERED marina values (regional x shelter_factor),
    # the factor itself and the exposed-point comparison. Only regional_kt is
    # scored -- the sheltered numbers cannot be verified without a sensor at the
    # cove -- so capturing the whole block here is the only way a future
    # recalibration of shelter_factor can be done against this period at all.
    # Water temperature, and the water-minus-air difference that drives steam
    # fog. The board has displayed water temperature all along but nothing
    # logged it, so the archive could not answer a question that needs the
    # SPREAD over a season: cold air over relatively warm water is Stull's
    # steam-fog mechanism (S6.8.1), and our inlets should do it in Nov-Dec
    # while the water still holds summer heat. Logging starts now because a
    # winter prediction cannot be tested with a record that begins in winter.
    sea = water_temperature()
    record = {
        "t": stamp,
        "sea": sea,
        "forecast": {k: nc.get(k) for k in FORECAST_KEYS},
        "wind": nc.get("wind"),
        "obs": {k: obs.get(k) for k in OBS_KEYS},
        "stations": key,
        "metar": metar,
    }
    if not obs or not snap:
        record["degraded"] = "stale/missing snapshot; obs and/or stations are null"
    try:
        with open(DATA_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")
        n = sum(1 for _ in open(DATA_LOG))
        print(f"  data_log.jsonl <- record #{n}")
    except OSError:
        traceback.print_exc()


if __name__ == "__main__":
    main()

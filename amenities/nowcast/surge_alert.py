"""Email alert when a storm surge + high tide would trip the board's ^/! marker.

Reproduces the marina board's exact trigger (indian-cove-board*.html): an upcoming
HIGH tide where  predicted + surge >= p95-high  AND  surge >= SURGE_MAJOR (1.5 ft)
-- i.e. exactly when the board draws the up-triangle + dagger. Surge = the live
Tacoma residual (observed - predicted) carried forward like makeSurgeFn (persist
12 h, fade to 0 by 36 h). Runs in the 30-min GitHub Action; dedupes so it emails
once per event; sends via Gmail SMTP (app password in repo secrets).

Env (all optional; absent -> dry-run, prints instead of sending):
  GMAIL_USER, GMAIL_APP_PASSWORD   Gmail account + app password to send FROM
  ALERT_TO                          recipient (default hpmatech@gmail.com)

  python surge_alert.py
"""
import json, os, ssl, smtplib, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "surge_alert_state.json")
MC = json.load(open(os.path.join(HERE, "microclimate.json")))
NOAA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
DP, TAC = "9446583", "9446484"           # McMicken Island (cove predictions), Tacoma (surge)
SURGE_MAJOR, PERSIST_H, FADE_H = 1.5, 12, 36
P95_FALLBACK, LOOKAHEAD_H = 15.0, 36
BOARD_URL = "https://herzog303-commits.github.io/hpma.org/amenities/marina-board.html?view=tides"
NOAA_TACOMA_URL = "https://tidesandcurrents.noaa.gov/stationhome.html?id=9446484"

def noaa(**kw):
    kw.setdefault("application", "hpma_marina_board"); kw.setdefault("format", "json")
    kw.setdefault("units", "english"); kw.setdefault("time_zone", "gmt")
    with urllib.request.urlopen(NOAA + "?" + urllib.parse.urlencode(kw), timeout=30) as r:
        return json.load(r)

def _t(s):                               # "2026-08-30 14:30" (GMT) -> aware UTC
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)

def surge_at(t, residual, now):
    """Persistence-with-fade, matching the board's makeSurgeFn 'live' branch."""
    h = (t - now).total_seconds() / 3600
    g = 1.0 if h <= PERSIST_H else 0.0 if h >= FADE_H else 1 - (h - PERSIST_H) / (FADE_H - PERSIST_H)
    return residual * g

def find_events(highs, surge_fn, p95):
    """Upcoming highs that trip the marker. surge_fn(t)->ft. Pure -> unit-testable."""
    out = []
    for e in highs:
        s = surge_fn(e["t"])
        total = e["h"] + s
        if total >= p95 and s >= SURGE_MAJOR:
            out.append({"t": e["t"], "h": e["h"], "surge": round(s, 2), "total": round(total, 2)})
    return out


def load_surge_forecast():
    """The multi-day surge forecast from surge_forecast.py, if published. Returns a
    surge_fn(t)->ft (interpolated) and a lead-days count, else (None, 0)."""
    path = os.environ.get("SURGE_FORECAST_FILE") or os.path.join(HERE, "..", "surge_forecast.json")
    if not os.path.exists(path):
        path = os.path.join(HERE, "surge_forecast.json")   # local/study fallback
    try:
        raw = json.load(open(path))
        pts = [(datetime.fromisoformat(x["t"].replace("Z", "+00:00")), float(x["ft"])) for x in raw]
        pts.sort()
    except Exception:  # noqa: BLE001
        return None, 0
    if len(pts) < 2:
        return None, 0

    def fn(t):
        if t <= pts[0][0]:
            return pts[0][1]
        if t >= pts[-1][0]:
            return pts[-1][1]
        for i in range(len(pts) - 1):
            if pts[i][0] <= t <= pts[i + 1][0]:
                (t0, v0), (t1, v1) = pts[i], pts[i + 1]
                return v0 + (v1 - v0) * (t - t0).total_seconds() / (t1 - t0).total_seconds()
        return pts[-1][1]
    lead_days = round((pts[-1][0] - pts[0][0]).total_seconds() / 86400, 1)
    return fn, lead_days


def nws_coastal_flood(zone):
    """Active NWS Coastal-Flood products for the marine zone (Part C: earliest,
    official lead). Returns [{id, event, headline, ends}] or []."""
    if not zone:
        return []
    url = "https://api.weather.gov/alerts/active?" + urllib.parse.urlencode({"zone": zone})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hpma-marina-board", "Accept": "application/geo+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            feats = json.load(r).get("features", [])
    except Exception as exc:  # noqa: BLE001
        print(f"surge_alert: NWS fetch failed ({exc})"); return []
    out = []
    for f in feats:
        p = f.get("properties", {})
        ev = p.get("event", "")
        if "coastal flood" in ev.lower() or ("flood" in ev.lower() and "warning" in ev.lower()):
            out.append({"id": p.get("id", ev), "event": ev,
                        "headline": (p.get("headline") or ev), "ends": p.get("ends") or p.get("expires")})
    return out

def current_residual():
    """Live Tacoma surge = latest observed water level - prediction at that time."""
    obs = noaa(product="water_level", station=TAC, date="latest", datum="MLLW")["data"]
    if not obs:
        return None
    last = obs[-1]; ot = _t(last["t"]); ov = float(last["v"])
    day = ot.strftime("%Y%m%d")
    pr = noaa(product="predictions", station=TAC, begin_date=day, end_date=day, datum="MLLW", interval="6")["predictions"]
    near = min(pr, key=lambda p: abs((_t(p["t"]) - ot).total_seconds()))
    return round(ov - float(near["v"]), 2)

def p95_high(now, state):
    """95th-percentile predicted high for the year (matches fetchAnnual). Cached per year."""
    if state.get("p95_year") == now.year and state.get("p95") is not None:
        return state["p95"]
    try:
        yr = noaa(product="predictions", station=DP, begin_date=f"{now.year}0101",
                  end_date=f"{now.year}1231", datum="MLLW", interval="hilo")["predictions"]
        highs = sorted(float(p["v"]) for p in yr if p["type"] == "H")
        p95 = round(highs[int(0.95 * len(highs))], 2) if highs else P95_FALLBACK
    except Exception:  # noqa: BLE001
        p95 = P95_FALLBACK
    state["p95"], state["p95_year"] = p95, now.year
    return p95

def fmt_local(t):
    try:
        from zoneinfo import ZoneInfo
        t = t.astimezone(ZoneInfo("America/Los_Angeles"))
    except Exception:  # noqa: BLE001
        t = t.astimezone(timezone(timedelta(hours=-8)))
    return t.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")

def _smtp_send(subject, body):
    to = os.environ.get("ALERT_TO", "hpmatech@gmail.com")
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pw):
        print("[dry-run: no GMAIL_USER/GMAIL_APP_PASSWORD] would send:\n" + subject + "\n" + body)
        return False
    msg = EmailMessage(); msg["From"] = user; msg["To"] = to; msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ssl.create_default_context()); s.login(user, pw); s.send_message(msg)
    print(f"sent to {to}: {subject}")
    return True

def send(events, p95, source, test=False):
    lead = events[0]
    subject = ("[TEST] " if test else "") + f"Indian Cove alert: surge + high tide {lead['total']:.1f} ft {fmt_local(lead['t'])}"
    lines = [f"  {fmt_local(e['t'])}  ->  {e['total']:.1f} ft   (NOAA {e['h']:.1f} + surge {e['surge']:+.1f} ft)"
             for e in events]
    body = (("*** THIS IS A TEST of the surge-alert email. The numbers below are made up; "
             "no real event is happening. ***\n\n" if test else "")
            + "Storm surge is coinciding with a high tide at Indian Cove Marina.\n\n"
            + "\n".join(lines)
            + f"\n\nSurge source: {source}.\n"
            + f"Trips the alert when a high >= {p95:.1f} ft (year's 95th percentile) with surge >= {SURGE_MAJOR} ft\n"
            + "-- the same up-triangle + dagger the board shows.\n\n"
            + "Check it live:\n"
            + f"  Marina board:  {BOARD_URL}\n"
            + f"  NOAA Tacoma:   {NOAA_TACOMA_URL}\n\n"
            + "Heights are NOAA prediction + surge, MLLW. Verify against NOAA/NWS before acting.\n")
    return _smtp_send(subject, body)

def send_nws(alerts):
    lead = alerts[0]
    subject = f"Indian Cove: NWS {lead['event']}"
    lines = [f"  {a['event']}: {a['headline']}" for a in alerts]
    body = ("NWS has issued a coastal-flood product for our marine zone (Puget Sound / Hood Canal).\n"
            "This is the official, earliest heads-up; our own surge+tide alert follows if the water\n"
            "is forecast to cross the local threshold.\n\n"
            + "\n".join(lines)
            + "\n\nCheck it live:\n"
            + f"  Marina board:  {BOARD_URL}\n"
            + f"  NOAA Tacoma:   {NOAA_TACOMA_URL}\n"
            + "  NWS zone:      https://www.weather.gov/zone/PZZ135\n")
    return _smtp_send(subject, body)

def main():
    now = datetime.now(timezone.utc)
    if os.environ.get("ALERT_TEST") == "true":     # one-click test from the Action (does not touch dedup state)
        demo = [{"t": now + timedelta(hours=6), "h": 14.2, "surge": 1.8, "total": 16.0}]
        ok = send(demo, 15.2, "persistence (TEST)", test=True)
        print("test email:", "sent" if ok else "dry-run (GMAIL_* secrets missing)")
        return
    state = {}
    if os.path.exists(STATE):
        try: state = json.load(open(STATE))
        except Exception: state = {}  # noqa: BLE001

    # surge source: multi-day pressure/wind forecast if published, else live persistence
    surge_fn, lead_days = load_surge_forecast()
    if surge_fn:
        lookahead = 72        # 3-day lead where the pressure forecast still has skill
        source = f"pressure/wind forecast, ~{lead_days:g}-day series (anchored to live gauge)"
    else:
        try:
            residual = current_residual() or 0.0
        except Exception as exc:  # noqa: BLE001
            print(f"surge_alert: residual fetch failed ({exc})"); residual = 0.0
        surge_fn = lambda t: surge_at(t, residual, now)
        lookahead = 36
        source = f"live Tacoma residual {residual:+.1f} ft, carried forward (~12 h)"

    p95 = p95_high(now, state)
    try:
        pr = noaa(product="predictions", station=DP, begin_date=now.strftime("%Y%m%d"),
                  end_date=(now + timedelta(hours=lookahead)).strftime("%Y%m%d"),
                  datum="MLLW", interval="hilo")["predictions"]
    except Exception as exc:  # noqa: BLE001
        print(f"surge_alert: predictions fetch failed ({exc})"); pr = []
    highs = [{"t": _t(p["t"]), "h": float(p["v"])} for p in pr
             if p["type"] == "H" and now < _t(p["t"]) <= now + timedelta(hours=lookahead)]
    events = find_events(highs, surge_fn, p95)
    print(f"surge@now {surge_fn(now):+.1f} ft | p95 {p95:.1f} ft | {len(highs)} highs to +{lookahead}h "
          f"| {len(events)} qualifying | {source}")

    last = state.get("last_alerted_high_t")
    fresh = [e for e in events if last is None or e["t"].isoformat() > last]
    if fresh:
        send(fresh, p95, source)
        state["last_alerted_high_t"] = max(e["t"] for e in fresh).isoformat()

    # Part C: NWS coastal-flood watch/warning/advisory -- earliest official lead
    nws = nws_coastal_flood(MC.get("nws_zone"))
    seen = set(state.get("nws_alerted_ids", []))
    new_nws = [a for a in nws if a["id"] not in seen]
    if new_nws:
        send_nws(new_nws)
        state["nws_alerted_ids"] = (list(seen) + [a["id"] for a in new_nws])[-30:]
    if nws:
        print(f"NWS coastal-flood active: {[a['event'] for a in nws]} ({len(new_nws)} new)")

    json.dump(state, open(STATE, "w"), indent=2)

if __name__ == "__main__":
    main()

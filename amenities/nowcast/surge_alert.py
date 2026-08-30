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

def find_events(highs, residual, p95, now):
    """Upcoming highs that trip the marker. Pure -> unit-testable. highs: [{t,h}]."""
    out = []
    for e in highs:
        s = surge_at(e["t"], residual, now)
        total = e["h"] + s
        if total >= p95 and s >= SURGE_MAJOR:
            out.append({"t": e["t"], "h": e["h"], "surge": round(s, 2), "total": round(total, 2)})
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

def send(events, p95, residual, test=False):
    to = os.environ.get("ALERT_TO", "hpmatech@gmail.com")
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    lead = events[0]
    subject = ("[TEST] " if test else "") + f"Indian Cove alert: surge + high tide {lead['total']:.1f} ft {fmt_local(lead['t'])}"
    lines = [f"  {fmt_local(e['t'])}  ->  {e['total']:.1f} ft   (NOAA {e['h']:.1f} + surge {e['surge']:+.1f} ft)"
             for e in events]
    body = (("*** THIS IS A TEST of the surge-alert email. The numbers below are made up; "
             "no real event is happening. ***\n\n" if test else "")
            + "Storm surge is coinciding with a high tide at Indian Cove Marina.\n\n"
            + "\n".join(lines)
            + f"\n\nCurrent surge (Tacoma residual): {residual:+.1f} ft, carried forward.\n"
            + f"Trips the alert when a high >= {p95:.1f} ft (year's 95th percentile) with surge >= {SURGE_MAJOR} ft\n"
            + "-- the same up-triangle + dagger the board shows.\n\n"
            + "Check it live:\n"
            + f"  Marina board:  {BOARD_URL}\n"
            + f"  NOAA Tacoma:   {NOAA_TACOMA_URL}\n\n"
            + "Heights are NOAA prediction + live surge, MLLW. Short lead time (same tide cycle);\n"
            + "surge is persistence-based. Verify against NOAA/NWS before acting.\n")
    if not (user and pw):
        print("[dry-run: no GMAIL_USER/GMAIL_APP_PASSWORD] would send:\n" + subject + "\n" + body)
        return False
    msg = EmailMessage(); msg["From"] = user; msg["To"] = to; msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ssl.create_default_context()); s.login(user, pw); s.send_message(msg)
    print(f"sent surge alert to {to}: {subject}")
    return True

def main():
    now = datetime.now(timezone.utc)
    if os.environ.get("ALERT_TEST") == "true":     # one-click test from the Action (does not touch dedup state)
        demo = [{"t": now + timedelta(hours=6), "h": 14.2, "surge": 1.8, "total": 16.0}]
        ok = send(demo, 15.2, 1.8, test=True)
        print("test email:", "sent" if ok else "dry-run (GMAIL_* secrets missing)")
        return
    state = {}
    if os.path.exists(STATE):
        try: state = json.load(open(STATE))
        except Exception: state = {}  # noqa: BLE001
    try:
        residual = current_residual()
    except Exception as exc:  # noqa: BLE001
        print(f"surge_alert: NOAA fetch failed ({exc})"); return
    if residual is None:
        print("surge_alert: no live water level"); return
    p95 = p95_high(now, state)
    pr = noaa(product="predictions", station=DP, begin_date=now.strftime("%Y%m%d"),
              end_date=(now + timedelta(hours=LOOKAHEAD_H)).strftime("%Y%m%d"),
              datum="MLLW", interval="hilo")["predictions"]
    highs = [{"t": _t(p["t"]), "h": float(p["v"])} for p in pr
             if p["type"] == "H" and now < _t(p["t"]) <= now + timedelta(hours=LOOKAHEAD_H)]
    events = find_events(highs, residual, p95, now)
    print(f"surge {residual:+.1f} ft | p95 {p95:.1f} ft | {len(highs)} highs ahead | {len(events)} qualifying")

    last = state.get("last_alerted_high_t")
    fresh = [e for e in events if last is None or e["t"].isoformat() > last]
    if fresh:
        send(fresh, p95, residual)
        state["last_alerted_high_t"] = max(e["t"] for e in fresh).isoformat()
    json.dump(state, open(STATE, "w"), indent=2)

if __name__ == "__main__":
    main()

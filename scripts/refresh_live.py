"""Refresh live/order.json (Tankathon projected draft order) and live/records.json (ESPN standings).

Run daily by .github/workflows/refresh-live.yml. Writes a file only when its data changed, and only after
validating it, so a Tankathon redesign or an ESPN outage leaves the last good copy in place.
Standard library only.
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent / "live"
TEAMS = set("ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WAS".split())
FIX = {"WSH": "WAS"}
# Tankathon keeps adjusting the order through the playoffs and pick trades until the draft
LAST_DAY = dt.date(2027, 5, 1)
RECORDS_LAST_DAY = dt.date(2027, 1, 13)  # end of the 2026 regular season


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (draftcraftpod.com mock draft refresh)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def parse_tankathon(html):
    picks = []
    for rnd, block in enumerate(re.split(r'class="round-title"', html)[1:], start=1):
        for no, body in re.findall(r'<tr><td class="pick-number">(\d+)</td>(.*?)</tr>', block, flags=re.S):
            logos = [FIX.get(c.upper(), c.upper()) for c in re.findall(r"/nfl/([a-z]+)\.svg", body)]
            if not logos:
                raise ValueError(f"pick {no}: no team logo found")
            picks.append([int(no), rnd, logos[0], logos[1] if len(logos) > 1 else logos[0]])
    if len(picks) != 224:
        raise ValueError(f"expected 224 picks, got {len(picks)}")
    for r in range(1, 8):
        rows = [p for p in picks if p[1] == r]
        if len(rows) != 32 or {p[3] for p in rows} != TEAMS or not {p[2] for p in rows} <= TEAMS:
            raise ValueError(f"round {r} is not 32 picks with every team once")
    if [p[0] for p in picks] != sorted(p[0] for p in picks):
        raise ValueError("pick numbers are out of order")
    return picks


def parse_espn(text):
    teams = {}

    def walk(node):
        for child in node.get("children", []):
            walk(child)
        for e in node.get("standings", {}).get("entries", []):
            stats = {s["name"]: s.get("value") for s in e["stats"]}
            code = FIX.get(e["team"]["abbreviation"], e["team"]["abbreviation"])
            teams[code] = [int(stats.get(k) or 0) for k in ("wins", "losses", "ties")]

    walk(json.loads(text))
    if set(teams) != TEAMS or not all(0 <= n <= 20 for rec in teams.values() for n in rec):
        raise ValueError(f"unexpected standings: {sorted(teams)}")
    return teams


def update(name, key, value, source):
    path = LIVE / name
    old = json.loads(path.read_text()) if path.exists() else {}
    if old.get(key) == value:
        print(f"{name}: unchanged")
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps({"asOf": stamp, "source": source, key: value}, separators=(",", ":")) + "\n")
    print(f"{name}: updated")


def main():
    today = dt.date.today()
    if today > LAST_DAY:
        print("Past the 2027 draft; nothing to refresh.")
        return 0
    failed = False
    try:
        update("order.json", "picks", parse_tankathon(fetch("https://www.tankathon.com/nfl/full-draft")), "Tankathon")
    except Exception as e:  # keep the last good order
        print(f"order.json: skipped ({e})")
        failed = True
    if today <= RECORDS_LAST_DAY:
        try:
            update("records.json", "teams", parse_espn(fetch("https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season=2026")), "ESPN")
        except Exception as e:
            print(f"records.json: skipped ({e})")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

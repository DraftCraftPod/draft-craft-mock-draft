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
# Compensatory picks: until the NFL awards them (usually early March), Tankathon shows OverTheCap's projections and the
# site marks them "projected" (they can't be traded). Set COMP_AWARDED = True the day the NFL announces them; failing
# that, they count as awarded from COMP_AWARDED_BY.
COMP_AWARDED = False
COMP_AWARDED_BY = dt.date(2027, 3, 20)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (draftcraftpod.com mock draft refresh)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def parse_tankathon(html):
    """Returns (picks, comp): the 224 regular picks and the compensatory picks, each [no, round, owner, original team]."""
    picks, comp = [], []
    for rnd, block in enumerate(re.split(r'class="round-title"', html)[1:], start=1):
        for no, tag, body in re.findall(r'<tr><td class="pick-number">(\d+)(<span.*?</span>)?</td>(.*?)</tr>', block, flags=re.S):
            logos = [FIX.get(c.upper(), c.upper()) for c in re.findall(r"/nfl/([a-z]+)\.svg", body)]
            if not logos:
                raise ValueError(f"pick {no}: no team logo found")
            row = [int(no), rnd, logos[0], logos[1] if len(logos) > 1 else logos[0]]
            if "Compensatory" in tag:
                comp.append(row)
            elif tag:
                raise ValueError(f"pick {no}: unknown marker {tag[:80]}")
            else:
                picks.append(row)
    if len(picks) != 224:
        raise ValueError(f"expected 224 picks, got {len(picks)}")
    for r in range(1, 8):
        rows = [p for p in picks if p[1] == r]
        if len(rows) != 32 or {p[3] for p in rows} != TEAMS or not {p[2] for p in rows} <= TEAMS:
            raise ValueError(f"round {r} is not 32 picks with every team once")
    if [p[0] for p in picks] != sorted(p[0] for p in picks):
        raise ValueError("pick numbers are out of order")
    if len(comp) > 40 or any(p[1] < 3 or not {p[2], p[3]} <= TEAMS for p in comp):
        raise ValueError(f"unexpected compensatory picks: {comp[:5]}")
    every = sorted(picks + comp)
    if len({p[0] for p in every}) != len(every) or [p[1] for p in every] != sorted(p[1] for p in every):
        raise ValueError("compensatory pick numbers collide or fall outside their round")
    return picks, comp


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


def update(name, key, value, source, extra=None):
    path = LIVE / name
    old = json.loads(path.read_text()) if path.exists() else {}
    extra = extra or {}
    if old.get(key) == value and all(old.get(k) == v for k, v in extra.items()):
        print(f"{name}: unchanged")
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps({"asOf": stamp, "source": source, key: value, **extra}, separators=(",", ":")) + "\n")
    print(f"{name}: updated")


def main():
    today = dt.date.today()
    if today > LAST_DAY:
        print("Past the 2027 draft; nothing to refresh.")
        return 0
    failed = False
    try:
        picks, comp = parse_tankathon(fetch("https://www.tankathon.com/nfl/full-draft"))
        awarded = COMP_AWARDED or today >= COMP_AWARDED_BY
        update("order.json", "picks", picks, "Tankathon", {"comp": comp, "compAwarded": awarded})
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

"""Refresh live/boards.json from Dan's and JP's Google Sheets big boards.

Run daily by .github/workflows/refresh-live.yml. Each sheet is published to the web as CSV (2027 tab).
Columns are found by header name, so the sheet layout can change: OR/Overall/Rank/B (board), Player/Name or First Name + Last Name,
POS/Pos., optional School/College/University, optional PR (position rank).

Players are matched to the General board (data/prospects/board.json, the page's BOARD) by name, so they keep
height, weight and class. Players nobody could match are listed in the GitHub run summary to fix spellings.
Standard library only.
"""
import csv
import difflib
import io
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "live"
BOARD = json.loads((ROOT / "data/prospects/board.json").read_text())
# Height, weight and class for sheet players who aren't on the General board, keyed like norm(name)
EXTRA = {k: v for k, v in json.loads((ROOT / "data/prospects/extra.json").read_text()).items() if not k.startswith("_")}

# One entry per board. "csv" is the sheet's File > Share > Publish to web link (CSV, the 2027 tab).
# "credit" and "link" are shown with the board on the site: who made it, and where to find them (https only).
# Keys are short lowercase ids; "dan" and "jp" together also make the Draft Craft Combined board.
SHEETS = {
    "dan": {"label": "Dan's board", "credit": "Dan, Draft Craft podcast", "link": "https://www.draftcraftpod.com",
            "csv": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRW-Z8YnL-PfFLpZ0T01ZfeEz_BHpwZDYSw50zxOzuaB3x-SSr5byinrAmdOcDjUY5pYTvD_7dAOnT7/pub?gid=845914004&single=true&output=csv"},
    "jp": {"label": "JP's board", "credit": "JP, Draft Craft podcast", "link": "https://www.draftcraftpod.com",
           "csv": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRA96EEUTsvqFa_KVlU5u5osmWiVDwytnwDXb3FKZvpcnkmw6c7XtAXBsO5thRL13UopFEUQcBEaRMY/pub?gid=1120011587&single=true&output=csv"},
    # Guest board example:
    # "smith": {"label": "Sam Smith's board", "credit": "Sam Smith, The Draft Show", "link": "https://example.com", "csv": "<published CSV link>"},
}

POSITIONS = {"QB", "RB", "WR", "TE", "OT", "IOL", "EDGE", "IDL", "LB", "CB", "S", "K", "P"}
POS_ALIASES = {"ER": "EDGE", "DE": "EDGE", "EDGE": "EDGE", "DL": "IDL", "DT": "IDL", "NT": "IDL", "G": "IOL", "OG": "IOL",
               "C": "IOL", "OC": "IOL", "OL": "OT", "T": "OT", "OLB": "LB", "ILB": "LB", "MLB": "LB", "DB": "CB",
               "FS": "S", "SS": "S", "HB": "RB"}
# Sheet school names include mascots ("Ohio State Buckeyes"). Two-word mascots are listed; otherwise the last word
# is the mascot. SCHOOL_FIX then maps full names and typos to the short names the General board uses.
TWO_WORD_MASCOTS = {"Crimson Tide", "Sun Devils", "Red Wolves", "Black Knights", "Golden Bears", "Blue Hens", "Blue Devils",
                    "Yellow Jackets", "Rainbow Warriors", "Fighting Illini", "Fighting Irish", "Golden Flashes",
                    "Ragin' Cajuns", "Thundering Herd", "Blue Raiders", "Golden Gophers", "Wolf Pack", "Mean Green",
                    "Nittany Lions", "Scarlet Knights", "Golden Eagles", "Horned Frogs", "Red Raiders", "Green Wave",
                    "Golden Hurricanes", "Golden Hurricane", "Demon Deacons", "Powder Puff"}
SCHOOL_FIX = {"California Los Angeles": "UCLA", "Southern California": "USC", "Louisiana State": "LSU",
              "Texas Christian": "TCU", "Southern Methodist": "SMU", "Brigham Young": "BYU", "Bringham Young": "BYU",
              "Central Florida": "UCF", "Miami": "Miami (FL)", "Miami (OH)": "Miami (OH)", "Pittsburgh": "Pitt",
              "North Carolina State": "NC State", "California": "Cal", "Washignton": "Washington",
              "Iowa Stae": "Iowa State", "Nevada Las Vegas": "UNLV", "Connecticut": "UConn", "Massachusetts": "UMass",
              "Alabama at Birmingham": "UAB", "Texas at El Paso": "UTEP", "Texas at San Antonio": "UTSA",
              "Louisiana Monroe": "ULM", "Florida International": "FIU", "Florida Atlantic": "FAU", "Hawai'i": "Hawaii",
              "Powder Puff": "—"}
# Sheet spellings that differ from the official roster, mapped to the official name (matched ignoring case and punctuation)
NAME_FIX = {
    "Trent Frailey": "Trent Fraley",
    "Dylan Labarbara": "Dylan LaBarbera",
    "Michael Killbane": "Michael Kilbane",
    "Dwayne McDougall III": "Dwayne McDougle III",
    "Kenyon Augurs": "Kenyon Agurs",
    "Tre'Quon Feggins": "Tre'Quon Fegans",
    "Dorian Flemming": "Dorian Fleming",
    "McHale Boley": "McKale Boley",
    "Mekhi Flowers": "Mehki Flowers",
    "Gideon Lampron": "Gideon ESPN Lampron",  # yes, really
}
# Rows sharing one OR value this many times or more are the sheet's "not ranked yet" bucket, not a tie
UNRANKED_BUCKET = 6
# Overall rank column names, in order of preference ("B" is JP's board column)
RANK_COLS = ("or", "overall", "rank", "b", "board")


def norm(name):
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", name.lower())
    return re.sub(r"[^a-z]", "", name)


NAME_FIX = {norm(k): v for k, v in NAME_FIX.items()}

GENERAL = {}
for i, b in enumerate(BOARD):
    GENERAL.setdefault(norm(b[0]), i)


def match_general(name, pos, school):
    """Exact name match, else a close spelling (Sammy/Samuel, Whitt/Whit) at the same school and position."""
    n = norm(name)
    if n in GENERAL:
        return GENERAL[n]
    best, score = None, 0.0
    for i, b in enumerate(BOARD):
        if b[2] != school or (pos and b[1] != pos):
            continue
        r = difflib.SequenceMatcher(None, n, norm(b[0])).ratio()
        if r > score:
            best, score = i, r
    return best if score >= 0.75 else None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mock draft board refresh)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig", "ignore")


def short_school(s):
    s = " ".join(s.split())
    if not s:
        return "—"
    if s in SCHOOL_FIX:
        return SCHOOL_FIX[s]
    words = s.split()
    base = " ".join(words[:-2]) if " ".join(words[-2:]) in TWO_WORD_MASCOTS else " ".join(words[:-1])
    if base.endswith(" Golden") or base.endswith(" Mean"):  # mascots not in the list above
        base = base.rsplit(" ", 1)[0]
    base = base or s
    return SCHOOL_FIX.get(base, base)


def find_header(rows):
    for n, row in enumerate(rows[:10]):
        cells = [c.strip().lower() for c in row]
        if any(c in RANK_COLS for c in cells) and any(c in ("pos", "pos.", "position") for c in cells):
            return n, cells
    raise ValueError("no header row with OR/Overall/Rank/B and POS found")


def col(cells, *names, contains=None):
    for n in names:
        if n in cells:
            return cells.index(n)
    if contains:
        for i, c in enumerate(cells):
            if contains in c:
                return i
    return None


def parse_board(text):
    rows = list(csv.reader(io.StringIO(text)))
    hn, cells = find_header(rows)
    c_or = col(cells, *RANK_COLS)
    c_pos = col(cells, "pos.", "pos", "position")
    c_pr = col(cells, "pr", "pos rank", "position rank")
    c_name, c_first, c_last = col(cells, "player", "name"), col(cells, "first name"), col(cells, "last name")
    c_school = col(cells, "school", "college", contains="university")
    if c_name is None and (c_first is None or c_last is None):
        raise ValueError("no Player or First Name + Last Name columns")

    get = lambda r, c: r[c].strip() if c is not None and c < len(r) else ""
    entries, seen = [], set()
    for n, r in enumerate(rows[hn + 1:]):
        name = get(r, c_name) if c_name is not None else f"{get(r, c_first)} {get(r, c_last)}"
        name = " ".join(name.split())
        name = NAME_FIX.get(norm(name), name)
        if not name or norm(name) in seen:
            continue
        seen.add(norm(name))
        try:
            overall = float(get(r, c_or))
        except ValueError:
            overall = None
        raw = get(r, c_pos).upper()
        pos = POS_ALIASES.get(raw, raw)
        pos = pos if pos in POSITIONS else None
        school = short_school(get(r, c_school))
        g = match_general(name, pos, school)
        if not pos:
            pos = BOARD[g][1] if g is not None else None
        pr = get(r, c_pr)
        entries.append({"row": n, "or": overall, "name": name, "pos": pos, "school": school,
                        "pr": int(pr) if pr.isdigit() else None, "g": g})

    bucket = {v for v, k in Counter(e["or"] for e in entries if e["or"] is not None).items() if k >= UNRANKED_BUCKET}
    ranked = sorted((e for e in entries if e["or"] is not None and e["or"] not in bucket), key=lambda e: (e["or"], e["row"]))
    others = [e for e in entries if e not in ranked]
    # A position rank repeated within a position (JP gives every unranked RB "20") is a fill-in, not a rank (unranked players only)
    pr_count = Counter((e["pos"], e["pr"]) for e in others if e["pr"] is not None)
    for e in others:
        if pr_count[(e["pos"], e["pr"])] >= 3:
            e["pr"] = None
    if len(ranked) < 40:
        raise ValueError(f"only {len(ranked)} ranked players")
    skipped = [e["name"] for e in ranked + others if not e["pos"]]
    def player(e, rank):
        p = {"key": norm(e["name"]), "name": e["name"], "pos": e["pos"], "school": e["school"], "rank": rank, "posRank": e["pr"], "g": e["g"]}
        if e["g"] is None and p["key"] in EXTRA:
            p.update({k: EXTRA[p["key"]][k] for k in ("ht", "wt", "cls") if k in EXTRA[p["key"]]})
        return p
    players = [player(e, rank) for rank, e in enumerate([e for e in ranked if e["pos"]], start=1)]
    players += [player(e, None) for e in others if e["pos"]]
    return players, skipped


def main():
    out_path = LIVE / "boards.json"
    old = json.loads(out_path.read_text()) if out_path.exists() else {"boards": {}}
    boards, failed, report = dict(old.get("boards", {})), False, []
    for key, cfg in SHEETS.items():
        label = cfg["label"]
        try:
            players, skipped = parse_board(fetch(cfg["csv"]))
        except Exception as e:  # keep the last good copy of this board
            print(f"{label}: skipped ({e})")
            failed = True
            continue
        ranked = [p for p in players if p["rank"]]
        missing = [p for p in ranked if p["g"] is None and "ht" not in p]
        print(f"{label}: {len(ranked)} ranked, {len(players) - len(ranked)} unranked, {len(missing)} ranked players not on the General board")
        report.append(f"### {label}\n{len(ranked)} ranked players, {len(players) - len(ranked)} listed without an overall rank.\n")
        if missing:
            report.append("Ranked players not found on the General board (shown without height/weight; fix the spelling if one should match):\n")
            report += [f"- #{p['rank']} {p['name']} ({p['pos']}, {p['school']})" for p in missing]
        if skipped:
            report.append("\nSkipped, no usable position: " + ", ".join(skipped))
        report.append("")
        entry = {"label": label, "credit": cfg.get("credit", ""), "link": cfg.get("link", ""), "players": players}
        if boards.get(key) != entry:
            boards[key] = entry
    boards = {k: v for k, v in boards.items() if k in SHEETS}
    if boards != old.get("boards"):
        import datetime as dt
        out_path.write_text(json.dumps({"asOf": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "boards": boards}, separators=(",", ":")))
        print("boards.json updated")
    else:
        print("boards.json unchanged")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Big boards\n" + "\n".join(report) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

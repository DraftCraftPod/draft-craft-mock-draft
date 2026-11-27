"""Copy Dan's and JP's big boards (live/boards.json) to the Big Board page on draftcraftpod.com.

Run daily by .github/workflows/refresh-live.yml, right after scripts/refresh_boards.py. The page lists the Webflow
CMS collection "Board Rankings" (one item per player per board); this script makes those items match the sheets:

- the top BOARD_SIZE players of each board (32 early in the season, 64 or 100 later; change BOARD_SIZE below)
- players new to the site get a Prospects item (name, school, position, height, weight); players already there get
  their name, school and position corrected to match the sheets
- each row's "+/-" shows how far the player moved since the board last changed (▲3, ▼2, NEW, –), and the board's
  header says "Updated <date>" with the day the change was picked up
- players who fell off the top BOARD_SIZE are removed from that board; grades and notes on remaining rows are kept

Movement is worked out from the full sheet ranking (so a player who climbs from #40 to #30 shows ▲10 when the board
grows past 32). live/site-boards.json keeps the ranking the site last showed and the movement worked out from it.

Needs WEBFLOW_TOKEN (a Webflow site API token with CMS read and write access) in the environment; without it the
script does nothing. `--dry-run` prints what would change without writing anything. Standard library only.
"""
import datetime as dt
import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# How many players each board shows on the site: 32 early in the season, then 64 or 100 (the page lists up to 100).
BOARD_SIZE = 64

SITE_BOARDS = {  # boards.json key -> the Webflow Boards item it fills, and the name used in item titles
    "dan": {"board": "6a1e5a6974e5b73c5aca552d", "who": "Dan"},
    "jp": {"board": "6a1e5a88d6193b350829182a", "who": "JP"},
}
RANKINGS = "6a1f5074049e4fed98642527"   # Board Rankings collection
PROSPECTS = "6a1e53158a264ca9d252ec38"  # Prospects collection
BOARDS = "6a1e5a4779f7626c6c321c21"     # Boards collection
POSITIONS = "6a1e422d00e8b73f96581849"  # Positions collection
DRAFT_YEAR = 2027
SITE_POS = {"EDGE": "ER", "IDL": "DL"}  # the site's position names where they differ from the sheets'

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "live"
STATE = LIVE / "site-boards.json"
GENERAL = json.loads((ROOT / "data/prospects/board.json").read_text())  # [name, pos, school, ht, wt, class, ...]
API = "https://api.webflow.com/v2"
DRY = "--dry-run" in sys.argv


def norm(name):
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", (name or "").lower())
    return re.sub(r"[^a-z]", "", name)


def letters(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def slugify(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


class Webflow:
    def __init__(self, token):
        self.token, self.calls = token, 0

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(6):
            r = urllib.request.Request(API + path, data=data, method=method, headers={
                "Authorization": f"Bearer {self.token}", "accept": "application/json",
                "content-type": "application/json", "User-Agent": "draft-craft-board-sync"})
            try:
                self.calls += 1
                with urllib.request.urlopen(r, timeout=60) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:  # rate limit (60 a minute) or a hiccup: wait and retry
                    time.sleep(int(e.headers.get("Retry-After") or 0) or 5 * (attempt + 1))
                    continue
                raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode(errors='replace')[:500]}") from None
        raise RuntimeError(f"{method} {path}: still failing after retries")

    def items(self, cid):
        out, offset = [], 0
        while True:
            page = self.req("GET", f"/collections/{cid}/items?limit=100&offset={offset}")
            out += page.get("items", [])
            offset += 100
            if offset >= page.get("pagination", {}).get("total", 0):
                return out

    def create(self, cid, field_data):
        return self.req("POST", f"/collections/{cid}/items", {"isDraft": False, "isArchived": False, "fieldData": field_data})

    def update(self, cid, updates):  # [(id, fieldData)]
        for i in range(0, len(updates), 100):
            chunk = [{"id": iid, "isDraft": False, "fieldData": fd} for iid, fd in updates[i:i + 100]]
            self.req("PATCH", f"/collections/{cid}/items", {"items": chunk})

    def publish(self, cid, ids):
        ids = list(dict.fromkeys(ids))
        for i in range(0, len(ids), 100):
            self.req("POST", f"/collections/{cid}/items/publish", {"itemIds": ids[i:i + 100]})

    def delete(self, cid, ids):
        for i in range(0, len(ids), 100):
            chunk = [{"id": x} for x in ids[i:i + 100]]
            try:  # take it off the live site, then delete it
                self.req("DELETE", f"/collections/{cid}/items/live", {"items": chunk})
            except RuntimeError as e:
                print(f"  (unpublish failed, deleting anyway: {e})")
            self.req("DELETE", f"/collections/{cid}/items", {"items": chunk})


def height(p):
    inches = p.get("ht") or (GENERAL[p["g"]][3] if p.get("g") is not None else None)
    return f"{inches // 12}'{inches % 12}\"" if isinstance(inches, int) and inches > 0 else None


def weight(p):
    w = p.get("wt") or (GENERAL[p["g"]][4] if p.get("g") is not None else None)
    return w if isinstance(w, int) and w > 0 else None


def movement(prev, rank):
    if prev is None:
        return "NEW", "new"
    if prev > rank:
        return f"▲{prev - rank}", "up"
    if prev < rank:
        return f"▼{rank - prev}", "down"
    return "–", "same"


class Prospects:
    """The site's Prospects, matched to sheet players by name (or a close spelling at the same school or position)."""

    def __init__(self, items):
        self.slugs = {it["fieldData"].get("slug") for it in items}  # archived items keep their slugs too
        self.items = {it["id"]: it for it in items if not it.get("isArchived")}
        self.by_name = {}
        for it in self.items.values():
            self.by_name.setdefault(norm(it["fieldData"].get("name")), it["id"])
        self.taken = set()

    def find(self, p, pos_id):
        key = norm(p["name"])
        if key in self.by_name and self.by_name[key] not in self.taken:
            return self.by_name[key]
        best, best_score = None, 0.0
        for iid, it in self.items.items():
            if iid in self.taken:
                continue
            fd = it["fieldData"]
            score = difflib.SequenceMatcher(None, key, norm(fd.get("name"))).ratio()
            same_place = letters(fd.get("school")) == letters(p["school"]) or (pos_id and fd.get("position") == pos_id)
            if score >= 0.88 and same_place and score > best_score:
                best, best_score = iid, score
        return best


def main():
    token = os.environ.get("WEBFLOW_TOKEN", "").strip()
    if not token:
        print("WEBFLOW_TOKEN not set: Big Board page not synced")
        return 0
    wf = Webflow(token)
    boards = json.loads((LIVE / "boards.json").read_text())["boards"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).date()  # US Eastern (close enough for a date)
    updated_label = f"Updated {today.strftime('%B')} {today.day}"

    positions = {it["fieldData"]["name"]: it["id"] for it in wf.items(POSITIONS)}
    prospects = Prospects(wf.items(PROSPECTS))
    rankings = wf.items(RANKINGS)
    report, failed = [], False

    for key, cfg in SITE_BOARDS.items():
        board = boards.get(key)
        if not board:
            print(f"{cfg['who']}: not in boards.json, skipped")
            continue
        ranked = sorted([p for p in board["players"] if p.get("rank")], key=lambda p: p["rank"])
        if len(ranked) < 20:
            print(f"{cfg['who']}: only {len(ranked)} ranked players, skipped")
            failed = True
            continue
        ranks = {p["key"]: p["rank"] for p in ranked}
        items = [it for it in rankings if it["fieldData"].get("board") == cfg["board"] and not it.get("isArchived")]
        row_slugs = {it["fieldData"].get("slug") for it in rankings}
        by_prospect = {}  # prospect id -> its rows on this board, best rank first (extra copies get removed)
        for it in sorted(items, key=lambda it: it["fieldData"].get("rank") or 999):
            by_prospect.setdefault(it["fieldData"].get("prospect"), []).append(it)

        # Movement since the board last changed: prev holds the full ranking from before that change.
        # The first run has no saved ranking, so it compares with the ranks the site showed until now.
        st = state.get(key)
        first = st is None
        changed = first or st.get("ranks") != ranks
        if changed:
            st = {"ranks": ranks, "prev": {} if first else st["ranks"], "updated": updated_label}
        label = st["updated"]

        top = ranked[:BOARD_SIZE]
        prospects.taken = set()  # one prospect per row on this board (both boards share prospects)
        creates, updates, keep, prospect_updates = [], [], set(), []
        for p in top:
            site_pos = SITE_POS.get(p["pos"], p["pos"])
            pos_id = positions.get(site_pos)
            pid = prospects.find(p, pos_id)
            if pid:
                fd = prospects.items[pid]["fieldData"]
                want = {"name": p["name"], "school": p["school"]}
                if pos_id:
                    want["position"] = pos_id
                if fd.get("draft-year") != DRAFT_YEAR:
                    want["draft-year"] = DRAFT_YEAR
                diff = {k: v for k, v in want.items() if fd.get(k) != v}
                if not fd.get("height") and height(p):
                    diff["height"] = height(p)
                if not fd.get("weight") and weight(p):
                    diff["weight"] = weight(p)
                if diff:
                    prospect_updates.append((pid, diff, fd.get("name")))
                    fd.update(diff)
            else:
                fd = {"name": p["name"], "school": p["school"], "draft-year": DRAFT_YEAR}
                if pos_id:
                    fd["position"] = pos_id
                if height(p):
                    fd["height"] = height(p)
                if weight(p):
                    fd["weight"] = weight(p)
                slug, n = slugify(p["name"]), 2
                while slug in prospects.slugs:
                    slug, n = f"{slugify(p['name'])}-{n}", n + 1
                fd["slug"] = slug
                prospects.slugs.add(slug)
                if DRY:
                    pid = f"new:{slug}"
                else:
                    pid = wf.create(PROSPECTS, fd)["id"]
                prospects.items[pid] = {"id": pid, "fieldData": fd}
                report.append(f"- New prospect: {p['name']} ({site_pos}, {p['school']})")
            prospects.taken.add(pid)

            if first:  # the rank the site showed for this prospect
                old = by_prospect.get(pid)
                if old and old[0]["fieldData"].get("rank"):
                    st["prev"][p["key"]] = old[0]["fieldData"]["rank"]
            prev_rank = st["prev"].get(p["key"])
            move, kind = movement(prev_rank, p["rank"])
            want = {"name": f"{cfg['who']} #{p['rank']} - {p['name']}", "rank": p["rank"], "board": cfg["board"],
                    "prospect": pid, "position-label": site_pos, "previous-rank": prev_rank, "movement": move,
                    "movement-type": kind, "board-updated": label}
            old = by_prospect.get(pid)
            if old:
                it = old[0]
                keep.add(it["id"])
                diff = {k: v for k, v in want.items() if it["fieldData"].get(k) != v}
                if diff:
                    updates.append((it["id"], diff))
            else:
                slug, n = f"{key}-{slugify(p['name'])}", 2
                while slug in row_slugs:
                    slug, n = f"{key}-{slugify(p['name'])}-{n}", n + 1
                row_slugs.add(slug)
                want["slug"] = slug
                creates.append(want)

        state[key] = st

        removes = [it["id"] for it in items if it["id"] not in keep]
        moved = [p for p in top if st["prev"].get(p["key"]) not in (None, p["rank"])]
        print(f"{cfg['who']}: top {len(top)}, board {'changed' if changed else 'unchanged'} ({label}); "
              f"{len(creates)} rows to add, {len(updates)} to update, {len(removes)} to remove, "
              f"{len(prospect_updates)} prospect fixes, {len(moved)} players moved")
        for pid, diff, was in prospect_updates:
            shown = {k: v for k, v in diff.items() if k in ("name", "school", "position")}
            if "position" in shown:
                shown["position"] = next((n for n, i in positions.items() if i == shown["position"]), shown["position"])
            if shown:
                report.append(f"- {was}: " + ", ".join(f"{k} → {v}" for k, v in shown.items()))
        if DRY:
            for c in creates:
                print(f"  + #{c['rank']} {c['name']} {c['movement']}")
            for iid, diff in updates:
                print(f"  ~ {iid} {diff}")
            print(f"  - remove {len(removes)} rows")
            continue

        if prospect_updates:
            wf.update(PROSPECTS, [(pid, diff) for pid, diff, _ in prospect_updates])
        new_ids = [wf.create(RANKINGS, fd)["id"] for fd in creates]
        if updates:
            wf.update(RANKINGS, updates)
        touched_prospects = [pid for pid, _, _ in prospect_updates] + [
            pid for pid in prospects.taken if not prospects.items[pid].get("lastPublished")]
        if touched_prospects:
            wf.publish(PROSPECTS, touched_prospects)
        if new_ids or updates:
            wf.publish(RANKINGS, new_ids + [iid for iid, _ in updates])
        if removes:
            wf.delete(RANKINGS, removes)
        if changed:
            wf.update(BOARDS, [(cfg["board"], {"last-updated": f"{today.isoformat()}T12:00:00.000Z"})])
            wf.publish(BOARDS, [cfg["board"]])

    if not DRY:
        STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
    print(f"{wf.calls} Webflow API calls")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and report:
        with open(summary, "a") as f:
            f.write("## Big Board page\n" + "\n".join(dict.fromkeys(report)) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

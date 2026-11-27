# Draft Craft Mock Draft Simulator

The page is `mock-draft.html`, a single self-contained file published at
https://claude.ai/artifact/TfZHS4teYL5bJS6hzH9JXo (private until shared from the page's Share menu).

## Live data

The page reads two documents from its own data store, collection `standings`:

- `order`: Tankathon's projected 2027 draft order, all 7 rounds with traded picks
- `current`: ESPN team records

The scheduled task "Draft Craft mock draft: refresh order and records" used to update both from this Mac; it is
turned off (Oct 26, 2026) because the website's GitHub job is the main refresh now. The claude.ai copy only changes
when someone copies `live/*.json` into its data store. The page also contains a snapshot of both from Oct 24, 2026,
used when the live copy can't be read.

## data/

- `prospects/`: big board sources. `consensus.txt` is the NFL Mock Draft Database consensus top 100
  (Oct 24, 2026); `drafttek.txt` is DraftTek's board, ranks 1–410 (Oct 21, 2026). `merge.py` combines them
  into `board.json`, which is pasted into the page as `BOARD`.
- `trade-charts/`: the five pick value charts (Jimmy Johnson, Rich Hill, Fitzgerald-Spielberger,
  Harvard/Meers, Chase Stuart). `build.py` scales each to #1 = 1000 and averages them into `values.json`,
  which is pasted into the page as `VALUES`.
- `live-data/`: `tank_parse.py` turns a saved Tankathon full-draft page into the pick list; `seed.json` and
  `order_seed.json` are the records and order first saved to the page's data store.

Team needs come from NFL.com's 2027 draft order article (entering Week 7, 2026) and are written directly in the page.

## Website version (draftcraftpod.com/mock-draft)

`mock-draft.html` stays the one source. `python3 scripts/build_web.py` turns it into the website bundle:

- `dist/mock-draft.css`: every style scoped under `#dc-md`, so nothing leaks into the Webflow site.
  Headlines use the site's Sporty Pro (from its Adobe Fonts kit), with Bungee as the fallback.
- `dist/mock-draft.js`: the app, mounted into `<div id="dc-md">`. It reads live data from `live/*.json`.

Live data on the website:

- `live/order.json` (Tankathon) and `live/records.json` (ESPN) live in the GitHub repo.
- `.github/workflows/refresh-live.yml` runs `scripts/refresh_live.py` every day at 12:00 UTC on GitHub's
  servers (no computer needs to be on) and commits the files only when something changed. It keeps refreshing
  the order through the 2027 draft; records stop after the regular season.
- The page re-checks the files every 15 minutes while open.
- Compensatory picks: `order.json` also carries `comp` (Tankathon's comp picks, projected by OverTheCap until the NFL
  awards them) and `compAwarded`. Projected comp picks are drafted in the mock but can't be traded and draw no CPU
  offers; once awarded they're ordinary picks. Set `COMP_AWARDED = True` in `scripts/refresh_live.py` the day the
  NFL announces them (usually early March); otherwise they switch on `COMP_AWARDED_BY` (Mar 20, 2027).
- Pick values run to #262 so comp picks past #224 keep falling in value (`data/trade-charts/build.py` extends the
  charts that stop earlier).

Big boards (`live/boards.json`):

- `scripts/refresh_boards.py` (same daily job) reads Dan's and JP's Google Sheets, published to the web as CSV.
  The links are in `SHEETS` at the top of the script, each with a `credit` and `link` shown with the board on the
  site (in the picker, under the prospect list, and in player profiles). Guest boards are added the same way. Columns are found by header name (OR, First/Last Name or
  Player, Pos., College/School, PR), so the sheets can be rearranged.
- Rows that share one OR value six or more times (e.g. a "273" fill-in) count as listed but not ranked.
- Players are matched to the General board by name, or by a close spelling at the same school and position, to
  keep height, weight and class. The job's run page on GitHub (Actions → the run → Summary) lists ranked players
  it couldn't match. For a player who really isn't on the General board, add his height (inches), weight and class
  to `data/prospects/extra.json` (e.g. Scooter Jackson); he then shows them on every board and drops off that list.
- `NAME_FIX` in the script maps sheet spellings to the official roster name (e.g. Trent Frailey → Trent Fraley), so
  the site shows the official name whatever the sheet says.
- The page's Big board picker offers General, Dan's, JP's and Draft Craft Combined (average of the two ranks; a
  player only one of them ranked counts as just past the end of the other's list). After a board's ranked players
  it continues in General board order. Only boards that have loaded are offered.
- The board picked at setup is the one the computer drafts from. In the draft room, the prospect list's board menu
  shows any other board's ranks (the computer's rank sits under each number) without changing how the computer
  drafts. Players only another board lists join the pool at the bottom of the computer's board so they can be drafted.
  A pasted board can't be viewed alongside the others.

Big Board page (draftcraftpod.com/big-board):

- The page lists Webflow CMS "Board Rankings" items (one per player per board, linked to a Prospects item).
  `scripts/sync_webflow_boards.py` (same daily job, after `refresh_boards.py`) makes them match Dan's and JP's sheets:
  it adds prospects the site doesn't have yet, corrects names, schools and positions, re-ranks, and removes players
  who fell out of the top `BOARD_SIZE`. Grades and notes on rows that stay are kept. Archived items are left alone.
- `BOARD_SIZE` at the top of the script is how many players each board shows: 32 early in the season, then 64 or
  100 (the page lists up to 100).
- The "+/-" column shows each player's move since the board last changed (▲3, ▼2, NEW, –), from the full sheet
  ranking, and the header shows "Updated <date>" for the day the change was picked up. `live/site-boards.json` keeps
  the ranking the site shows and the one before it.
- It needs the repo secret `WEBFLOW_TOKEN`: a Webflow site API token (Site settings → Apps & integrations → API
  access) with CMS read and write. Without it the step does nothing. The run summary lists new prospects and fixes.
- The page's custom CSS and the script that fills in "Updated ..." are in `webflow/big-board-footer.html` (paste it
  into the page's Before </body> code if it's ever changed).
- Positions on the site use ER and DL where the sheets say EDGE and IDL.

Trade chart tab (next to Mock draft):

- Every 2027 pick in the current projected order with its value on the chosen chart; click a pick to add it to the trade.
- A two-team calculator with 2027 picks and each team's own 2028–2030 picks. "Match the other side" fills in the
  fewest picks worth 100–115% of the other side.
- "Shop a pick" lists each team's best offer to move up to a pick, using the CPU offer rules (`searchPackages`).
- "Copy link" gives a `#trade/...` link that opens the same trade on this tab.
- It doesn't touch the mock draft; switching to it pauses a running draft.

Everything is served by GitHub Pages from this repo, at https://draftcraftpod.github.io/draft-craft-mock-draft/
(`dist/` for the app, `live/` for the data). After changing the app, run the build and push; Pages republishes in
about a minute, and browsers may hold the old copy for up to 10 minutes.

### One-time setup

The repo is https://github.com/draftcraftpod/draft-craft-mock-draft (public, under the DraftCraftPod account).

1. Create the public repository and push this folder to it.
2. In the repo's Actions tab, run "Refresh live draft order and records" once to confirm it works.
3. In Webflow, create a page at `/mock-draft`, add a Code Embed element, and paste `webflow/embed.html`.
4. Make sure the site's Adobe Fonts kit (`lth2uit`) loads on that page (it does if it's in the site-wide head code).
5. Publish the site.

`webflow/test-page.html` mimics a Webflow page for local testing: serve this folder and open it.

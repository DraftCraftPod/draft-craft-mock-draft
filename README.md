# Draft Craft Mock Draft Simulator

The page is `mock-draft.html`, a single self-contained file published at
https://claude.ai/artifact/TfZHS4teYL5bJS6hzH9JXo (private until shared from the page's Share menu).

## Live data

The page reads two documents from its own data store, collection `standings`:

- `order`: Tankathon's projected 2027 draft order, all 7 rounds with traded picks
- `current`: ESPN team records

The scheduled task "Draft Craft mock draft: refresh order and records" updates both every day at about 8 AM
while the Claude app is open, and stops after the regular season ends (Jan 13, 2027).
The page also contains a snapshot of both from Oct 24, 2026, used when the live copy can't be read.

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

Files are served from GitHub: the JS/CSS through jsDelivr's CDN, the JSON straight from the repo.
After changing the app, run the build and push; jsDelivr can take up to 12 hours to pick up a new
`@main` version unless you purge it at `https://purge.jsdelivr.net/gh/draftcraftpod/draft-craft-mock-draft@main/dist/mock-draft.js`
(and the same for `.css`).

### One-time setup

The repo is https://github.com/draftcraftpod/draft-craft-mock-draft (public, under the DraftCraftPod account).

1. Create the public repository and push this folder to it.
2. In the repo's Actions tab, run "Refresh live draft order and records" once to confirm it works.
3. In Webflow, create a page at `/mock-draft`, add a Code Embed element, and paste `webflow/embed.html`.
4. Make sure the site's Adobe Fonts kit (`lth2uit`) loads on that page (it does if it's in the site-wide head code).
5. Publish the site.

`webflow/test-page.html` mimics a Webflow page for local testing: serve this folder and open it.

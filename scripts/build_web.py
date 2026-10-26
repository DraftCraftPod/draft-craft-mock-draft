"""Build the draftcraftpod.com version of the simulator from mock-draft.html.

mock-draft.html (the claude.ai artifact) stays the single source. This script turns it into:
  dist/mock-draft.css  every rule scoped under #dc-md so it can't touch the rest of the Webflow site
  dist/mock-draft.js   the app wrapped in one function that mounts into <div id="dc-md">, reading live
                       data from the JSON files in live/ instead of the claude.ai data store

Run from the project folder:  python3 scripts/build_web.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "mock-draft.html"
DIST = ROOT / "dist"
SCOPE = "#dc-md"

FONTS = "https://fonts.googleapis.com/css2?family=Bungee&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&family=Permanent+Marker&display=swap"

# The site already provides its own header and logo, so the app gets a slim title bar instead
MARKUP = """<div class="wrap">
  <header class="top">
    <div class="brand"><div><b><em>Mock</em> Draft</b><span>Simulator</span></div></div>
    <span class="tag" id="dcmd-fresh">Order as of Oct 24, 2026</span>
  </header>
  <main id="dcmd-app"></main>
</div>
<div id="dcmd-overlay"></div>"""

# Webflow's base styles set margins and weights on these tags; neutralize them inside the app
RESET = f"""
{SCOPE} {{ padding-left: 0; padding-right: 0; scroll-margin-top: 96px; }}
{SCOPE} p, {SCOPE} label, {SCOPE} ul {{ margin: 0; }}
{SCOPE} label {{ font-weight: inherit; }}
{SCOPE} img {{ vertical-align: middle; }}
{SCOPE} a {{ color: var(--field); }}
{SCOPE} .scrim {{ z-index: 2000; }}
{SCOPE} .drawer, {SCOPE} .sheet {{ z-index: 2001; }}
{SCOPE} .toast {{ z-index: 2002; }}
"""


def scope_selector(sel):
    sel = sel.strip()
    if sel in (":root", "body"):
        return SCOPE
    if sel == "*":
        return f"{SCOPE}, {SCOPE} *"
    return f"{SCOPE} {sel}"


def scope_rules(css):
    """Prefix every selector with the scope; recurse one level into @media blocks."""
    out, i = [], 0
    while i < len(css):
        brace = css.find("{", i)
        if brace == -1:
            break
        head = css[i:brace].strip()
        depth, j = 1, brace + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        body = css[brace + 1:j - 1]
        if head.startswith("@media"):
            out.append(f"{head} {{\n{scope_rules(body)}\n}}")
        else:
            sels = ", ".join(scope_selector(s) for s in head.split(","))
            out.append(f"{sels} {{{body}}}")
        i = j
    return "\n".join(out)


def build_css(html):
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # Sporty Pro comes from the site's Adobe Fonts kit; Bungee stays as the fallback
    css = css.replace('--display: "Bungee"', '--display: "sporty-pro", "Bungee"')
    return f'@import url("{FONTS}");\n' + scope_rules(css) + RESET


LIVE_LOADER = """// Live data: JSON files refreshed daily by the GitHub Action, at the URL given in data-live
const LIVE_BASE = root.dataset.live || "";
async function loadLive() {
  if (!LIVE_BASE) return;
  const get = name => fetch(LIVE_BASE + name, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).catch(() => null);
  const [order, records] = await Promise.all([get("order.json"), get("records.json")]);
  if (order) applyOrder(order);
  if (records) applyRecords(records);
}
loadLive();
setInterval(loadLive, 15 * 60 * 1000);"""


def build_js(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    swaps = [
        (re.compile(r"\(async \(\) => \{\n  const db = await window\.claude\?\.use\?\.\(\"db\"\);.*?\n\}\)\(\);", re.S), LIVE_LOADER),
        ('const app = document.getElementById("app"), overlay = document.getElementById("overlay");',
         'const app = root.querySelector("#dcmd-app"), overlay = root.querySelector("#dcmd-overlay");'),
        ('const el = document.getElementById("fresh");', 'const el = root.querySelector("#dcmd-fresh");'),
        ('document.querySelector(".toast")?.remove();', 'root.querySelector(".toast")?.remove();'),
        ("t.textContent = msg; document.body.append(t);", "t.textContent = msg; root.append(t);"),
        ("renderRoom(); window.scrollTo(0, 0);", 'renderRoom(); root.scrollIntoView({ block: "start" });'),
    ]
    for old, new in swaps:
        if isinstance(old, re.Pattern):
            js, n = old.subn(lambda _: new, js)
        else:
            n = js.count(old)
            js = js.replace(old, new)
        if n != 1:
            raise SystemExit(f"build_web: expected one match for {getattr(old, 'pattern', old)[:60]!r}, found {n}")
    head = ("/* Draft Craft Mock Draft Simulator, built from mock-draft.html by scripts/build_web.py. Do not edit by hand. */\n"
            "(() => {\n"
            'const root = document.getElementById("dc-md");\n'
            "if (!root || root.dataset.mounted) return;\n"
            'root.dataset.mounted = "1";\n'
            f"root.innerHTML = {MARKUP!r};\n")
    return head + js + "\n})();\n"


def main():
    html = SRC.read_text(encoding="utf-8")
    DIST.mkdir(exist_ok=True)
    (DIST / "mock-draft.css").write_text(build_css(html), encoding="utf-8")
    (DIST / "mock-draft.js").write_text(build_js(html), encoding="utf-8")
    for f in ("mock-draft.css", "mock-draft.js"):
        print(f"dist/{f}: {(DIST / f).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()

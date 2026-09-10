"""Screenshot the desk in readable pieces, for the project wiki.

Run it after a change to a screen, then copy wikishots/ into the wiki repo's
screens/ folder and push. The wiki is at
github.com/masalasev-ops/PremarketDesk/wiki and its pages reference these
filenames, so a new name needs a page edit and a changed picture does not.

ONE PICTURE PER SCREEN DOES NOT WORK. The Morning screen is 6,800 pixels tall;
a wiki scales an image to its content width, so the whole screen in one file
arrives as a thumbnail with three pixel text. These are sections instead, each
about a screenful, brought to the top of the window by shifting the body
rather than by scrolling, because a headless capture takes the viewport at
rest and a scroll may or may not have settled by then.

The theme is pinned to DARK and every fold is opened, so a rebuild a month
from now produces the same pictures. Dark because that is how this desk is
read, before seven in the morning, and because GitHub renders a wiki dark, so
a light screenshot sat on the page as a lit panel in a dark room.

REPLACING A PICTURE UNDER ITS OWN NAME IS NOT ENOUGH. GitHub caches wiki
assets by path and went on handing browsers the previous copy for a while
after the push, from the same URL that curl answered correctly. If a picture
has to change immediately rather than eventually, rename it and edit the page.
"""
import re
import subprocess
import tempfile
from pathlib import Path

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site" / "PremarketDesk.html"

# NOTHING IS WRITTEN INSIDE THE WORKING TREE. The suite photographs the whole
# tree before and after it runs and fails on any path it did not expect, and a
# tool that leaves fourteen PNGs and fourteen HTML copies beside the source is
# a tool nobody can run while anything else is happening.
HERE = Path(tempfile.gettempdir()) / "premarketdesk-wiki"
HERE.mkdir(parents=True, exist_ok=True)
OUT = HERE / "wikishots"
PROFILE = HERE / "cshot"

# name, route, css selector to bring to the top, window height
SHOTS = [
    ("morning-list", "", "#screen", 960),
    ("morning-card", "", ".deck", 760),
    ("morning-panels", "", ".deck-grid", 1180),
    ("morning-funnel", "", ".pipe", 620),
    ("morning-evidence", "", "#screen section:nth-of-type(4)", 760),
    ("first-hour", "session/2026-09-09/ladder", "#screen", 1180),
    ("similar", "session/2026-09-09/precedent", "#screen", 1080),
    ("midday", "session/2026-09-09/midday", "#screen", 980),
    ("record", "record", "#screen", 1180),
    ("record-conclusion", "record", "#screen section:nth-of-type(3)", 620),
    ("sessions", "sessions", "#screen", 820),
    ("health", "health/2026-09-09", "#screen", 1080),
    ("name", "name/ODD", "#screen", 900),
    ("report", "session/2026-09-09/report", "#screen", 1080),
]

OUT.mkdir(exist_ok=True)

page = SITE.read_text(encoding="utf-8")
light = re.sub(r"<html([^>]*)>", r'<html\1 data-theme="dark">', page, count=1)

TEMPLATE = """<script>
window.addEventListener("load", function () {
  setTimeout(function () {
    var folds = document.querySelectorAll("details");
    for (var i = 0; i < folds.length; i++) folds[i].open = true;
    setTimeout(function () {
      var el = document.querySelector(%s);
      if (!el) { document.title = "MISSING"; return; }
      var y = el.getBoundingClientRect().top + window.scrollY;
      /* the sticky header would otherwise sit over the section */
      var bar = document.querySelector(".bar");
      if (bar) bar.style.position = "static";
      document.body.style.marginTop = (-y + 12) + "px";
    }, 500);
  }, 1200);
});
</script>"""

for name, route, selector, height in SHOTS:
    src = HERE / f"shot_{name}.html"
    src.write_text(
        light.replace("</body>", TEMPLATE % repr(selector) + "</body>"),
        encoding="utf-8")
    shot = OUT / f"{name}.png"
    if shot.exists():
        shot.unlink()
    subprocess.run(
        [str(CHROME), "--headless", "--disable-gpu", "--no-sandbox",
         "--hide-scrollbars", "--force-device-scale-factor=2",
         f"--user-data-dir={PROFILE}", "--virtual-time-budget=22000",
         f"--window-size=1280,{height}", f"--screenshot={shot}",
         src.resolve().as_uri() + "#/" + route],
        capture_output=True, text=True, cwd=str(HERE))
    size = shot.stat().st_size if shot.exists() else 0
    print(f"{name:20s} {size // 1024:5d} KB   1280x{height}"
          f"{'   FAILED' if not size else ''}")

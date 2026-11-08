"""Screenshots of the running dashboard for the demo film (needs the local server on :8790 serving site/).
Run: .venv/Scripts/python.exe video/capture.py [--list]  -> video/assets/*.png"""
import pathlib, sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8790/"
OUT = pathlib.Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)
TABS = ["verdict", "machines", "demand", "plan", "model", "evidence"]
# shot name -> (tab, case-insensitive text inside the card's h2, or None for the page top)
SHOTS = {
    "verdict": ("verdict", None),
    "verdict-table": ("verdict", "bottom 10"),
    "funnel": ("machines", "luck funnel"),
    "hitrate": ("machines", "hit-rate"),
    "demand": ("demand", "b40-to-rest"),
    "model": ("model", "relative error"),
    "plan": ("plan", None),
    "plan-cards": ("plan", "allocates"),
    "evidence": ("evidence", None),
}

SCROLL = """(a) => { const h = [...document.querySelectorAll('#app h2')].find(e => e.textContent.toLowerCase().includes(a));
  if (!h) return null; const card = h.closest('.card') || h; const bar = document.querySelector('.filterbar, header');
  const off = bar ? bar.getBoundingClientRect().height + 12 : 80;
  window.scrollTo(0, card.getBoundingClientRect().top + window.scrollY - off); return h.textContent; }"""


def tab(pg, name):
    pg.click(f".tabbtn[data-tab='{name}']"); pg.wait_for_timeout(1500)
    pg.evaluate("window.scrollTo(0,0)"); pg.wait_for_timeout(300)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.25)
    pg.goto(URL); pg.wait_for_timeout(3000)
    if "--list" in sys.argv:
        for t in TABS:
            tab(pg, t)
            print(t, pg.evaluate("[...document.querySelectorAll('#app h2')].map(e=>e.textContent.slice(0,70))"))
        sys.exit()
    for name, (t, anchor) in SHOTS.items():
        tab(pg, t)
        if anchor:
            print(name, "->", pg.evaluate(SCROLL, anchor)); pg.wait_for_timeout(900)
        pg.screenshot(path=OUT / f"{name}.png")
    # drill-down: holdout period + one zone + one bank
    tab(pg, "machines")
    pg.click(".preset[data-preset='holdout']"); pg.wait_for_timeout(800)
    z = pg.evaluate("[...document.querySelectorAll('#zoneSel option')].map(o=>o.value).find(v=>/back|b40|forty/i.test(v)) || document.querySelectorAll('#zoneSel option')[1].value")
    pg.select_option("#zoneSel", z); pg.wait_for_timeout(800)
    bk = pg.evaluate("document.querySelectorAll('#bankSel option')[1]?.value")
    if bk:
        pg.select_option("#bankSel", bk); pg.wait_for_timeout(1200)
    pg.evaluate("window.scrollTo(0,0)"); pg.wait_for_timeout(300)
    pg.screenshot(path=OUT / "filtered.png")
    print("filtered", z, bk)
    b.close()
print("done", sorted(p.name for p in OUT.glob("*.png")))

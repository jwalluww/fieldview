"""Playwright check for the landscape EPL/MLS PitchView: no dot or name-pill intersections.
6 formations x 2 pages x 2 viewport sizes x sidebar closed/open. Also asserts the pitch is landscape, the right column is 360px,
and the page never scrolls. Needs `python -m http.server 8765` from the repo root.
Every team is checked (sidebar open only for the first). Screenshots (4-3-3 and 3-5-2, first team of each page, both sizes, sidebar open/closed) -> nfl/tests/screens/ (gitignored).
Usage: fieldview_env\\Scripts\\python.exe nfl/tests/check_pitch_overlap.py [base_url]
"""
import os, sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8765').rstrip('/')
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, 'screens'); os.makedirs(SHOTS, exist_ok=True)
FORMS = ['433', '442', '352', '343', '451', '532']
PAGES = {'epl': ('ARS', 'LIV'), 'mls': (None, None)}
fails = []


def check(cond, msg):
    if not cond:
        print('FAIL ' + msg); fails.append(msg)


JS = """() => {
  const R = e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const hit = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
  const cards = [...document.querySelectorAll('#playersLayer .player-card')];
  const dots = cards.map(c => R(c.querySelector('.player-dot'))), names = cards.map(c => { const n = c.querySelector('.player-name'); return n ? R(n) : null; });
  const ranks = cards.map(c => { const n = c.querySelector('.player-rank'); return n ? R(n) : null; });
  let d = 0, n = 0, o = 0;
  for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) {
    if (hit(dots[i], dots[j])) d++;
    if (names[i] && names[j] && hit(names[i], names[j])) n++;
    // a pill running into a neighbour's dot / rank label
    if (names[i] && hit(names[i], dots[j])) o++;
    if (names[j] && hit(names[j], dots[i])) o++;
    if (ranks[i] && ranks[j] && hit(ranks[i], ranks[j])) o++;
  }
  const cv = document.querySelector('.court-canvas').getBoundingClientRect(), cr = cv.right, cb = cv.bottom;
  let out = 0; cards.forEach(c => { const r = c.getBoundingClientRect(); if (r.left < cv.left - 1 || r.right > cr + 1 || r.top < cv.top - 1 || r.bottom > cb + 1) out++; });
  const side = document.querySelector('body.sb-open') ? document.getElementById('playerSidebar') : document.querySelector('.right-col');
  return { cards: cards.length, d, n, o, out, cw: cv.width, ch: cv.height, side: side.getBoundingClientRect().width,
           scroll: document.documentElement.scrollHeight - innerHeight, hscroll: document.documentElement.scrollWidth - innerWidth };
}"""

with sync_playwright() as pw:
    b = pw.chromium.launch()
    for league, (t1, t2) in PAGES.items():
        for (w, h) in [(1280, 900), (1920, 1080)]:
            page = b.new_page(viewport={'width': w, 'height': h})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)))
            page.goto(f'{BASE}/{league}/pitch-view.html')
            page.wait_for_selector('#playersLayer .player-card[data-pid]')
            teams = [x for x in page.evaluate("Object.keys(TEAMS)")]
            for tm in teams:
                if tm != teams[0]:
                    page.evaluate(f"selectTeam('{tm}')"); page.wait_for_timeout(250)
                for f in FORMS:
                    page.evaluate(f"setFormation('{f}')"); page.wait_for_timeout(120)
                    for open_ in ((False, True) if tm == teams[0] else (False,)):
                        if open_:
                            page.evaluate("document.querySelector('#playersLayer .player-card[data-pid]').click()")
                        else:
                            page.evaluate("closeSidebar()")
                        page.wait_for_timeout(100)
                        r = page.evaluate(JS)
                        tag = f'{league} {w}x{h} {f} sidebar={"open" if open_ else "closed"}'
                        check(r['d'] == 0, f'{tag}: {r["d"]} dot intersections')
                        check(r['n'] == 0, f'{tag}: {r["n"]} name-pill intersections')
                        check(r['o'] == 0, f'{tag}: {r["o"]} pill/dot/label collisions')
                        check(r['out'] == 0, f'{tag}: {r["out"]} cards outside the pitch')
                        check(r['cw'] > r['ch'], f'{tag}: pitch not landscape {r["cw"]}x{r["ch"]}')
                        check(abs(r['side'] - 360) < 1.5, f'{tag}: right column {r["side"]}px, expected 360')
                        check(r['scroll'] <= 1 and r['hscroll'] <= 1, f'{tag}: page scrolls ({r["scroll"]}, {r["hscroll"]})')
                        print(f'{"ok  " if all([r["d"]==0, r["n"]==0, r["o"]==0]) else "BAD "}{tag}: cards {r["cards"]} pitch {r["cw"]:.0f}x{r["ch"]:.0f}')
                        if f in ('433', '352') and tm == teams[0]:
                            page.screenshot(path=os.path.join(SHOTS, f'pitch_{league}_{tm}_{f}_{w}x{h}_{"open" if open_ else "closed"}.png'))
            check(not errs, f'{league} {w}x{h} page errors {errs}')
            page.close()
    b.close()

print('\nFAILS:', len(fails) if fails else 'none')
sys.exit(1 if fails else 0)

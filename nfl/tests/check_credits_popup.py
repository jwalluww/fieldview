"""Playwright check: the Credits & disclaimer popup on all six field views (needs `python -m http.server 8765`).
Opens via the header button; closes via Esc, the x button and a backdrop click; asserts no vertical page scroll at
1280x900 and 1920x1080 and that the footer is gone. Exit 1 on any failure."""
import sys
from playwright.sync_api import sync_playwright
BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8765').rstrip('/')
PAGES = ['nfl/nfl-formation-view.html', 'nba/court-view.html', 'mlb/diamond-view.html', 'nhl/ice-view.html',
         'epl/pitch-view.html', 'mls/pitch-view.html']
fails = []
with sync_playwright() as p:
    br = p.chromium.launch(); pg = br.new_page()
    for path in PAGES:
        for w, h in ((1280, 900), (1920, 1080)):
            pg.set_viewport_size({'width': w, 'height': h})
            pg.goto(f'{BASE}/{path}'); pg.wait_for_selector('#fvCreditsBtn'); pg.wait_for_timeout(1200)
            scroll = pg.evaluate('document.documentElement.scrollHeight - window.innerHeight')
            vis = pg.evaluate('(() => { const b = document.getElementById("fvCreditsBtn").getBoundingClientRect(); return b.right <= innerWidth && b.width > 0 && b.top >= 0 && b.bottom <= 60 })()')
            foot = pg.locator('.fv-footer').count()
            if scroll > 0 or foot or not vis: fails.append((path, w, 'scroll', scroll, 'footer', foot, 'btn-visible', vis))
        res = []
        for how in ('esc', 'x', 'backdrop'):
            pg.click('#fvCreditsBtn')
            opened = pg.locator('#fvCredits').count() == 1 and 'Not affiliated' in pg.inner_text('#fvCredits') and 'Privacy' in pg.inner_text('#fvCredits')
            if how == 'esc': pg.keyboard.press('Escape')
            elif how == 'x': pg.click('.fv-modal-x')
            else: pg.mouse.click(5, 5)
            closed = pg.locator('#fvCredits').count() == 0
            res.append(opened and closed)
        print(path, 'popup open/close esc,x,backdrop:', res)
        if not all(res): fails.append((path, 'popup', res))
    br.close()
print('FAILS:', fails or 'none')
sys.exit(1 if fails else 0)

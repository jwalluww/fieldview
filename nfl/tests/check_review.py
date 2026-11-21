"""Playwright check for nfl/review.html (run from the repo root with `python -m http.server 8765` up).
Real data, 1280x900 and 1920x1080: default week = latest, week switch, card expand/collapse, leader link opens
FormationView with the sidebar open, no page scroll (the grid scrolls inside), escapeHtml poisoning, credits link.
Screenshots go to nfl/tests/screens/review_* (gitignored).
Usage: fieldview_env\\Scripts\\python.exe nfl/tests/check_review.py [base_url]
"""
import json, os, sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8765').rstrip('/')
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'screens')
os.makedirs(SHOTS, exist_ok=True)
fails = []


def check(c, m):
    print(('PASS ' if c else 'FAIL ') + m)
    if not c:
        fails.append(m)


NOSCROLL = 'document.documentElement.scrollHeight <= innerHeight && document.body.scrollHeight <= innerHeight'

with sync_playwright() as pw:
    b = pw.chromium.launch()
    idx = json.load(open('nfl/data/review/index.json'))
    latest = idx['latest_week']
    n_latest = len(json.load(open(f'nfl/data/review/week_{idx["season"]}_{latest}.json', encoding='utf-8'))['games'])
    for (w, h) in [(1280, 900), (1920, 1080)]:
        page = b.new_page(viewport={'width': w, 'height': h})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(BASE + '/nfl/review.html')
        page.wait_for_selector('.game')
        check(page.input_value('#weekSel') == str(latest), f'{w}: default week is latest ({latest})')
        cap = page.inner_text('#caption')
        check(cap.startswith(f'Through Week {latest}, as of '), f'{w}: caption "{cap}"')
        check(page.locator('.game').count() == n_latest, f'{w}: {n_latest} game cards for the latest week')
        check(page.evaluate(NOSCROLL), f'{w}: no page scroll')
        page.screenshot(path=os.path.join(SHOTS, f'review_grid_{w}.png'))
        page.select_option('#weekSel', '3')
        page.wait_for_function('document.querySelectorAll(".game").length === 16')
        check(page.inner_text('#caption').startswith('Through Week 3'), f'{w}: week switch to 3 (16 games)')
        page.select_option('#weekSel', str(latest))
        page.wait_for_function(f'document.querySelectorAll(".game").length === {n_latest}')
        page.locator('.game-head').first.click()
        page.wait_for_selector('.game.open .detail')
        check(page.locator('.game.open .statrow').count() == 6, f'{w}: 6 team stat rows')
        check(page.locator('.game.open .leader').count() >= 6, f'{w}: leaders shown')
        check(page.locator('.game.open .play').count() >= 1, f'{w}: scoring plays shown')
        check(page.evaluate(NOSCROLL), f'{w}: no page scroll with a card open')
        page.screenshot(path=os.path.join(SHOTS, f'review_open_{w}.png'))
        page.locator('.game.open .game-head').click()
        check(page.locator('.game.open').count() == 0, f'{w}: collapse')
        page.locator('.game-head').first.click()
        link = page.locator('.game.open .leader a').first
        href = link.get_attribute('href')
        name = link.inner_text()
        with page.expect_navigation():
            link.click()
        page.wait_for_selector('#playersLayer .player-node')
        page.wait_for_timeout(1000)
        sb = page.evaluate("() => { const s = document.getElementById('playerSidebar'); "
                           "return s ? { open: getComputedStyle(s).display !== 'none' && s.innerText.trim().length > 0, "
                           "text: s.innerText.slice(0, 80) } : null }")
        print(f'     {name}: {href} -> sidebar {sb}')
        check('player=' in page.url and 'team=' in page.url, f'{w}: leader link {href}')
        check(bool(sb and sb['open'] and name.split()[-1].lower() in sb['text'].lower()),
              f'{w}: FormationView opened with {name} in the sidebar (on-field leader)')
        page.screenshot(path=os.path.join(SHOTS, f'review_link_{w}.png'))
        check(not errs, f'{w}: no page errors {errs}')
        page.close()

    page = b.new_page(viewport={'width': 1280, 'height': 900})
    page.goto(BASE + '/nfl/review.html?week=10')
    page.wait_for_selector('.game')
    page.locator('.hl-flag').first.click()
    page.wait_for_selector('.game.open .hl')
    a = page.locator('.game.open .hl').first
    check(a.get_attribute('target') == '_blank' and 'noopener' in a.get_attribute('rel'), 'highlight opens ESPN in a new tab with noopener')
    page.screenshot(path=os.path.join(SHOTS, 'review_highlight.png'))
    page.close()

    page = b.new_page(viewport={'width': 1280, 'height': 900})
    poison = '<img src=x onerror=window.__pwn=1>'
    page.route('**/data/review/week_2026_10.json', lambda r: r.fulfill(
        status=200, content_type='application/json',
        body=json.dumps({'season': 2026, 'week': 10, 'games': [{
            'id': 'x1', 'date': '2026-11-13T01:15Z', 'status': 'Final' + poison, 'venue': None,
            'home': {'team': 'NYG<b>', 'score': 1, 'winner': True, 'record': '1-0<i>', 'linescore': []},
            'away': {'team': 'WAS', 'score': 0, 'winner': False, 'record': '0-1', 'linescore': []},
            'team_stats': {'home': {}, 'away': {}},
            'leaders': [{'cat': 'pass', 'team': 'NYG<b>', 'name': poison, 'line': poison, 'player_id': None, 'pos': 'QB'}],
            'scoring_plays': [{'quarter': 1, 'clock': '1:00', 'team': 'WAS', 'text': poison, 'away': 0, 'home': 0}],
            'highlights': [{'title': poison, 'thumbnail': 'javascript:alert(1)', 'url': 'javascript:alert(1)'}]}]})))
    page.goto(BASE + '/nfl/review.html?week=10')
    page.wait_for_selector('.game')
    page.locator('.game-head').first.click()
    page.wait_for_timeout(300)
    check(page.evaluate('window.__pwn === undefined') and page.locator('.game img[src="x"]').count() == 0,
          'poisoned data renders as text (no injection)')
    check(page.locator('.hl').count() == 0, 'non-https highlight URL dropped')
    page.close()

    page = b.new_page(viewport={'width': 1280, 'height': 900})
    page.goto(BASE + '/nfl/review.html')
    page.wait_for_selector('.game')
    check(page.locator('header.header').get_by_text('Credits').count() >= 1, 'Credits & disclaimer link in header')
    b.close()
print('\nFAILS:', fails if fails else 'none')
sys.exit(1 if fails else 0)

"""Playwright check for the FormationView team-needs strip/panel and the draft Fit sort (run from the repo root,
with `python -m http.server 8765` up). Real data, 1280x900 and 1920x1080.

Asserts: the needs strip exists and is one line high; the page does not scroll; the panel opens/closes from the strip,
from the Draft panel and with Esc; drafting an EDGE onto a team with EDGE in its top 3 drops that score live; the Fit sort
reorders the board; the rookie sidebar shows "Replaces ..." and the need change. Prints the top-3 needs table (--table).
Screenshots go to nfl/tests/screens/ (gitignored).
Usage: fieldview_env\\Scripts\\python.exe nfl/tests/check_team_needs.py [--table] [base_url]
"""
import os, sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
BASE = (ARGS[0] if ARGS else 'http://localhost:8765').rstrip('/')
URL = BASE + '/nfl/nfl-formation-view.html'
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'screens')
os.makedirs(SHOTS, exist_ok=True)
fails = []


def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def load(page, team):
    page.goto(f'{URL}?team={team}')
    page.wait_for_selector('#playersLayer .player-node')
    page.wait_for_function('document.querySelectorAll("#needsChips .ns-chip").length === 3')


def top3(page):
    return page.evaluate("""() => { const n = getNeeds(); return n.ranked.slice(0, 3).map(g => [g, n.byGroup[g].score, n.byGroup[g].reason]); }""")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    for (w, h) in [(1280, 900), (1920, 1080)]:
        page = b.new_page(viewport={'width': w, 'height': h})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        tag = f'{w}x{h}'
        load(page, 'NYJ')
        box = page.evaluate("() => { const r = document.getElementById('needsStrip').getBoundingClientRect(); return [r.height, r.width, getComputedStyle(document.getElementById('needsStrip')).whiteSpace]; }")
        check(20 <= box[0] <= 34, f'{tag} needs strip is one line high ({box[0]:.0f}px)')
        check(page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1'), f'{tag} no page scroll (strip, panel closed)')
        page.wait_for_timeout(900)
        page.screenshot(path=os.path.join(SHOTS, f'needs_strip_{tag}.png'))

        # panel from the strip
        page.click('#needsStrip')
        page.wait_for_selector('#playerSidebar.open .nq-card')
        check(page.locator('#playerSidebar .nq-card').count() == 11, f'{tag} panel lists all 11 groups')
        check(page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1'), f'{tag} no page scroll (panel open)')
        check(page.evaluate("document.getElementById('needsStrip').getBoundingClientRect().height") < 34, f'{tag} strip still one line with the panel open')
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(SHOTS, f'needs_panel_{tag}.png'))
        page.keyboard.press('Escape')
        check(page.evaluate("!document.getElementById('playerSidebar').classList.contains('open')"), f'{tag} Esc closes the panel')
        # panel from the Draft panel
        page.click('#draftBtn'); page.click('#draftMenu button:has-text("Pick players")')
        page.wait_for_selector('#playerSidebar .nm-row')
        check(page.locator('#playerSidebar .nm-row').count() == 3, f'{tag} Draft panel shows the top 3 needs')
        page.click('#playerSidebar button:has-text("Team needs")')
        page.wait_for_selector('#playerSidebar .nq-card')
        check(True, f'{tag} Team needs button opens the panel from the Draft panel')
        page.click('#playerSidebar .sb-close')
        check(page.evaluate("!document.getElementById('playerSidebar').classList.contains('open')"), f'{tag} x closes the panel')
        # needs panel and player sidebar are mutually exclusive
        page.click('#needsStrip'); page.click('#playersLayer .player-node[data-pos="QB"]')
        check(page.evaluate('needsOpen === false && sidebarPos === "QB"'), f'{tag} player sidebar replaces the needs panel')
        page.keyboard.press('Escape')
        # sidebar toggle Off: strip + panel still work
        page.click('#sbToggle'); page.click('#needsStrip'); page.wait_for_selector('#playerSidebar .nq-card')
        check(True, f'{tag} panel opens with the sidebar toggle Off')
        page.click('#playerSidebar .sb-close'); page.click('#sbToggle')
        # hover highlight
        page.hover('.ns-chip')
        check(page.locator('#playersLayer .player-node.need-hl').count() >= 1, f'{tag} chip hover highlights on-field cards')
        page.mouse.move(5, 5)

        # drafting an EDGE drops EDGE need live
        load(page, 'NYJ')
        top = top3(page)
        print(f'  NYJ top 3: {top}')
        target = 'EDGE'
        before = page.evaluate(f"getNeeds().byGroup['{target}'].score")
        page.click('#draftBtn'); page.click('#draftMenu button:has-text("Pick players")')
        page.wait_for_selector('#playerSidebar .dp-pick')
        page.click('#playerSidebar .dp-pick >> nth=0')
        page.wait_for_selector('#playerSidebar .dp-row')
        # Fit sort reorders the board
        order_c = page.evaluate("[...document.querySelectorAll('#dpList .dp-nm')].slice(0, 12).map(e => e.textContent)")
        page.click('#playerSidebar .sort-toggle button:has-text("Fit")')
        order_f = page.evaluate("[...document.querySelectorAll('#dpList .dp-nm')].slice(0, 12).map(e => e.textContent)")
        fits = page.evaluate("[...document.querySelectorAll('#dpList .dp-fit')].slice(0, 12).map(e => Number(e.textContent))")
        check(order_c != order_f, f'{tag} Fit sort reorders the board')
        check(fits == sorted(fits, reverse=True), f'{tag} Fit sort is descending by fit ({fits[:6]}...)')
        check(page.evaluate("document.querySelectorAll('#dpList .dp-fit').length > 5"), f'{tag} every row carries a Fit badge')
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(SHOTS, f'needs_fit_{tag}.png'))
        page.click('#playerSidebar .sort-toggle button:has-text("Consensus")')
        page.select_option('#playerSidebar .dp-ctrls select', 'EDGE')
        page.click('#dpList .dp-row >> nth=0')
        slots = page.evaluate("[...document.querySelectorAll('#playersLayer .player-node.drop-target')].map(n => n.dataset.pos)")
        page.click(f'#playersLayer .player-node[data-pos="{slots[0]}"]')
        page.wait_for_selector('#playerSidebar .dp-pick.used')
        after = page.evaluate(f"getNeeds().byGroup['{target}'].score")
        check(after < before, f'{tag} drafting an EDGE drops EDGE need live ({before} -> {after})')
        page.click(f'#playersLayer .player-node[data-pos="{slots[0]}"]')
        page.wait_for_selector('#playerSidebar .sb-pill.proj')
        txt = page.inner_text('#playerSidebar')
        check('Replaces' in txt and 'EDGE need' in txt, f'{tag} rookie sidebar shows "Replaces..." and the need change')
        print('  ' + [l for l in txt.splitlines() if 'need' in l.lower() or 'Replaces' in l][0:3].__repr__())
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(SHOTS, f'needs_rookie_{tag}.png'))
        page.keyboard.press('Escape')
        # chips in the strip updated (EDGE tier / score) and no page error
        check(page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1'), f'{tag} no page scroll after drafting')
        # Reset clears manual subs only: hidden while the only change is a rookie, and it leaves the rookie in place
        reset, clear = page.locator('#resetStartersBtn'), page.locator('#clearDraftBtn')
        check(not reset.is_visible() and clear.is_visible(), f'{tag} rookies only: Reset hidden, Clear draft shown')
        starter = page.evaluate("getStarter('QB').id")
        page.click('#playersLayer .player-node[data-pos="QB"]')
        page.click('#playerSidebar .sb-sub >> nth=0')
        page.click('#playerSidebar button:has-text("Swap in")')
        check(page.evaluate("getStarter('QB').id") != starter and reset.is_visible(), f'{tag} a manual QB sub shows Reset')
        check(page.evaluate(f"getNeeds().byGroup['{target}'].score") == after, f'{tag} a manual sub does not change the EDGE need ({after})')
        reset.click()
        check(page.evaluate("getStarter('QB').id") == starter and not reset.is_visible(), f'{tag} Reset restores the QB and hides')
        check(page.evaluate(f"getStarter('{slots[0]}').isRookie === true && getNeeds().byGroup['{target}'].score") == after,
              f'{tag} Reset keeps the rookie (EDGE need stays {after})')
        # Clear draft (two-step) removes the rookie and recomputes
        clear.click()
        check(clear.inner_text().lower().startswith('confirm'), f'{tag} Clear draft asks to confirm')
        clear.click()
        check(page.evaluate(f"getNeeds().byGroup['{target}'].score") == before and not clear.is_visible(),
              f'{tag} Clear draft restores the EDGE need ({before})')
        check(not errs, f'{tag} no console/page errors {errs[:2]}')
        page.close()

    if '--table' in sys.argv:
        page = b.new_page(viewport={'width': 1920, 'height': 1080})
        load(page, 'BUF')
        teams = page.evaluate('Object.keys(TEAMS)')
        rows = {}
        for t in teams:
            load(page, t)
            rows[t] = top3(page)
        import json
        print('TABLE ' + json.dumps(rows))
    b.close()

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)

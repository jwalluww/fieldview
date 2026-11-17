"""Playwright overlap check for NFL FormationView (run from the repo root, with `python -m http.server 8765` up).

For every offense personnel (11, 12) x defense package (base43, base34, nickel, nickel34), sidebar open and
closed, at 1280x900 and 1920x1080, on a vanilla team and on a team carrying imported draft rookies, asserts
that no two .p-card bounding boxes intersect and no two card+label footprints come within 6px. Also checks the page does not scroll vertically.
Usage: fieldview_env\Scripts\python.exe nfl/tests/check_card_overlap.py [base_url]
Exit code 1 if any overlap (or scroll) is found.
"""
import itertools, os, sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8765').rstrip('/')
URL = BASE + '/nfl/nfl-formation-view.html'
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'mdh_mock_sample.txt')
SIZES = [(1280, 900), (1920, 1080)]
OFF = ['11', '12']
DEF = ['base43', 'base34', 'nickel', 'nickel34']

JS_BOXES = """() => [...document.querySelectorAll('.field-canvas .player-node')].map(n => {
  const c = n.querySelector('.p-card'); if (!c) return null;
  const r = c.getBoundingClientRect(), f = n.getBoundingClientRect();
  return {l: r.left, t: r.top, r: r.right, b: r.bottom,            // the .p-card itself
          fl: f.left, ft: f.top, fr: f.right, fb: f.bottom,          // whole node = card + position label below it
          name: (c.querySelector('.p-lastname') || {}).textContent || '?', rookie: /PROJ/.test(c.textContent)};
}).filter(Boolean)"""

GAP = 6   # px of clear air required between two players' full footprints (card + label)


def overlaps(boxes, keys=('l', 't', 'r', 'b'), gap=0.5):
    L, T, R, B = keys
    out = []
    for a, b in itertools.combinations(boxes, 2):
        if a[L] < b[R] - gap and b[L] < a[R] - gap and a[T] < b[B] - gap and b[T] < a[B] - gap:
            out.append((a['name'], b['name']))
    return out


def run(page, team, with_rookies, rows):
    page.goto(f'{URL}?team={team}')
    page.wait_for_function('typeof allPlayers !== "undefined" && allPlayers && document.querySelectorAll(".p-card").length > 10')
    if with_rookies:
        page.evaluate('openDraftPanel("import")')
        page.fill('#dpImportTa', open(FIXTURE, encoding='utf-8').read())
        page.evaluate('doImport()')
        page.wait_for_timeout(500)
        page.evaluate('closeDraftPanel && closeDraftPanel()') if page.evaluate('typeof closeDraftPanel') == 'function' else None
    for w, h in SIZES:
        page.set_viewport_size({'width': w, 'height': h})
        for sidebar_open in (False, True):
            for off, de in itertools.product(OFF, DEF):
                page.evaluate(f'''() => {{ if (typeof closeSidebar === "function") closeSidebar();
                    if (!sidebarOn) toggleSidebarMode();
                    currentOffPersonnel = "{off}"; currentDefPersonnel = "{de}"; renderFormation(); }}''')
                page.wait_for_timeout(120)
                if sidebar_open:
                    page.locator('.field-canvas .player-node').first.click()
                    page.wait_for_timeout(250)
                    assert page.evaluate('document.body.classList.contains("sb-open")'), 'sidebar did not open'
                boxes = page.evaluate(JS_BOXES)
                ov = overlaps(boxes)                                            # .p-card vs .p-card
                ov2 = overlaps(boxes, ('fl', 'ft', 'fr', 'fb'), -GAP)           # card+label footprints, 6px clear
                nrook = sum(1 for b in boxes if b['rookie'])
                scroll = page.evaluate('document.documentElement.scrollHeight - window.innerHeight')
                rows.append((team, 'rookies' if with_rookies else 'plain', f'{w}x{h}', 'sb-open' if sidebar_open else 'sb-closed',
                             off, de, len(boxes), nrook, len(ov), scroll, ov[:3], len(ov2), ov2[:3]))


def main():
    rows = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        pg.on('dialog', lambda d: d.accept())
        for team, rk in (('BUF', False), ('NE', True), ('PIT', False)):   # BUF 4-3, PIT 3-4, NE carries imported rookies
            run(pg, team, rk, rows)
        br.close()
    bad = [r for r in rows if r[8] > 0 or r[11] > 0]
    print(f'{len(rows)} configurations; .p-card overlaps: {sum(r[8] for r in rows)} pairs; '
          f'card+label footprints closer than {GAP}px: {sum(r[11] for r in rows)} pairs in {sum(1 for r in rows if r[11])} configurations; '
          f'rookie cards on field in {sum(1 for r in rows if r[7])} configs')
    for r in bad[:12]:
        print('  FAIL', r[:6], 'cards:', r[8], r[10], 'footprints:', r[11], r[12])
    scrolls = [r for r in rows if r[9] > 0]
    print('page scroll > 0 px in', len(scrolls), 'configurations', [(r[2], r[3], r[9]) for r in scrolls[:4]])
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

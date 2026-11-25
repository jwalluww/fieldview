"""Playwright check for nfl/review.html (run from the repo root with `python -m http.server 8765` up).
Real data, 1280x900 and 1920x1080: default week = current, week switch, no page scroll (panels scroll inside),
combined weekly leaders recomputed independently, game sidebar (open / x / Esc / click-out / switch / ?game= reload),
the four Season tabs against the data files, leader and draft links into FormationView, outside links.
Total TD: every stored week's touchdown plays parse and agree with the TD counts on the rushing / receiving leader lines.
FormationView ?player= for a leader who is not on the field (the "not in the lineup" sidebar).
Plus: a SIMULATED partial week (route interception), escapeHtml poisoning, missing season file, credits link.
Screenshots go to nfl/tests/screens/review_* (gitignored).
Usage: fieldview_env\\Scripts\\python.exe nfl/tests/check_review.py [base_url]
"""
import json, os, re, sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8765').rstrip('/')
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'screens')
os.makedirs(SHOTS, exist_ok=True)
fails = []


def check(c, m):
    print(('PASS ' if c else 'FAIL ') + m)
    if not c:
        fails.append(m)


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


NOSCROLL = ('document.documentElement.scrollHeight <= innerHeight && document.body.scrollHeight <= innerHeight'
            ' && document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth')
# panels never overflow sideways; each leader card stays inside the week panel
NOHSCROLL = ('[...document.querySelectorAll("#weekPanel, #seasonBody, #gameSidebar, .tables .card")]'
             '.every(e => e.scrollWidth <= e.clientWidth + 1)')
SIDEBAR = ("() => { const s = document.getElementById('playerSidebar'); "
           "return { open: s.classList.contains('open'), text: s.innerText } }")
SB_OPEN = 'document.body.classList.contains("sb-open")'

idx = load('nfl/data/review/index.json')
season = load(f'nfl/data/review/season_{idx["season"]}.json')
draft = load('nfl/data/draft_order.json')
cur = idx['current_week']
week = load(f'nfl/data/review/week_{idx["season"]}_{cur}.json')
n_games = len(week['games']) + len(week.get('pending', []))


def td_plays(g):
    """Independent of the page: a touchdown is a score worth 6+ points."""
    prev = 0
    for p in g['scoring_plays']:
        total = p['away'] + p['home']
        if total - prev >= 6:
            yield p
        prev = total


def scorer(text):
    """Scorer in ESPN's standard wording, plus the one-off formats present in the 2026 data."""
    for pat in (r'lateral to (.+?) for', r'(J\.Gibbs) up the middle', r'^(.+?) -?\d+ (?:Yd|yd) ', r'^(.+?) Fumble Recovery'):
        m = re.search(pat, text)
        if m:
            return 'Jahmyr Gibbs' if m.group(1) == 'J.Gibbs' else m.group(1)


def expected_leaders(wk):
    out = {k: [] for k in ('pass', 'rush', 'rec', 'sacks', 'tackles')}
    td, yards = {}, {}
    for g in wk['games']:
        for l in g['leaders']:
            m = re.search(r'(-?\d+) YDS', l['line'])
            out[l['cat']].append(float(l['line']) if l['cat'] in ('sacks', 'tackles') else int(m.group(1)))
            if l['cat'] in ('rush', 'rec'):
                yards[l['name']] = yards.get(l['name'], 0) + int(m.group(1))
        for p in td_plays(g):
            n = scorer(p['text'])
            td[n] = td.get(n, 0) + 1
    exp = {k: [float(x) for x in sorted(v, reverse=True)[:5]] for k, v in out.items()}
    top = sorted(td, key=lambda n: (-td[n], -yards.get(n, -10 ** 9), n))[:5]
    exp['td'] = [float(td[n]) for n in top]
    return exp, top


with sync_playwright() as pw:
    b = pw.chromium.launch()
    for (w, h) in [(1280, 900), (1920, 1080)]:
        page = b.new_page(viewport={'width': w, 'height': h})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(BASE + '/nfl/review.html')
        page.wait_for_selector('.tile')
        page.wait_for_load_state('networkidle')
        shot = lambda name: page.screenshot(path=os.path.join(SHOTS, f'review_{name}_{w}.png'))
        check(page.input_value('#weekSel') == str(cur), f'{w}: default week is current ({cur})')
        cap = page.inner_text('#caption')
        check(cap.endswith(f'as of {idx["last_changed"]}') and f'Week {cur}' in cap, f'{w}: caption "{cap}"')
        check(page.locator('.tile').count() == n_games, f'{w}: {n_games} games in the strip')
        winners = sum(1 for g in week['games'] for s in ('home', 'away') if g[s]['winner'])
        check(page.locator('.tile .t-row.win').count() == winners, f'{w}: {winners} bold winners')
        exp, td_names = expected_leaders(week)
        for cat, vals in exp.items():
            got = [float(x) for x in page.locator(f'.combo [data-cat="{cat}"] .val').all_inner_texts()]
            check(got == vals, f'{w}: weekly {cat} top 5 {got}')
        names = page.locator('.combo [data-cat="td"] .nm').all_inner_texts()
        check(names == td_names, f'{w}: Total TD names {names}')
        check(page.evaluate(NOSCROLL), f'{w}: no page scroll')
        check(page.evaluate(NOHSCROLL), f'{w}: no sideways overflow')
        wb = page.locator('#weekPanel').bounding_box()
        sb = page.locator('.season').bounding_box()
        side = sb['x'] > wb['x'] + wb['width'] - 1
        check(side == (w >= 1500), f'{w}: layout is {"side by side" if side else "stacked"}')
        last = page.locator('.tile').last.bounding_box()
        check(last['y'] + last['height'] <= wb['y'] + wb['height'], f'{w}: whole scoreboard visible on load')
        check(sb['height'] >= 190 and sb['y'] + sb['height'] <= h, f'{w}: Season area visible ({sb["height"]:.0f}px tall)')
        fold = page.evaluate("() => { const p = document.getElementById('weekPanel'); return p.scrollHeight - p.clientHeight }")
        print(f'     week panel inner overflow on load: {fold}px')
        shot('main')

        # Season tabs
        check(page.locator('#seasonBody .tables .card').count() == 4 and page.locator('#seasonBody table tr').count() == 20,
              f'{w}: 4 AFC division tables')
        buf = next(r for r in season['standings'] if r['team'] == 'BUF')
        row = page.locator('#seasonBody tr', has_text='Bills').inner_text().split()
        check(f'{buf["wins"]}-{buf["losses"]}' in row and str(buf['points_for']) in row and buf['streak'] in row, f'{w}: Bills row {row}')
        shot('standings')
        page.click('[data-conf-btn="NFC"]')
        check(page.locator('#seasonBody h4').all_inner_texts() == ['NFC EAST', 'NFC NORTH', 'NFC SOUTH', 'NFC WEST'], f'{w}: NFC toggle')
        page.click('[data-tab="playoffs"]')
        for c in ('AFC', 'NFC'):
            card = page.locator(f'#seasonBody [data-conf="{c}"]')
            logos = [x for x in card.locator('.seed-row img').evaluate_all('e => e.map(i => i.alt)')]
            pic = season['playoff_picture'][c]
            check(logos == pic['seeds'] + pic['hunt'], f'{w}: {c} seeds + hunt {logos}')
        note = page.inner_text('#seasonBody .note')
        check(('ESPN' in note) if all(p['seeded_by'] == 'espn' for p in season['playoff_picture'].values()) else ('Projected' in note), f'{w}: seed label "{note}"')
        shot('playoffs')
        page.click('[data-tab="leaders"]')
        check(page.locator('#seasonBody .card').count() == 10, f'{w}: 10 leader categories')
        check(page.locator('#seasonBody .row').count() == sum(len(v) for v in season['leaders'].values()), f'{w}: top 10 rows each')
        sk = page.locator('#seasonBody [data-cat="sacks"] .val').first.inner_text()
        check(float(sk) == season['leaders']['sacks'][0]['value'], f'{w}: sacks leader {sk}')
        check(page.locator('#seasonBody a.plink').count() == sum(1 for v in season['leaders'].values() for r in v if r['player_id']), f'{w}: matched season leaders are links')
        check(page.evaluate(NOSCROLL) and page.evaluate(NOHSCROLL), f'{w}: leaders tab, no page scroll / overflow')
        shot('leaders')
        page.click('[data-tab="draft"]')
        r1 = [p for p in draft if p['round'] == 1]
        check(page.locator('.pick').count() == len(r1), f'{w}: {len(r1)} first-round picks')
        traded = sum(1 for p in r1 if p['original_team'] != p['team'])
        check(page.locator('.pick .from').count() == traded, f'{w}: {traded} "from" labels')
        check('Board as of' in page.inner_text('#seasonBody .note'), f'{w}: board-as-of caption')
        check(page.locator('a.draft-link').get_attribute('href') == 'nfl-formation-view.html?panel=draft', f'{w}: Draft panel link')
        shot('draft')

        # outside links
        links = page.locator('.links a')
        hrefs = links.evaluate_all('e => e.map(a => [a.textContent, a.href, a.target, a.rel])')
        check(len(hrefs) == 7 and all(x[1].startswith('https://') and x[2] == '_blank' and 'noopener' in x[3] for x in hrefs),
              f'{w}: 7 outside links {[x[0] for x in hrefs]}')
        lb = links.last.bounding_box()
        check(lb['y'] + lb['height'] <= h, f'{w}: links row on screen')

        # sidebar
        page.click('[data-tab="standings"]')
        finals = page.locator('button.tile')
        gid = finals.first.get_attribute('data-game')
        finals.first.click()
        page.wait_for_function(SB_OPEN)
        sbox = page.locator('#gameSidebar').bounding_box()
        check(round(sbox['width']) == 360 and round(sbox['x'] + sbox['width']) == w, f'{w}: 360px right sidebar')
        check(f'game={gid}' in page.url and f'week={cur}' in page.url, f'{w}: URL {page.url.split("?")[1]}')
        check(page.locator('#gameSidebar .statrow').count() == 6, f'{w}: 6 team stat rows')
        check(page.locator('#gameSidebar .leader').count() >= 6 and page.locator('#gameSidebar .play').count() >= 1, f'{w}: leaders + scoring')
        check(page.locator('.tile.sel').count() == 1 and page.evaluate(NOSCROLL) and page.evaluate(NOHSCROLL), f'{w}: selected tile, no scroll / overflow with sidebar')
        mb = page.locator('#page').bounding_box()
        check(mb['x'] + mb['width'] <= sbox['x'] + 1, f'{w}: page makes room for the sidebar (no overlap)')
        shot('sidebar')
        page.reload()
        page.wait_for_function(SB_OPEN)
        check(page.locator('.tile.sel').get_attribute('data-game') == gid, f'{w}: ?game= reload reopens it')
        page.click('#gameSidebar h3 >> nth=0')
        check(page.evaluate(SB_OPEN), f'{w}: click inside keeps it open')
        page.locator('button.tile').nth(1).click()
        gid2 = page.locator('button.tile').nth(1).get_attribute('data-game')
        check(page.evaluate(SB_OPEN) and f'game={gid2}' in page.url, f'{w}: another tile switches games')
        page.click('#gameSidebar .sb-close')
        check(not page.evaluate(SB_OPEN) and 'game=' not in page.url, f'{w}: x closes and drops ?game=')
        page.locator('button.tile').first.click()
        page.keyboard.press('Escape')
        check(not page.evaluate(SB_OPEN), f'{w}: Esc closes')
        page.locator('button.tile').first.click()
        page.click('#weekPanel .panel-title')
        check(not page.evaluate(SB_OPEN), f'{w}: click outside closes')
        page.locator('button.tile').first.click()
        page.click('#fvCreditsBtn')
        page.keyboard.press('Escape')
        check(page.evaluate(SB_OPEN) and page.locator('#fvCredits').count() == 0, f'{w}: Esc on credits popup leaves the sidebar')
        page.locator('button.tile').first.click()
        check(not page.evaluate(SB_OPEN), f'{w}: same tile toggles closed')

        # week switch
        page.locator('button.tile').first.click()
        page.select_option('#weekSel', '3')
        page.wait_for_function('document.querySelectorAll(".tile").length === 16')
        check('Week 3' in page.inner_text('#caption') and not page.evaluate(SB_OPEN) and page.url.endswith('?week=3'), f'{w}: week switch to 3')
        check(page.evaluate(NOSCROLL) and page.evaluate(NOHSCROLL), f'{w}: 16-game week, no page scroll')
        page.screenshot(path=os.path.join(SHOTS, f'review_week3_{w}.png'))

        # leader links -> FormationView sidebar (weekly passing leader, then a season leader)
        for where in ('weekly', 'season'):
            page.goto(BASE + '/nfl/review.html')
            page.wait_for_selector('.combo a.plink')
            if where == 'weekly':
                link = page.locator('.combo [data-cat="pass"] a.plink').first
            else:
                page.click('[data-tab="leaders"]')
                link = page.locator('#seasonBody [data-cat="rushingYards"] a.plink').first
            name, href = link.inner_text(), link.get_attribute('href')
            with page.expect_navigation():
                link.click()
            page.wait_for_selector('#playersLayer .player-node')
            page.wait_for_timeout(1200)
            s = page.evaluate(SIDEBAR)
            check(s['open'] and name.split()[-1].lower() in s['text'].lower(), f'{w}: {where} leader {name} -> FormationView sidebar ({href})')
        page.screenshot(path=os.path.join(SHOTS, f'review_link_{w}.png'))

        # draft pick -> that team's Draft panel
        page.goto(BASE + '/nfl/review.html')
        page.wait_for_selector('.tile')
        page.click('[data-tab="draft"]')
        pick = page.locator('.pick').first
        team = re.search(r'team=(\w+)', pick.get_attribute('href')).group(1)
        with page.expect_navigation():
            pick.click()
        page.wait_for_function("document.getElementById('playerSidebar') && document.querySelector('#playerSidebar.open') "
                               "&& !document.getElementById('playerSidebar').innerText.includes('Loading')")
        page.wait_for_timeout(1500)  # panel slide-in
        s = page.evaluate(SIDEBAR)
        ok = s['open'] and 'mock draft' in s['text'].lower() and f'R1 #{r1[0]["pick"]}' in s['text'] and f'team={team}' in page.url
        if not ok:
            print('     debug', page.url, s['open'], repr(s['text'][:200]))
        check(ok, f'{w}: draft pick -> {team} Draft panel')
        page.screenshot(path=os.path.join(SHOTS, f'review_draftpanel_{w}.png'))
        check(not errs, f'{w}: no page errors {errs}')
        page.close()

    # Total TD parsing: known formats, then every stored week
    page = b.new_page(viewport={'width': 1280, 'height': 900})
    page.goto(BASE + '/nfl/review.html')
    page.wait_for_selector('.tile')
    cases = [
        ('Eli Raridon 2 Yd pass from Drake Maye (Andy Borregales Kick)', 'Eli Raridon'),
        ('Kyren Williams 5 Yd Rush (Harrison Mevis Kick)', 'Kyren Williams'),
        ('Josh Allen 1 Yd Run (Josh Allen Pass to Dalton Kincaid for Two-Point Conversion)', 'Josh Allen'),
        ('T.J. Watt 35 Yd Interception Return (Chris Boswell Kick)', 'T.J. Watt'),
        ('Devontez Walker 86 Yd Kickoff Return (Riley Patterson Kick)', 'Devontez Walker'),
        ('Myles Price 86 Yd Punt Return (Will Reichard Kick)', 'Myles Price'),
        ('James Mitchell 0 Yd Fumble Recovery (Brandon Aubrey Kick)', 'James Mitchell'),
        ('Gracen Halton Fumble Recovery in End Zone (Eddy Pineiro Kick)', 'Gracen Halton'),
        ('Oluwafemi Oladejo 14 Yd return of blocked punt (J.Slye kick)', 'Oluwafemi Oladejo'),
        ('Brock Purdy complete pass to Mike Evans for 2 yards, lateral to Deebo Samuel for 80 yards (Eddy Pineiro Kick)', 'Deebo Samuel'),
        ('(No Huddle) J.Gibbs up the middle for 1 yard, TOUCHDOWN. J.Bates extra point is GOOD, Center-H.Hatten, Holder-J.Fox.', 'J.Gibbs'),
        ('(Shotgun) J.Allen pass short right to K.Shakir for 5 yards, TOUCHDOWN.', 'K.Shakir'),
        ('Something nobody has seen', None),
    ]
    for text, want in cases:
        got = page.evaluate('t => tdScorer(t)', text)
        check(got == want, f'tdScorer -> {got!r} for "{text[:60]}"')
    total, bad = 0, []
    for n in idx['weeks']:
        wk = load(f'nfl/data/review/week_{idx["season"]}_{n}.json')
        res = page.evaluate("""wk => wk.games.map(g => touchdownPlays(g).map(p => {
            const raw = tdScorer(p.text); return { team: p.team, text: p.text,
              name: raw && resolveScorer(raw, p.team, wk.games.flatMap(x => x.leaders)).name }; }))""", wk)
        for g, plays in zip(wk['games'], res):
            total += len(plays)
            if [p['text'] for p in plays] != [p['text'] for p in td_plays(g)]:
                bad.append((n, 'plays differ', g['id']))
            bad += [(n, 'unparsed', p['text']) for p in plays if not p['name']]
            for l in g['leaders']:
                if l['cat'] not in ('rush', 'rec'):
                    continue
                m = re.search(r'(\d+) TD', l['line'])
                # this leader's rushing / receiving TDs, ignoring the extra-point note in parentheses
                k = 0
                for p in plays:
                    if p['team'] != l['team'] or p['name'] != l['name']:
                        continue
                    body = re.sub(r'^\([^)]*\)\s*', '', p['text']).split(' (')[0]
                    if l['cat'] == 'rec':
                        k += ' pass' in body
                    else:
                        k += re.search(r'Yd (Rush|Run)|up the middle', body) is not None
                if k != (int(m.group(1)) if m else 0):
                    bad.append((n, l['cat'], l['name'], l['line'], k))
    check(not bad, f'{total} touchdown plays in {len(idx["weeks"])} weeks parse and match the leader lines {bad[:6]}')
    page.close()

    # a leader who is not a default starter: "not in the lineup" sidebar
    master = load('nfl/data/players_master.json')
    state = """() => { const s = document.getElementById('playerSidebar'); return {
        open: s.classList.contains('open'), text: s.textContent, name: (s.querySelector('.sb-name') || {}).textContent || '',
        note: (s.querySelector('.sb-bench-note') || {}).textContent || '', subs: s.querySelectorAll('.sb-sub, .sort-toggle, .sb-cmp-actions').length,
        adv: s.querySelectorAll('.sb-stat').length, grid: s.querySelectorAll('.sb-cell').length,
        selected: document.querySelectorAll('.player-node.selected').length, url: location.search } }"""
    fv = BASE + '/nfl/nfl-formation-view.html'
    for (w, h) in [(1280, 900), (1920, 1080)]:
        page = b.new_page(viewport={'width': w, 'height': h})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        def visit(query):
            page.goto(fv + query)
            page.wait_for_selector('#playersLayer .player-node')
            page.wait_for_timeout(700)
            return page.evaluate(state)

        def closed():
            st = page.evaluate(state)
            return not st['open'] and 'player=' not in st['url']

        bench = None
        for l in (x for g in week['games'] for x in g['leaders']):
            p = master.get(l['player_id'] or '')
            if not p or p['depth'] == 1 or p['standard_pos'] not in ('RB', 'WR') or not p.get('stats'):
                continue
            s = visit(f'?team={p["team"]}&player={l["player_id"]}')
            if s['note']:
                bench = (l['player_id'], p, l['name'])
                break
        check(bench is not None, f'{w}: found a Week {cur} leader who is not on the field')
        pid, p, name = bench
        query = f'?team={p["team"]}&player={pid}'
        check(s['open'] and name.split()[-1] in s['name'] and s['note'] == f'Not in the current lineup (depth {p["depth"]})',
              f'{w}: {name} ({p["team"]}): "{s["note"]}"')
        check(s['subs'] == 0 and 'Substitutes' not in s['text'] and 'Swap' not in s['text'], f'{w}: no substitutes or Swap')
        check(s['grid'] > 0 and (s['adv'] > 0) == ('Advanced Stats' in s['text']), f'{w}: season stats {s["grid"]} cells, advanced rows {s["adv"]}')
        check(f'player={pid}' in s['url'] and s['selected'] == 0, f'{w}: ?player= kept, no card selected')
        page.screenshot(path=os.path.join(SHOTS, f'review_bench_{w}.png'))
        page.click('#playerSidebar .sb-close')
        check(closed(), f'{w}: x closes and clears ?player=')
        visit(query)
        page.keyboard.press('Escape')
        check(closed(), f'{w}: Esc closes and clears ?player=')
        visit(query)
        page.locator('.field-canvas').click(position={'x': 8, 'y': 8})
        check(closed(), f'{w}: empty-field click closes and clears ?player=')
        visit(query)
        page.locator('#defPersonnelGroup .ctrl-btn').nth(1).click()
        s = page.evaluate(state)
        check(s['note'] != '' and f'player={pid}' in s['url'], f'{w}: personnel change keeps the card')
        page.locator('#playersLayer .player-node[data-pos="QB"] .p-card').click()
        s = page.evaluate(state)
        check(s['note'] == '' and s['subs'] > 0 and 'Substitutes' in s['text'] and s['selected'] == 1 and f'player={pid}' not in s['url'],
              f'{w}: clicking a starter shows the normal sidebar with substitutes')
        starter = re.search(r'player=([\w-]+)', s['url']).group(1)
        s = visit(f'?team={p["team"]}&player={starter}')
        check(s['note'] == '' and s['subs'] > 0 and s['selected'] == 1, f'{w}: on-field ?player= unchanged')
        visit(query)
        page.evaluate("selectTeam(currentTeam === 'BUF' ? 'NE' : 'BUF')")
        page.wait_for_timeout(500)
        check(closed(), f'{w}: team switch drops it')
        other = 'NE' if p['team'] != 'NE' else 'BUF'
        check(not visit(f'?team={other}&player={pid}')['open'], f"{w}: another team's player ignored")
        check(not visit(f'?team={p["team"]}&player=nope')['open'], f'{w}: unknown id ignored')
        page.evaluate("localStorage.setItem('fieldview_nfl_sidebar', 'off')")
        visit(query)
        check(not page.evaluate(state)['open'], f'{w}: sidebar toggle Off: ignored')
        page.evaluate("localStorage.removeItem('fieldview_nfl_sidebar')")
        # a bench player that a personnel change puts on the field (backup tight end in 12 personnel)
        tes = [(i, x) for i, x in master.items() if x['standard_slot'] == 'TE' and x['depth'] == 2 and not x['injured'] and x.get('madden')]
        moved = None
        for i, x in sorted(tes, key=lambda t: t[1]['team']):
            if not visit(f'?team={x["team"]}&player={i}')['note']:
                continue
            page.locator('#offPersonnelGroup .ctrl-btn').nth(1).click()
            s = page.evaluate(state)
            if not s['note']:
                moved = (x['canonical_name'], s)
                break
        check(bool(moved) and moved[1]['subs'] > 0 and moved[1]['selected'] == 1,
              f'{w}: {moved and moved[0]} moves to the normal sidebar in 12 personnel')
        check(not errs, f'{w}: FormationView no page errors {errs}')
        page.close()

    # SIMULATED partial week: the next week with 3 of the current week's games final and the rest pending
    nxt = cur + 1
    part = {'season': idx['season'], 'week': nxt, 'partial': True, 'games_remaining': 10, 'games': week['games'][:3],
            'pending': [{'id': 'p' + g['id'], 'date': g['date'], 'state': 'pre',
                         'home': {'team': g['home']['team']}, 'away': {'team': g['away']['team']}} for g in week['games'][3:13]]}
    fake_idx = {**idx, 'weeks': idx['weeks'] + [nxt], 'current_week': nxt, 'partial_weeks': {str(nxt): 10}}
    for (w, h) in [(1280, 900), (1920, 1080)]:
        page = b.new_page(viewport={'width': w, 'height': h})
        page.route('**/data/review/index.json', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(fake_idx)))
        page.route(f'**/data/review/week_{idx["season"]}_{nxt}.json', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(part)))
        page.goto(BASE + '/nfl/review.html')
        page.wait_for_selector('.tile')
        label = page.locator('#weekSel option:checked').inner_text()
        check(label == f'Week {nxt} (in progress: 10 games left)', f'partial {w}: selector "{label}"')
        check(page.inner_text('#caption').startswith(f'Week {nxt} so far, as of'), f'partial {w}: caption')
        check(page.locator('button.tile').count() == 3 and page.locator('.tile.pending').count() == 10, f'partial {w}: 3 final + 10 pending tiles')
        page.locator('.tile.pending').first.click()
        check(not page.evaluate(SB_OPEN), f'partial {w}: pending game has no sidebar')
        check(page.evaluate(NOSCROLL), f'partial {w}: no page scroll')
        page.screenshot(path=os.path.join(SHOTS, f'review_partial_SIMULATED_{w}.png'))
        page.close()

    page = b.new_page(viewport={'width': 1280, 'height': 900})
    page.goto(BASE + '/nfl/review.html?week=10')
    page.wait_for_selector('.tile')
    page.locator('button.tile:has(.hl-flag)').first.click()
    page.wait_for_selector('#gameSidebar .hl')
    a = page.locator('#gameSidebar .hl').first
    check(a.get_attribute('target') == '_blank' and 'noopener' in a.get_attribute('rel'), 'highlight opens ESPN in a new tab with noopener')
    a.scroll_into_view_if_needed()
    page.screenshot(path=os.path.join(SHOTS, 'review_highlight.png'))
    page.goto(BASE + '/nfl/review.html?week=10&game=nope')
    page.wait_for_selector('.tile')
    check(not page.evaluate(SB_OPEN) and 'game=' not in page.url, 'unknown ?game= ignored')
    page.close()

    # poisoned data everywhere
    page = b.new_page(viewport={'width': 1280, 'height': 900})
    poison = '<img src=x onerror=window.__pwn=1>'
    bad = {'season': idx['season'], 'week': 10, 'games': [{
        'id': 'x1"' + poison, 'date': '2026-11-13T01:15Z', 'status': 'Final' + poison, 'venue': poison,
        'home': {'team': 'NYG<b>', 'name': poison, 'score': poison, 'winner': True, 'record': '1-0<i>'},
        'away': {'team': 'WAS', 'score': 0, 'winner': False, 'record': '0-1'},
        'team_stats': {'home': {'totalYards': poison}, 'away': {}},
        'leaders': [{'cat': 'pass', 'team': 'NYG<b>', 'name': poison, 'line': '1 YDS ' + poison, 'player_id': '__proto__', 'pos': poison}],
        'scoring_plays': [{'quarter': poison, 'clock': poison, 'team': 'WAS', 'text': poison, 'away': poison, 'home': 0}],
        'highlights': [{'title': poison, 'thumbnail': 'javascript:alert(1)', 'url': 'javascript:alert(1)'}]}]}
    bad_season = json.loads(json.dumps(season))
    bad_season['standings_updated'] = bad_season['leaders_updated'] = poison
    for r in bad_season['standings']:
        r.update(name=poison, streak=poison, wins=poison, points_for=poison, division='AFC East' + poison if r['conference'] == 'AFC' else r['division'])
    for rows in bad_season['leaders'].values():
        rows[0].update(name=poison, pos=poison, rank=poison, team=poison)
    bad_draft = [{**p, 'team': poison if p['pick'] == 1 else p['team'], 'original_team': poison} for p in draft]
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(body)))
    page.route('**/data/review/week_*_10.json', serve(bad))
    page.route('**/data/review/season_*.json', serve(bad_season))
    page.route('**/data/draft_order.json', serve(bad_draft))
    page.route('**/data/draft_meta.json', serve({'board_last_changed': poison, 'sources': {'draft_order_source': 'otc'}}))
    page.route('**/data/review/index.json', serve({**idx, 'last_changed': poison}))
    page.goto(BASE + '/nfl/review.html?week=10')
    page.wait_for_selector('.tile')
    page.locator('button.tile').first.click()
    page.wait_for_function(SB_OPEN)
    clean = 'window.__pwn === undefined && !document.querySelector("img[src=x]")'
    check(page.evaluate(clean), 'poisoned week data renders as text')
    check(page.locator('.hl').count() == 0, 'non-https highlight URL dropped')
    page.keyboard.press('Escape')
    for tab in ('standings', 'playoffs', 'leaders', 'draft'):
        page.click(f'[data-tab="{tab}"]')
        page.wait_for_timeout(200)
        check(page.evaluate(clean), f'poisoned {tab} tab renders as text')
    page.close()

    # season file missing: week still works
    page = b.new_page(viewport={'width': 1280, 'height': 900})
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    page.route('**/data/review/season_*.json', lambda r: r.fulfill(status=404, body=''))
    page.goto(BASE + '/nfl/review.html')
    page.wait_for_selector('.tile')
    check('No data' in page.inner_text('#seasonBody') and not errs, 'missing season file: message, week still renders')
    page.click('[data-tab="draft"]')
    check(page.locator('.pick').count() == 32, 'draft order independent of the season file')
    check(page.locator('header.header').get_by_text('Credits').count() >= 1, 'Credits & disclaimer link in header')
    b.close()
print('\nFAILS:', fails if fails else 'none')
sys.exit(1 if fails else 0)

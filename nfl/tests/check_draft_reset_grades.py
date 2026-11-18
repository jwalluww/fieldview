"""Playwright check: Reset keeps rookies, header Clear draft two-step, pick grades, sidebar draft line.
Run from the repo root with `python -m http.server 8765` up. 1280x900 + 1920x1080. Screenshots -> nfl/tests/screens/ (gitignored).
Usage: fieldview_env\\Scripts\\python.exe nfl/tests/check_draft_reset_grades.py [base_url]
"""
import os, sys, json
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8765').rstrip('/')
URL = BASE + '/nfl/nfl-formation-view.html'
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, 'screens'); os.makedirs(SHOTS, exist_ok=True)
FIX = open(os.path.join(HERE, 'fixtures', 'mdh_mock_sample.txt'), encoding='utf-8').read()
fails = []


def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def load(page, team, extra=''):
    page.goto(f'{URL}?team={team}{extra}')
    page.wait_for_selector('#playersLayer .player-node')
    page.wait_for_function('document.querySelectorAll("#needsChips .ns-chip").length === 3')


def vis(page, id_):
    return page.evaluate(f"document.getElementById('{id_}').style.display !== 'none'")


def place(page, pick, pid, slot):
    page.evaluate("async ([pick, pid, slot]) => { await openDraftPanel('pick'); selectDraftPick(pick); selectDraftProspect(pid); placeRookieFromPanel(slot); }", [pick, pid, slot])


with sync_playwright() as pw:
    b = pw.chromium.launch()
    for (w, h) in [(1280, 900), (1920, 1080)]:
        tag = f'{w}x{h}'
        page = b.new_page(viewport={'width': w, 'height': h})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        load(page, 'NYJ')
        check(not vis(page, 'clearDraftBtn'), f'{tag} Clear draft hidden with no rookies')
        # --- manual rookie + manual vet sub
        pid = page.evaluate("async () => { await loadDraftData(); const o = draftData.order.find(o => o.team === 'NYJ' && o.round === 1); return [o.pick, draftData.prospects.find(p => p.standard_pos === 'EDGE').prospect_id]; }")
        place(page, pid[0], pid[1], 'LDE' if page.evaluate("!!document.querySelector('#playersLayer .player-node[data-pos=\"LDE\"]')") else 'LEDG')
        slot = page.evaluate("rookieEntries()[0] && rookieEntries()[0].slot")
        check(slot is not None, f'{tag} manual rookie placed ({slot})')
        check(vis(page, 'clearDraftBtn'), f'{tag} Clear draft shown with a manual rookie')
        check(not vis(page, 'resetStartersBtn'), f'{tag} Reset hidden when only a rookie exists')
        # vet sub on another slot
        page.evaluate("() => { const c = getSubCandidates('QB')[0]; if (c) selectSub('QB', c.id); }")
        check(vis(page, 'resetStartersBtn'), f'{tag} Reset shown with a manual sub')
        page.evaluate("resetStarters()")
        check(page.evaluate("rookieEntries().length") == 1, f'{tag} Reset keeps the manual rookie')
        check(not vis(page, 'resetStartersBtn'), f'{tag} Reset hidden again after reset')
        # --- two-step clear
        page.click('#clearDraftBtn')
        check(page.text_content('#clearDraftBtn') == 'Confirm clear?', f'{tag} first click -> Confirm clear?')
        page.wait_for_timeout(3300)
        check(page.text_content('#clearDraftBtn') == 'Clear draft' and page.evaluate("rookieEntries().length") == 1, f'{tag} confirm times out after 3s, nothing cleared')
        page.click('#clearDraftBtn'); page.click('#clearDraftBtn')
        check(page.evaluate("rookieEntries().length") == 0 and not vis(page, 'clearDraftBtn'), f'{tag} second click clears manual rookies')
        # --- import
        page.evaluate("async () => { await openDraftPanel('import'); }")
        page.wait_for_selector('#dpImportTa')
        page.fill('#dpImportTa', FIX)
        page.evaluate("doImport()")
        page.wait_for_function("importRookies.length > 0")
        check(vis(page, 'clearDraftBtn'), f'{tag} Clear draft shown with an import')
        before = page.evaluate("importRookies.length + '|' + Object.keys(autoPlaced).join(',')")
        page.evaluate("resetStarters()")
        after = page.evaluate("importRookies.length + '|' + Object.keys(autoPlaced).join(',')")
        check(before == after and page.evaluate("importRookies.length") > 0, f'{tag} Reset keeps the import rookies ({before})')
        # grades in the haul
        page.evaluate("openDraftPanel('import')")
        haul = page.evaluate("document.querySelectorAll('.dp-haul .dp-grade').length")
        team_g = page.evaluate("(document.querySelector('#playerSidebar .sb-sort .dp-grade') || {}).textContent")
        check(haul == page.evaluate("importRookies.length") and team_g, f'{tag} haul shows {haul} pick grades + team grade {team_g}')
        page.screenshot(path=os.path.join(SHOTS, f'grades_haul_{tag}.png'))
        # rookie sidebar
        slot = page.evaluate("[...document.querySelectorAll('#playersLayer .player-node')].map(n => n.dataset.pos).find(p => getStarter(p) && getStarter(p).isRookie)")
        if slot:
            page.evaluate("(s) => openSidebar(s)", slot)
            txt = page.inner_text('#playerSidebar')
            check('Grade' in txt, f'{tag} rookie sidebar shows Grade')
            page.screenshot(path=os.path.join(SHOTS, f'grades_sidebar_{tag}.png'))
        page.click('#clearDraftBtn'); page.click('#clearDraftBtn')
        check(page.evaluate("importRookies.length") == 0 and page.evaluate("localStorage.getItem('fieldview_nfl_mock')") is None, f'{tag} Clear draft clears the import + localStorage')
        # --- board grades
        page.evaluate("async () => { await openDraftPanel('pick'); const o = draftData.order.find(o => o.team === 'NYJ' && o.pick === 4) || teamDraftPicks()[0]; selectDraftPick(o.pick); }")
        n = page.evaluate("document.querySelectorAll('#dpList .dp-row .dp-grade').length")
        check(n > 10, f'{tag} board rows show grades ({n})')
        page.screenshot(path=os.path.join(SHOTS, f'grades_board_{tag}.png'))
        check(page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1'), f'{tag} no page scroll')
        # --- sidebar draft line (veteran)
        load(page, 'KC')
        line = page.evaluate("""() => { const out = []; for (const n of document.querySelectorAll('#playersLayer .player-node')) { const p = getStarter(n.dataset.pos); if (p) out.push([p.name, draftLine(p), p.attainment]); } return out.filter(x => x[1]).slice(0, 4); }""")
        print(tag, 'draftLine samples', line)
        check(len(line) > 0, f'{tag} draft line renders')
        check(not errs, f'{tag} no page errors {errs}')
        page.close()

    # --- acceptance
    page = b.new_page(viewport={'width': 1920, 'height': 1080})
    load(page, 'NYJ')
    res = page.evaluate("""async () => {
      await loadDraftData();
      const find = (re) => draftData.prospects.find(p => re.test(p.name));
      const show = (team, nm, pickNo) => {
        // team needs before the pick
        const pr = nm;
        const nd = computeNeeds({ beforePick: pickNo });
        const gr = gradeFor(pr, pickNo, nd);
        return { name: pr.name, pos: pr.standard_pos, rank: gr.rank, pick: pickNo, group: gr.g, value: +gr.value.toFixed(3), rawNeed: +gr.rawNeed.toFixed(1), need: +gr.need.toFixed(3), pv: gr.pv, score: +gr.score.toFixed(3), letter: gr.letter };
      };
      const out = {};
      const carr = find(/CJ Carr/);
      out.carr = carr ? show('NYJ', carr, 4) : null;
      // LB ranked ~8 at #8 by the team with the highest LB need
      const lbs = draftData.prospects.filter(p => p.standard_pos === 'LB' && p.consensus_rank).sort((a, b) => a.consensus_rank - b.consensus_rank);
      const rbs = draftData.prospects.filter(p => p.standard_pos === 'RB' && p.consensus_rank).sort((a, b) => Math.abs(a.consensus_rank - 60) - Math.abs(b.consensus_rank - 60));
      out.lbTop = lbs.slice(0, 3).map(p => [p.name, p.consensus_rank]);
      out.rb = rbs.slice(0, 2).map(p => [p.name, p.consensus_rank]);
      // the team with the highest LB raw need
      let best = null;
      for (const t of Object.keys(TEAMS)) { await selectTeam(t); const nd = computeNeeds({}); const v = nd.byGroup.LB.rawNeed; if (!best || v > best[1]) best = [t, v]; }
      out.bestLbTeam = best;
      await selectTeam(best[0]);
      const lb = lbs[0];
      out.lb = show(best[0], lb, Math.max(1, lb.consensus_rank));
      // also at #8 exactly
      out.lb8 = show(best[0], lb, 8);
      await selectTeam('NYJ');
      out.rb10 = rbs[0] ? show('NYJ', rbs[0], 10) : null;
      return out;
    }""")
    print(json.dumps(res, indent=1))
    b.close()

print('\nFAILS:', fails if fails else 'none')
sys.exit(1 if fails else 0)

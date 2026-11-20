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


# ---- needs refresh (manual + import) and sequential grades
SYNC = """() => { const f = computeNeeds();
  const freshL = f.ranked.slice(0, 3).map(g => NEED_LABEL[g] + ':' + f.byGroup[g].score).join(',');
  const stripL = [...document.querySelectorAll('#needsChips .ns-chip')].map(c => c.querySelector('b').textContent + ':' + c.title.split(' \\u00b7 ')[1].replace('need ', '')).join(',');
  const q = (sel, a, b) => [...document.querySelectorAll(sel)].slice(0, 3).map(r => r.querySelector(a).textContent + ':' + r.querySelector(b).textContent).join(',');
  return { freshL, stripL, mini: q('#playerSidebar .nm-row', '.nm-g', '.nm-s'), panel: q('#playerSidebar .nq-card', '.nq-g', '.nq-score') }; }"""
SEQ = "(pick) => { const r = needsRookies().find(x => x.pick === pick); return gradeFor(r.prospect, r.pick, computeNeeds({ beforePick: r.pick }), r.posRaw).score; }"


def synced(page, tag, what, mini=False, panel=False):
    r = page.evaluate(SYNC)
    ok = r['stripL'] == r['freshL'] and (not mini or r['mini'] == r['freshL']) and (not panel or r['panel'] == r['freshL'])
    check(ok, f'{tag} needs in sync after {what}: {r}')


def board_ok(page, tag, what):
    bad = page.evaluate("""() => { const pick = draftSel.pick; if (!pick) return -1; const f = getNeeds(), ndB = computeNeeds({ beforePick: pick }); let n = 0, seen = 0;
      for (const row of document.querySelectorAll('#dpList .dp-row')) { const fits = row.querySelectorAll('.dp-fit, .dp-grade'); seen++; if (fits.length < 2) n++; }
      const first = document.querySelector('#dpList .dp-row .dp-grade');
      return first ? n : -2; }""")
    check(bad == 0, f'{tag} board rows carry Fit + grade badges after {what} ({bad})')


with sync_playwright() as pw:
    b = pw.chromium.launch()
    for (w, h) in [(1280, 900), (1920, 1080)]:
        tag = f'{w}x{h}'
        page = b.new_page(viewport={'width': w, 'height': h})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        load(page, 'NYJ')
        page.evaluate("openDraftPanel('pick')"); page.wait_for_function('draftData && document.querySelector(".nm-row")')
        synced(page, tag, 'manual start', mini=True)
        firstpick = None
        for i, pos in enumerate(['EDGE', 'CB']):
            pk = page.evaluate("""([pos, i]) => { const o = draftData.order.filter(o => o.team === 'NYJ').sort((a, b) => a.pick - b.pick)[i]; if (draftSel.pick !== o.pick) selectDraftPick(o.pick);
              const pr = draftData.prospects.filter(p => p.standard_pos === pos && p.consensus_rank).sort((a, b) => a.consensus_rank - b.consensus_rank)[0];
              selectDraftProspect(pr.prospect_id);
              const slot = [...document.querySelectorAll('#playersLayer .player-node.drop-target')].map(n => n.dataset.pos)[0];
              placeRookieFromPanel(slot); return o.pick; }""", [pos, i])
            check(page.evaluate('needsRookies().length') == i + 1, f'{tag} manual pick {i + 1} placed')
            synced(page, tag, f'manual pick {i + 1}', mini=True)
            if i == 0:
                firstpick = pk
                g0 = page.evaluate(SEQ, pk)
            page.evaluate("() => { const o = draftData.order.filter(o => o.team === 'NYJ' && !needsRookies().some(r => r.pick === o.pick))[0]; if (o) selectDraftPick(o.pick); }")
            board_ok(page, tag, f'manual pick {i + 1}')
        g1 = page.evaluate(SEQ, firstpick)
        check(abs(g1 - g0) < 1e-9, f'{tag} earlier grade frozen when a later pick is added ({g0:.3f} -> {g1:.3f})')
        page.evaluate("openNeedsPanel()"); synced(page, tag, 'open Team Needs panel', panel=True)
        page.evaluate("() => removeRookie(rookieEntries()[0].slot)")
        synced(page, tag, 'manual removal (panel open)', panel=True)
        page.evaluate("clearDraft()"); synced(page, tag, 'manual clear (panel open)', panel=True)
        # import: three teams, panel closed / open
        page.evaluate("openDraftPanel('import')"); page.wait_for_selector('#dpImportTa'); page.fill('#dpImportTa', FIX); page.evaluate("doImport()")
        page.wait_for_function("importRookies.length > 0")
        synced(page, tag, 'import NYJ', mini=True)
        for t in ['DAL', 'MIA', 'NYJ']:
            page.evaluate(f"selectTeam('{t}')"); page.wait_for_function(f"currentTeam === '{t}'"); page.wait_for_timeout(300)
            synced(page, tag, f'switch to {t} (import loaded)')
            page.evaluate("openNeedsPanel()"); synced(page, tag, f'{t} Team Needs panel', panel=True)
            page.evaluate("openDraftPanel('import')"); page.wait_for_selector('.dp-haul'); synced(page, tag, f'{t} import panel', mini=True)
        sig = page.evaluate("() => { getNeeds(); const a = needsCache.sig; importRookies[0].pick += 1; getNeeds(); const b = needsCache.sig; importRookies[0].pick -= 1; return a !== b; }")
        check(sig, f'{tag} needs cache signature changes with the pick number')
        page.evaluate("clearImport()")
        # sequential grades: WR repeat penalty, earlier picks frozen, removal recomputes later ones
        seq = page.evaluate("""() => { const picks = draftData.order.filter(o => o.team === 'NYJ').slice(0, 4);
          const wrs = draftData.prospects.filter(p => p.standard_pos === 'WR' && p.consensus_rank).sort((a, b) => a.consensus_rank - b.consensus_rank).slice(0, 4);
          importRookies = picks.map((o, i) => makeRookie(o, wrs[i]));
          const sc = r => gradeFor(r.prospect, r.pick, computeNeeds({ beforePick: r.pick }), r.posRaw);
          const out = importRookies.map(r => [sc(r).k, sc(r).rep]);
          const first = sc(importRookies[0]).score, lastBefore = sc(importRookies[3]).score;
          const removed = importRookies.splice(1, 1); const lastAfter = sc(importRookies[2]).score; const first2 = sc(importRookies[0]).score;
          importRookies = []; return { out, same: Math.abs(first - first2) < 1e-9, later: lastAfter > lastBefore }; }""")
        check([x[0] for x in seq['out']] == [0, 1, 2, 3] and [x[1] for x in seq['out']] == [1, 0.6, 0.35, 0.2], f'{tag} repeat penalty k/rep per WR pick {seq["out"]}')
        check(seq['same'], f'{tag} an earlier pick grade ignores later picks')
        check(seq['later'], f'{tag} removing a pick recomputes later grades')
        check(not errs, f'{tag} no page errors {errs}')
        page.close()
    b.close()


print('\nFAILS:', fails if fails else 'none')
sys.exit(1 if fails else 0)

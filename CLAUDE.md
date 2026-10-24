# FieldView — Claude Code Context

Multi-sport intelligence platform. Live at `jwalluww.github.io/fieldview/` (GitHub Pages). Repo: https://github.com/jwalluww/fieldview (public).

Purpose: each sport gets a FieldView (players on the field/court/pitch in their real positions, with substitutions) and a TableView (sortable/filterable stat table). A future ReView (replays, box scores, highlights) comes after every sport's FieldView/TableView are dialed in — not started for any sport.

*Snapshot verified against the live repo on 2026-10-24 (after 8153527). Anything not re-checked is marked "unverified".*

---

## Current status (2026-10-24)

All six sports ship a FieldView + TableView with real data and a real cloud job (`scrape.yml`, six jobs). Every FieldView dot shows the video-game overall rating (0-99, shared `ratingColor()` gradient — copy it verbatim between sports).

| Sport | State | Players / rated | Ratings source |
|---|---|---|---|
| **NFL** | FormationView (offense + defense together, "Opponent View" phase 1) with a click-to-open player sidebar; TableView with per-tab column picker. | 2,369 / Madden on 1,842 (77.8%) | **EA drop-api, Madden 27**, weekly iteration (Week 6 now) |
| **NBA** | CourtView (positionless subs, undo) + TableView (PPG/RPG/APG/MPG only). Roster/stats universe is stale — see Known Bugs. | 587 / 565 rated (96.3%) | **nba2kapi.com** (JSON mirror of 2kratings.com), cloud job, keyless fallback |
| **MLB** | DiamondView with player sidebar + on/off toggle, 40-man roster incl. injured; TableView. | 1,359 / 1,354 (99.6%) | **MLB The Show official API** (`series == "Live"`) |
| **NHL** | IceView + TableView. No sidebar, no "ratings as of" caption. | 797 / 715 (89.7%) | **nhlratings.net via ScraperAPI** (EA publishes only its top 300 NHL players) |
| **EPL** | PitchView with 6-formation switcher + TableView incl. Advanced tab. | 668 / 558 (83.5%) | **EA drop-api, FC 27** (EA id == sofifa id) |
| **MLS** | PitchView with formation switcher + TableView (Age, xG-family Advanced columns). | 1,069 / 777 (72.7%) | **EA drop-api, FC 27** |

- **Ratings-as-of captions:** NFL ("Madden ratings: Week 6, as of <date>"), NBA, MLB, EPL, MLS show one; NHL has none (source has no date).
- **`potential` is gone** from MLB, EPL and MLS (no source publishes it). NHL's master still carries `potential` (`Low/Med/High`) but no page shows it.
- **Local-only pieces that remain:** NBA stats/rosters (`fetch_stats.py` — stats.nba.com blocks GitHub-hosted runners, permanent) and NFL Spotrac contracts (`scrape_contracts_spotrac.py`, never wired into the cloud job). Both silently go stale when nothing commits their output — see Known Bugs. The NBA 2K Task Scheduler job is **retired, but the owner has not yet disabled it** (it ran again today and dirtied two files — see Known Bugs).
- **Owner-side steps pending** (Claude can't do these): disable (not delete) the Task Scheduler job `FieldView NBA 2K Ratings Scrape`; make sure the repo secret `NBA2KAPI_KEY` is set; `git checkout -- nba/data/nba_ratings_2k.json nba/data/ratings_2k_scrape_state.json` to discard today's local rewrite.
- **Not started:** ReView; mobile pass (desktop-only by choice); custom domain.

---

## Stack & pipeline

- Frontend: plain HTML/CSS/JS, no React, no build tools. Hosting: GitHub Pages (100% static).
- Backend: Python 3.11 scrapers; `duckdb`/`pandas` purely as a **build-time join engine** (matching OurLads+Madden+OTC+Spotrac etc. is a multi-table join); the flat result is exported to JSON the frontend `fetch()`es. DuckDB-WASM was deliberately rejected ("JSON as the data format, not client-side SQL engines"). Every `.duckdb` file is ephemeral and gitignored (NFL/NBA/EPL/MLB/NHL; MLS has no DB layer) — check this if a sport is added. Raw per-scraper JSON snapshots let a broken match step be re-run without re-hitting a live site.
- **Local Python:** use `fieldview_env\Scripts\python.exe` (system Python lacks duckdb/rapidfuzz). Verify pages with `python -m http.server` + headless Playwright against real data.
- **Automation:** `.github/workflows/scrape.yml`, six jobs (`scrape`=NFL, `scrape-nba`, `scrape-mlb`, `scrape-nhl`, `scrape-epl`, `scrape-mls`), one shared schedule (`cron: '0 10 * * 2'`, Tuesdays 10:00 UTC) + `workflow_dispatch`; no stagger. Every job commits with `git pull --rebase && git push` (a manual local commit once collided mid-run). Steps use `continue-on-error` on the soccer jobs; a failed fetch keeps the previous snapshot by design.
- **Cloud jobs' ratings steps:** NFL `scrape_madden_ea.py`; NBA `scrape_nba2kapi.py` (env `NBA2KAPI_KEY`); MLB `scrape_show_api.py`; NHL `scrape_ratings.py` (env `SCRAPERAPI_KEY`); EPL/MLS `scrape_ea_fc.py`. `scrape_qbr.py` runs only in the cloud NFL job (not in `run_nfl.bat`).
- **Local orchestration:** `run_nfl/nba/mlb/nhl/epl/mls.bat` run one sport's pipeline end to end (fail-and-continue per step, never commit); `run_all.bat` chains all six — **it has never completed in one sitting** (two attempts killed by host restarts), low priority since every sport has a cloud job. The bats are for pre-cloud testing.
- **Retiring a redundant job:** disable, don't delete (Task Scheduler jobs, scraper files, workflow steps — commented out). Retired and left in place: `scrape_madden.py`, `scrape_2kratings.py` (+ `schedule_2kratings_scrape.bat`, `ratings_2k_scrape_state.json`), `scrape_sofifa.py`, `mlb/scripts/scrape_ratings.py` (theshowratings.com).
- Task Scheduler (Windows): `FieldView NBA 2K Ratings Scrape` is **Ready/enabled (should be disabled)**; `FieldView NHL Ratings Scrape` is Disabled.
- **Site infra:** GA4 `G-TP0M77Z31N` on every HTML page. Custom domain dropped (`fieldview.com` is owned by someone else). AdSense needs a real top-level domain; premium networks gate on traffic.

---

## Workflow notes

- Use chat (claude.ai) for architecture, pushback and diagnosing against the live repo; use Claude Code (VS Code) for implementation, real-data verification and live recon. Give recon against live external systems to Claude Code as one broad task, not probe-per-question.
- For real scripts, give Claude Code a precise spec with verified facts and named edge cases, not code written blind in chat — bugs are repeatedly caught only because Claude Code tested against real data.
- Long local verification runs go in the foreground, watched (a host restart killed two background runs). Start a new chat when switching sport or feature area.
- **Every Claude Code instruction block is one fenced code block** that restates, every time: (1) end with a summary mapped to the request plus a plain-language `TLDR:` (a few sentences, no jargon or file names); (2) commit and push, saying explicitly what is **live immediately** (frontend files, committed data) vs what **needs the next pipeline run** (Python/pipeline changes).
- **Owner-side steps (secrets, Task Scheduler, manual commits, anything Claude can't or mustn't touch) must be called out explicitly at the end of every report.**
- Chat verifies every Claude Code diff against the live repo after it's pushed — this has repeatedly caught unpushed commits, scope creep and wrong "already fixed" claims. "Documented as shipped" is not "verified."

---

## Key cross-sport learnings

**Data sources**
- **Look at the ratings page's network calls before building a scraper.** Official/first-party JSON feeds (EA's drop-api, The Show's API) beat scraping mirror sites: no anti-bot fight, whole pool per call, versioned.
- **Write a replacement source's output in the EXACT old file shape** so downstream matching, position logic and the frontend stay untouched — how Madden, NBA 2K and the soccer ratings were swapped without regressions.
- **A silent fallback-to-last-known-data is only safe if staleness is visible.** Madden kept 24 of 32 teams on August data for weeks. Surface a date, and use a diff-based "ratings as of" caption (carry the date forward if content is identical, bump to today if anything changed) on every sport whose source lacks one.
- **Local-only jobs silently go stale once nothing commits their output.** NBA 2K ratings sat 4 weeks behind; `nba_stats.json` is still 2.5 months behind. Every source should run in the cloud or show its staleness on the page.
- **Never hardcode a page-size increment** — advance by what the page returned (NFL/MLB `/v1/stats`, NHL's 100-row cap, sofifa, EA's `totalItems`-only-on-page-1 all bit).
- **Anti-bot is not one problem:** test a complete `User-Agent`/header set with plain `requests` before `curl_cffi` or a paid proxy. A numeric ID in a photo/asset URL may be a real join key or a lookalike — verify by hand in both directions.
- When two real sources disagree on rosters/teams/clubs, that's signal (different snapshots, fake exhibition clubs, transfer lag) — investigate, don't average.
- **A pipeline whose steps merge into shared intermediate files has a required order; a partial re-run can silently zero fields.** (NFL: `scrape_depth` wipes what `scrape_otc`/`scrape_stats` add.) After any partial re-run, compare field coverage (non-null counts) against the previous commit before committing.
- A live re-run produces different real numbers than the original build (rosters and ratings update); that's expected, not a regression.

**Matching**
- Any lookup keyed on a person's name collides with same-name/same-surname players: key by (name, team), require a first-initial match for last-name fallbacks, and look for identical values across different people to find the bugs.
- A name matcher's documented design can be right for its cases and still miss a class (EPL's first-token gate couldn't catch "Mitoma Kaoru" vs "Kaoru Mitoma"). Check the actual gating condition.
- **A tightened name-only tier should require an independent attribute to agree** (MLB: bats/throws + pitcher-vs-hitter; EPL: position group; both also require uniqueness).
- A retry gated behind an expensive fetch strands failures when the fetch is sampled (NBA's 2K trickle froze Lillard unmatched); cheap in-memory re-matches should run every time.
- A scraper's "generic slot" label (NB nickel, reserve labels ED/CB/S/LB/OG/CE/SUS) is not a position — resolve by label where unambiguous, else another source, drop only as a last resort.
- **Use the right roster concept:** MLB's `active` roster silently dropped Judge and ~230 others; the 40-man is the real universe (status codes carried through).

**Frontend**
- A per-zone "pick the best player for this slot" function breaks when two zones share one candidate pool (NHL D1/D2 shared `positionCode 'D'` — fixed; EPL/MLS `computeStarters()` is single-pass for this reason). Check any two zones for the same filter key.
- A shared CSS color is only as safe as its least-typical surface: `var(--text-muted)` on saturated backgrounds and `var(--text-dim)` (`#404660`) on near-black surfaces were both unreadable in places. Check computed contrast on the outlier surface.
- Any table view with a separate mobile card-list path must re-render it from every function that changes the filtered set, not just sort.

---

## Pattern: player sidebar (built on NFL and MLB)

Hover is light (name / position / rating / INJ); **click opens a sidebar** (360px, `Esc`, the x button, an empty-field click or a team switch close it; the selected card keeps a cyan outline that follows a swap). No hero stat — the old hero is just the first advanced row.
- **Layout:** header (name, jersey, team, position, bio, overall rating, INJ detail) → Advanced Stats → Season Stats grid → Substitutes. Players with no advanced values skip the advanced section.
- **Advanced rows:** raw value + percentile bar + one-line definition. Percentile = % of the qualified same-position population beaten (ties count half, lower-is-better inverted, **capped at 99**, population < 10 → no bar), colored red → amber → green via `pctColor()`. **Style stats** (not good/bad — NFL TTT/aDOT/Air Yd Shr/aDOT Allowed, MLB BABIP) get a **neutral grey bar** and descriptive text ("quicker than N% of QBs"). Percentile math/`pctColor()` is copied between sports — copy it, don't rewrite it.
- **Sample-size gates:** an unqualified player is excluded from every population and shows raw value + definition + a muted **"low sample"** tag, no bar.
- **Season stats grid:** per-position keys with derived rates (Comp%, YPA, YPC… / OPS-family); source blocks spell some keys several ways (NFL `SACK`/`SACKS`, `INT`/`INTs`, `PBU`/`PD`), all handled.
- **Sub comparison:** clicking a substitute opens starter-vs-candidate (season-stat table, better value **bold green**, both players' advanced bars and percentiles, **no deltas**); **Swap in** substitutes, **Back** cancels. Only blocks both players have are compared.
- **`?player=<player_id>`** is written while the sidebar is open (with the other params) and reopens it on load if that player is currently on the field for the loaded team; ignored otherwise, dropped on team switch.
- **Reset to starters** button in the header: clears manual subs, keeps the personnel/formation choice, refreshes or closes the sidebar; hidden when there are no manual subs.
- **Per-sport differences:**
  - **NFL** — push layout (the field gets right padding; cards slim to 66px under 1500px so ~22 cards never overlap); always on. Qualifiers come from `nfl/data/advanced_meta.json` (`league_max_games`, `field_season`) and each player's `adv_volume`: QB `att >= 14×G`, RB `car >= 6.25×G`, WR/TE `tgt >= 1.875×G` (G = the season's max team games; gate inert if the sidecar is empty or `adv_volume` absent). Percentile population = same `standard_pos` across all loaded players. NB-slot comparisons across CB/S compare shared stats only.
  - **MLB** — replaces the batting-order/pitching-staff column (`body.sb-open`; the field doesn't resize); header **Sidebar On/Off toggle**, `localStorage` key `fieldview_mlb_sidebar` (default ON; OFF = original popover + full hover card; `?player=` written only when ON). Everything computed client-side from `batting_stats`/`pitching_stats` (statsapi rates are strings — use counts). Qualifiers: batters PA ≥ 3.1×G, SP IP ≥ 1.0×G, RP IP ≥ 0.25×G, G = 162 once the season is complete else the max games played (`leagueG`). **`inningsPitched` is in thirds** ("85.2" = 85⅔, `ipToNum()`). Pitchers ranked within role (SP if GS ≥ half of games). Two-way players get both sections. Field height is fixed (`--fh`), never `min-height`.
- **Not ported:** NBA, NHL, EPL, MLS. **NBA is next**, once a richer cloud-friendly NBA stats source exists (current stats are only PPG/RPG/APG/MPG).

---

## Pattern: external ratings APIs — gotchas

**EA drop-api** (`https://drop-api.ea.com/rating/{slug}`, slugs `ea-sports-fc` / `madden-nfl` / `nhl`; verified from a GitHub Actions runner too). Shared fetcher: `shared/scripts/ea_ratings.py` → `fetch_all(slug, extra_params, min_total, validate)`.
- **`drop-referrer: https://www.ea.com/games/{slug}/ratings` is REQUIRED** — without it EA answers 200 with LAST season's data (and `nhl` returns zero items). `x-feature` is not needed.
- **EA's CDN caches by URL (~10 min) and ignores that header** → every request carries a random `cb=` cache-buster.
- **`totalItems` is only valid on page 1**; page size is capped (100 FC/Madden, 50 NHL; larger `limit` → 400); advance by the count returned.
- Headless Chromium/Chrome is blocked at ea.com's *page*; the API needs no browser (plain `requests` works).
- **Guards:** `fetch_all` returns `None` (caller keeps its old snapshot, exit 0) on a failed/truncated pull, duplicate card ids, total below `min_total`, or a failed `validate` edition check. Edition checks: **FC** has no version marker (avatars say "FC25") → men's total (`gender=0`) ≥ 17,000 (last season 16,228, now 17,849) and ≥ 0.97× the previous snapshot, ≥ 500 EPL / 650 MLS cards, ≥ 18 / 28 clubs; **Madden** → ≥ 95% of `avatarUrl` contain `madden-nfl-27` (bump `EDITION_MARKER` for Madden 28), one iteration, 32 teams, total ≥ 1,800 and ≥ 0.97× previous; **NHL** (unused) would be `NHL27` in `avatarUrl`, but EA publishes only the top 300 players and has no external ids.
- Card fields: FC `id` (= sofifa id), `firstName/lastName/commonName`, `overallRating`, `team.label`, `leagueName` (`Premier League`, `MLS`), `position.shortLabel`, `gender`; Madden adds `iteration {id,label}`, `age`, `yearsPro`, `college`, `archetype`, no usable external id. **No `potential`, no per-card date** in FC. A forced bad fetch (header dropped) is rejected by these guards.

**The Show (MLB):** `mlb26.theshow.com/apis/items.json?type=mlb_card` (25/page, loops `total_pages`), keep `series == "Live"` (~2,084 cards); plain `requests` + Chrome UA, no Cloudflare/ScraperAPI. **No MLB player id, no potential.** A truncated pull (< 1,500 Live cards) keeps the old snapshot.

**nba2kapi (`https://api.nba2kapi.com`):** free JSON mirror of 2kratings.com, MIT repo `wkoverfield/nba2kapi`, fan-made, **no stated terms or attribution rule**, refreshed ~weekly, 2K27 current. `GET /api/players/bulk?teamType=curr` (`X-API-Key`; counts as one request) returns the whole current-era pool; the keyless `GET /api/public/players?teamType=curr&limit=100&cursor=…` (60 requests/min/IP, ~7 pages) is the fallback. **No NBA player id, no jersey number.** Card fields: `name, slug, team (full name; offseason free agents = "Free Agency"), teamType, overall, positions[], height, attributes{threePointShot,drivingDunk,…}, gameVersion, lastUpdated, ratingHistory, playerUrl`. Documented rate limits disagree (100 vs 500/hour).

**ScraperAPI:** used only by NHL's `scrape_ratings.py` (~139 requests/month of a 1,000 free-credit plan). Keep the `SCRAPERAPI_KEY` secret.

---

## NFL (FormationView)

**Files:** `nfl/nfl-formation-view.html` (offense + defense simultaneously), `nfl/depth-chart.html` (table: Overview/Financial/Madden/Passing/Rushing/Receiving/Defense), per-team `nfl/data/<abbr>.json` (OurLads scrape; only `index.html`'s player-count tile reads them), `nfl/data/players_master.json` (what both pages read), sidecars `advanced_meta.json` (`field_season`, `league_max_games`; written by `build_db.py`) and `madden_meta.json`.

**Pipeline** (`nfl/scripts/`): `scrape_depth.py` (OurLads; `INJURED_SECTIONS`, `SLOT_MAP_34/43`) → `scrape_otc.py` / `scrape_stats.py` (last-name stats fallback requires a first initial — a wrong stat is worse than a missing one) / `scrape_madden_ea.py` / `scrape_contracts_spotrac.py` (local only) / `scrape_qbr.py` (cloud only) → `build_db.py` → `build_match.py` (joins Madden **before** GSIS matching so it can fix positions) → `export_master.py <path>`. **Step order matters:** `scrape_depth.py` rewrites every per-team file *without* `cap_number`/`stats`; `scrape_otc.py` and `scrape_stats.py` merge them back in, so a partial re-run (e.g. depth → build_db → build_match → export) silently zeroes contracts and season stats in the master — this shipped in d9dd6af on 2026-10-24 and was repaired in 8153527. Always run depth → otc → stats (+ madden/spotrac/qbr) before `build_db.py`. `build_master.py` isn't run standalone but `build_match.py` imports it (aliases, `find_madden_player`, `build_madden_pos_ranks` keyed by (name, team), `years_pro` clamped ≥ 0, `find_roster_gsis_for_ol()`). Last full run: 2,369 players, GSIS-matched 1,841 (77.7%), Madden 1,842 (77.8%), age 95.9%, `cap_number` 1,786 (75%), season `stats` 1,255, `years_remaining` 93%.

**Madden source (`scrape_madden_ea.py`):** writes `madden.json` in exactly the old shape (`firstName, lastName, overallRating, team{label}, jerseyNum, position{shortLabel}`); position labels pass through (EA's 22 equal the old source's: QB HB FB WR TE LT LG C RG RT LEDG REDG DT SAM MIKE WILL CB FS SS K P LS); team labels pass through except `NY Giants`/`NY Jets` → full names (`MADDEN_TEAM_MAP`). `madden_meta.json` = every team code → fetch date + `"_iteration": {id, label}` (keys starting `_` aren't teams; both frontends skip them; `NON_TEAM_FILES` skips the file). Caption "Madden ratings: Week 6, as of <date>" on FormationView (selected team) and depth-chart (oldest date; "(N teams older)").
- **Aliases:** EA's spellings differ from the old source for ~180 players (suffix punctuation and curly apostrophes are neutralized by `normalize_madden`; real differences like Pat/Greg/Cam/Dre). `find_madden_player()` tries the aliased name, then the player's own name; `normalize_madden` folds accents. **Wrong-way for EA, left in place and harmless:** Madden aliases Nnamdi Madubuike, Mike Onwenu, Kenny Gainwell, Dax Hill, Vega Ioane, Joshua Palmer, Olu Fashanu, DJ Glaze, Bam Knight, Matt Peart, Zach Carter, Kiko Mauigoa, Matt Hibner; shared `NAME_ALIASES` Kam Curl, Juju Brents, Pat Surtain II, Riq Woolen, Dru Phillips, Cobie Durant, Greg Rousseau, Cam Ward, Zach Bako-bewele (must stay as written for GSIS/OTC). `MADDEN_NAME_ALIASES['Josh Uche']` → `'Joshua Uche'`; added Mitch Tinsley, Nate Thomas, Cameron Heyward. Four same-surname pairs deliberately not aliased (different people): Chris Moore/Nick Moore BAL, Christian Jones/Jaylon Jones CHI, Marvin Jones Jr./Jacoby Jones WAS, Pharaoh Brown/Austin Brown IND.
- 26 players that had a rating on the old stale source have none now (2 depth-1: Art Green ARZ CB, Chris Braswell HOU ED); EA's search and a league-wide last-name+initial scan found no same-person card. J.J. McCarthy matches (NYG QB, 72).

**Positions (`build_match.py`):**
- **NB safeties:** OurLads' NB row is a nickel slot, not a position; an NB-row `CB` whose Madden label is FS/SS/S gets `standard_pos 'S'` (`standard_slot` stays `NB`; 15 players). The GSIS retry tries the other of S/CB.
- **Reserve "DEF" rows:** reserve/IR/PUP labels (`ED CB S LB OG CE SUS PS/IR LEFT …`) arrive as `standard_pos 'DEF'`; `RESERVE_LABEL_MAP` (`ED→EDGE, CB→CB, S→S, LB→LB, OG→OL`) else the Madden position (`MADDEN_POS_MAP`) else the row is dropped. `CE` is unmapped on purpose (mixed rows). The master has 0 `DEF`; the per-team files still do (see Known Bugs).
- **Injured sections** `IR / PUP / NFI / PUP-R / DFR` (DFR = designated for return): kept, `injured: true`, `standard_slot` = the label, so `getStarter()` (needs `depth === 1` and a real formation slot) never fields them; position via Madden, dropped if none; deduped against a real depth-chart row. 252 flagged on the last run. `INJURED_SLOTS` in the frontend lists the same labels but is currently **unused** (see decision below).
- **OL bio recovery:** `find_gsis()` skips OL by design (crosswalk lacks OL), so `find_roster_gsis_for_ol()` does an independent name+team match against nflreadpy rosters to recover age/draft_year/college (433/435 OL have age) without changing `entry['gsis_id']`.
- **Seattle SLB:** Seattle is tagged 3-4 on OurLads but uses 4-3 labels; `SLOT_MAP_34` has `'SLB': ('LOLB','EDGE')` plus a general cross-scheme fallback in `enrich_positions()`.

**FormationView:**
- State: `currentOffPersonnel` ('11'/'12'), `currentDefPersonnel` (`base43/base34/nickel/nickel34`, defaulted per team scheme), independent; a sub on one side survives a personnel change on the other. URL: `?team=&off=&def=&player=`. `.p-card` width 96px (66px with the sidebar open; 72px mobile query untouched). Madden legend lives in the formation-bar row, right-aligned (`.legend-strip`, `margin-left:auto`), next to the "as of" caption.
- **Sub pools:** `getSubCandidates()` filters by `standard_pos`; FS/SS draw from every `S`; the **NB slot draws from `CB` + `S`**; anyone on the field is excluded. **Decision (a49bada): injured-list and reserve players ARE valid sub candidates** (they carry the red INJ badge; ~219 reserve players are real CB/S/LB/EDGE/OL rows). Excluding them would be a one-line filter on `INJURED_SLOTS`, applying to all injured sections.
- **Hover/INJ:** red INJ badge on the card and hover header; injury detail (body part + Out/Doubtful/Questionable, native `title`) and height/weight come from nflreadpy `load_injuries()`/`load_rosters()`; there is no free "how long out" field — don't build toward one. `selectSub()` replaces a single node instead of re-rendering.
- **Defensive stat display rule:** defensive keys (`TKL, SACK(S), INT(s), PBU, PD, TFL, QB_HIT, FF`) render only for `EDGE/DI/LB/CB/S` (hover generic block and, via `getStatVal()`, the TableView Defense tab display *and* sort; other rows show "—"). WR/TE hover branches key off `p.standard_pos`, not the slot key.
- **Offense advanced stats** (all SEASON → SEASON-1 fallback in `build_db.py`): QB `epa_per_play`/`success_rate` (nflverse pbp), `ngs_time_to_throw`/`cpoe` (NGS), `qbr` (ESPN via `scrape_qbr.py`, which writes the season ESPN actually served); RB `ryoe_per_att`/`box_rate` (NGS rushing), `yac_per_att`/`broken_tackle_rate` (PFR); WR/TE `adot`/`air_yards_share`/`avg_separation`/`yac_above_expectation` (NGS receiving, populated for only ~127 of 420), `drop_rate`/`broken_tackle_rate_rec` (PFR), `target_share`. Each player carries `adv_volume {"<season>": {att, car, tgt}}` (regular season, joined by `gsis_id`; absent season = unknown, never zeros). Qualifier rules are in the sidebar pattern.
- **Defender advanced stats:** source PFR season `def` table (`load_pfr_advstats_safe('def')`), currently falling back to **2025**; every rate uses that same season S (`def_advanced_season`; snaps filtered to `game_type == 'REG'` — playoff snaps understated per-100 by ~11% at the median). Fields (null for non-defenders): `pressures_per100`, `sacks_per100` (EDGE/DI), `tfl_per100`, `tkl_per100` (EDGE/DI/LB), `missed_tackle_rate` (all groups), `comp_pct_allowed`, `rating_allowed`, `yds_per_target_allowed`, `adot_allowed` (LB/S/CB), `int_pd_per_target` (S/CB). Gates: per-100 null under 100 snaps; coverage null under 10 targets; missed-tackle null under 20 attempts. Card (`buildDefAdvBlock()`, `DEF_CARD`): hero Pressures/100 (EDGE/DI), Missed Tkl% (LB), Rating Allowed (S/CB); only used when a defender has ≥ 1 advanced value. **Tier cutoffs** keyed `<stat>_<standard_pos>` (33rd/67th percentile of qualified players: 300+ snaps or 10+ targets; `DEF_RANGES` = 10th–90th for tooltips); tooltips cite `DEF_CUTOFF_SEASON = 2025`. **If cutoffs are recomputed, regenerate `STAT_TIERS`' defender block and `DEF_RANGES` together and bump the constant.** The compact stat line is prefixed `<stats_season>: ` when it differs from `def_advanced_season`. Coverage of depth-1 defenders: EDGE 63/96, DI 69/96, LB 65/95, S 67/95, CB 82/120 (misses are mostly no 2025 PFR row).
- **Opponent View phase 1:** `FORMATION_COORDS` offense (y 57–80) and defense (y 8–43) never overlap and no position key collides, so both render together via `buildFormationSlots()`. **Phase 2** (a real opponent matchup) and a **density/sizing pass** for ~22 cards are not built.

**TableView (`depth-chart.html`):** the old Advanced tab was removed (d04855b); its stats live in the position tabs behind a per-tab column picker (17 stat slots; Receiving = WR+TE). Position tabs default-sort by their production stat (PASS_YDS, RUSH_YDS, REC_YDS, TKL) descending. Null check is `av == null || av === ''` — a real 0 is not missing.

**GSIS matching:** primary dynastyprocess crosswalk CSV, fallback nflreadpy rosters. Known low-impact gap: the fallback tags all DBs generically `DB` (CB 73.9%, S 78.5% matched via the crosswalk). OL snap-share coverage is ~66% (291/439; real source ceiling).

**Schema:** `players_master.json` keys: `player_id, gsis_id, match_confidence, canonical_name, ourlads_name, team, team_name, base_defense, ourlads_pos, standard_slot, standard_pos, depth, jersey, madden, madden_rank, madden_rank_total, madden_pos_label, cap_number, attainment, injured, stats, stats_season, nflreadpy_name, match_source, draft_year, college, years_pro, age, snap_pct, years_remaining, cash_total_remaining, cash_guaranteed_remaining, avg_annual_remaining` plus the defender/RB/WR/TE advanced fields, `def_advanced_season`, `adv_volume`, height/weight/injury detail. `standard_pos`: `QB WR RB TE OL EDGE DI LB CB S`; special teams are stripped.

---

## NBA (CourtView)

**Files:** `nba/court-view.html` (starting five in half-court zones + rotation list ranked by minutes), `nba/player-table.html`. Pipeline: `fetch_stats.py` (**local only**, writes `nba_stats.json`) + `scrape_contracts_spotrac.py` + `scrape_nba2kapi.py` + `scrape_nbadepthcharts.py` → `build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py`. `nba_stats.json` is the **match target and player universe** (587 players); the master's `rotation_status`/`mpg` etc. come from it.

**Ratings (`scrape_nba2kapi.py`, 2026-10-24):** writes `nba/data/nba_ratings_2k.json` in the old shape (`{ratings, unmatched}`; per rating `name, 2k_name, name_norm, team, jersey_number (always null — jersey comes from nba_stats.json), positions ("SG/PG/6'5\"" = positions + height), overall_rating, profile_url (playerUrl), attr_3pt (threePointShot), attr_dnk (drivingDunk), player_id, loaded_at (API lastUpdated, stable so unchanged pulls rewrite a byte-identical file)`) and `nba/data/ratings_meta.json` (`ratings_last_changed` diff-based, `game_version`, `source_total`) → CourtView caption "2K ratings as of <date>" (tooltip credits nba2kapi/2kratings). Fetch: bulk endpoint with `NBA2KAPI_KEY` (env/repo secret, never printed or logged), falling back to the keyless public endpoint if the key is missing/rejected/rate-limited. Guards (keep the old file, exit 0): < max(500, 0.9× previous) cards, < 28 NBA teams, non-numeric overalls, > 1 `gameVersion`, or `gameVersion` ≠ `/api/versions` `meta.current`. Matching reuses the alias → name+team → unique-name tiers (`NBA_NAME_ALIASES` in `nba/scripts/name_utils.py`; added Alexandre Sarr → Alex Sarr, Carlton Carrington → Bub Carrington). The API's 138 "Free Agency" cards get team `FA` and can only match by unique name. Result: 565/587 stats players rated; 92 of 657 cards unmatched (13 free agents; the rest mostly 2026 rookies/veterans absent from the stale `nba_stats.json`). Gate checks before the switch: coverage 95.9% vs 77.9% for the old file; identical to the old scraper on every row it had loaded after 2K27 launched (the differences were August/undated rows).
- **The bulk (keyed) path has never run: it was untested from Claude's sandbox (no key visible) — only the public path, the 401 fallback and the guards were exercised.**
- Alias rule: keys in `NBA_NAME_ALIASES` are the *rating source's* name → nba_api's name (Herb Jones → Herbert Jones, Ron Holland → Ronald Holland II, `Egor Dёmin` has a Cyrillic ё).

**CourtView:** substitution pool is fully positionless (any bench player fills any zone); single-level zone-keyed undo, cleared on team switch. Team/Position filters use NFL depth-chart's multiselect pattern. `computePositionRanks()` ranks by 2K rating within position group (`PF 3/46`; no rating → no badge). `.subs-pop` is still the older 184px convention (others are 200px) — bring it in line if NBA subs get revisited. `var(--text-muted)` (not `--text-dim`) for `.bench-stat-label`/`.popup-pos`/`.popup-stat-label`.

**Schema:** `nba_players_master.json`: `player_id, name, team, position, jersey_number, height, weight, ppg, rpg, apg, mpg, games_played, games_started, rotation_status, rotation_source, depth_rank, overall_rating, contract_salary, contract_years_remaining`. Coverage: contract salary ~75%; rotation from nbadepthchart.com ~75%, rest `mpg_derived`.

---

## MLB (DiamondView)

**Files:** `mlb/diamond-view.html`, `mlb/player-table.html`. Pipeline: `scrape_roster.py` → `scrape_stats.py` → `scrape_show_api.py` → `build_mlb_match.py` → `export_mlb_master.py`.

- **Roster (`rosterType=40Man`, ~1,360):** each row carries its raw status code as `roster_status` (`A`, `40M` non-active 40-man, `D60/D15/D7/D10` injured list, `RM` reassigned, `PL` paternity); `injured` is true for `D<number>` only. Traded/released players on no 40-man are absent. DiamondView: injured players are never natural starters, never in sub pools or the batting-order/pitching-staff lists; anyone with 0 PA and 0 IP (`hasPlayed()`) is also excluded from pools/lists. TableView shows all 40-man players with the red INJ tag.
- **Empty-slot fallback (`computeLineup()`):** manual subs → natural starters → any still-empty field zone (except P) filled by the healthy, not-yet-placed batter with the most PA (never a pitcher or the two-way player). Fill-ins get a muted italic position label, a `title` note and a gold note in the sidebar header; "No Player" only if no eligible batter exists.
- **Ratings (`scrape_show_api.py`):** raw snapshot `mlb/data/show_api_live.json` + `mlb/data/ratings_meta.json` (`ratings_as_of` = newest `roster_updates.json` date) → DiamondView "Ratings as of <date>". **Matching (`build_mlb_match.py`):** normalized name + team (`ARI→AZ, WAS→WSH, OAK→ATH`); tiers are team-scoped and need exactly one card: exact, `NAME_ALIASES` (Leo Rivas, Cam Cauley, Robby Ahlstrom, Leo Balcazar), hyphenated-surname truncation; last, if the API team is "FA" and the name is unique among Live cards, a name-only match that must also agree on bats/throws and pitcher-vs-hitter (`fa_agrees()`, ~168 players). Same-name players only match on name + team. Unmatched → `overall_rating: null` + `mlb/data/unmatched_mlb.txt` (6 on the last run: five without a Live card, one rejected by the FA bats check). A first spot-check of the FA tier found no wrong-person matches.
- **Rating dot** shows `overall_rating`; position label `.player-rank` uses `var(--text)`; popover/bench tags sized up.
- **TableView:** Overview has a Rating column and sorts by it; Batting has BABIP, Pitching has K/BB (both wired into `FLOAT_SORT_COLS` because statsapi sends strings). Sidebar behavior: see the sidebar pattern. `.court-canvas` height is fixed via `--fh`; the page never scrolls at 1280×900/1920×1080.
- **Schema:** `mlb_players_master.json`: `player_id, name, team, team_abbr, position, position_group, position_group_source, player_type, jersey_number, height, weight, bats, throws, batting_stats, pitching_stats, roster_status, injured, match_source, overall_rating`.

---

## NHL (IceView)

**Files:** `nhl/ice-view.html`, `nhl/player-table.html`. Pipeline: `scrape_roster.py` → `scrape_stats.py` → `scrape_ratings.py` (nhlratings.net via ScraperAPI, cloud) → `build_nhl_match.py` → `export_nhl_master.py`; `season_utils.py` resolves roster/stats seasons from the API (not the date). There is **no persisted raw ratings snapshot** (scrapes live), so NHL can't get the raw-vs-matched audit MLB/EPL/NBA got.
- **D1/D2:** both defense zones share `positionCode 'D'`; `getStarter('D2')` excludes whoever D1 naturally resolves to when D1 has no manual override (D1 = highest `toiPerGame`).
- **Rink:** `ICE_ZONES` order matches the drawn rink — goalie in the crease (y 7), defense y 26, forwards y 50–55. The sub popover positions itself with `getBoundingClientRect()`.
- **Subs/bench:** `subEligiblePlayers()` and `renderBenchList()` exclude anyone with 0 GP this season (prospects, long injuries). `.player-name` light text is nearly invisible on the pale ice — keep that surface in mind for label colors.
- **TableView:** Overview Rating column + default sort; Skaters has S%; Goalies default-sort by Save%.
- **Schema:** `nhl_players_master.json`: `player_id, name, team_abbr, position_group, position_code, jersey_number, shoots_catches, height_in_inches, weight_in_pounds, birth_date, birth_city, birth_country, birth_state_province, skater_stats, goalie_stats, stats_source, overall_rating, potential` (potential `Low/Med/High`, not shown anywhere).

---

## EPL (PitchView)

**Files:** `epl/pitch-view.html`, `epl/player-table.html` (Overview/Stats/Fantasy/Advanced). Pipeline: `scrape_fpl.py` + `shared/scripts/scrape_ea_fc.py epl epl/data/ea_fc_epl.json` → `build_epl_db.py` (loads `fpl_players` and `ea_ratings` into DuckDB) → `build_epl_match.py` → `export_epl_master.py`. `soccer_name_utils.py` holds `SOCCER_NAME_ALIASES` (keys = the base population's name; e.g. `Dominic Solanke-Mitchell` → `Dominic Solanke`).
- **Base population is FPL** (live roster). `standard_pos` is EA's granular position (ST/CAM/CDM/LB/CB…); `position_group` is FPL's coarse `GKP/DEF/MID/FWD` (deliberately the reverse of NFL's naming).
- **Matching** (`EPL_TEAM_ALIASES`: only 5 variants — Bournemouth, Ipswich Town, Leeds, Man City, Newcastle): exact name+team → unique name-only → team-scoped token overlap (same first token + shared further token) → team-scoped token-set equality (name-order swaps: Mitoma Kaoru, Endo Wataru) → **league-wide token match with a position-group check** (`find_league_token_match()`, `EA_POS_TO_FPL_GROUPS`; used because EA's club label lags transfers and FPL carries longer legal names — Emiliano Martínez, Daniel Muñoz, Evanilson). Each EA card is indexed under first+last and `commonName`; tiers dedupe by card id. Result: 558/668 (83.5%) — the 110 unmatched mostly have no EA Premier League card (transfers listed under other leagues); 37 had minutes at the last check.
- **Formation switcher:** `FORMATIONS` registry (4-3-3, 4-4-2, 3-5-2, 3-4-3, 4-5-1, 5-3-2), `groupForZone()` derives the group from the zone-name prefix, `setFormation()` wipes `manualStarters` (zone names don't map across formations); `computeStarters()`/`rankedGroupPool()`/`subEligiblePlayers()` iterate whatever `ZONE_ORDER` is current. Persisted in `localStorage` key `fieldview_epl_formation`. It can't model sub-role nuance (winger vs striker) — the data's granularity.
- **Advanced tab:** xG (`expected_goals`), xA, ICT Index, Defensive Contribution, Tackles from the FPL `stats` block (string fields parsed at load).
- Pitch `.left-col` 560px; subs popover 200px with scroll.
- **Schema:** `epl_players_master.json`: `player_id, name, web_name, team, team_short, position_group, standard_pos, overall_rating, sofifa_id (= EA card id), match_source, stats{…}`.

---

## MLS (PitchView)

**Files:** `mls/pitch-view.html` (same formation switcher as EPL; `groupForZone()` returns `G/D/M/F`; `localStorage` key `fieldview_mls_formation`), `mls/player-table.html` (Overview/Stats/Advanced). Pipeline (no DuckDB layer): `scrape_espn_roster.py` + `fetch_asa_stats.py` + `shared/scripts/scrape_ea_fc.py mls mls/data/ea_fc_mls.json` → `build_mls_match.py` (JSON → `mls_player_match.json`) → `export_mls_master.py`.
- **Base population:** ESPN's roster minus 47 non-club rows (`MLS All-Stars`, `Liga MX All-Stars`, stray `team_id 359` = Arsenal's EPL squad). `ESPN_TO_ASA_TEAM` (4) and `ESPN_TO_EA_TEAM` (11) map team names. Matching tiers mirror EPL (exact, unique name-only, token overlap, token-set), with the EA cards also indexed by `commonName`. ASA joins separately (a transferred player's ASA row has a list `team_id` → team left unresolved). The league-wide EPL tier was simulated for MLS and recovers only 1 player, so it was not added.
- **Numbers:** ratings 777/1,069 (72.7%) — 777 of EA's 806 MLS cards used, the rest not on ESPN's roster; 292 unmatched, 115 with minutes, mostly no EA card. EA's MLS ratings differ a lot from the old sofifa snapshot (17% identical; Messi 86 → 89) — EA's live page is the source. Unmatched list: `mls/data/unmatched_ea.txt`; ASA: `unmatched_asa.txt`.
- **TableView:** Overview has Age; Advanced has G-xG, xG+xA, A-xA, xPts Add (775 populated, the rest have no ASA match); Stats/Advanced hide keepers by default (tab sets the position filter to D/M/F; tick GK to add back); Position column sorts by the displayed label.
- **Schema:** `mls_players_master.json`: `player_id, name, team, team_abbreviation, jersey, age, height, weight, citizenship, position_group, standard_pos, overall_rating, sofifa_id (= EA card id), sofifa_match_source, asa_player_id, asa_match_source, stats{…}`; `position_group` is ESPN's single-letter code.

**EPL/MLS shared (`scrape_ea_fc.py <epl|mls> <path>`):** one snapshot per league (`epl/data/ea_fc_epl.json`, `mls/data/ea_fc_mls.json`: men's cards `id, first_name, last_name, common_name, overall_rating, team_name, position, league` + `fetched_at`, `source_total`) and `ratings_meta.json` beside it — per-league so the concurrent jobs never edit the same file. `ratings_last_changed` is diff-based; PitchView shows "Ratings as of <date>" (nothing if missing); popup row label is "EA FC".

---

## Statistics research (which stats best represent player value)

- **NFL:** Madden ratings are UI candy, not evaluative. Free evaluative stats: QB EPA/play + CPOE + success rate (nflverse pbp), NGS time-to-throw (style stat), ESPN QBR; RB RYOE; WR/TE target share + air yards; EDGE/DI pressure rate over sacks; CB/S has the weakest free data (targets-against/completion-allowed from pbp is the best proxy).
- **OL (investigated Sept 2026):** individually attributed OL performance is the thinnest anywhere. ESPN's PBWR/RBWR exist but only top-10 leaderboards and team-level are public — **don't try to scrape a full table**. "Yards before contact" is an RB stat, not OL. FTN charting is play context, not lineman grading (`is_qb_fault_sack` is useful for team-level sack rate). Free proxies: penalty rate, snap_pct/games started, draft capital, contract. Real grades are PFF-paywalled (PFF+ ~$100–120/yr; Pro ~$200 adds an API) — **decision: not pursuing**; revisit deliberately.
- **QB ruled out:** Big-Time-Throw/Turnover-Worthy rates (PFF human grading, no free equivalent); QBERT (Substack project, paywalled charts, no data feed).
- **Cross-sport:** "genuinely evaluative metric" (NFL pressure rate, NBA BPM/VORP, MLB WAR/xwOBA, NHL GAR/xG) is its own future project needing new sources; NFL's QB/RB/WR/TE advanced work is the first partial step.

---

## Conventions & gotchas

- **TableView shapes:** (1) uniform box score tabbed by category (NBA); (2) position-gated disjoint stats, row-filtered by tab (NFL/MLB/NHL); (3) metric-lens switching (EPL/MLS); (4) cosmetic rating vs genuine evaluative metric — not yet separated anywhere.
- OurLads codes: `ARZ` (not ARI), `JAX` (not JAC). Team JSON may be a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`.
- Minimal targeted edits only; match existing style; no speculative features; plain HTML/CSS/JS; copy `ratingColor()`/`pctColor()` verbatim rather than rewriting.
- **Substitution popover** (`.subs-pop`/`.subs-dot`/`.subs-name`/`.subs-mpg`) is 200px / 22px dot / 13px name / 11px text with `max-height:280px; overflow-y:auto` on NHL/MLB/EPL/MLS; NBA is still 184px.
- **Scraper hardening:** test a real header set with plain `requests` before `curl_cffi`; paid proxy only if a full-scale run still won't clear. **Graceful degradation:** keep the last-known snapshot on a failed pull (and show its date); EPL/MLS's dashed "No Player" placeholder is the frontend model.
- Python scripts may print non-ASCII (player names): on Windows set `PYTHONIOENCODING=utf-8` and open files with `encoding='utf-8'`.

---

## Known Outstanding Bugs (verified 2026-10-24 unless marked)

**Open — owner action needed**
- **NBA 2K Task Scheduler job is still enabled and fights the cloud job.** It ran again today (~09:21, result 0) after the nba2kapi switch, re-scraped OKC/BOS/ORL from 2kratings.com, overwrote 51 API-sourced rows and rewrote the file's formatting — **uncommitted, live site unaffected**. Disable (not delete) the job and `git checkout --` the two NBA 2K files before anything commits them.
- **`NBA2KAPI_KEY` bulk path is unverified.** Confirm the first cloud run logs "via /api/players/bulk" (and that the secret exists).

**Open — data**
- **NBA `nba_stats.json` is stale: last committed 2026-08-11** (local-only `fetch_stats.py`, nothing commits it). Rosters/teams are 2.5 months old and the stats are last season's; 92 nba2kapi cards (mostly 2026 rookies) can't match because they're not in this universe. Fix = a cloud-friendly NBA stats source (Roadmap #2).
- **Westbrook is 42 in nba2kapi's "Free Agency" bucket** (81 on SAC in the old file) — possibly a wrong/placeholder card; unchecked, API value kept.
- **26 players lost their Madden rating** in the switch to EA (verified: no EA card under any spelling or team; 2 depth-1: Art Green ARZ CB, Chris Braswell HOU ED). Not a matching bug.
- **`index.html`'s NFL player-count tile sums the per-team files (2,501 rows) instead of the master (2,369).** The per-team files carry 604 rows with `standard_pos 'DEF'`; harmless to FormationView/TableView (they read the master, 0 `DEF`).
- **NFL section labels not flagged injured:** `PS/IR` (10, practice-squad injured reserve — a likely candidate), `SUS` (4), `LEFT` (1), `CE` (1, ambiguous; Terrion Arnold SEA is dropped for having no Madden row).
- **NFL `.field-outer` scroll bug (cause 2) is still unapplied:** `.field-outer` still uses `min-height: calc(100vh - 52px)`, so if the formation-bar/field/legend need more than the viewport (e.g. the legend wraps to two lines) the page grows past it. Spec'd fix: `min-height` → `height`. (Cause 1, the `.players-layer` 1000px floor, is fixed with `min-height:0` on `.field-canvas`.) The Madden legend move into the formation-bar row **is** in place.
- **NFL `attainment`** (draft round/status) is populated for 2,108 of 2,369 (suffix is read from the `dc-key` span).
- **NFL first-initial stats fallback** dropped a handful of real nickname matches (Dru Phillips, Sai'vion Jones, Jaylon Jones, Dalton Johnson, Mike Reid) — deliberately not chased.
- **MLB/EPL/MLS unmatched lists:** MLB 6 (`unmatched_mlb.txt`), EPL 110, MLS 292 (`unmatched_ea.txt`) — mostly no EA/Live card.
- **NHL (unverified):** `season_utils.resolve_seasons()` was fixed in 7013d4d against a mocked manifest only; confirm `roster_season` resolves to 20262027 by itself once the NHL publishes real standings. NHL has no "ratings as of" caption and no raw ratings snapshot.
- **`run_all.bat`** has never completed in one sitting (low priority).

**Cloud runs not yet observed** (all verified only via local/standalone runs): the EA Madden step in the `scrape` job, the EA FC steps in `scrape-epl`/`scrape-mls`, and the nba2kapi step in `scrape-nba` — first scheduled run is Tuesday 2026-10-27.

**Recorded decisions (not bugs):** injured-list and reserve players are valid substitution candidates in NFL FormationView (INJ badge, `INJURED_SLOTS` unused); EA is the Madden/FC source of truth even where it disagrees with older snapshots; the Free Agency bucket's API ratings are kept as-is.

---

## Roadmap

**Up Next (in order)**
1. **Confirm the Tuesday 2026-10-27 cloud runs:** the NBA log shows the nba2kapi bulk path ("via /api/players/bulk", fresh `ratings_last_changed`); the Madden EA fetch ran (all 32 teams carry the run's date, iteration label present); the EPL/MLS EA fetches ran clean. (And the owner-side steps above are done.)
2. **NBA stats-source recon:** a cloud-friendly, richer source than `fetch_stats.py` (stats.nba.com blocks GitHub runners) — TS%, usage, rebound/assist rates, ideally BPM. **Check ESPN's API first.** This also fixes the stale `nba_stats.json` universe.
3. **Port the sidebar pattern to NBA** (advanced rows, sub comparison, `?player=`, Reset to starters) once #2 provides the stats.
4. **NFL draft prospect installer** (target December, before mock-draft season): pick a prospect from a big board, drop him into a FormationView slot with an R badge and a projected Madden from a pick-number → rookie-Madden curve fit on current rookies (`load_draft_picks()` + Madden). Not a full simulator; team-need auto-mock only if phase 1 gets used. Big-board source not yet investigated.
5. **NFL Opponent View phase 2** (your offense vs a real opponent's defense) **+ the ~22-card density/sizing pass**.

**Backlog**
- Flag `PS/IR` as injured (and decide on SUS/LEFT/CE); fix the `.field-outer` scroll bug; fix the home-page NFL count tile.
- Port the sidebar to NHL/EPL/MLS if wanted; add an NHL "ratings as of" caption.
- NHL TableView: expose `evGoals`, `evPoints`, `faceoffWinPct` (already in the data). More `nflreadpy` sources: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()`.
- A real raw-vs-matched ratings audit for MLB (raw snapshot exists) and NHL (needs a persisted snapshot).
- "Genuinely evaluative metric" project (see Statistics). Confirm a full `run_all.bat` run in one foreground sitting.

**Future State:** ReView (replays, highlights, box scores, tweets, podcasts) after every sport's FieldView/TableView are dialed in; mobile responsiveness pass (desktop-only for now); a real custom domain if AdSense is ever pursued; real per-game soccer formations (needs a match-day lineup provider and a tighter freshness model — parked, not the same as the shipped formation switcher).

**Dropped:** NBA Big/Wing/Guard bucket UI (superseded by positionless subs); OOTP as an MLB ratings source (legal exposure); historical rating trends and player comparison (outside scope); the `www.fieldview.com` CNAME (domain owned by someone else).

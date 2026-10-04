# FieldView — Claude Code Context

Multi-sport intelligence platform. Live at `jwalluww.github.io/fieldview/` (GitHub Pages).

Repo: https://github.com/jwalluww/fieldview (public)

Purpose: each sport gets a FieldView (players on the field/court/pitch in their real positions, with substitutions) and a TableView (sortable/filterable stat table). A future ReView (replays, box scores, highlights) comes after every sport's FieldView/TableView are dialed in — not started yet, tracked in Roadmap only.

**Current status, verified against the real repo (2026-09-26), not carried forward from any prior summary:**
- **All six sports** — FieldView + TableView shipped, real data, real GitHub Actions automation (`scrape.yml`'s six jobs). **All six sports' FieldView dots now show the video-game overall rating** (0-99, shared `ratingColor()` gradient) — NHL and MLB switched over this pass from stat-driven dots (points/save%, AVG/ERA); NFL/NBA/EPL/MLS already worked this way.
- **This pass's focus**: a large backlog of real bugs and small features surfaced by actually looking at every FieldView/TableView page, plus a new NFL feature (Opponent View phase 1) and a new EPL/MLS feature (formation switcher). See each sport's section below for specifics — this intro doesn't repeat them all.
- **Latest pass (2026-09)**: NFL got a position-aware Advanced tab, real QB/RB/WR/TE advanced stats, safety/nickel and reserve-row position fixes, a wrong-teammate stats-match fix, and Madden freshness tracking (all detailed in the NFL section). MLS's TableView got its long-owed review. **Several NFL fixes are verified locally but only take effect on the next Tuesday pipeline run** — see Known Outstanding Bugs.
- **ReView** — not started, any sport.

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no build tools
- Backend: Python 3.11 scrapers, `duckdb`/`pandas` for the match/join layer
- Hosting: GitHub Pages (100% static — no server, no backend process at request time)
- Automation: GitHub Actions, `.github/workflows/scrape.yml`, one workflow file holding six jobs (`scrape`=NFL, `scrape-nba`, `scrape-mlb`, `scrape-nhl`, `scrape-epl`, `scrape-mls`), all triggered by a **single shared schedule** (`cron: '0 10 * * 2'` — every Tuesday 10am UTC) plus manual `workflow_dispatch`. No per-job stagger exists — all six fire at the same time.
  - **Push resilience**: all six jobs do `git pull --rebase && git push` instead of a bare push, added after a real collision was traced to the repo owner's own manual local commit script (an old morning `git add . && commit && push` habit, since retired) landing mid-run.
- Local orchestration: `run_nfl.bat` / `run_nba.bat` / `run_mlb.bat` / `run_nhl.bat` / `run_epl.bat` / `run_mls.bat` each run that sport's full pipeline end-to-end locally (fail-and-continue per step, never git add/commit/push); `run_all.bat` chains all six. Most are now redundant for regular use since every sport has a real cloud job, but stay valuable for testing script changes before pushing — this is how every pipeline fix this session got verified pre-cloud.
  - **Three pieces of data are genuinely load-bearing locally, not just redundant**, and must NOT be deleted or allowed to stop running: NFL Spotrac contract data (never wired into the cloud `scrape` job), NBA real stats (`fetch_stats.py` — stats.nba.com blocks the GitHub-hosted runner's IP specifically, permanent structural limitation, not temporary), NBA 2K ratings (`scrape_2kratings.py` via Task Scheduler — local by choice, cloud has no fallback for this data at all).
  - Pattern for retiring a redundant local job: disable, don't delete (see NHL's ratings Task Scheduler job as the precedent) — costs nothing to leave in place, everything to rebuild from scratch if a cloud path ever breaks.
  - **The full six-sport `run_all.bat` chain has still never completed in one sitting** — two attempts were killed by session/host restarts before finishing, not a pipeline error. Lower priority now that every sport refreshes independently via its own cloud job regardless.
- Task Scheduler (Windows, local machine only): `FieldView NBA 2K Ratings Scrape` (daily 09:15) is Enabled/Ready. `FieldView NHL Ratings Scrape` is Disabled (not deleted) since NHL ratings run via the cloud job instead.
- **Data persistence architecture, why JSON and not "just DuckDB":** the site is 100% static (GitHub Pages, no server) — a browser can only ever `fetch()` a static file at request time, it cannot query a database that isn't there. DuckDB-in-the-browser (DuckDB-WASM) is technically possible but was deliberately rejected as a founding principle ("JSON as the data format, not client-side SQL engines") — at a few thousand rows per sport, plain JS array `.filter()`/`.sort()` already does everything a SQL engine would, without adding a WASM dependency to every visitor's page load. DuckDB's real, legitimate role in this project is purely a **build-time join engine** — matching disparate scraped sources (OurLads+Madden+OTC+Spotrac for NFL, roster+stats+ratings for MLB/NHL) is fundamentally a multi-table join problem, and SQL is a better tool for that than hand-rolled Python dict-merging across 4-6 sources. Once the pipeline's join finishes, DuckDB's job is done and the flat result gets flattened into the JSON the frontend actually reads.
  - Every sport's `.duckdb` file is meant to be ephemeral — gitignored, rebuilt from scratch every pipeline run, never a source of truth. **Confirmed and fixed this pass**: MLB's and NHL's `.duckdb` files were the only two actually tracked in git (missing from `.gitignore`, almost certainly an oversight from when those two sports were built) — added to `.gitignore` and untracked (files left in place on disk, just no longer part of the repo).
  - Raw per-scraper JSON snapshots (distinct from both DuckDB and the final master JSON) exist for pipeline hygiene: caching each scraper's output independently means a broken match step can be fixed and re-run against the same cached raw data without re-hitting a live site.

---

## Site Infrastructure

**Custom domain — attempted, dropped**: a `CNAME` at the repo root once pointed `www.fieldview.com` at GitHub Pages, but this never resolved — someone else already owns `fieldview.com`. Site runs on the default `jwalluww.github.io/fieldview/` URL. Revisit only if a different domain is chosen.

**Analytics**: Google Analytics (GA4), `gtag.js`, Measurement ID `G-TP0M77Z31N`, present on every real HTML page in the repo.

**Monetization notes, factual not advisory**: AdSense has no minimum traffic requirement, but does require a real top-level domain, not a shared `github.io` subdomain. Premium networks (Mediavine, Raptive/AdThrive) gate by traffic instead — check each network's current site directly when actually approaching that point.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback, and diagnosing bugs against the live repo before writing a spec.
- Use Claude Code (VS Code chat panel) for implementation, real data verification, and live reconnaissance against external sites/APIs.
- **Reconnaissance against live external systems belongs in Claude Code, handed off as one broader investigation task** — splitting recon into one probe-per-question wastes round trips.
- **For real scripts, give Claude Code a precise spec with verified facts and named edge cases, rather than full verbatim code written blind in chat.** Chat can't execute or test what it writes. Real bugs and necessary follow-on fixes have repeatedly been caught only because Claude Code tested its own code against real data rather than trusting it on inspection (see Key Cross-Sport Learnings for specific examples).
- **Long-running local verification (e.g. a full multi-sport `run_all.bat` pass) should be run in the foreground, watched directly by the user** — backgrounding it risks the process getting silently killed by a session/host restart mid-run, which has happened twice with zero pipeline-level cause.
- Chat's real value-add: cross-cutting consistency a per-file view might miss, and catching when a "documented as shipped" claim doesn't match the live repo (this has happened multiple times this project — always verify a diff before trusting a summary, including this chat's own past summaries).
- Start a new chat when switching to a new sport or major new feature area.
- **Every Claude Code instruction block from this chat is delivered as a single fenced code block** (copy-pasteable in one motion), and explicitly restates — every time, regardless of whether CLAUDE.md was pasted this session — that Claude Code must:
  1. End its response with a summary of changes in relation to what was asked, plus a plain-language TLDR (label it `TLDR:`, a few sentences, no jargon or file names, something a non-technical read could follow).
  2. Commit and push when done, and say explicitly whether the change is live immediately (frontend files) or needs the next pipeline run to take effect (Python/data pipeline files).
- Chat verifies every Claude Code diff against the live repo after it's pushed, before accepting the summary at face value — this has repeatedly caught real discrepancies between what was reported and what actually shipped (unpushed commits, scope creep, an incorrect claim of "already fixed").

---

## Key Cross-Sport Learnings

- **"Verify the real field/column names before writing normalize logic" has paid off on every sport built so far**, including EPL/MLS: FPL's real `element_type`/`first_name`/`second_name` shape, ESPN's core-API athlete shape, ASA's real `itscalledsoccer` column names were all confirmed live before a matching script got written.
- **Silent bulk-endpoint truncation and pagination bugs are a recurring, not one-off, class of bug.** NFL/MLB's `/v1/stats` needed a bigger `limit`. NHL's `/stats/rest` hard-caps at 100 rows regardless of `limit`. sofifa's scraper assumed a wrong page size and silently double-fetched. **Lesson generalized: never hardcode a page-size increment from an assumption — increment by what the page actually returned.**
- **Anti-bot protection is not one problem with one fix.** theshowratings.com/2kratings.com/nhlratings.net all needed real work (TLS impersonation, and for MLB/NHL, a paid proxy via ScraperAPI). sofifa.com needed none of that — a complete `User-Agent` string alone cleared it. **Test the cheapest thing before reaching for TLS impersonation or a proxy.**
- **A numeric ID in a photo/asset URL can be a real join key, or a lookalike fake — verify against known real players by hand, in both directions.** theshowratings.com's photo URL embeds MLB's real `person_id`. nhlratings.net's superficially similar photo URL is actually the site's own WordPress post ID. sofifa's player-listing URL has two numbers and only the first is a real per-player ID.
- **When two or more real sources disagree on "who's on which team" or "which teams exist," that's real signal, not noise to average away.** NHL's roster-vs-stats disagreement (different-season snapshots), EPL's FPL-vs-sofifa 3-club squad lag, MLS's ESPN/ASA/sofifa team-count mismatch (fake exhibition clubs + one real defunct club never filtered) were all real, investigated, and explained rather than assumed away.
- **A per-zone-independent "pick the best player for this slot" function silently breaks the moment two zones share one candidate pool — and this bug class is easy to under-diagnose even after you've named it once.** EPL/MLS's `computeStarters()` was built single-pass specifically to avoid this. NHL's `ice-view.html` was *believed* safe because its forward trio (LW/C/RW) maps to distinct position codes — but its **D1/D2 zones share one identical `positionCode: 'D'` pool**, and this was missed in an earlier documentation pass that called NHL "harmless." Confirmed live: with no manual subs, D1 and D2 independently resolved to the *same* top-TOI defenseman on every single team, since neither zone's natural-fallback resolution excluded the other. Fixed by making D2's resolution aware of D1's natural pick (not just manual overrides). **Lesson sharpened: don't just check "does this pool get shared conceptually" — check whether any two zones in `ZONE_ORDER` literally share the exact same filter key, even ones that don't look alike (a rink's two D-slots aren't obviously "the same shape of problem" as soccer's 4 DEF slots until you look at the actual position-code map).**
- **An "unmatched" record frozen from a partial/trickle scraper can go stale forever if the retry logic only re-checks freshly-scraped populations.** NBA's 2K ratings scraper only re-attempts a match for teams randomly picked that day (3-team daily trickle) — a player whose team simply doesn't come up again keeps whatever `player_id` (including `None`) they had from their last scrape, even though the match target (`nba_stats.json`) updates independently and could start agreeing with a previously-failed match at any time. Confirmed concretely on Damian Lillard: both sources agreed on name+team, yet his rating stayed stuck as missing because Portland hadn't been freshly re-scraped since before that agreement existed. Fixed by re-attempting a match for every currently-unmatched record on *every* run (pure in-memory lookup against data already loaded, zero extra network cost) — not gated behind a fresh scrape at all. **Lesson: if a retry only fires alongside a fresh fetch, and the fetch is sampled/rate-limited/trickled, silently-stale failures are a structural risk, not a one-off — check whether cheap, no-network retries are being gated behind expensive ones for no real reason.**
- **A name-matching function's own documented design can be correct for its stated cases and still miss an entire class of failure it wasn't built for.** EPL's `find_token_overlap_match()` correctly handles three real documented name-format mismatches (abbreviated middle name, dropped surname, extra surname carried by sofifa) — all three share the same *first* name token, differing only in the tail. It requires first-word equality before checking further overlap, which is *why* it couldn't catch a genuine full name-order swap (FPL's "Mitoma Kaoru" vs sofifa's "Kaoru Mitoma") — neither name's first word matches the other's at all, so the function never even reaches its own overlap check. Fixed with a separate, final tier: exact token-*set* equality regardless of order, same ambiguity safety bar (team-scoped, only accepted if unambiguous). Confirmed this wasn't overfit to one player — the same fix caught two more real players with the identical pattern (Ao Tanaka, Wataru Endo) on the same run. **Lesson: "this function already handles name-format mismatches" isn't the same claim as "this function is order-independent" — check the actual gating condition, not just the general category of problem it was built for.**
- **A CSS variable that's "light text for a dark theme" can still be badly wrong on one specific surface if that surface breaks the theme's usual assumption.** Every sport's FieldView shares `.player-name { color: var(--text) }`, which reads fine against NBA's wood court, MLB's dirt/grass, and EPL/MLS's green pitch — all genuinely dark-ish surfaces. NHL's ice is realistically pale, and the shared light-text convention was nearly invisible against it (measured near-1:1 contrast). Separately, `var(--text-dim)` (a dark slate, `#404660`) turned out to be dark-on-dark against this project's own near-black surface colors (`#111318`/`#181c24`) in three different label elements across NBA's court/hover-card components — a more severe version of the same underlying "shared component, unusual surface" class of bug already seen in EPL/MLS's pitch labels earlier. **Lesson: a shared color convention is only as safe as its least-typical background — check the actual surface color, don't assume "it's the dark-theme text color, it'll be fine everywhere."**
- **Name-only keys and last-name-only fallbacks both misattribute to same-name/same-surname players — key by (name, team) and require a first-initial match.** Two bugs this pass, same shape: the Madden position-rank lookup keyed by name gave WR Justin Jefferson the LB Justin Jefferson's rank, and the stats scraper's last-name fallback gave OL Donovan Jackson S Theo Jackson's tackles (91 same-team clusters of identical stats surfaced it). **Lesson: any lookup keyed on a person's name is a collision risk; check for identical values across different people to find them.**
- **A "generic slot" label from a scraper is not a position.** OurLads' NB row (nickel) and its reserve-list labels (ED/CB/S/LB/OG/CE/SUS…) were being force-fit into a position by a default (`CB`, `DEF`); the real position needed a second source (Madden). Resolve by label where the label is unambiguous, by another source where not, and drop only as a last resort.
- **A silent fallback-to-last-known-data is only safe if staleness is visible.** Madden's per-team fallback kept 24 of 32 teams on August data for weeks with nothing on the site to say so; the fix is a per-team freshness date surfaced in the UI, not just a log warning.
- **A live re-run of the same pipeline will produce different real numbers than the original build, and that's expected, not a regression** — live sports rosters and third-party rating databases both update continuously.
- **Any table view with a separate mobile card-list rendering path needs every function that changes the filtered result set to trigger that mobile re-render, not just the sort function** — worth checking explicitly on every sport's TableView.

---

## NFL (FormationView) — shipped, Opponent View phase 1 live

### File Map
- `index.html` — home page, entry cards for all sports
- `nfl/nfl-formation-view.html` — formation view, **now shows offense and defense simultaneously** (see Opponent View section below)
- `nfl/depth-chart.html` — OOTP-style data table (tabs: Overview/Financial/Madden/Passing/Rushing/Receiving/Defense; Advanced tab removed in d04855b, see TableView)
- `nfl/data/advanced_meta.json` — sidecar written by `build_db.py` every run: `field_season` (each offense advanced field -> the season its value actually came from, read from the loaded source's own `season` column *after* any SEASON -> SEASON-1 fallback) and `league_max_games` (season -> most completed regular-season games any team has played, from `load_schedules`). A season only gets a `league_max_games` entry if its volume loaded, so a failed load leaves the frontend gate inert instead of disqualifying everyone. In `NON_TEAM_FILES`. First committed from a real local run (all 16 fields 2026, `league_max_games` {2026: 4}).
- `nfl/data/madden_meta.json` — sidecar, per-team date (YYYY-MM-DD) of the last *successful* fresh Madden fetch; committed as `{}` and filled in by the pipeline (see Madden freshness below)

### Scripts (`nfl/scripts/`)
- `scrape_depth.py` — OurLads depth chart scraper. `SLOT_MAP_34` now has a direct `'SLB': ('LOLB', 'EDGE')` entry (see Seattle SLB Mapping below), plus a general cross-scheme fallback in `enrich_positions()` for any other team whose OurLads page mixes 4-3/3-4 label conventions.
- `scrape_stats.py` — **the last-name-only fallback now also requires a matching first initial** (or the `A.Rodgers`-style short key). Last name alone attached a same-team teammate's stats to a different player (OL Donovan Jackson carried S Theo Jackson's tackles; QB Kyle Allen carried Josh Allen's passing line; a tackle carried a kicker's field goals). A local before/after run dropped 49 wrongly-attached stat blocks; a handful of real nickname matches (e.g. Dru Phillips) may have been lost too — an honestly empty stat beats a wrong one.
- `scrape_madden.py` — same retry/cooldown/fallback-to-last-known-rows behavior, **plus it now writes `nfl/data/madden_meta.json`** (only teams fetched fresh get today's date; a team that fell back to old rows keeps its old date or has none). `build_db.py`'s `NON_TEAM_FILES` skips the sidecar.
- `scrape_otc.py`, `scrape_contracts_spotrac.py` — unchanged.
- `build_db.py` → `build_match.py` → `export_master.py <output_path>` — same pipeline shape. **`build_match.py` now joins Madden *before* GSIS matching** so it can fix positions (see Position fixes below), and `export_master.py` reads `standard_pos` from the match table (`pm.standard_pos`), not the raw scrape (`op.standard_pos`).
- `build_master.py` — not run standalone in production, kept because `build_match.py` imports its functions. ****`build_madden_pos_ranks()` is now keyed by (name, team), not name alone** — two different players can share a name (Justin Jefferson WR/MIN and LB/CLE) and the name-only key handed the WR the LB's "50/88 MIKE" rank badge; `load_madden()`/`load_madden_from_db()` carry a `team` field for this. `NAME_ALIASES` now includes `'Greg Rousseau': 'Gregory Rousseau'`** (his real Madden-scrape name; same bug class as the earlier Surtain/Woolen fixes). **`years_pro` computation is now clamped to a minimum of 0** — a player whose `entry_year` is the season that technically hasn't "started" yet by `get_current_season()`'s Sept 1 cutoff (e.g. drafted into the upcoming season, pipeline runs in late August) was computing a nonsensical negative years-of-experience; the Sept 1 cutoff itself is untouched since it's correct for stats-season purposes. **A new `find_roster_gsis_for_ol()` function recovers age/draft_year/college for OL specifically** — see OL Bio Recovery below.
- **Offense advanced stats: season + volume (for the sample-size gate).** Sources: QB `epa_per_play`/`success_rate` from nflverse pbp (`load_pbp_cached`), `ngs_time_to_throw`/`cpoe` from NGS passing, `qbr` from ESPN (`scrape_qbr.py`, which now writes the season ESPN actually served into each record from `content.currents.seasonAndType`); RB `ryoe_per_att`/`box_rate` from NGS rushing, `yac_per_att`/`broken_tackle_rate` from PFR rush(+rec); WR/TE `adot`/`air_yards_share`/`avg_separation`/`yac_above_expectation` from NGS receiving, `drop_rate`/`broken_tackle_rate_rec` from PFR rec; `target_share` (RB/WR/TE) from `load_player_stats(summary_level='reg')`. Each has its own SEASON -> SEASON-1 fallback in `build_db.py`. Every player now also carries `adv_volume`: `{"<season>": {"att", "car", "tgt"}}` for each season in `field_season`, regular season only, joined by `gsis_id` from `load_player_stats` (`adv_volume` table -> `build_match.py` -> `export_master.py`); no `gsis_id` or no row -> season omitted (never zeros), a player with none gets `{}`.
- **Qualifier rules (frontend gate, per team game, G = `league_max_games[S]`, S = that field's season):** QB fields need `att >= 14 x G`, RB fields `car >= 6.25 x G`, WR/TE fields `tgt >= 1.875 x G`. Gated by position group, not field. Unqualified players are excluded from every percentile population and show raw value + definition + a muted "low sample" tag, no bar. The gate is inert when `advanced_meta.json` is empty or a player has no `adv_volume` key (pre-pipeline data); once the key exists, a player with no volume for S is unqualified. Defender stats are unchanged (already gated in the pipeline).
- `name_utils.py`, `season_utils.py` — unchanged.

### OL Bio Recovery (build_master.py)
Root cause: `find_gsis()` hard-skips OL entirely (`if standard_pos == 'OL': return None, None`) — this blocks both the primary crosswalk *and* the fallback `roster_df` path, so age/draft_year/college (all keyed off a resolved `gsis_id`) could never reach an OL player. Confirmed live before the fix: 0 of 304 OL players had age, 100% correlated with 0 GSIS matches. Fixed with an independent name+team match against nflreadpy's own roster data (which does have a real `gsis_id` for OL players — our own pipeline just never looked it up for them) via `_match_in_df`'s existing 95%/80% confidence tiers, feeding the recovered `gsis_id` into the *same* `entry_year_by_gsis`/`college_by_gsis`/`birth_date_by_gsis` dicts every other position already uses — no new lookup dicts, no change to `entry['gsis_id']` itself (so `match_source`/`match_confidence` keep accurately reporting that OL was never primarily GSIS-matched). Verified via a controlled before/after test: 302 of 304 OL players gained real age/draft_year/college/years_pro, zero non-OL players affected, five real linemen spot-checked by hand against known facts (Dion Dawkins, Charles Cross, Grey Zabel, Austin Corbett, Lloyd Cushenberry — all correct). **Not yet reflected in a live pipeline run's committed numbers** (see Real current numbers below, which predate this fix).

### Seattle SLB Position Mapping (scrape_depth.py)
Root cause: Seattle is scheme-tagged "Base 3-4" on OurLads (`is_34 = True`, selecting `SLOT_MAP_34`), but their individual player rows still use 4-3-convention linebacker labels (SLB/WLB/MLB) — `SLOT_MAP_34` had no `SLB` key at all, so the lookup fell through to a generic "unknown position" branch tagging affected players `standard_pos: 'DEF'` — not one of the 10 valid position codes anywhere else in the schema. Fixed in two stages: (1) a general cross-scheme fallback in `enrich_positions()` for any team whose primary scheme-map lookup fails (checks the *other* scheme's map before giving up), which correctly promoted these players to `standard_pos: 'LB'` but landed them on a generic `'SAM'` slot that doesn't exist in `FORMATION_COORDS.defense.base34`; (2) a precise fix specifically for Seattle — since `RUSH` already claims `ROLB`, `WLB`→`ILB_L`, `MLB`→`ILB_R`, the remaining `SLB` player is structurally the team's *other* outside linebacker, not a generic backer — added `'SLB': ('LOLB', 'EDGE')` directly to `SLOT_MAP_34`. Verified: all 4 of base34's real slots now uniquely fill for Seattle (Demarcus Lawrence/ROLB, Uchenna Nwosu/LOLB, Drake Thomas/ILB_L, Ernest Jones IV/ILB_R), zero regression on other 3-4 teams (BAL spot-checked, produces byte-identical output). The general cross-scheme fallback from stage 1 stays in place as a safety net for any other team with a similar quirk not yet found.

### FormationView Opponent View — phase 1 (offense + defense simultaneously)
Previously the page required picking Offense *or* Defense via a unit toggle, one personnel package visible at a time. Now both units render together (~22 player cards), with two independent, always-visible personnel selectors instead of one shared toggle. Enabled by a fact already true of the coordinate data before this change: `FORMATION_COORDS`'s offense (y:57-80) and defense (y:8-43) zones never overlapped, and no position-code key collides between units — the underlying data model already supported this, it just wasn't being used that way.
- State: `currentOffPersonnel` ('11'/'12') and `currentDefPersonnel` (`base43`/`base34`/`nickel`/`nickel34`, auto-defaulted per team's real scheme) replace the old shared `currentUnit`/`currentPersonnel`.
- `renderFormation()` now builds and renders slots from *both* `FORMATION_COORDS.offense[currentOffPersonnel]` and `.defense[currentDefPersonnel]` in one pass via a new `buildFormationSlots()` helper.
- Personnel changes on one side no longer wipe `currentStarters` (the old `setUnit()` did this on every toggle) — a substitution on one side survives a personnel change on the other, verified directly (subbed a WR, changed defensive personnel, sub held; subbed the QB, changed offensive personnel, sub held).
- URL params changed from `?unit=&pkg=` to `?off=&def=`, both independently restored on page load and preserved across team switches (only the Nickel/Base *choice* is preserved across a team switch — `updateDefPersonnelButtons()` recomputes the correct scheme-specific key for the new team).
- **Deliberately deferred**: visual density/sizing with ~22 cards on the field at once wasn't addressed in this pass — agreed to look at it once actually visible rather than guess at spacing blind. Still open, see Roadmap.
- **Not yet built**: phase 2 (a real opponent-vs-opponent matchup — your team's offense against an actual opponent's defense) is still future, per the original roadmap sequencing.

### FormationView hover-card/INJ/card-width pass (d04855b, 1f72b97, 721c923, a49bada)
- Hover cards rebuilt to even-weight stat rows (QB/RB/WR-TE/defender blocks), hover-card widened to 300px. Red INJ badge added to both the on-field `.p-card` (small red corner badge) and the hover-card header (inline pill); injured players were also removed from the sub-pool exclusion (they're now valid sub candidates). Substitution no longer does a full `renderFormation()`: `selectSub()` does a targeted single-node replacement and refreshes other slots' hidden `.sub-dropdown` content in place. Shipped, d04855b.
- `.p-card`/`.p-pos-bar` width history: 105px → 88px (d04855b, wrong fix for a scroll bug) → 105px (1f72b97, reverted once the real cause was found) → 96px (721c923, final "shrink a bit" pass). Current committed value is 96px (verified). The mobile media-query size (72px) was never touched.
- Height/weight (hover-card meta line) and injury detail (body part + Out/Doubtful/Questionable designation, native `title` tooltip on both INJ badges) shipped in a49bada, via nflreadpy's `load_rosters()` and `load_injuries()`. There is no real "how long out" field anywhere free — don't build toward one. Pipeline-side, so live after the next pipeline run.
- **Madden legend moved:** the Madden Rating key now sits in the formation-bar row, right-aligned just above the field's top-right edge (no outline). The floating-box-inside-the-field version was tried and rejected.

### FormationView player sidebar (click a card)
Replaced the rich hover card. Hover now shows only name / position / Madden / INJ designation. Clicking a `.p-card` opens a 360px right sidebar (the field *pushes*, `.field-outer` gets right padding, and cards slim to 66px under 1500px so 22 cards never overlap; overlay mode was tried and dropped). Esc, the x button, a click on empty field, or a team switch closes it; the selected card keeps a cyan outline. **No hero stat**: the former hero is simply the first row of the Advanced Stats list.
- **Layout:** header (name/jersey/team/pos, Madden, age, height/weight, contract, INJ detail) -> Advanced Stats rows -> Season Stats grid -> Substitutes. Players with no advanced values skip the advanced section (OL show Snap% only).
- **Advanced rows:** raw value + percentile bar + one-line definition. Percentile = % of the same-`standard_pos` population beaten across all loaded players (ties half, lower-is-better inverted, population < 10 -> no bar), colored red -> amber -> green (`pctColor()`). Style stats (TTT, aDOT, Air Yd Shr, aDOT Allowed) get a neutral bar and descriptive text ("quicker than N% of QBs"). Offense stats are gated by the qualifier rules above.
- **Season Stats grid:** per-position keys from the `stats` block with derived Comp%/YPA/YPC/Y/Rec; the block spells some keys several ways (`SACK`/`SACKS`, `QB_HIT`/`QB HIT`, `INT`/`INTs`, `PBU`/`PD`), all handled.
- **Substitutes:** clicking one opens a starter-vs-candidate comparison (season-stat table with the better value in green, advanced rows with both players' bars and percentiles, no deltas); "Swap in" does the substitution, "Back" cancels. Cross-position pairs (NB slot CB vs S) compare shared stats only.
- **`?player=<player_id>`** is written while the sidebar is open (alongside `?team=&off=&def=`) and reopens it on load if that player is currently on the field for the loaded team; ignored otherwise, dropped on team switch.
- **Reset to starters** (header, next to the personnel buttons): `resetStarters()` clears `currentStarters` for both offense and defense in one go, keeps the current Off/Def personnel, and re-renders (the sidebar refreshes, or closes if its slot is gone). Hidden while there are no manual subs (`updateResetBtn()`, called from `renderFormation()` and `selectSub()`).

### TableView (depth-chart.html)
**Update (d04855b): the Advanced tab was removed.** Its stats were merged into the 4 position tabs behind a per-tab checkbox column picker, the stat-slot system went 7→17 columns, and the Receiving tab expanded to WR+TE. The Advanced-tab paragraph below describes the pre-d04855b design and is partly stale.

**Advanced tab now covers QB, RB, WR and TE with position-aware columns.** `VIEWS.advanced.pos = ['QB','RB','WR','TE']`; the column set follows the position filter (`advancedGroup()`): all-RB → RB set (RYOE/Att default sort, YAC/Att, Brk Tkl%, Box%, Tgt Shr%), WR and/or TE only → WR/TE set (7 columns, default sort Tgt Shr%), anything else (empty/mixed/QB) → QB set (EPA/DB, SUCC%, CPOE, TTT, QBR; default QBR). Two extra stat slots (`stat6`/`stat7`) exist for the 7 WR/TE stats. `applyFilters()` swaps columns and resets to that set's default sort when the group changes; nulls always sort last and a real 0 stays in place. Note the tab *opens* with all four positions selected, i.e. the QB fallback set. `loadAll()`'s allowlist carries all 11 RB/WR/TE advanced fields (WR/TE tracking-based fields are populated for only ~127 of 420 players).

The Passing/Rushing/Receiving/Defense tabs previously defaulted to sorting alphabetically by name — every other sport's position-gated tabs default to a real production stat. Fixed: each tab now defaults to its most meaningful stat (PASS_YDS, RUSH_YDS, REC_YDS, TKL respectively), sorted descending (`setView()`'s direction logic updated to match).

Separately, a real null-sort bug was fixed in `sortPlayers()`: the null-check included `|| av === 0 && sortCol !== 'depth'`, but no sortable column named `'depth'` exists anywhere in the file, so that exception could never fire — meaning `=== 0` was unconditionally treated as missing data on every sortable numeric column (age, cap, years_remaining, all five position-specific stat columns). A rookie with 0 tackles, or a player with 0 years left on a contract, was always sorted to the bottom regardless of direction. Fixed to match the correct convention already used everywhere else (`av == null || av === ''`).

### Position fixes (build_match.py) — verified locally, live on the next pipeline run
- **NB safeties.** OurLads' NB row is a nickel *slot*, not a position. `scrape_depth.py` tags every NB player `CB` (its Madden-based S resolution runs before Madden is joined, so it never fires), which made star safeties invisible to safety logic and blocked their GSIS match (crosswalk says `S`), so no age. Now: an NB-row `CB` whose Madden label is FS/SS/S gets `standard_pos: 'S'` (`standard_slot` stays `NB`); 15 players (Kyle Hamilton, Derwin James Jr., Jalen Ramsey, Caleb Downs, Quentin Lake, Nick Emmanwori, and others). A GSIS retry as `S` for any remaining unmatched NB `CB` is kept.
- **Reserve "DEF" rows.** 230 players had the invalid `standard_pos: 'DEF'` — OurLads' reserve/practice-squad rows use generic labels (`ED`, `CB`, `S`, `LB`, `OG`, `SUS`, `PS/IR`, `CE`, `LEFT`) that `scrape_depth`'s SLOT_MAPs don't cover. `RESERVE_LABEL_MAP` in `build_match.py` maps `ED→EDGE, CB→CB, S→S, LB→LB, OG→OL`; anything else falls to the Madden position (`MADDEN_POS_MAP`); no usable position → row dropped. Local run: 219 by label, 6 by Madden, 5 dropped; no `DEF` remains. Age coverage 86.6% → 95.2% overall (DEF rows 0/230 → 165/225). **`CE` is deliberately unmapped** — its 3 rows are mixed (Jonathon Cooper DEN = EDGE, Josh Jacobs GB = RB, Terrion Arnold SEA = CB), so it resolves via Madden, and Arnold has no Madden row and is dropped. Side effect: ~219 reserve players are now real CB/S/LB/EDGE/OL rows and appear in substitution pools.

### FormationView hover cards & substitution pools (live)
- **WR/TE card fix.** `buildHoverCard(p, pos)`'s `pos` is the *formation slot key* (`LWR`/`SWR`/`RWR`/`TE2`…), so `pos === 'WR'` never matched and WRs (and the 12-personnel second TE) got the generic card. WR/TE legs now branch on `p.standard_pos`; QB/RB legs were unaffected (their slot names equal their positions). WR/TE cards show the full 7-stat block (YAC Above Exp hero + Tgt Share, aDOT, Air Yd Shr, Sep, Drop%, Brk Tkl%) with tier dots/tooltips, identical to TE.
- **Sub pools.** `getSubCandidates()` filters by `standard_pos`. FS/SS slots always draw from every `S`; the **NB slot draws from `CB` + `S`**. Anyone already on the field is excluded (so Derwin at NB in nickel isn't offered at FS/SS, but is in base defense).
- **Defensive-stat display rule.** Defensive stat keys (`TKL, SACK(S), INT(s), PBU, PD, TFL, QB_HIT/QB HIT, FF`) render only for `EDGE/DI/LB/CB/S` (plus the legacy `DEF`) — in the hover card's generic stats block and, via `getStatVal()`, on the TableView Defense tab (display *and* sort). QB/RB/WR/TE cards use explicit keys and are unaffected; on the Defense tab non-defensive rows now show "—".
- **"Ratings as of" caption.** FormationView shows the selected team's `madden_meta.json` date beside the Madden legend ("Ratings date unknown" if that team has no date but the sidecar has others); depth-chart shows the oldest known date near the row count, with "(N teams older)" when not every team has a date. An empty/`{}` sidecar shows nothing; a missing file shows nothing (the browser still logs its own 404 line — the file is committed to avoid that).

### Madden freshness — real status
The scraper hits Cloudflare 202 challenge pages (a JS challenge plain `requests` can't pass) on a large, varying fraction of teams. A team that fails both attempts silently keeps its previous rows (by design), so stale rows persist. **Confirmed from the committed file (2026-09-22): only 8 of 32 teams had post-cutdown roster sizes (56-60 players); 24 still carried the ~74-player August snapshot.** A live re-scrape from a local machine hit 8 of 32 failures on a full run and 6 of 10 on a sampled run. The weekly Tuesday cron also trails Madden's own mid-week updates by a few days (e.g. Justin Jefferson 96 → 97; ~8% of sampled players differ by 1-2 points). No scraper fix yet — see Roadmap.

### Defender advanced stats (pipeline + FormationView card) — cards go live after the next pipeline run
- **Source and season rule.** PFR's season `def` table (`load_pfr_advstats_safe('def')`), which today falls back to **2025** (2026 isn't charted yet). Every rate uses that same season S (`def_advanced_season`, stored on each defender): `build_db.py` loads S's snaps (`def_snaps_season`) and TFL/PBU (`def_season_stats`, from nflreadpy weekly stats) alongside the PFR table (`pfr_def_stats`) — never the cached current-season snap counts, which are a different, partial season. **Snaps are filtered to regular season (`game_type == 'REG'`)**: the snap table also carries playoff games, and PFR/TFL/PBU are regular-season only, so unfiltered playoff snaps understated every playoff defender's per-100 by ~11% at the median (up to 71%).
- **Fields** (`build_match.py`, exported as floats; all null for non-defenders): `pressures_per100` (EDGE/DI), `sacks_per100` (EDGE/DI), `tfl_per100`, `tkl_per100` (EDGE/DI/LB), `missed_tackle_rate` (all five groups; = missed / (tackles + missed)), `comp_pct_allowed`, `rating_allowed`, `yds_per_target_allowed`, `adot_allowed` (LB/S/CB), `int_pd_per_target` = (INT + PBU) / targets × 100 (S/CB), `def_advanced_season`. **Gates:** per-100 stats null under 100 defensive snaps; coverage stats null under 10 targets; missed tackle rate null under 20 tackle attempts.
- **Card** (`buildDefAdvBlock()`, `DEF_CARD` layouts): EDGE/DI hero Pressures/100; LB hero Missed Tkl%; S/CB hero Rating Allowed; 3-col grid for EDGE/DI, 2x2 for LB/S/CB; compact line + "Advanced: <season>" caption; Madden in the header. Used only when the defender has at least one advanced value — otherwise the generic card, byte-identical to before. aDOT Allowed has no tier dot (it describes how he's tested, not quality). **Tier cutoffs are keyed `<stat>_<standard_pos>`** (e.g. `pressures_per100_edge`, `rating_allowed_cb`) — 33rd/67th percentile of qualified players (300+ snaps, or 10+ targets), `lowerIsBetter` for missed tackle rate, rating/comp%/yds-per-target allowed; `DEF_RANGES` holds the 10th-90th percentile for tooltips. **Tooltips cite the constant `DEF_CUTOFF_SEASON = 2025`** (the season the cutoffs were computed from), not the live `def_advanced_season`; offense tooltips are fixed strings and have no such issue. **If the cutoffs are ever recomputed, regenerate `STAT_TIERS`' defender block and `DEF_RANGES` together and bump the constant.**
- **The compact line (TKL/SACK/etc., snap %) comes from the `stats` block / current-season snap table (2026 partial), so it's prefixed with `<stats_season>: ` whenever that differs from `def_advanced_season`.**
- **Local coverage (depth-1 defenders with any advanced value):** EDGE 66/97, DI 81/97, LB 63/95, S 72/104, CB 83/116. Of the starters with none: mostly no 2025 PFR row (rookies, new arrivals, non-rookies with no 2025 charting, e.g. Aaron Donald), or no `pfr_id` and no PFR row by name; only ~6 are a real `pfr_id` matching miss (Jeremiah Moon, Jihad Ward, Elijah Ponder, Natrone Brooks, Tavierre Thomas, Travis Hunter); a few are under the gates.
- **NB retag follow-up:** the GSIS retry for NB rows now tries the *other* of `S`/`CB` (Jalen Ramsey lost his ID after the safety retag because the crosswalk lists him as CB).

### Injured-list players (IR / PUP / NFI / PUP-R) — verified locally, live on the next pipeline run
`scrape_depth.py` used to drop these OurLads sections entirely, so stars like Myles Garrett (now LAR, IR), Micah Parsons (GB, PUP), Laremy Tunsil (WAS, IR), Kerby Joseph and Brian Branch (DET, PUP) had no row anywhere. The rows use the same table layout as depth rows (each entry: jersey, name link, a `dc-key` span with a position such as `CB^`/`OLB^`). Now: `INJURED_SECTIONS` are kept and flagged `injured: true`; they fall through `enrich_positions()` as `standard_pos: 'DEF'` with `standard_slot` = the section label (`IR`/`PUP`/`NFI`), so `getStarter()` (which matches `depth === 1` **and** a real formation slot) can never field them; `build_match.py` resolves their position via `MADDEN_POS_MAP` (the same fallback as the DEF reserve rows) and **drops rows with no usable Madden position**; an injured-list row never displaces — and is replaced by — a real depth-chart row for the same player (dedupe). `getSubCandidates()` excludes `standard_slot` in `INJURED_SLOTS` so they are never substitution options. They appear in the TableView with the existing INJ marker (the table has no depth filter, nothing vanishes; the `ourlads_pos` column reads `IR`/`PUP`). Specialist labels (K, P, LS, KO, PK, H, PT, KR, PR) and `EXE`/`RES` stay skipped. Local scratch run: 264 injured-list rows league-wide (IR 230, PUP 26, NFI 8, PUP-R 0), 210 kept, 53 dropped (no Madden match, or a P/LS position); total players 2,136 → 2,346, age coverage 95.5% → 95.7%. **Possible improvement (not done): the OurLads `dc-key` span gives a position for all 264 rows and would rescue the ~53 dropped ones, but it uses labels (`DE`, `OG`, `OT`, `ILB`…) that would need their own map.**

### Real current numbers (2,786 total players — predates the OL bio-recovery fix above)
- GSIS-matched: 2,052 (73.7%); fallback slug ID: 734 (26.3%)
- Madden: 2,099 (75.3%) before the Rousseau alias fix — expect a small further bump once the pipeline re-runs
- `snap_pct`: 1,709 (61.3%) — OL alone: 302/503 (60.0%), real data-source ceiling
- `age`/`draft_year`: 2,030/2,040 pre-OL-fix — expect ~302 more of each once the pipeline re-runs live
- Spotrac remaining contract: 2,575 (92.4%)
- `cap_number`: all 32 teams non-zero coverage (IR/PUP parsing + shared name aliases)

### Schema
`players_master.json` top-level keys (30): `player_id, gsis_id, match_confidence, canonical_name, ourlads_name, team, team_name, base_defense, ourlads_pos, standard_slot, standard_pos, depth, jersey, madden, madden_rank, madden_rank_total, madden_pos_label, cap_number, attainment, injured, stats, stats_season, nflreadpy_name, match_source, draft_year, college, years_pro, age, snap_pct, years_remaining, cash_total_remaining, cash_guaranteed_remaining, avg_annual_remaining`.

`standard_pos` values: `QB, WR, RB, TE, OL, EDGE, DI, LB, CB, S` (no `DEF` after the reserve-row mapping). Special teams stripped from the pipeline entirely. Also carries the defender advanced fields above, `def_advanced_season`, and the RB/WR/TE advanced fields.

### GSIS Matching
- Primary source: dynastyprocess crosswalk CSV. Fallback: nflreadpy `import_weekly_rosters`.
- OL skipped from GSIS matching entirely by design (crosswalk doesn't carry OL) — this is *why* the separate OL Bio Recovery mechanism above exists, bypassing GSIS matching altogether for that one position.
- **CB/S taxonomy gap, still real, low-impact**: the fallback path tags all DBs generically as `DB`. Barely dents the real match rate (CB 73.9%, S 78.5%) since the primary crosswalk carries real `CB`/`S` tags directly.

---

## NBA (CourtView) — shipped, positionless substitution fully live, ratings-pipeline hardened

### File Map
- `nba/court-view.html` — starting five in half-court zones + rotation list ranked by minutes
- `nba/player-table.html` — sortable/filterable player table

### Scripts (`nba/scripts/`)
- `fetch_stats.py` — local/manual only (stats.nba.com blocks the hosted Actions runner's IP specifically, permanent).
- `scrape_2kratings.py` — 2kratings.com per-team scraper, daily-trickle (3 random teams/run). **A real structural bug is fixed here**: matching previously only ran for teams freshly scraped that specific run — any team not picked that day kept its existing `player_id` (including unmatched `None`) frozen indefinitely, even as `nba_stats.json` (the match target) updated independently and could start agreeing with a name/team long after the ratings side stopped changing. Confirmed concretely on Damian Lillard (see Key Cross-Sport Learnings for the full story) and a second player, Thomas Sorber (OKC), with the same stuck-unmatched pattern. Fixed by re-attempting a match for *every* currently-unmatched record on every run — a pure in-memory lookup against the already-built match index, zero extra network cost, not gated behind a fresh scrape at all.
- `scrape_contracts_spotrac.py`, `scrape_nbadepthcharts.py`, `build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py` — unchanged.

### Substitution — confirmed fully positionless, and undo is real and shipped
The subs-popover pool has no position filter at all — any bench player can fill any court zone. A single-level, zone-keyed undo button exists and clears on team switch. **Both of these were previously reported as shipped in an earlier documentation pass and are now independently re-confirmed directly against the live diff** — worth remembering that "documented as shipped" isn't the same guarantee as "verified against the live repo" (this project has hit that gap more than once).

Team/Position filters use NFL `depth-chart.html`'s multiselect checkbox pattern (Eastern/Western and Guards/Wings/Bigs group shortcuts) — also re-confirmed live, not just assumed from docs.

### CourtView readability fixes
Three label elements (`.bench-stat-label`, `.popup-pos`, `.popup-stat-label`) used `var(--text-dim)` (`#404660`, a dark slate) against this project's near-black surface colors (`#111318`/`#181c24`) — genuinely dark-on-dark, worse than the medium-contrast issues fixed elsewhere this pass. Bumped to `var(--text-muted)` (readable, still visually secondary to the bold values next to them) plus small font-size increases. Separately, `.popup-jersey` (the jersey number in the hover-card header) was bumped from `var(--text-muted)` to full `var(--text)` for clarity, since it was specifically flagged as hard to see.

### 2K Ratings — real current status
`nba_ratings_2k.json`: cumulative trickle coverage has reached all 30 teams. The Task Scheduler job's last recorded run had a non-zero result code — **still genuinely unresolved** (separate issue from the stale-unmatched-record bug fixed above); Task Scheduler history logging is disabled so the specific historical code isn't recoverable, and a manual re-run reproduced a clean exit 0. Basic error logging (`nba/data/2kratings_errors.log`) was added so a future occurrence leaves a trail.

### Real current numbers (587 total players — predates the stale-unmatched fix above)
`overall_rating`: 478 (81.4%) — expect this to climb over time now that stale unmatched records self-heal every run instead of staying frozen. `contract_salary`: 438 (74.6%). `rotation_source`: `nbadepthchart.com` 444 (75.6%), `mpg_derived` 143 (24.4%).

### Schema
`nba_players_master.json` keys: `player_id, name, team, position, jersey_number, height, weight, ppg, rpg, apg, mpg, games_played, games_started, rotation_status, rotation_source, depth_rank, overall_rating, contract_salary, contract_years_remaining`.

### NBA Position Ranking (court-view.html)
`computePositionRanks(players)` computes each player's league-wide rank within their position group by 2K `overall_rating` (e.g. `PF 3/46`). Players with no rating get no badge at all — never a placeholder.

---

## MLB (DiamondView) — shipped, ratings now live in the cloud *and* in the UI

### File Map
- `mlb/diamond-view.html`, `mlb/player-table.html`

### Scripts (`mlb/scripts/`)
`scrape_roster.py` → `scrape_stats.py` → `scrape_show_api.py` (MLB The Show's official API) → `build_mlb_match.py` → `export_mlb_master.py`. **`scrape_ratings.py` (theshowratings.com via ScraperAPI) is retired** — left in place, unused; no longer in the `scrape-mlb` job or `run_mlb.bat`.

### Rating-driven dot (diamond-view.html)
The field dot previously showed AVG (batters) or ERA (pitchers), colored by position-specific heuristics (`battingColor()`/`pitchingColor()`). **Switched to the shared `ratingColor()` gradient used by every other sport**, showing `overall_rating` directly (or an em dash if null) — matching NFL/NBA/EPL/MLS's convention. The old heuristic functions are fully removed (confirmed unused anywhere else in the file).

### DiamondView readability pass
Four fixes, all in `diamond-view.html`: the on-field position label (`.player-rank`) had the same low-contrast `var(--text-muted)`-on-colored-surface issue already fixed in EPL/MLS — bumped to `var(--text)`, bigger/bolder, and the jersey number was dropped from this label entirely (redundant with the hover popup, which already shows it clearly) so the position itself reads cleaner on the smaller card. Hover-card stat grid (AVG/HR/RBI/OPS) sized up. Substitution popover enlarged to match NHL's already-fixed version (200px, bigger dot/text, scrollable if long). Batting-order/pitching-staff position and role tags (`.bench-meta`, e.g. "DH", "SP"/"RP") sized up from 9px.

### TableView (player-table.html)
Overview tab gained a Rating column and now sorts by it by default (previously sorted alphabetically with zero rating/stat signal — the weakest Overview of all six sports before this fix). Batting tab gained a BABIP column; Pitching tab gained a K/BB (`strikeoutWalkRatio`) column — both real fields already present in `mlb_players_master.json`, previously unexposed, both meaningfully better "quality" indicators than raw AVG/ERA per this project's own stated metric instincts. Both wired into `FLOAT_SORT_COLS` so they sort numerically (they arrive as formatted strings from statsapi.mlb.com, same as `era`/`whip`).

### Real current numbers (779 total players)
`overall_rating` (The Show API, name + team match; 2026-10-04 local run on the 40-man roster): 1,355 / 1,360 (99.6%). Unmatched (5, no Live card exists): Eiberson Castellano (COL), Johan Rojas (PHI), Rowan Wick (SF), Jonathan Heasley (TB), Devereaux Harrison (TOR); list in `mlb/data/unmatched_mlb.txt`. 169 matches are the "FA" name-only tier (reassigned/IL/released players the API lists without a team). `roster_status` counts: A 1,080, D60 171, 40M 88, RM 15, D15 5, PL 1 (176 `injured`).

### Roster source — 40-man, injured handling (2026-10)
- `scrape_roster.py` pulls `rosterType=40Man` (~1,360 players), not `active` (which dropped Judge, Devers and ~230 other players with 2026 stats). Each row carries its raw status code into the master as `roster_status` (`A`, `40M` non-active 40-man, `D60`/`D15`/(`D7`/`D10`) injured list, `RM` reassigned to minors, `PL` paternity); `injured` is true for `D<number>` codes only. Players traded/released and on no 40-man are still absent (~227 with stats).
- DiamondView: injured players are never natural starters (so a team can have an empty slot, e.g. SF 1B while Devers is on the 60-day IL), never in sub pools, never in the batting-order/pitching-staff lists. Sub pools and both lists also exclude anyone with 0 PA and 0 IP this season (`hasPlayed()`, non-injured 40-man filler). The sidebar header shows a red INJ pill if ever opened for an injured player. Judge (status `40M`, not injured) resolves as NYY's RF starter.
- player-table.html shows all 40-man players, injured included, with the same red INJ tag as NFL's depth chart.


### Ratings source — The Show official API (replaced theshowratings.com, 2026-10)
- `scrape_show_api.py` pulls `mlb26.theshow.com/apis/items.json?type=mlb_card` (25/page, loops `total_pages`), keeps `series == "Live"` (~2,084 cards, one per real player; ~884 are team "FA"), and writes the raw snapshot `mlb/data/show_api_live.json` plus `mlb/data/ratings_meta.json` (`ratings_as_of` = newest `roster_updates.json` date, weekly updates). Plain `requests` + Chrome UA works, no Cloudflare, no ScraperAPI. A failed/truncated fetch (< 1,500 Live cards) keeps the previous snapshot and exits 0 — staleness shows up as an old as-of date. No MLB player ID and no potential rating exist in the API.
- **Matching** (`build_mlb_match.py`, replaces the old `person_id` join): normalized name (accents, periods, Jr./Sr./II-IV stripped, hyphens -> spaces) + team (`ARI→AZ, WAS→WSH, OAK→ATH`). Tiers, all team-scoped and accepted only if exactly one card qualifies: exact, `NAME_ALIASES` (Leo Rivas, Cam Cauley, Robby Ahlstrom, Leo Balcazar), hyphenated-surname truncation (Encarnacion-Strand -> Encarnacion); last, if the API team is "FA" and the name is unique among Live cards, a name-only match (10 players locally). Same-name players (Max Muncy LAD 81 / ATH 63) only ever match on name + team. Unmatched -> `overall_rating: null` + `mlb/data/unmatched_mlb.txt`.
- The ratings are noticeably different from theshowratings.com's (which looked stale): e.g. Webb 94 -> 80, Raleigh 95 -> 79, Freeman 90 -> 81. `potential` was **removed** from the master and the UI (sidebar header no longer shows "Pot").
- DiamondView shows "Ratings as of <date>" next to "Starting Nine" from `ratings_meta.json` (nothing if missing).


### Player sidebar, bigger field, Reset to starters (diamond-view.html, frontend-only)
- **Field**: `.court-canvas` uses a fixed height (`--fh` = viewport minus header/margins, also capped by width so field + 360px column fit) and the page never scrolls at 1280x900 or 1920x1080; `.right-col` scrolls on its own. Dots are ~1.4x (`--dot` = `min(90px, 9.3vh)`; name/rank/dot fonts and card width derive from it). DIAMOND_ZONES retuned for the bigger cards (CF y10, P y58, 2B x62, SS x34). Don't use `min-height` for the field (NFL's scroll bug).
- **Toggle**: header "Sidebar: On/Off", `localStorage` key **`fieldview_mlb_sidebar`** (`'on'`/`'off'`, default ON). OFF = the original click-to-sub popover and full hover card, untouched.
- **ON**: hover = name / position / rating only. Click a starter opens a 360px sidebar that *replaces* the batting-order/pitching-staff column (`body.sb-open`; the field doesn't resize). Esc, x, empty-field click, team switch close it; selected card keeps a cyan ring that follows a swap. Layout: header (name, jersey, team, position, bats/throws, height/weight, overall rating) -> Advanced Stats -> Season Stats grid -> Substitutes. No hero stat. Two-way players (Ohtani) get both batting and pitching sections (pitching first when he's at P).
- **Advanced stats** (`buildAdv()` computes everything client-side from `batting_stats`/`pitching_stats`; statsapi rates are strings, so counts are used where possible): batters OPS, OBP, SLG, ISO (SLG-AVG), BB% (BB/PA), K% (lower better), BABIP (style stat: neutral grey, "higher than N% of hitters") ranked among all qualified batters league-wide; pitchers ERA, WHIP, K% (SO/BF), BB%, K-BB%, HR/9 ranked within role (SP if GS >= half of games, else RP). **`inningsPitched` is in thirds** ("85.2" = 85 2/3), parsed by `ipToNum()`. Percentile math/`pctColor()` copied from NFL (ties half, inverted for lower-is-better, cap 99, population < 10 -> raw + definition only).
- **Qualifiers**: batters PA >= 3.1 x G, SP IP >= 1.0 x G, RP IP >= 0.25 x G. G = 162 once the regular season is complete, else the max games any player has played (`leagueG`; currently 162, logged to the console). Unqualified players are excluded from populations and show raw + definition + a "low sample" tag, no bar (so most bench bats and nearly every reliever, and Ohtani's pitching line, are "low sample").
- **Sub comparison**: starter vs candidate header + Back / Swap in, season-stat table (better value bold green; ERA/WHIP/BB/BB%/K%/HR/9 lower-is-better) plus both players' advanced bars/percentiles, no deltas. Only blocks both players have are compared, with a caption otherwise (in practice only pitcher-vs-Ohtani at P; batter slot pools never contain pitchers).
- **`?player=<player_id>`** (and `?team=`) written only while the toggle is ON, other params preserved; reopens on load only if that player is currently on the field for the loaded team.
- **Reset to starters**: button in the field header, clears `manualStarters`, refreshes/closes the sidebar; hidden when there are no manual subs.

### Schema
`mlb_players_master.json` keys: `player_id, name, team, team_abbr, position, position_group, position_group_source, player_type, jersey_number, height, weight, bats, throws, batting_stats, pitching_stats, roster_status, injured, match_source, overall_rating`.

---

## NHL (IceView) — shipped, ratings live in the UI, several real bugs fixed

### File Map
- `nhl/ice-view.html`, `nhl/player-table.html`

### Scripts (`nhl/scripts/`)
`scrape_roster.py` → `scrape_stats.py` → `scrape_ratings.py` (nhlratings.net via ScraperAPI) → `build_nhl_match.py` → `export_nhl_master.py` — unchanged pipeline shape.

### D1/D2 duplicate defenseman bug — fixed
See Key Cross-Sport Learnings for the full root cause. `getStarter('D2')` now additionally excludes whoever `D1` naturally resolves to when D1 has no manual override (the general `manualStarters`-based exclusion already handled the reverse case and the both-manual case correctly). D1's own behavior is unchanged — it's still the team's single highest-`toiPerGame` defenseman; D2 now correctly resolves to the second-highest instead of duplicating D1. Verified across 8 different teams with no manual subs (two distinct real defensemen every time) plus multiple manual-substitution scenarios (subbing into D1 correctly leaves D2 on its normal natural pick, and vice versa).

### Rink orientation — fixed
`ICE_ZONES`' depth ordering was backwards relative to the rink's actual drawn markings: the goal crease/goal line sit at roughly 3-10% down the SVG, but the goalie zone was placed at `y: 78` (near the far blue line, nowhere close to the net), while forwards sat at `y: 8-12` (almost on top of the crease). Reordered so the goalie sits in the crease (`y: 7`), defense in the defensive zone between the crease and the near blue line (`y: 26`), forwards up near center ice (`y: 50-55`) — matching the rink's real blue-line (32%)/center-line (51%)/far-blue-line (70%) positions. Confirmed visually (screenshot), and confirmed the substitution popover — which positions itself dynamically via `getBoundingClientRect()`, not fixed coordinates — still opens correctly for all six zones after the move.

### Rating-driven dot (ice-view.html)
The dot previously showed points-per-game (skaters) or save% (goalies), colored by custom `skaterColor()`/`goalieColor()` heuristics. **Switched to the shared `ratingColor()` gradient**, showing `overall_rating` directly. The old heuristic functions are fully removed.

### Substitution UI — enlarged and de-cluttered
Two fixes: (1) the click-triggered substitution popover (`.subs-pop`) was genuinely tiny (150px, 18px dot/7px font) — enlarged to match the convention now shared with MLB/EPL/MLS (200px, bigger dot/text, `max-height`+`overflow-y:auto` so a long list scrolls in a contained box instead of growing indefinitely). (2) The separate, always-visible persistent bench list (`renderBenchList()`) had no filtering at all — it showed *every* non-starting player on the full organizational roster, including prospects/AHL players who've never appeared in an NHL game. Confirmed concretely on Toronto: 8 of 27 forwards had zero games played and no stats block at all (e.g. Gavin McKenna, a well-known prospect, not yet an NHL player). Fixed by filtering both `subEligiblePlayers()` and `renderBenchList()`'s population to exclude anyone with zero games played this season (skater or goalie) — a 0-GP player, whether a true prospect or an injured veteran, isn't a realistic substitution option for either list.

### TableView (player-table.html)
Overview tab gained a Rating column and now sorts by it by default (previously alphabetical, zero rating/stat signal — matching the same gap MLB's Overview had). Skaters tab gained an S% (shooting percentage) column. Goalies tab's default sort changed from Wins (team/luck-dependent) to Save% (already a column, more skill-isolated) — Wins remains available as a manual sort choice, just no longer the default.

### Real current numbers (1,266 total players)
`overall_rating`: 855/1266 (67.5%) — now genuinely visible on both the field dot and in the table.

### Schema
`nhl_players_master.json` keys: `player_id, name, team_abbr, position_group, position_code, jersey_number, shoots_catches, height_in_inches, weight_in_pounds, birth_date, birth_city, birth_country, birth_state_province, skater_stats, goalie_stats, stats_source, overall_rating, potential`.

---

## EPL (PitchView) — shipped, formation switcher + Advanced tab added, real match bug fixed

### File Map
- `epl/pitch-view.html` — **formation switcher** (6 formations, see below), no longer fixed 4-3-3 only
- `epl/player-table.html` — Overview/Stats/Fantasy/**Advanced** tabs

### Scripts
`scrape_fpl.py`, `shared/scripts/scrape_sofifa.py`, `shared/scripts/soccer_name_utils.py` — unchanged. `epl/scripts/build_epl_match.py` — see the matching fix below.

### Formation Switcher (pitch-view.html)
Previously fixed 4-3-3 for every team. Added a dropdown offering 4-3-3/4-4-2/3-5-2/3-4-3/4-5-1/5-3-2 — this genuinely changes how many players go in each of the DEF/MID/FWD buckets and where they're drawn (a real, meaningful distinction at the data's actual granularity), though it can't model sub-role tactical nuance (winger vs. striker, center-back vs. full-back) since FPL/sofifa's position data doesn't go that granular. Architecture: a `FORMATIONS` registry (each formation = a set of zone coordinates), `groupForZone()` derives the position-group from a zone's name prefix instead of hand-maintaining a separate group-map per formation, and `setFormation()` swaps the active zone set and wipes `manualStarters` (zone names don't map 1:1 across formations — e.g. 4-3-3's `MID3`/`FWD3` don't exist in 4-4-2 — so this follows the same "reset on structural change" convention used everywhere else in the project, rather than guessing at a mapping). `computeStarters()`/`rankedGroupPool()`/`subEligiblePlayers()` needed zero changes — they already iterate over whatever `ZONE_ORDER` is current, so they're formation-agnostic by construction. Persisted via `localStorage` (survives a page reload and a team switch). Verified across all 6 formations on real teams: correct headcount per group every time, zero duplicate players, zero empty slots.

### Advanced Tab (player-table.html)
New tab showing xG (`expected_goals`), xA (`expected_assists`), ICT Index, Defensive Contribution, and Tackles — all real fields FPL already scrapes into `epl_players_master.json`'s `stats` block, previously never exposed anywhere in the table. Mirrors MLS's pre-existing Advanced tab (which already showcased ASA's real xgoals data) — EPL was the one soccer sport missing this despite having the underlying data already. `xg`/`xa`/`ict_index` are parsed from FPL's string fields at load time (same pattern as the existing `form` field); `defensive_contribution`/`tackles` are already numeric.

### PitchView sizing pass
`.left-col` (the pitch) was a fixed 480px while `.right-col` (bench list) took the entire flex remainder (~630px) for content that didn't need nearly that much room — for comparison, NBA's equivalent left-col is already 598px. Bumped to 560px, letting the bench list shrink to fit its actual content rather than explicitly resizing it. Substitution popover and hover-card sizing brought in line with the same fixes applied to NHL/MLB/NBA (bigger popover with scroll, bigger/brighter hover-card stats and jersey number).

### Name-order-swap matching bug — fixed
See Key Cross-Sport Learnings for the full root cause (`find_token_overlap_match()`'s first-word-must-match gate). Added `find_token_set_match()` as a final tier in `find_sofifa_match()`: exact token-set equality regardless of word order, team-scoped, only accepted if exactly one candidate qualifies. Verified: recovers Kaoru Mitoma (rating 81) plus two more real players with the identical pattern, Ao Tanaka and Wataru Endo — confirmed not overfit to one case. Total matches rose from 400 to 403 of 623 in a standalone verification run; all other tiers' counts unchanged (no new false positives introduced). **Not yet reflected in the live committed data** — the regenerated `unmatched_epl.txt` from the verification run was deliberately not committed, since the real regeneration should come from the next actual pipeline run.

### Real current numbers (pre-Mitoma-fix baseline)
604→623-626 FPL players across separate runs (normal week-to-week roster drift), sofifa match rate 63.9-65.7% depending on run — all within the same normal range documented previously. Expect a small further bump once the name-order-swap fix runs live.

### Schema
`epl_players_master.json` keys: `player_id, name, web_name, team, team_short, position_group, standard_pos, overall_rating, potential, sofifa_id, match_source, stats{...}` (now includes `expected_goals`/`expected_assists`/`ict_index`/`defensive_contribution`/`tackles`, exposed via the new Advanced tab). `position_group` = FPL's coarse `GKP/DEF/MID/FWD`.

---

## MLS (PitchView) — shipped, formation switcher + sizing pass added

### File Map
- `mls/pitch-view.html` — same formation switcher as EPL (see below)
- `mls/player-table.html` (Overview/Stats/Advanced tabs) — **reviewed this pass**: Overview gained an **Age** column (1,024 of 1,047 players have one); Advanced gained **G-xG, xG+xA, A-xA, xPts Add** (all four exist in the master's `stats` block, 775 of 1,047 populated — the rest have no ASA match) after xA, default sort still xG; **Stats and Advanced hide keepers by default** via each tab setting the position filter (Stats/Advanced → D/M/F, Overview → none, same pattern as NFL's `setView()`; tick GK to add them back, Clear resets to none) — keepers had almost no attacking data (1 of 105 has a goal); **the Position column now sorts on the label it displays** (`standardPos`, else GK/DEF/MID/FWD), alphabetically, instead of the coarse G/D/M/F letter.

### Scripts
Unchanged pipeline shape (`scrape_espn_roster.py` → `fetch_asa_stats.py` + `shared/scripts/scrape_sofifa.py` → `build_mls_match.py` → `export_mls_master.py`).

### Formation Switcher + sizing pass
Identical structural changes to EPL's (see EPL section for the full architecture write-up) applied to `mls/pitch-view.html`: same 6-formation `FORMATIONS` registry, same `setFormation()`/`groupForZone()` pattern, same `.left-col`/subs-popover/hover-card sizing fixes. Two differences, both intentional: `groupForZone()` returns MLS's real single-letter position codes (`G`/`D`/`M`/`F`, not EPL's `GKP`/`DEF`/`MID`/`FWD`), and the formation choice persists under a separate `localStorage` key (`fieldview_mls_formation`) so the two sports' saved preferences don't collide. Verified identically to EPL: correct headcount, zero duplicates, zero empty slots across all 6 formations and 30 teams.

MLS's Advanced tab already showed real ASA xgoals data before this pass — it was the reference example EPL's new Advanced tab was built to match, not something that needed its own fix here.

### Schema
`mls_players_master.json` keys: `player_id, name, team, team_abbreviation, jersey, age, height, weight, citizenship, position_group, standard_pos, overall_rating, potential, sofifa_id, sofifa_match_source, asa_player_id, asa_match_source, stats{...}`. `position_group` = ESPN's coarse single-letter code (`G/D/M/F`).

---

## Statistics

Research notes on which stats best represent player value per sport/position, for populating `advanced_value_stat`/`advanced_value_source`. Ongoing — sports get filled in as we work through them.

### NFL

- Madden ratings are UI candy, not evaluative — display only, never treat as a real signal.
- Solid free evaluative stats by position: QB → EPA/play + CPOE; RB → rush yards over expected (RYOE, via `load_nextgen_stats()`, unused); WR/TE → target share + air yards.
- EDGE/DI → pressure rate + pass-rush win rate, not sacks. Sacks are scheme/luck-dependent; pressure rate is the better free signal.
- CB/S → weakest free data spot in football analytics. No good free per-target coverage stat exists; targets-against/completion%-allowed from play-by-play is the best available proxy.

#### Offensive Line

**Investigated Sept 2026.** Individually-attributed OL performance data is the thinnest of any position group, free or paid — grading who "won" a block requires watching tape, no tracking-data shortcut exists like it does for other positions.

- **PBWR / RBWR** (ESPN Analytics, built off restricted NFL Next Gen Stats tracking): real, computed by ESPN at the individual level, but **not publicly available as a full-league table**. ESPN only publishes team-level rankings + "Top 10 at OT/OG/C" leaderboards. No API, no CSV. Individual numbers outside the top 10 only surface secondhand in other outlets' articles. **Don't spend more time trying to scrape a full table — it doesn't exist.**
- **Overall Block Win Rate** = (PBWR × team pass-play%) + (RBWR × team run-play%) — the "single number" version, team-level only.
- **"Yards before contact" is NOT an OL stat** — it's attributed to the RB, not the blockers. Ruled out for per-lineman use; noting here so we don't re-investigate this.
- **FTN charting** (`load_ftn_charting()`, free/unused in our stack) is play-context charting (blitzers, play-action, motion, `is_qb_fault_sack`, etc.) — NOT lineman grading. `is_qb_fault_sack` is a legit free nugget for cleaning up team-level sack rate (QB hold-time sacks vs. OL-fault sacks), but attributes nothing to a specific lineman.
- **What's actually free and individually attributed:** penalty rate (false starts/holds — real player-level data in official play-by-play), snap_pct/games started (already have), draft capital (`load_draft_picks()`), contract value (already have via Spotrac/OTC). These are proxies/context, not direct performance grades.
- **Real individual performance signal is paywalled:** PFF+ ($99.99–$119.99/yr as of Aug 2026) has player-level pass-block/run-block grades + pressures-allowed-per-snap. PFF Pro ($199.99/yr) adds an actual API/CLI — the clean way in if we ever go this route, vs. scraping their site directly (ToS risk).
- **Decision: not pursuing a PFF subscription right now.** Interim OL story = penalty rate + snap_pct + team-level PBWR/RBWR as context (not individually isolated). Revisit as a deliberate call if OL becomes a priority, not a default next step.

#### Quarterbacks

**Investigated Sept 2026.** Unlike OL, QB is the best-served position for free, individually-attributed advanced stats — most of it already sits in our existing `nflreadpy` dependency, no new scraping needed for 3 of the 5.

- **EPA/play (Expected Points Added)** — measures how much a play is worth given the situation (down, distance, field position, score, time), instead of just raw yards. A 5-yard gain on 3rd-and-3 counts for a lot more than a 5-yard gain on 3rd-and-15. **Source:** free, from nflverse play-by-play (already in our pipeline via `nflreadpy`). Can split into passing/rushing/sack EPA separately.
- **CPOE (Completion % Over Expected)** — actual completion rate minus what a model expects given the throw's difficulty (distance, coverage, etc). Tells you if a QB is genuinely accurate, or just racking up easy completions. Pairs with EPA — EPA rewards big/aggressive plays, CPOE checks if the guy's actually accurate doing it. **Source:** free, same nflverse play-by-play as EPA.
- **Success rate** — % of dropbacks that "beat the down" (gained enough yards to keep the offense on schedule for that down/distance). A steadier, less streaky companion to EPA — one huge touchdown can skew EPA/play in a small sample, success rate won't move as much. **Source:** free, computed from the same play-by-play (down/distance/yards gained columns).
- **NGS Time to Throw** — average seconds from snap to release. Not inherently "good" or "bad" on its own (some great QBs hold it longer to let deep shots develop) — it's a process/style stat, useful paired with the others to explain *how* a QB is generating his EPA/CPOE numbers. **Source:** free, NFL's own tracking data via `load_nextgen_stats()` (already available in our pipeline, currently unused). Published as a full public leaderboard for all qualifying QBs — unlike PBWR, NFL doesn't gate this one.
- **ESPN Total QBR** — 0-100 all-in-one QB rating, ESPN's proprietary blend of EPA-like value plus clutch/game-context weighting. Formula's a black box, but the actual numbers are fully public for every qualifying QB (not top-10-only). **Source:** free to view, but no API — requires scraping the table at espn.com/nfl/qbr, our only new scraper of the 5.

**Ruled out, noting so we don't re-investigate:**
- **Big Time Throw rate / Turnover Worthy Play rate** — PFF-exclusive. This is a human charter grading every throw -2.0 to +2.0 by difficulty/placement, not derivable from tracking data or a box score. No free equivalent exists; closest free proxies (NGS Aggressiveness, CPOE split by air-yard bucket) only capture half the concept each. PFF+ subscription only.
- **QBERT (Nate Silver / Silver Bulletin)** — a personal Substack project, not a licensed data source. Paywalled ("Paid" post), and even as a subscriber there's no API/CSV — renders as embedded charts meant for humans, not a pipeline. Conceptually it's chasing the same signal our EPA/CPOE/success-rate stack already captures, just with his own hand-tuned weights (credits drops to WR not QB, discounts sneak TDs, etc). Not viable to build around either way.

---

## ScraperAPI — real status

Used only by `nhl/scripts/scrape_ratings.py` (NHL cloud job). **MLB no longer uses ScraperAPI** — its ratings moved to The Show's official API (2026-10); `mlb/scripts/scrape_ratings.py` is retired but left in place. Keep the `SCRAPERAPI_KEY` secret. Free plan is 1,000 credits/month; NHL's real usage (~139 requests/month) sits well under that.

---

## Conventions & Gotchas
- **TableView design framework — four shapes:** (1) uniform box score, tabbed by category (NBA); (2) position-gated disjoint stats, row-filtered by tab (NFL/MLB/NHL); (3) metric-lens switching, not position-gated (EPL/MLS); (4) cosmetic rating vs. genuine evaluative metric — not yet separated in any sport. **What's changed:** NFL's Advanced tab now covers QB/RB/WR/TE with position-aware columns (the column set follows the position filter: all-RB → RB set, WR/TE → WR/TE set, anything else → QB set).
- OurLads abbreviations: `ARZ` (not ARI), `JAX` (not JAC)
- Team JSON can come out as a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`
- Minimal targeted edits only — no unrelated refactors, no adjacent "improvements"
- Match existing code style even if you'd write it differently
- No speculative features or config beyond what's asked
- Plain HTML/CSS/JS only — no React, no build tools
- A plain `python -m http.server` + headless Playwright is what's been used to verify FieldView/PlayerTable pages end-to-end against real data before calling a build done.
- **The 0-99 rating gradient (`ratingColor()`) and its color-coded dot convention is now genuinely identical across all six sports' FieldView dots** — if you're touching one sport's dot logic, copy the existing function verbatim from another sport rather than reinventing it (NBA/EPL's implementations are the reference copies used to port MLB/NHL over this pass).
- **Substitution-popover sizing (`.subs-pop`/`.subs-dot`/`.subs-name`/`.subs-mpg`) is now standardized at 200px/22px-dot/13px-name/11px-text with `max-height:280px; overflow-y:auto` across NHL/MLB/EPL/MLS** — NBA's is still the older, smaller convention (184px) and wasn't touched this pass; worth bringing in line if NBA's substitution UX gets revisited.
- **`var(--text-muted)` can still be low-contrast against a saturated/colored background** (fixed on EPL/MLS/MLB/NHL's on-field position labels this pass) **and `var(--text-dim)` can be flatly dark-on-dark against this project's own near-black surface colors** (fixed on three NBA label elements this pass) — when a shared label component looks fine on most sports' backgrounds, check the actual computed contrast on the outlier surface (ice, a saturated pitch green, a near-black popup) rather than assuming the shared convention is safe everywhere.
- **A per-zone-independent starter-resolution function needs to be checked zone-by-zone for shared filter keys, not just "does this sport have positionless zones conceptually"** — see the NHL D1/D2 entry in Key Cross-Sport Learnings; this was previously believed handled and wasn't.
- **A retry mechanism that only fires alongside a fresh/expensive fetch can leave failures stuck indefinitely if the fetch itself is sampled or trickled** — see NBA's 2K stale-unmatched fix in Key Cross-Sport Learnings; a cheap in-memory re-check should generally not be gated behind an expensive one.
- **Every sport's `.duckdb` file must be listed in `.gitignore`** — confirmed and fixed for MLB/NHL this pass; check this explicitly if a new sport is ever added.
- **Scraper hardening pattern**: test a real, complete header set with plain `requests` before reaching for `curl_cffi` impersonation, and reach for a paid proxy only if a full-scale run still won't clear.
- **Graceful degradation over all-or-nothing**, for both scrapers and frontends: Madden's retry+cooldown+fallback-to-last-known-data pattern is the model for scrapers; EPL/MLS's "No Player" dashed placeholder is the model for frontends.

---

## Known Outstanding Bugs

*(Resolved this pass — full detail in each sport's section above, not repeated here: NHL's D1/D2 duplicate defenseman, NHL's backwards rink orientation, NHL's bloated/unfiltered substitution lists, NFL's OL missing age/draft_year/college, NFL's Seattle SLB position-taxonomy bug, NFL's negative years_pro edge case, NFL's Greg Rousseau Madden-alias miss, NFL's alphabetical-sort TableView tabs, NFL's real-zero-treated-as-null sort bug, NBA's dark-on-dark label contrast, NBA's 2K stale-unmatched-record bug, EPL's Kaoru-Mitoma-class name-order-swap matching bug, MLB's and NHL's stat-driven (non-rating) FieldView dots, MLB's/NHL's/EPL's/MLS's undersized substitution and hover-card UI, MLB's and NHL's missing DuckDB `.gitignore` entries.)*

- **NFL field scroll bug — two separate causes, don't conflate them:** (1) `.players-layer`'s CSS fallback `height:1000px` floored `.field-canvas` via the flex `min-height:auto` default — FIXED, `min-height:0` added to `.field-canvas`, 1f72b97. (2) Residual scroll on narrower windows: `.field-outer` uses `min-height` (a floor, not a cap), so if its flex children (formation-bar + field-canvas + legend-strip) need more room than the viewport (e.g. legend wraps to 2 lines) the box grows past it. Spec'd fix: `min-height` → `height` on `.field-outer`. **Verified 2026-10-03: `.field-outer` still uses `min-height: calc(100vh - 52px)` — this fix has NOT been applied.** Re-check before doing anything further about scrolling.
- **NFL**: `attainment` was 0/2343 populated. Root cause: OurLads puts the draft-round/status suffix in a `<span class="dc-key">` sibling of the player's `<a>`, not inside the anchor; the old regex only read the anchor text. Fixed in `scrape_depth.py` (1f72b97) — reads the `dc-key` span; the digit-or-slash requirement filters out the span's unrelated position-code use on injured-list rows. Needs a pipeline rerun to populate `players_master.json`.
- **NFL/Madden missing-ratings investigation** (Diggs, Okereke, Keenan Allen, Rayshawn Jenkins, Jonnu Smith, Fatukasi, Hines-Allen, Chris Moore): 6 of 8 are genuine EA free-agent data lag on maddenratings.com itself — not fixable on our end. Hines-Allen was a real bug (`normalize_madden()` deleted the hyphen instead of spacing it, so "Josh Hines Allen" never matched "Hines-Allen") — fixed in `name_utils.py` (b5374e8), needs a pipeline rerun. Chris Moore stays unexplained (absent from every source checked, low priority). Incidental, not fixed: KC's Chris Roland-Wallace scrapes with a mashed name (`firstName:"ChrisRoland-Wallace"`), single depth-2 player.
- **NHL**: `season_utils.py`'s `resolve_seasons()` jumped `roster_season` to a not-yet-published season when the API's `standingsEnd` looked stale (20262027 showed `standingsEnd: "2026-10-02"`, three days after a Sept 29 start). Fixed in 7013d4d by confirming the next season id exists in the manifest before advancing. Verified against a mocked manifest only — re-run in a week or two to confirm `roster_season` resolves to 20262027 on its own once the NHL publishes the real standings range.
- **NFL**: **Offense gate live after the next pipeline run, verify then.** Expect `adv_volume` on players in `players_master.json` (it's absent from the committed file until then, which keeps the gate inert), backup QBs / low-target WRs showing "low sample", and `advanced_meta.json` regenerated.
- **NFL**: OL snap-share coverage sits at ~60% (302/503) — real data-source ceiling, not worth chasing further.
- **NFL**: CB/S taxonomy gap in the nflreadpy-rosters GSIS fallback (all DBs tagged generically `DB`) — real but low-impact.
- **NFL**: the OL bio-recovery, Rousseau/years_pro, NB-safety retag, reserve-`DEF` mapping, first-initial stats fallback and Madden rank rekey fixes are all verified against controlled/local runs but **not yet reflected in the committed `players_master.json`** — confirm after the next Tuesday run (expect no `DEF` rows, ~15 NB safeties tagged `S`, age coverage ~95%).
- **NFL/Madden**: **24 of 32 teams are on August Madden data** (Cloudflare 202 challenges make the scraper fall back to last-known rows; see Madden freshness). `madden_meta.json` will show real per-team dates after the next run; until then the caption can't say how stale a given team is.
- **NFL**: ~219 reserve/practice-squad players (formerly `DEF`) are now real CB/S/LB/EDGE/OL rows and therefore appear in substitution pools and can be picked in the subs popover — a side effect of the DEF mapping, not yet judged good or bad in practice. Terrion Arnold (SEA) was dropped (`CE` label, no Madden row).
- **NFL/Madden**: **Kayshon Boutte is Madden NE but OurLads HOU** (stale Madden team) — his Madden match is team-scoped so it can miss or land on the wrong side until one source updates.
- **NFL/Madden**: a Madden-side alias audit found 29 same-team, same-last-name unmatched OurLads/Madden pairs; 25 were confirmed same-person and are now in `MADDEN_NAME_ALIASES` (`build_master.py`, consulted by `find_madden_player()` before the shared `NAME_ALIASES`, which also drives GSIS/OTC where a different spelling is right — e.g. 'Cam Bynum' → 'Cameron Bynum' for the crosswalk but Madden says 'Camryn'). Includes Madubuike (OurLads 'Nnamdi'), Onwenu ('Mike', IR), Metellus, Bynum, Holland, Fashanu, Hollywood Brown/Marquise Brown, etc. **Four unique-looking pairs were deliberately not aliased (different people, position mismatch):** Chris Moore/Nick Moore (BAL), Christian Jones/Jaylon Jones (CHI), Marvin Jones Jr./Jacoby Jones (WAS), Pharaoh Brown/Austin Brown (IND). Zach Tom (GB) is on OurLads under his former name 'Zach Bako-Bewele' (already aliased for GSIS and Madden). Scratch run: Madden matches 1,827 → 1,852, none lost. Live after the next pipeline run. ~49 injured-list rows are still dropped for lack of a usable Madden position.
- **NFL**: the first-initial stats fallback may have lost a few real nickname matches (Dru Phillips, Sai'vion Jones, Jaylon Jones, Dalton Johnson, Mike Reid were on the 49-player dropped list) — not chased; a wrong stat is worse than a missing one.
- **NBA**: 2K ratings Task Scheduler job's last recorded run had a non-zero result code — separate, still-unresolved issue from the stale-unmatched-record bug fixed this pass. Task Scheduler history logging is disabled (needs an elevated/admin session to enable) so the historical code isn't recoverable; basic error logging was added for future occurrences.
- **NBA**: `scrape_2kratings.py` has still never completed a full 30-team run in one pass — cumulative trickle coverage has reached all 30 teams, but no single run has. Lower-priority now that stale unmatched records self-heal every run regardless.
- **EPL/MLS**: the full six-sport `run_all.bat` chain has still never completed in one sitting — lower priority now that each sport refreshes independently via its own cloud job regardless.
- **EPL**: the original unmatched-pool breakdown (99 on 3 clubs sofifa's database lag, rest genuine academy/transfer gaps) hasn't been re-verified against the newer ~223-239 unmatched counts from later runs — worth a fresh look if EPL matching becomes a focus again.
- **Cross-sport ratings audit gap**: NFL (Rousseau), EPL (Mitoma + 2 more), and NBA (Lillard + Sorber) all had real, findable alias/matching bugs surfaced by actually going looking this pass. MLB and NHL were *not* covered by the same audit — neither has a raw ratings-source file committed to the repo (both scrape live via ScraperAPI without a persisted raw snapshot), so the same "compare raw source vs. matched output" technique doesn't directly apply. This is a real, acknowledged gap in coverage, not a clean bill of health for those two sports.

---

## Roadmap

**Up Next**
- ⬜ NFL draft prospect installer (target: December, ahead of mock-draft season). Not a full simulator. Pick a prospect from a big board and drop him into a FormationView slot with an R badge and a projected Madden from a pick-number → rookie-Madden curve fit on current rookies (`load_draft_picks()` + madden). Phase 2 (team-need auto-mock) only if phase 1 gets used. Prospect big-board source not yet investigated.
- ⬜ NFL Opponent View, phase 2 — a real opponent-vs-opponent matchup (your team's offense against an actual opponent's defense), building on phase 1's same-team offense+defense view shipped this pass
- ⬜ NFL Opponent View visual density/sizing pass — ~22 cards on the field at once wasn't sized for that density; deliberately deferred until actually visible rather than guessed at blind
- ⬜ Confirm a full six-sport `run_all.bat` chain completes end-to-end in one watched, foreground run — still not achieved, still not a freshness blocker for any sport since all six have independent cloud jobs
- ⬜ NBA 2K Task Scheduler job's non-zero last-run result code — root cause still not resolved, needs elevated-session history logging if it recurs
- ⬜ Additional NFL data sources via `nflreadpy`: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()` — all free, unused
- ⬜ Confirm the EPL name-order-swap fix and NBA 2K stale-unmatched fix both land cleanly in a real live pipeline run (both verified via standalone/controlled tests only so far)
- ✅ MLS TableView review — done 2026-09-26 (Age, four new Advanced columns, keepers hidden on Stats/Advanced, Position sort by displayed label); see MLS section
- ⬜ After Tuesday's run, confirm the injured-list rows, defender advanced cards (with regular-season snaps) and NB/reserve fixes landed in `players_master.json` (expect ~2,340 players, no `DEF`, IR/PUP players present)
- ⬜ After Tuesday's run, check `madden_meta.json` coverage, then decide on `curl_cffi` or ScraperAPI for the Madden scraper
- ⬜ NHL TableView: expose `evGoals`, `evPoints`, `faceoffWinPct` — all already available in the data, never added to the table
- ⬜ NBA stat richness: `fetch_stats.py` only pulls ppg/rpg/apg/mpg, and richer stats mean changing the scraper (a local-only script, stats.nba.com blocks the cloud runner), not just the table
- ⬜ "Genuinely evaluative metric" — its own future project, needs new data sources: separate cosmetic video-game ratings from real evaluative stats (NFL pressure rate over sacks, NBA BPM/VORP, MLB WAR/xwOBA, NHL GAR/xG). NFL's advanced-stat work (QB/RB/WR/TE hover cards + the Advanced tab) is the first partial step on this
- ⬜ A real audit approach for MLB/NHL's ratings-matching (no raw source file exists to compare against the way NFL/EPL/NBA's audit worked — would need checking the scrape scripts' own unmatched-reporting, if any exists, or a different technique entirely)

**Future State**
- ⬜ ReView — replays, highlights, box scores, tweets, podcasts; comes after every sport's FieldView/TableView are dialed in. Not started for any sport.
- ⬜ Mobile responsiveness pass — desktop-only is the explicit call for now
- ⬜ A real custom domain, if AdSense monetization is ever pursued
- ⬜ Real per-game soccer formations (as opposed to the manual formation *switcher* shipped this pass) — would need a genuinely new data source (match-day lineup provider) and a much tighter freshness model than this project's weekly batch cadence; explicitly parked, not the same feature as what shipped

**Dropped**
- ~~NBA Big/Wing/Guard bucket UI~~ — superseded by the shipped positionless substitution.
- ~~OOTP as an MLB ratings source~~ — legal exposure too high. Dropped in favor of theshowratings.com, which was itself replaced by The Show's official API (2026-10).
- Historical rating trends - not a part of the scope or goal of this website
- Player comparison - not a part of the scope or goal of this website
- A `CNAME` at the repo root pointing `www.fieldview.com` — didn't work, someone else appears to own it. Site stays on the default GitHub Pages URL.

**Not in FieldView — called ReView:** League leaderboards, game reviews, highlights, replays, podcasts, tweets.
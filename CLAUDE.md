# FieldView — Claude Code Context

Multi-Sport intelligence platform.
Soon to be live at https://www.fieldview.com (custom domain — see Site Infrastructure below; current jwalluww.github.io/fieldview/ URL resolves via GitHub Pages)
Repo: https://github.com/jwalluww/fieldview (public)
Purpose: FieldView is the primary website for sports analytics. Each sport will have a FieldView and a TableView. NFL has FormationView, NBA has CourtView, NHL has IceView, MLB has DiamondView, MLS has PitchView (EPL will also have PitchView). This view will show all the players in their positions on the playing field with important metrics & statistics and substitutions. TableView for each sport will be a table with statistics. Eventually, ReView will be created for each sport. FieldView is for before the game - understanding where players play on the field. ReView is for after the game - replays, highlights, tweets, stats, box scores, etc. - a one-stop-shop for what happened last night or last week in the sport in general.

Flow: NFL, NBA, MLB, and NHL all have a shipped first pass — FormationView/CourtView/DiamondView/IceView and each sport's PlayerTable are all live and reading real data. MLB's ratings are fully resolved (theshowratings.com unblocked via a ScraperAPI proxy, 95.3% of the roster carries a real rating). NBA's and NHL's ratings scrapers are correctly built (retry+fallback+daily-trickle, mirroring Madden's pattern) and running unattended via Windows Task Scheduler, but both source sites (2kratings.com, nhlratings.net) are still mid-cooldown as of the last check — this is expected to resolve on its own over time, not something actively blocking anything. Site-wide analytics and a custom domain are now in soon to be in place (see Site Infrastructure). EPL and MLS are next — no real data-source recon has been done for either yet.

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no frameworks
- Backend: Python 3.11 scrapers
- Hosting: GitHub Pages
- Automation: GitHub Actions (runs Tuesdays at 10am UTC) — note `fetch_stats.py` (NBA) is no longer part of the cloud job, see NBA Stats Scraper section below. Only two jobs exist in `scrape.yml` as of the last check: `scrape` (NFL) and `scrape-nba` (NBA) — MLB and NHL have no cloud automation yet, both are still manual/local (`updateCadence: 'Stub'` on their index-page cards, and correctly so, not an oversight).
- Dev environment: Windows, VS Code + Claude Code extension (chat panel)
- Data pipelines land in DuckDB directly where the source is a live API (statsapi.mlb.com, nhl-api-py) — no intermediate JSON dump. Where the source is a scrape needing careful parsing (theshowratings.com), same DuckDB-first approach once past the network layer.

---

## Site Infrastructure

**Custom domain**: `www.fieldview.com`, via a `CNAME` file at the repo root soon to be pointed at GitHub Pages. Added specifically to unblock Google AdSense, which rejects `github.io` subdomain URLs outright ("URL must be a valid top-level domain") since that domain is shared across every GitHub Pages user, not something any one user actually controls. Also a real upgrade independent of ads — a real domain reads as a real product, not a project page.

**Analytics**: Google Analytics (GA4) wired into all 9 real HTML pages — `index.html` plus every sport's formation/court/diamond/ice view and player-table file. Standard `gtag.js` snippet placed right after `<head>` on each page, Measurement ID `G-TP0M77Z31N`. Added ahead of any real monetization push deliberately: premium ad networks (Mediavine, Raptive/AdThrive) typically want to see an established GA history as part of applying, and AdSense itself has no traffic minimum at all, so there's no reason to have waited.

**Monetization notes, factual not advisory**: AdSense has no minimum traffic requirement. Premium networks gate access by traffic (Mediavine's classic threshold has been ~50,000 sessions **per month**, not per day or week — a common point of confusion) but exact current thresholds should be checked directly on each network's site when actually getting close, not assumed from memory, since these programs get restructured over time.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback.
- Use Claude Code (VS Code chat panel) for implementation, real data verification, and live reconnaissance against external sites/APIs.
- **Reconnaissance against live external systems belongs in Claude Code, handed off as one broader investigation task — not run as a sequence of probe scripts round-tripped through chat.** This chat's sandbox has no working browser and a locked-down network (package registries only, not arbitrary sites/APIs), so any live fact-finding has to go through Claude Code anyway. Splitting it into one probe-per-question wastes round trips; Claude Code can investigate, adjust, and retry inside its own loop and report back once. (MLB's stats-endpoint and ratings-site recon both got done this way properly late in that build; NHL's kickoff recon was handed off as one combined task from the start.)
- **For real scripts, give Claude Code a precise spec with verified facts and named edge cases, rather than full verbatim code written blind in chat.** Chat can't execute or test what it writes — a real bug shipped this way mid-MLB-build (a `fetch_with_retry` helper written without a `timeout` parameter, then called with `timeout=30` anyway, would've thrown immediately). Claude Code, writing and testing its own implementation, independently caught two more substantive bugs later in the same build with zero chat involvement: a blanket-zero `batting_stats` block leaking pure pitchers into batting orders, and a `position_group` mislabel (`'CF'` instead of the group `'OF'`) that would've silently broken one player's substitution eligibility. Neither would've been caught by chat writing code blind.
- Chat's actual value-add on the implementation side is cross-cutting consistency a per-file view might miss: flagging "extract this into a shared file, a second script needs it now" (this is what produced `nfl/scripts/season_utils.py`, `nba/scripts/name_utils.py`, and `mlb/scripts/statsapi_utils.py`), or "these two tables aren't 1:1, don't treat a mismatch as a bug" ahead of time.
- Front-load thinking in chat → hand Claude Code a crisp specific instruction (spec, not code, where the code needs testing to be trusted).
- Start a new chat when switching to a new sport or major new feature area.
- Paste this CLAUDE.md at the top of any new chat to restore context.

---

## Key Cross-Sport Learnings
- **"Verify the real field/column names before writing normalize logic" has paid off on every sport so far** — NFL's EDGE/DI position-alias gap, MLB's stats endpoint field names, NHL's roster/stats shapes were all confirmed against real source code or real API responses before a matching script got written, not assumed from memory or documentation summaries.
- **Silent bulk-endpoint truncation is 3-for-3, but the fix mechanism isn't always the same**: NFL/MLB's `/v1/stats` just needed a bigger `limit`/`playerPool=all` param. NHL's skater/goalie stats endpoints are different — confirmed live that they hard-cap each response at 100 rows server-side *regardless* of the `limit` value passed (tried up to 100000, still 100 back), so the real fix was pagination via the `start` param, not a bigger limit. Worth checking which kind of cap a new bulk endpoint has, not just whether one exists.
- **Anti-bot protection on fan-ratings sites turned out to be a genuinely harder, multi-layered problem than it first looked** — see the full arc in the MLB/NBA/NHL Ratings sections below. Short version: `curl_cffi`'s Chrome-TLS impersonation cleared single-page tests on 2kratings.com and theshowratings.com early on, but repeated full-run attempts on both failed anyway, and theshowratings.com's block was eventually confirmed to also catch a real headless-Chromium session with an unspoofed TLS handshake — meaning at least that block was IP/session-reputation-based, not TLS-fingerprint-based. The fix that actually worked at scale was a residential-proxy service (ScraperAPI), not a better browser impersonation. **Real, generalizable lesson for MLS/EPL's likely-similarly-protected ratings source (sofifa.com)**: don't assume `curl_cffi` alone will be enough just because a single-page test clears — budget for a proxy-service fallback from the start rather than rediscovering this the hard way a third time.
- **A "population mismatch" between a roster snapshot and a season-stats pull is expected, not a bug**: MLB's `statsapi_stats_hitting`/`statsapi_stats_pitching` (702/799 players, includes anyone who played in 2026 at all — including traded/released players) don't 1:1 match `statsapi_roster` (782 players, today's snapshot only). `mlb_players_master.json` uses roster as the base population deliberately, since DiamondView's job is showing today's team, not full-season history. NHL hit the same pattern at a much larger scale (23.3% roster/stats team disagreement) because its roster and stats seasons are a full year apart during the offseason, not just a same-season snapshot-timing gap — same underlying lesson, bigger number.
- **A numeric ID buried in an unrelated-looking asset URL can be a real, reliable join key, but always verify it's the same ID space before trusting it** — theshowratings.com's player photo `data-src` embeds the actual MLB Advanced Media `person_id`, a genuine zero-fuzzy-matching win. nhlratings.net's photo URLs looked like the same pattern but turned out to be the site's own internal WordPress post ID, completely unrelated to the NHL API's `playerId` (confirmed by checking real players — digit counts didn't even match). Worth checking this pattern on sofifa.com too, but confirm it against a real NHL-API-equivalent ID before designing a join around it, not just because the pattern worked once before.
- **Graceful degradation beats "all or nothing" for anything hitting a temperamental external source.** `nfl/scripts/scrape_madden.py`'s retry+cooldown-retry+fallback-to-last-known-data pattern is why Madden "just works" while the ratings scrapers didn't for a long time — not because Madden's site has no protection, but because its script was built to accept partial success instead of requiring a full clean run. This pattern got retrofitted into NHL's and NBA's ratings scrapers and should be the default starting shape for any new scraper hitting a site that might rate-limit or block, not something added after the fact.
- **A real `scrape.yml` push-collision source was found and retired, not just theorized.** Cloud jobs started intermittently failing their own final "Commit updated data" step — e.g. the 2026-08-18 scheduled run, where `scrape`'s (NFL's) every scraping step succeeded and only the `git push` itself was rejected. Traced to a manual `git add`/`commit`/`push` cycle the repo owner ran from their own terminal most mornings (visible in git log as "Automated commit at \<date\>" — despite the name, **not** a registered Task Scheduler job; confirmed via `Get-ScheduledTask` that no such task exists). **That manual cycle was retired as of 2026-08-23.** All four `scrape.yml` jobs' commit steps were also made rebase-safe (`git pull --rebase && git push` instead of a bare `git push`) as a second, independent layer of protection regardless of the source. **If unexplained "Automated commit" entries still appear in git log going forward, treat that as a fresh, real signal worth investigating — don't assume it's resolved just because this note says so;** something else could be pushing.

---

## File Map

### Frontend
- `index.html` — home page, entry cards (shared across sports)
- `nfl/nfl-formation-view.html` — formation view, player cards on field
- `nfl/depth-chart.html` — OOTP-style data table

### Scripts
- `nfl/scripts/scrape_depth.py` — OurLads depth chart scraper
- `nfl/scripts/scrape_madden.py` — Madden ratings scraper, writes `nfl/data/madden.json` (replaced `merge_madden.py`, which no longer exists in the repo — this File Map entry was stale)
- `nfl/scripts/scrape_otc.py` — Over The Cap contract data
- `nfl/scripts/scrape_stats.py` — nflreadpy season stats
- `nfl/scripts/scrape_contracts_spotrac.py` — Spotrac remaining-contract data (years/cash/APY), single-page league-wide scrape
- `nfl/scripts/build_db.py` — DuckDB raw ingestion: loads every scraper's current output into `nfl/data/fieldview.duckdb`, unmodified (one table per source, `row_id` + `loaded_at`). Also fetches the GSIS crosswalk CSV and nflreadpy rosters/snap counts live and caches them as tables instead of re-fetching per run.
- `nfl/scripts/build_match.py` — matching. Imports `find_gsis`/`find_madden_player`/`find_pfr_id`/`find_spotrac_contract` and alias/position-map constants **directly from `build_master.py`** (not reimplemented) and runs them against the DB tables `build_db.py` loaded, writing a `player_match` table.
- `nfl/scripts/export_master.py` — joins `player_match` back to the raw `ourlads_players` table and writes `players_master.json` in the production schema. Takes an output path as its first CLI arg.
- `nfl/scripts/build_master.py` — **not run by the production pipeline anymore** (see `nfl/PIPELINE.md`). Kept only because `build_match.py` imports its matching functions directly; still runs standalone and produces byte-identical output to the DB path.
- `nfl/scripts/season_utils.py` — `get_current_season()`, resolves the active NFL season dynamically from today's date
- `nfl/scripts/resolve_names.py` — diagnostic: fuzzy name match review
- `nfl/scripts/audit_positions.py` — diagnostic: position mapping review

### Data
- `nfl/data/arz.json` ... `nfl/data/was.json` — 32 team JSON files (OurLads source)
- `nfl/data/madden.json` — Madden ratings source
- `nfl/data/players_master.json` — canonical player registry (GSIS-keyed)
- `nfl/data/fieldview.duckdb` — gitignored, rebuilt by `build_db.py` every run; holds the raw per-source tables `build_match.py`/`export_master.py` read

Full pipeline detail (sources, join keys, execution order, current match-rate numbers): `nfl/PIPELINE.md`.

All NFL scripts are invoked from the repo root (e.g. `python nfl/scripts/scrape_depth.py`) and their internal `data/...` references are written as `nfl/data/...` accordingly — cwd stays the repo root, not `nfl/`.

### Frontend (NBA)
- `nba/court-view.html` — starting five in half-court zones + rotation list ranked by minutes, hardwood court background (not a re-skinned field); renamed from `formation.html`
- `nba/player-table.html` — sortable/filterable player table, mirrors `nfl/depth-chart.html`'s pattern

### Scripts (NBA)
- `nba/scripts/fetch_stats.py` — nba_api season averages (`leaguedashplayerstats`) + roster bio (`commonteamroster`, all 30 teams), writes `nba/data/nba_stats.json`. **Runs locally/manually only — removed from the GitHub Actions `scrape-nba` job.** See NBA Stats Scraper section below for why.
- `nba/scripts/scrape_2kratings.py` — 2kratings.com per-team pages (table `id="lists-table"`, no all-players index — 30 separate team-page fetches), writes `nba/data/nba_ratings_2k.json`. Rebuilt as retry+fallback+daily-trickle (mirrors Madden's pattern) — see 2K Ratings Scraper section below. Full 30-team run still blocked; trickle mode (3 random teams/day) is genuinely running via Windows Task Scheduler.
- `nba/scripts/scrape_contracts_spotrac.py` (NBA version, distinct file from `nfl/scripts/scrape_contracts_spotrac.py`) — spotrac.com/nba/contracts/remaining, single-page league-wide scrape, writes `nba/data/contracts_nba.json`
- `nba/scripts/scrape_nbadepthcharts.py` — nbadepthcharts.com's published Google Sheet (CSV export), writes `nba/data/nba_depth_chart.json`. See "NBA Depth Chart Source" below.
- `nba/scripts/build_nba_db.py` — DuckDB raw ingestion: loads `nba_stats.json`/`contracts_nba.json`/`nba_ratings_2k.json`/`nba_depth_chart.json` into `nba/data/fieldview.duckdb`, unmodified (one table per source, `row_id` + `loaded_at`). No live pulls here — every NBA source is already a static file by this point.
- `nba/scripts/build_nba_match.py` — matching (join + resolve). Imports `resolve_position`/`resolve_rotation`/`resolve_team`/`format_salary` **directly from `build_nba_master.py`** (not reimplemented) and runs them against the DB tables `build_nba_db.py` loaded, writing a `player_match` table. Note: the actual fuzzy name matching for NBA already happened upstream, inside each scraper (see below) — this script only joins already-matched sources by `player_id`.
- `nba/scripts/export_nba_master.py` — joins `player_match` back to `nba_stats` and writes `nba_players_master.json` in the production schema. Takes an output path as its first CLI arg.
- `nba/scripts/build_nba_master.py` — **not run by the production pipeline anymore** (see `nba/PIPELINE.md`). Kept only because `build_nba_match.py` imports its resolution functions directly; still runs standalone and produces byte-identical output to the DB path. See "NBA Two-Tier Resolution" below for what it (and now `build_nba_match.py`) actually resolves.
- `nba/scripts/name_utils.py` — shared `normalize_name()`/`normalize_for_matching()`/`NBA_NAME_ALIASES`, used by every NBA scraper that fuzzy-matches against `nba_stats.json` (2k ratings, Spotrac contracts, depth chart) — this is where NBA's real name matching lives, not in the master-build step

### Data (NBA)
- `nba/data/nba_stats.json` — real scraped output from `fetch_stats.py`, league-wide (587 players as of the last run), keyed by nba_api `PLAYER_ID`
- `nba/data/nba_ratings_2k.json` — `{ratings: [...], unmatched: [...]}`, 2K overall ratings matched to `player_id`, records now carry a `loaded_at` timestamp (added this round to distinguish fresh vs. stale-carryover rows, since the file itself previously had no way to answer that). 518/518 records, 509/518 matched (98.3%).
- `nba/data/contracts_nba.json` — `{contracts: [...], unmatched: [...]}`, Spotrac remaining-contract data matched to `player_id`
- `nba/data/nba_depth_chart.json` — `{last_changed, depth_chart: [...], unmatched: [...]}`, nbadepthcharts.com starter/rotation tiers matched to `player_id`
- `nba/data/nba_players_master.json` — canonical merged player registry, keyed by `player_id` (string). This is real data produced by the DB pipeline (`build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py`), and it's what both `court-view.html` and `player-table.html` read. Fields: `player_id, name, team, position, jersey_number, height, weight, ppg, rpg, apg, mpg, games_played, games_started, rotation_status, rotation_source, depth_rank, overall_rating, contract_salary, contract_years_remaining`
- `nba/data/ratings_2k_scrape_state.json` — persisted rolling-pool state for the daily-trickle scraper (`remaining_pool`, `cycle`, `cycle_started`)
- `nba/data/fieldview.duckdb` — gitignored, rebuilt by `build_nba_db.py` every run; holds the raw per-source tables `build_nba_match.py`/`export_nba_master.py` read

Full pipeline detail (sources, join keys, execution order, current match-rate numbers): `nba/PIPELINE.md`.

NBA scripts are also invoked from the repo root (e.g. `python nba/scripts/fetch_stats.py`), same convention as NFL.

### NBA Data Pipeline Order
`fetch_stats.py` first — **now run locally/manually, not in the cloud job** — then `scrape_contracts_spotrac.py` / `scrape_2kratings.py` / `scrape_nbadepthcharts.py` in any order (all independent of each other), then **`build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py nba/data/nba_players_master.json`** last, still in the cloud job. The `scrape-nba` job in `scrape.yml` runs off whatever `nba_stats.json` is currently committed rather than a fresh cloud pull.

---

## Data Pipeline Order (NFL)
Run locally or via GitHub Actions in this exact order (matches `scrape.yml`'s `scrape` job, confirmed against the live workflow file):
1. scrape_depth.py
2. scrape_otc.py
3. scrape_stats.py (uses the `nflreadpy` package, not `nfl_data_py`)
4. scrape_madden.py
5. scrape_contracts_spotrac.py
6. **build_db.py** — raw ingestion into `nfl/data/fieldview.duckdb` (also fetches the GSIS crosswalk + nflreadpy rosters/snap counts live, caching them as DB tables)
7. **build_match.py** — matching, importing functions from `build_master.py` directly
8. **export_master.py nfl/data/players_master.json** — writes the final production file

`resolve_names.py` and `audit_positions.py` are diagnostic only — run locally when investigating match quality, not part of the pipeline. `build_master.py` itself is no longer a pipeline step — see `nfl/PIPELINE.md` §0 for why it's still in the repo.

No need to delete JSONs before running — scrapers overwrite cleanly.

---

## Player JSON Schema (per-team files)
name, depth, injured, attainment, jersey, madden, age, years_pro,
cap_number, stats, stats_season, standard_slot, standard_pos,
madden_rank, madden_rank_total, madden_pos_label

## players_master.json Schema (canonical)
player_id (GSIS if matched, else name-pos-team slug),
gsis_id, match_confidence, canonical_name, ourlads_name,
team, team_name, base_defense, ourlads_pos, standard_slot, standard_pos, depth,
jersey, age, years_pro (computed: current_season - entry_year, via nflreadpy's load_rosters; current_season resolved dynamically via nfl/scripts/season_utils.get_current_season(), not a hardcoded constant), draft_year, college, madden, madden_rank,  madden_rank_total, madden_pos_label, cap_number, attainment, injured, stats (normalized keys), stats_season, nflreadpy_name, match_source,
years_remaining, cash_total_remaining, cash_guaranteed_remaining, avg_annual_remaining (all from Spotrac, fuzzy-matched — no shared ID),
snap_pct (nflreadpy load_snap_counts; matched via pfr_id — GSIS-chain first, independent name+team fuzzy match against the snap-count crosswalk as a second pass for gaps like OL, whose pfr_id is 0% populated in load_rosters)

`standard_pos` values: `QB, WR, RB, TE, OL, EDGE, DI, LB, CB, S`
Special teams (K, P, KR, PR, KO, PK, LS, PT, H) are stripped from pipeline entirely.

---

## Stat Key Normalization
Stats are normalized by position in `build_master.py` via `STAT_MAP`. Canonical keys:
- Passing: `CMP, ATT, PASS_YDS, PASS_TDS, INT, SACK, RUSH_YDS`
- Rushing: `CAR, RUSH_YDS, RUSH_TDS, REC, REC_YDS, TGT, YAC`
- Receiving: `TGT, REC, REC_YDS, REC_TDS, YAC`
- Defense: `TKL, SACK, INT, PBU, TFL, QB_HIT`

Frontend `STAT_COLS` in `nfl/depth-chart.html` uses these canonical keys.

---

## GSIS Matching Pipeline
- GSIS ID is the NFL's own official player-ID system, not something inherently weak on any position — what's actually weak on OL/DI is the **dynastyprocess crosswalk**, the one community-maintained, fantasy-oriented CSV this pipeline uses as its primary GSIS *source*. That distinction matters: it's a source-quality limitation, not a GSIS limitation.
- Primary source: dynastyprocess crosswalk CSV (fantasy-focused, good QB/WR/RB/TE coverage, poor OL/DI coverage)
- Fallback: nflreadpy roster data via `import_weekly_rosters`
- OL skipped entirely from GSIS matching by design (not in the fantasy crosswalk) — 0% OL match rate is intentional, not a gap
- Matching logic: strip to bare letters, no spaces/punctuation/suffixes, fuzzy match within position group first, team as tiebreaker only
- Both the crosswalk and the nflreadpy-rosters fallback get their own `EDGE`/`DI` position-alias translation (`CROSSWALK_POS_ALIASES`/`ROSTERS_POS_ALIASES` in `build_master.py`) before filtering — neither source uses this project's EDGE/DI split natively (crosswalk tags `DE`/small `DL`; rosters collapses both into one `DL` bucket), so without the alias a position-filtered search would silently return zero candidates regardless of name quality. This fix is responsible for most of the match-rate jump below.
- Name aliases handled via `NAME_ALIASES` dict in `build_master.py`
- `None` alias value = force no-match (wrong player in crosswalk)

### Team abbreviation map (dynastyprocess → OurLads)
`ARI→ARZ, KCC→KC, LVR→LV, TBB→TB, SFO→SF, GNB→GB, NOR→NO, NWE→NE`

### Current match results (2026-08-03 run — re-run `build_match.py` for current figures)
- 2,782 total players, 2,082 GSIS matched (74.8%) — up from ~51% before the EDGE/DI alias fix above
- Madden: 2,218/2,782 (79.7%), matched independently by name+team, not gated behind GSIS
- Most remaining unmatched are OL (skipped by design) + defensive depth
- Skill position (QB/WR/RB/TE) unmatched: 15
- **CB/S has the same taxonomy-collapse problem EDGE/DI had, currently unfixed**: nflreadpy rosters (the GSIS fallback source) has *zero* rows tagged `CB` or `S` — all defensive backs use a generic `DB` tag there, so the fallback path can never match a CB/S player at all. A known, accepted limitation, not yet addressed. Full detail: `nfl/PIPELINE.md` §5.

---

## NBA Stats Scraper (nba/scripts/fetch_stats.py)
- stats.nba.com fingerprints on header *completeness*, not just User-Agent — a thin/hand-rolled header dict gets the connection dropped outright even with a convincing UA string. The header set in the script (full Sec-Ch-Ua/Accept-Encoding/Pragma set, not just User-Agent+Referer) was verified against a live pull — don't trim it down.
- **GitHub Actions IP block (resolved):** the script started failing exclusively on the hosted Actions runner — read-timeout after 6 retries, no successful requests at all that run — while working perfectly when run locally on the same day with the same code. Confirmed as an IP-level issue (cloud/datacenter IPs like GitHub-hosted runners get treated worse by stats.nba.com than residential IPs), not a header/code problem, since identical code succeeded locally and failed only on the runner. Fixed by pulling `fetch_stats.py` out of the cloud `scrape-nba` job — it now runs locally/manually only, with the rest of the NBA pipeline (`build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py`) continuing in the cloud off whichever `nba_stats.json` is currently committed.
- `games_started` has no bulk NBA stats endpoint — only `playercareerstats`, one call per player (~580 extra calls for the full league). Decided against pulling it (too slow, too much extra rate-limit exposure for one field). `rotation_status` is derived from minutes-per-game alone instead: starter if MPG >= 24, rotation if MPG >= 15, else bench. **Starting guess, not a settled rule** — revisit once real usage patterns are known.
- Season format is `"YYYY-YY"` (e.g. `"2025-26"`), named by the year it starts (Oct–June) — before October, "current season" resolves to the prior year's, same shape as `nfl/scripts/season_utils.py` but with an October cutoff instead of September.
- Every call goes through an exponential-backoff retry wrapper — stats.nba.com throttles/blocks aggressively, budget for retries not a single clean pull.

---

## 2K Ratings Scraper (nba/scripts/scrape_2kratings.py) — full 30-team run still blocked, but daily-trickle mode is genuinely running
- Started failing with 403 Forbidden mid-run — TLS-fingerprint-class Cloudflare protection, confirmed via a direct browser test showing the site loads fine from the same machine/IP while the script still gets 403'd with a full header set.
- `curl_cffi` (Chrome-120 impersonation) cleared a single-page test cleanly, but full 30-team runs have never completed — best case so far is 1/30 teams before a block. Re-tested after widening per-team pacing to 8-15s (matching NHL/MLB's fix): still blocked at the same point, confirming pacing alone doesn't touch this specific block, consistent with it being TLS-fingerprint/session-class rather than volume-based.
- **Real bug found and fixed**: `fetch_with_retry()` used to exhaust its blocked-retry budget, log, and fall through without raising or returning a response, crashing the caller with `TypeError: Incoming markup is of an invalid type: None`. Now raises the last exception on exhaustion, same as Madden's version.
- **Rebuilt as retry+fallback+daily-trickle, mirroring `nfl/scripts/scrape_madden.py`'s actual pattern**: per-team fetch retries (now raising cleanly), one same-run cooldown retry for whatever's still failed, then fall back to that team's existing rows in `nba_ratings_2k.json` rather than writing empty. Layered under a persisted rolling-pool state file (`nba/data/ratings_2k_scrape_state.json`) sampling 3 random teams per run, upserted immediately.
- **First real trickle-mode test — genuine partial success**: picked `['MIL', 'CHA', 'DET']`. MIL and DET scraped clean (17 rows each); CHA blocked on both the initial pass and the cooldown retry, fell back to its existing 18 rows rather than going empty. Merged file: 518 records across all 30 teams, 509/518 matched (98.3%).
- **`FieldView NBA 2K Ratings Scrape` now genuinely registered** in Windows Task Scheduler (daily, 09:15, via `schedule_2kratings_scrape.bat`) — confirmed via `schtasks /query /v` showing `Status: Ready` and a real `Next Run Time`, not just the command being printed. Real caveat, not yet addressed: `Logon Mode: Interactive only` — this task will not fire if the machine is locked or logged out at its scheduled time, only if an interactive session is active. Worth revisiting (`schtasks /change /RU ... /RP ...` or recreating with "run whether user is logged on or not") if it turns out to matter in practice.
- Added `loaded_at` to the `nba_ratings_2k.json` record schema this round — fresh records get one at scrape time, stale-carryover records keep their original — since there was previously no way to independently verify which records in a merged file were actually fresh vs. carried over.
- **NOT confirmed: 2kratings.com blocking the GitHub Actions runner specifically.** `scrape-nba`'s cloud job used to also invoke this script (bare, no args — same 3-team trickle logic against the same rolling-pool state file as the local Task Scheduler job, not a bigger/different attempt). Its one observed cloud failure (2026-08-18 scheduled run) was, on investigation, more likely caused by that job's `pip install` line never including `curl_cffi` — which this script imports at module load and would crash on immediately — than by a real site-level block against the runner's IP. The step never got far enough to prove either way. It's since been removed from `scrape-nba` entirely (the local trickle already owns `nba_ratings_2k.json`/`ratings_2k_scrape_state.json`; running it again from the cloud only doubled the odds of both writers colliding on a push — see the push-collision note in Key Cross-Sport Learnings), so this is now **untested on Actions with the dependency fixed**, not resolved and not proven blocked either. The local-machine blocking evidence elsewhere in this section (direct browser test, repeated `curl_cffi` full-run failures) is unaffected by this and remains real.

---

## NBA Position Ranking (court-view.html)
- `computePositionRanks(players)` computes each player's league-wide rank within their position group (`PG/SG/SF/PF/C`) by 2K `overall_rating`, e.g. `PF 3/46` — mirrors NFL's `madden_pos_label` convention exactly. Computed once, client-side, in `loadAllPlayers()` right after `allPlayers` is built — league-wide across all 30 teams, not per-team.
- Displayed under the player name on court starters, and replacing the plain position letter in `.bench-meta` for bench rows (falls back to plain `p.pos` if no rank exists, never blank).
- Players with no `overall_rating` get no badge at all — not an "NR" placeholder. **LeBron James currently has `rating: null`** and gets no badge — likely a data bug, not a real gap. **Not yet investigated** — check `nba_ratings_2k.json`'s `unmatched` array for his name before trusting the position-rank feature's edge cases further.
- Ties (equal ratings) get sequential ranks based on JS's stable sort order, not a shared "tied" rank — intentional, not a bug.

---

## NBA Substitution — positionless (in progress, not yet confirmed shipped)
- Original click-to-sub only offered same-position bench players. Abandoned the Guard/Wing/Big bucket idea after research turned up no usable existing data source. **Positionless subbing was chosen as the replacement**, not an addition — any bench player can sub into any court slot now.
- Fix design (drafted, not yet confirmed applied):
  - `getStarter(pos)`'s natural-fallback path now excludes any player id already placed via `manualStarters` in a *different* zone.
  - The subs popover excludes all 5 currently-resolved starters (not just the clicked zone's own starter), computed via `getStarter()` across `ZONE_ORDER`.
  - `substitutePlayer(pid, targetPos)` now takes the target zone explicitly rather than deriving it from the incoming player's own position.
- The position-rank badge still shows the player's *real* position regardless of which zone they're standing in.

---

## NBA Depth Chart Source (nba/scripts/scrape_nbadepthcharts.py)
- Source: nbadepthcharts.com, which embeds a published Google Sheet via iframe. Fetched via the sheet's own CSV export URL — plain `requests.get`, no headless browser needed.
- Structure: 30 team blocks, each laying out 4 depth tiers (STARTERS/2ND STRING/3RD STRING/OTHER) as 4 fixed-width column groups side by side. Parsed by fixed column position, not the sheet's own sub-header text (Washington's sub-header row is corrupted at the source).
- Only **Rookie** status survives into the CSV as plain text; the other 4 legend flags are color-only and would need a headless browser to read.
- Name-matching edge cases fixed via `NBA_NAME_ALIASES`: "Ron Holland" (missing "II" suffix) and "Egor Dёmin" (Cyrillic 'е' vs. Latin 'ë').
- Match rate: 440/518 (84.9%). Of the 78 unmatched, 59 are draft picks not yet in `nba_stats.json`'s roster snapshot, 19 are veterans genuinely absent from that snapshot.

### Staleness Tracking
- `last_changed` computed by diffing each run's parsed output against the previous run's — unchanged data carries the date forward, changed data bumps it to today. Deliberately not using the site's own displayed date, confirmed it just prints today's date via JS regardless of actual freshness.

---

## NBA Two-Tier Resolution (build_nba_master.py, imported by build_nba_match.py)
- `resolve_rotation()`/`resolve_team()` both layer: a `nba_depth_chart.json` match wins if present (`rotation_source: "nbadepthchart.com"`, real `depth_rank`), otherwise falls back to `nba_stats.json`'s MPG-derived value (`rotation_source: "mpg_derived"`, `depth_rank: null`). Both tiers coexist by design so `rotation_source` is always debuggable.
- nbadepthcharts.com reflects trades faster than the stats snapshot — 87 players had their `team` corrected this way as of the last merge.

---

## NBA Team Logos (court-view.html)
- `cdn.nba.com` returns 200 to a plain GET but fails with `ERR_HTTP2_PROTOCOL_ERROR` on actual browser navigation (verified via Playwright) — would break for real visitors despite looking fine in a quick test.
- ESPN's CDN verified working both ways, all 30 codes. Two exceptions: New Orleans is `no` (not `nop`), Utah is `utah` (not `uta`).

---

## NBA Navigation
- `index.html` reads `?sport=` from the URL at load via `selectSport()`.
- Both NBA pages' logo/back buttons link to `../index.html?sport=nba`.
- Index page background: per-sport texture generated at runtime as inline SVG data URIs (`nflTexture()`/`nbaTexture()`/`mlbTexture()`/`nhlTexture()`/`placeholderTexture()`/`applyFieldBackground(sport)`).

---

## CourtView Frontend Interactions (court-view.html)
- **Layout:** two-column — `.left-col` (compact court) + `.right-col` (full bench/rotation list). Bench rows show PPG/RPG/APG/MPG per player.
- **Court zone alignment (resolved):** `COURT_ZONES` needed correction once the court render doubled in size — offset post positions instead of a dead-center-under-the-hoop `C`.
- **Substitution — now positionless**, see NBA Substitution section above. `manualStarters` remains pure frontend view state, reset on every team switch.
- **Hover stat popup**: `mouseenter`/`mouseleave` attached directly per rendered node, re-attached after every render via `attachPopupHandlers()`.
- **Known gap**: `.subs-name` in the substitution popover still truncates long names.

---

## Formation View
- Team selector persisted via localStorage, overridden by URL params
- Formation sharing via URL: `?team=KC&unit=defense&pkg=nickel`
- Offense/defense toggle, 11/12 personnel, base/nickel defense
- Auto-detects 3-4 vs 4-3 from `base_defense` field in team JSON
- Package keys: `11, 12, base43, base34, nickel, nickel34`
- Player cards: Madden color gradient, hover card (stats/cap/age), substitution dropdown
- Tags: INJ, R (rookie), attainment
- Mobile responsive (v1 — functional, not polished)

---

## Depth Chart Table
- Loads all 32 teams at once from `players_master.json`
- OOTP-style view tabs: Overview, Financial, Madden Ratings, Passing, Rushing, Receiving, Defense
- Sortable columns, nulls always sort last
- Filters: search, team, unit, position, depth
- Sticky header/filter bar
- Two position columns: ourlads_pos (specific slot) + standard_pos (group badge)
- Mobile: card list layout below 600px breakpoint

---

## MLB (DiamondView) — shipped, including ratings

### Data sources, verified before building anything
- **Roster + bio**: `statsapi.mlb.com` (MLB's own public API, no key required).
  - `GET /v1/teams` — team list, real `abbreviation` field
  - `GET /v1/teams/{teamId}/roster?rosterType=active` — roster, jersey number, position code/abbreviation/name, status
  - `GET /v1/people?personIds=...` (bulk) — height, weight, birth date, `batSide`/`pitchHand` codes, primary position
- **Stats**: same `statsapi.mlb.com`, `GET /v1/stats?stats=season&group=hitting|pitching&sportIds=1&season=YYYY&limit=2000&playerPool=all`. **`playerPool=all` is load-bearing** — without it, only "qualified" players come back (142 hitters / 55 pitchers in a real test). With it: 702 hitters, 799 pitchers.
- **Ratings**: `theshowratings.com`, base/live ratings only, no Diamond Dynasty content. Official `theshow.com/roster_updates` intentionally not scraped (higher legal exposure than a fan site). OOTP ruled out entirely for the same reason.

### Real column names confirmed (from live `DESCRIBE` output)
- Hitting (41 cols): `avg, obp, slg, ops, babip, stolenBasePercentage` are VARCHAR; `homeRuns, rbi, hits, runs, strikeOuts, stolenBases` etc. are BIGINT. `plateAppearances` is the real PA field name.
- Pitching (69 cols): `era, whip, inningsPitched, strikeoutsPer9Inn, walksPer9Inn, winPercentage` are VARCHAR; `wins, losses, saves, strikeOuts, battersFaced` etc. are BIGINT.

### Position taxonomy — clean, no EDGE/DI-style collapse
Real distribution from `statsapi_roster` (782 rows): `P 390, C 63, CF 48, 2B 48, RF 45, LF 44, SS 42, 3B 41, 1B 38, DH 21`, plus two singleton edge cases:
- `TWP` (Ohtani) — `player_type: "two_way"`, `position_group: null`.
- `OF` (Cristian Pache) — `position_group` stays the clean `"OF"` group value with `position_group_source: "defaulted"` flagging the specific field zone wasn't in the source data.

`position_group` mapping: IF = `1B/2B/3B/SS`, OF = `LF/CF/RF`, standalone = `C/P/DH`.

### mlb/scripts/ pipeline
- `scrape_roster.py` — all 30 teams, 780 roster rows / 780 people rows (exact parity).
- `scrape_stats.py` — bulk `playerPool=all` pull, 702 hitting / 799 pitching rows.
- `build_mlb_match.py` — joins roster + bio + left-joins hitting/pitching stats on `person_id`, roster as base population. Derives `position_group`/`player_type`. **Now also left-joins `show_ratings` onto the roster population by `person_id`**, deduped defensively by most-recent `loaded_at` (zero duplicates observed in the current pull, dedup runs unconditionally anyway since a future trade could produce one).
- `export_mlb_master.py <output_path>` — writes `mlb/data/mlb_players_master.json`. **782 players**. Fields: `player_id, name, team, team_abbr, position, position_group, position_group_source, player_type, jersey_number, height, weight, bats, throws, batting_stats, pitching_stats, match_source, overall_rating, potential`. Stats match rate: 779/782 (99.6%). **Ratings match rate: 745/782 roster players (95.3%)** carry a real `overall_rating`/`potential`; unmatched get `null`, never dropped/defaulted.

### theshowratings.com Scraper — RESOLVED via ScraperAPI proxy
- Plain `requests` and `curl_cffi` (Chrome-120 impersonation) both eventually got a real, persistent Cloudflare 403 — three sessions in a row, immediate block on team 1, getting worse each time rather than better.
- **Real finding: a genuine headless-Chromium (Playwright) session got the identical 403**, byte-for-byte the same block page, no JS challenge markers present. This ruled out TLS fingerprinting as the cause for this specific site — a real, unspoofed browser TLS handshake failed too, pointing at IP/session-reputation blocking instead, which no amount of better browser impersonation fixes.
- **Fix that actually worked: a ScraperAPI proxy.** `SCRAPERAPI_KEY` read from the environment (never hardcoded/committed), requests routed through `http://api.scraperapi.com?api_key={key}&url={target}`. Single-page test cleared first (183KB real page vs. the ~52-byte block page) before spending a full run on it. **Full 30-team run completed clean: 1346 rows, 30/30 teams fresh** (Washington needed one same-run cooldown retry). First time this site was ever fully collected in this project.
- **Real bug found and fixed, dormant since the script was first written**: `parse_team_page()` read player data from `tds[0]`, but that's actually the row-counter cell (`"1."`) — real cells are `tds[1]`/`tds[2]`/`tds[3]`. Never surfaced before because every prior run got blocked before reaching real content to parse against.
- 747/1346 rows (55.5%) join to `statsapi_roster.person_id` directly — expected, not a problem, since theshowratings.com pulls full org depth (40-51 rows/team), not just the 26-man active roster. The clean numeric-ID join itself (via the photo `data-src` URL) is confirmed solid on real players (Ketel Marte 606466, Corbin Carroll 682998, Geraldo Perdomo 672695).

### MLB Team Logos (diamond-view.html, player-table.html)
- ESPN's MLB CDN, verified live. Two exceptions: Arizona is `ari` (not `az`), Chicago White Sox is `chw` (not `cws`). Athletics' `ath`/`oak` are byte-identical, either works.

### DiamondView Frontend (mlb/diamond-view.html)
- Mirrors `court-view.html`'s real patterns: `DIAMOND_ZONES`, `ZONE_ORDER`, `ESPN_TEAM_CODES`/`teamLogoUrl()`, `getStarter()`/`substitutePlayer()`, `attachPopupHandlers()`.
- 9 fielding zones (P/C/1B/2B/3B/SS/LF/CF/RF) — held up correctly on the first real render. DH is not a field zone, batting-order sidebar only.
- **Substitution gated by `position_group`**: IF-for-IF, OF-for-OF, C/P/DH standalone.
- **Batting order derived** (no real daily-lineup source exists): batters ranked by plate appearances descending, pitchers split into starters (`gamesStarted > 0`) vs. bullpen.
- **Ohtani (`TWP`) P-zone fix**: additionally allows `player_type === 'two_way'`, scoped to the P-zone pool only.
- **Real bug found and fixed**: `statsapi.mlb.com` gives every rostered player a present `batting_stats` block (all zeros for pure pitchers) — was leaking zero-stat pitchers into batting orders. Fixed with a `pa > 0` gate.

### PlayerTable (mlb/player-table.html)
- Mirrors `nfl/depth-chart.html`'s real-named-columns-per-tab pattern (not NBA's flat single-column-set approach) — MLB's batting/pitching stats are disjoint like NFL's position-split stats.
- 3 tabs: Overview / Batting / Pitching.
- **Sort fix**: `avg/obp/slg/ops/era/whip/ip` need `parseFloat()`, not string comparison — naive string-sort ranked ERAs of 10+ ahead of legitimate 2.00-2.08 arms.
- **Null handling diverges from NFL's**: a real `0 HR` or `0 SO` is meaningful data, not missing. Only true `null`/`''` sorts last.

---

## NHL (IceView) — shipped, ratings still blocked pending cooldown

### Data sources, verified before building anything
- **Package**: `nhl-api-py`. Two API bases: `api-web.nhle.com/v1/` (roster, standings) and `api.nhle.com/stats/rest/` (stats, uses a `cayenneExp` filter-expression query language).
- **Roster**: `GET /v1/roster/{team_abbr}/{season}` — returns `forwards`/`defensemen`/`goalies` groups, not a flat list. Real fields: `id, firstName.default, lastName.default, sweaterNumber, positionCode, birthDate, birthCountry`.
- **Bulk stats**: `skater_stats_summary()`/`goalie_stats_summary()`. **Gotcha**: both endpoints hard-cap at 100 rows per response *regardless* of the `limit` value passed — real fix is pagination via `start`, not a bigger limit.
- **Season format is `YYYYYYYY`** (e.g. `"20252026"`). `nhl/scripts/season_utils.py`'s `resolve_seasons()` calls `standings.season_standing_manifest()` for real per-season end dates. **Real, non-obvious finding**: roster and stats need two *different* season ids during the offseason — roster uses the upcoming season id (fuller/current), stats uses the prior/completed season id (upcoming returns zero rows until games are played).

### Ratings sources
- **Official**: `ea.com/games/nhl/ratings` — populated only starting with NHL 27, currently empty.
- **Fan-made**: `nhlratings.net` — structure confirmed: 32 per-team pages (`/teams/{team-slug}`), a main roster table + small IR table, separate `/lists/{position}` pages, individual player pages at a bare name-slug URL.
- **No clean join key here, unlike MLB — confirmed, not assumed**: photo URLs embed a numeric ID, but it's a different ID space entirely from the NHL API's `playerId` (checked 2 real players, digit counts didn't even match — likely the site's own internal WordPress post ID). Matches by name+team instead via `nhl/scripts/name_utils.py`, ported from NBA's approach.
- **Caveat found, not chased down**: TOR's team page lists Sergei Bobrovsky (Florida's real goalie) as a Maple Leaf — likely a lag in this "NHL 27" ratings data's own update cadence vs. live transactions, same class of staleness risk as NBA 2K.
- **Blocked, real Cloudflare 403** — one full-run attempt with `curl_cffi` (matching pacing already at 8-15s) got 1/32 teams (ANA, 37 rows, 91.9% matched) before blocking on team 2. **Rebuilt as retry+fallback+daily-trickle**, mirroring Madden's pattern, same as NBA's. First real trickle test (`['PHI','CHI','WPG']`) got all 3 blocked on both the initial pass and the cooldown retry — no existing data to fall back to, so `nhl_ratings` was correctly left uncreated rather than written empty. **`FieldView NHL Ratings Scrape` genuinely registered** in Task Scheduler (daily, 09:00) — same `Logon Mode: Interactive only` caveat as NBA's task.
- **Unlike MLB's theshowratings.com, nhlratings.net hasn't been tried through a proxy service yet** — worth considering if the site's own cooldown doesn't lift on its own.

### Status
- **`nhl_roster`**: 811 rows, all 32 teams. By `position_group`: 468 forwards, 260 defensemen, 83 goalies. `sweater_number` missing on 42/811 (5.2%, incoming signees without a number yet). Season resolved to `20262027`.
- **`nhl_stats_skaters`**: 940 rows league-wide, season `20252026`. **`nhl_stats_goalies`**: 98 rows.
- **ID space confirmed shared** between `nhl_roster.player_id` and `nhl_stats_skaters.playerId` — verified by name on 5 real players (Burns, Perry, Ovechkin, Malkin, Crosby), all matched correctly.
- **Roster-vs-stats team disagreement, real and large**: of 703 joined skaters, 164 (23.3%) show a different team; 50 are legitimate multi-team stat rows, 114 are genuine offseason moves. `nhl_roster` is the trusted source for "current team," never `teamAbbrevs`.
- **`nhl_players_master.json` built**: 811 players, 779 matched to skater/goalie stats (96.1%). Shipped without ratings — `build_nhl_match.py` checks for the ratings table's existence and joins it automatically once one exists.

### IceView Frontend (nhl/ice-view.html)
- Mirrors `diamond-view.html`/`court-view.html`'s real patterns.
- **6 rink zones**: LW, C, RW, D, D, G — two generic `D1`/`D2` slots (both display as plain "D"), since `nhl_roster.position_code` has no L-D/R-D split, just a single `D` value for all defensemen.
- **Starters**: forward zones ranked by `timeOnIcePerGame` within their real `position_code` (L/C/R). Either D zone takes any `D`. Goalie starter is highest `gamesStarted`.
- **Substitution — positionless within group**: forward pool positionless across LW/C/RW, D pool positionless across both D zones, G standalone.
- **No 0-99 rating yet** (site still blocked) — dot color/display driven by `pointsPerGame`/`points` (skaters) and `savePct` (goalies) instead.
- **ESPN team-logo exceptions, verified live**: Los Angeles is `la` (not `lak`), San Jose is `sj` (not `sjs`), Tampa Bay is `tb` (not `tbl`). New Jersey stayed the full `njd`.

### PlayerTable (nhl/player-table.html)
- Mirrors `mlb/player-table.html`'s real-named-columns-per-tab pattern. 3 tabs: Overview / Skaters / Goalies.
- **Confirmed no MLB-style VARCHAR problem**: `faceoffWinPct`, `pointsPerGame`, `shootingPct`, `timeOnIcePerGame`, `goalsAgainstAverage`, `savePct` all came back as real JSON numbers — no `parseFloat` coercion needed.
- 5 real `position_code` filter values (`C, L, R, D, G`), with `L`/`R` displayed as `LW`/`RW` in filter labels.

---

## Conventions & Gotchas
- OurLads abbreviations: `ARZ` (not ARI), `JAX` (not JAC)
- Team JSON can come out as a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`
- Minimal targeted edits only — no unrelated refactors, no adjacent "improvements"
- Match existing code style even if you'd write it differently
- No speculative features or config beyond what's asked
- Plain HTML/CSS/JS only — no React, no build tools
- Live Server (VS Code extension by Ritwick Dey) for local dev preview
- **Scraper hardening pattern, corrected after this round's evidence**: anti-bot protection isn't one problem with one fix. TLS-fingerprint impersonation (`curl_cffi`) genuinely clears some blocks (single-page tests on 2kratings.com/theshowratings.com both cleared this way) but not all of them at scale — theshowratings.com's actual block turned out to be IP/session-reputation-based, confirmed by a real headless browser hitting the identical 403. The fix that worked there was a residential-proxy service, not a better TLS fingerprint. Budget for both tools being needed, in that order (try impersonation first since it's free, escalate to a proxy service if a full run still won't clear), rather than assuming the first thing that clears a single-page test is the complete fix.
- **Silent bulk-endpoint truncation** is 3-for-3, but not always the same fix: NFL/MLB's `/v1/stats` just needs a bigger `limit`/`playerPool=all`; NHL's `/stats/rest` skater/goalie endpoints hard-cap at 100 rows per response regardless of `limit`, requiring real pagination via `start`.
- **Graceful degradation over all-or-nothing**: any scraper hitting a source that might rate-limit or block should default to Madden's pattern (retry, cooldown-retry, fall back to last-known-good data) from the start, not bolt it on after repeated full failures.

---

## Known Outstanding Bugs
- OL snap-share coverage sits at ~61% (306/504) — real data-source ceiling, not considered worth chasing further
- NFL: CB/S has the same position-taxonomy-collapse problem EDGE/DI had — nflreadpy rosters tags all defensive backs generically as `DB`. Known, not fixed.
- NBA: no undo path for a single court substitution short of switching teams away and back
- NBA: `.subs-name` popover text truncation
- NBA: LeBron James `rating: null` in `nba_players_master.json` — suspected 2kratings.com name-match bug. Not yet checked against `nba_ratings_2k.json`'s `unmatched` array.
- NBA: `scrape_2kratings.py`'s full 30-team run is still blocked (never completed one in this project). Trickle mode is working at its own scale, not resolved at the full-run scale.
- ~~MLB: `scrape_ratings.py` (theshowratings.com) blocked~~ — **RESOLVED** via a ScraperAPI proxy. Full 30-team run completed clean, joined into `mlb_players_master.json` (95.3% roster coverage).
- NHL: `scrape_ratings.py` (nhlratings.net) rebuilt as retry+fallback+daily-trickle. A real 3-team trickle test still got blocked on all 3. Not resolved at the site level; the trickle design is built and tested, waiting on the site's cooldown to lift (or a proxy service, untried here so far).

---

## Roadmap

**In Progress**
- ⬜ **EPL & MLS expansion kickoff** — the last two sports on the original roadmap. No real data-source recon done for either yet (no roster/stats API confirmed, no ratings site probed). sofifa.com/EA FC flagged as the strongest ratings candidate for both leagues combined, worth checking whether one scraper genuinely covers both before treating them as two separate builds. Given this round's hard-won lesson on anti-bot protection (see Key Cross-Sport Learnings), budget for a proxy-service fallback from the start if sofifa.com turns out to be Cloudflare-protected, rather than rediscovering the curl_cffi-isn't-always-enough lesson a third time.
- ⬜ 2K ratings scraper — full 30-team run still blocked, daily-trickle mode running and genuinely working at its own pace.
- ⬜ NHL ratings scraper — same status as 2K; a proxy-service attempt (MLB's fix) hasn't been tried here yet.
- ⬜ Tactical stat selection — feeds both FieldView hover/bench cards and TableView columns across all sports, solve once.

**Up Next**
- ⬜ Opponent overlay (NFL)
- ⬜ Additional NFL data sources via `nflreadpy`: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()` — all free, unused
- ⬜ NFL age source swap — OurLads to Spotrac
- ⬜ TableView stat/view-package refinement across all sports
- ⬜ Popover `.subs-name` truncation fix (NBA)
- ⬜ LeBron James `rating: null` investigation
- ⬜ NBA positionless substitution — design drafted, not yet confirmed applied/verified

**Backlog**
- ⬜ ReView overview — replays, highlights, box scores, tweets, podcasts; comes after every sport's FieldView/TableView are dialed in
- ⬜ Mobile responsiveness pass — desktop-only is the explicit call for now
- ⬜ NBA table view column cleanup (same treatment NFL's/MLB's/NHL's tables already got)

**Wish List**
- ⬜ Player comparison
- ⬜ Historical rating trends

**Dropped**
- ~~NBA Big/Wing/Guard bucket UI~~ — no usable existing data source found. Superseded by positionless substitution.
- ~~OOTP as an MLB ratings source~~ — legal exposure too high for a paid game's extracted files in a public repo. Dropped in favor of theshowratings.com.

**Not in FieldView - called ReView:** League leaderboards, game reviews, highlights, replays, podcasts, tweets — these belong in a separate media/highlights page down the road.

---

## NFLDATAPY
nflreadpy — a few of these are genuinely worth grabbing:

`load_ftn_charting()` — FTN's charted stats (pressure rate, missed tackles, target quality) are free and already in nflreadpy, worth trying before a PFF scrape.
`load_nextgen_stats()` — real tracking-derived metrics (separation, time to throw, closing speed) — exactly the kind of layered data that makes a player comparison view interesting.
`load_participation()` — personnel groupings and snap-level participation, directly relevant to formation view and the planned opponent overlay.
`load_combine()` — combine results, already on the roadmap as a separate source, sitting here for free too.
`load_contracts()` (OTC data) also exists here — redundant with the working Spotrac/OTC pipeline, not a gap.
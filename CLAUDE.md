# FieldView — Claude Code Context

NFL (and soon multi-sport) intelligence platform.
Live at https://jwwalluww.github.io/fieldview/
Repo: https://github.com/jwwalluww/fieldview (public)

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no frameworks
- Backend: Python 3.11 scrapers
- Hosting: GitHub Pages
- Automation: GitHub Actions (runs Tuesdays at 10am UTC)
- Dev environment: Windows, VS Code + Claude Code extension (chat panel)

---

## File Map

### Frontend
- `index.html` — home page, entry cards (shared across sports)
- `nfl/nfl-formation-view.html` — formation view, player cards on field
- `nfl/depth-chart.html` — OOTP-style data table

### Scripts
- `nfl/scripts/scrape_depth.py` — OurLads depth chart scraper
- `nfl/scripts/merge_madden.py` — merges Madden ratings + position ranks
- `nfl/scripts/scrape_otc.py` — Over The Cap contract data
- `nfl/scripts/scrape_stats.py` — nflreadpy season stats
- `nfl/scripts/scrape_contracts_spotrac.py` — Spotrac remaining-contract data (years/cash/APY), single-page league-wide scrape
- `nfl/scripts/build_master.py` — builds players_master.json with GSIS matching
- `nfl/scripts/season_utils.py` — `get_current_season()`, resolves the active NFL season dynamically from today's date
- `nfl/scripts/resolve_names.py` — diagnostic: fuzzy name match review
- `nfl/scripts/audit_positions.py` — diagnostic: position mapping review

### Data
- `nfl/data/arz.json` ... `nfl/data/was.json` — 32 team JSON files (OurLads source)
- `nfl/data/madden.json` — Madden ratings source
- `nfl/data/players_master.json` — canonical player registry (GSIS-keyed)

All NFL scripts are invoked from the repo root (e.g. `python nfl/scripts/scrape_depth.py`) and their internal `data/...` references are written as `nfl/data/...` accordingly — cwd stays the repo root, not `nfl/`.

### Frontend (NBA)
- `nba/formation.html` — starting five in half-court zones + rotation list ranked by minutes, hardwood court background (not a re-skinned field)
- `nba/player-table.html` — sortable/filterable player table, mirrors `nfl/depth-chart.html`'s pattern

### Scripts (NBA)
- `nba/scripts/fetch_stats.py` — nba_api season averages (`leaguedashplayerstats`) + roster bio (`commonteamroster`, all 30 teams), writes `nba/data/nba_stats.json`

### Data (NBA)
- `nba/data/nba_players_master.json` — hand-built stub (13 mock players, LAL/BOS/DEN only) used to build/verify the frontend before any real pipeline existed. **Not wired to `nba_stats.json`** — the frontend still reads this stub, not the real scrape.
- `nba/data/nba_stats.json` — real scraped output from `fetch_stats.py`, league-wide (582 players), keyed by nba_api `PLAYER_ID`

NBA scripts are also invoked from the repo root (e.g. `python nba/scripts/fetch_stats.py`), same convention as NFL.

---

## Data Pipeline Order
Run locally or via GitHub Actions in this exact order:
1. scrape_depth.py
2. scrape_otc.py
3. scrape_stats.py (now uses the `nflreadpy` package, not `nfl_data_py` — switched this session)
4. merge_madden.py
5. scrape_contracts_spotrac.py
6. build_master.py (pulls in nflreadpy's load_rosters + load_snap_counts directly, plus nfl/data/spotrac_contracts.json)

`resolve_names.py` and `audit_positions.py` are diagnostic only — run locally when investigating match quality, not part of the pipeline.

No need to delete JSONs before running — scrapers overwrite cleanly. `build_master.py` skips any file with "master" in the name.

**Note:** `build_master.py` not yet added to `scrape.yml`. When ready, add it after merge_madden step and add `pandas rapidfuzz` to the pip install line.

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
- Primary source: dynastyprocess crosswalk CSV (fantasy-focused, good QB/WR/RB/TE coverage, poor OL/DI coverage)
- Fallback: nflreadpy roster data via `import_weekly_rosters` (was broken/TBD, resolved this session)
- OL skipped entirely from GSIS matching (not in fantasy crosswalk)
- Matching logic: strip to bare letters, no spaces/punctuation/suffixes, fuzzy match within position group first, team as tiebreaker only
- Name aliases handled via `NAME_ALIASES` dict in `build_master.py`
- `None` alias value = force no-match (wrong player in crosswalk)

### Team abbreviation map (dynastyprocess → OurLads)
`ARI→ARZ, KCC→KC, LVR→LV, TBB→TB, SFO→SF, GNB→GB, NOR→NO, NWE→NE`

### Current match results
- 2784 total players, 1432 GSIS matched (~51%)
- Most unmatched are OL + defensive depth (expected, no stats anyway)
- Skill position (QB/WR/RB/TE) unmatched: 107

---

## NBA Stats Scraper (nba/scripts/fetch_stats.py)
- stats.nba.com fingerprints on header *completeness*, not just User-Agent — a thin/hand-rolled header dict gets the connection dropped outright even with a convincing UA string. The header set in the script (full Sec-Ch-Ua/Accept-Encoding/Pragma set, not just User-Agent+Referer) was verified against a live pull — don't trim it down.
- `games_started` has no bulk NBA stats endpoint — only `playercareerstats`, one call per player (~580 extra calls for the full league). Decided against pulling it (too slow, too much extra rate-limit exposure for one field). `rotation_status` is derived from minutes-per-game alone instead: starter if MPG >= 24, rotation if MPG >= 15, else bench. **Starting guess, not a settled rule** — revisit once real usage patterns are known.
- Season format is `"YYYY-YY"` (e.g. `"2025-26"`), named by the year it starts (Oct–June) — before October, "current season" resolves to the prior year's, same shape as `nfl/scripts/season_utils.py` but with an October cutoff instead of September.
- Every call goes through an exponential-backoff retry wrapper — stats.nba.com throttles/blocks aggressively, budget for retries not a single clean pull.

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
- `syncFieldHeight()` called after render to fix mobile field scaling

---

## Depth Chart Table
- Loads all 32 teams at once from `players_master.json` (wired this session — was per-team JSONs)
- OOTP-style view tabs: Overview, Financial, Madden Ratings, Passing, Rushing, Receiving, Defense
- Sortable columns, nulls always sort last
- Filters: search, team, unit, position, depth
- Sticky header/filter bar (dynamic offset via `updateStickyOffset()`)
- Two position columns: ourlads_pos (specific slot) + standard_pos (group badge)
- Special teams positions removed from display
- Mobile: card list layout below 600px breakpoint

---

## Conventions & Gotchas
- OurLads abbreviations: `ARZ` (not ARI), `JAX` (not JAC)
- Team JSON can come out as a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`
- Minimal targeted edits only — no unrelated refactors, no adjacent "improvements"
- Match existing code style even if you'd write it differently
- No speculative features or config beyond what's asked
- Plain HTML/CSS/JS only — no React, no build tools
- Live Server (VS Code extension by Ritwick Dey) for local dev preview

---

## Known Outstanding Bugs
- `build_master.py` not yet added to `scrape.yml`
- OL snap-share coverage sits at ~61% (306/504) — real data-source ceiling (import_snap_counts/PFR crosswalk coverage for OL specifically), not considered worth chasing further
- NBA: `nba_players_master.json` (3-team mock stub) and `nba_stats.json` (real 582-player scrape) are two separate files, not yet merged — no NBA equivalent of `build_master.py` exists yet, so the frontend still reads the stub
- NBA: no contracts data yet (Spotrac NBA scraper in progress)

---

## Roadmap (priority order)
1. ⬜ Finish player identity pipeline (fix bugs above, get skill-pos unmatched count)
2. ✅ Wire `depth-chart.html` and `nfl-formation-view.html` to `players_master.json` (each keeping its own loading strategy — depth chart loads all 32 teams at once, formation view fetches/filters per team)
3. ✅ Fix formation view hybrid scheme bug (Colts, Seahawks missing defender)
4. ⬜ Opponent overlay — same-team offense+defense simultaneously, then versus view
5. ✅ Additional data sources (contracts): Spotrac remaining-contract data (years/cash/APY), snap share via nflreadpy's load_snap_counts
6. ⬜ Additional data sources (advanced metrics): PFF grades, RAS scores, combine data, EPA/DVOA (see note below about nfldatapy)
7. ⬜ Player comparison
8. ⬜ Historical rating trends
9. ⬜ Multi-sport expansion — MLB first, then NHL/NBA/MLS/EPL

**Not in FieldView scope:** League leaderboards, game reviews, highlights, replays, podcasts, tweets — these belong in a separate media/highlights page down the road. Called ReView for being able to review the past day/week of games, highlights, box scores, stats, tweets, drama, reddit posts, podcasts, etc. Just to catch up on the league and all it's action.

---

## NFLDATAPY
nflreadpy — yes, a few of these are genuinely worth grabbing, and one of them actually shortcuts your own roadmap:

load_ftn_charting() — this is the one I'd flag hardest. Your roadmap lists PFF as a future paid data source, but FTN's charted stats (pressure rate, missed tackles, target quality, that kind of PFF-style manual charting) are free and already in nflreadpy. Worth trying before you go looking for a PFF scrape.
load_nextgen_stats() — real tracking-derived metrics (separation, time to throw, closing speed, etc.). This is exactly the kind of "surprising, layered" data that makes a player comparison view actually interesting instead of just a stat table.
load_participation() — personnel groupings and snap-level participation. This one's relevant specifically to formation view and your planned "opponent overlay" — it's literally per-play personnel package data, which is the same shape of information your formation view already visualizes.
load_combine() — combine results, already on your roadmap as a separate source, but it's just sitting here for free too.

load_contracts() also exists here (OTC data) — you already have a working Spotrac/OTC pipeline for that, so I wouldn't switch just to consolidate, but worth knowing it's redundant with what you built rather than a gap.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback
- Use Claude Code (VS Code chat panel) for direct file edits
- Front-load thinking in chat → hand Claude Code a crisp specific instruction
- Start a new chat when switching to a new sport or major new feature area
- Paste this CLAUDE.md at the top of any new chat to restore context

---

NFL v1 considered feature-complete as of 2026-07-23 — remaining polish will be driven by live usage once the season starts. Next sport: NBA.
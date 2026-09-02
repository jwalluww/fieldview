# Last verified against the live site: 2026-07-24. This is the most
# likely of the NBA scrapers to break on a redesign -- it scrapes 2K's
# fan-run ratings site (2kratings.com), not an official API, and there
# is no "all players" table: ratings live per-team on 30 separate pages
# (table id="lists-table"), reached only by browsing a team page, not
# from any single index. If this stops working, re-fetch a team page
# (e.g. https://www.2kratings.com/teams/los-angeles-lakers) and re-verify
# the table id and column structure before assuming the parser is still
# right -- don't just bump a selector and hope.
#
# RUN LOCALLY ONLY -- NOT IN GITHUB ACTIONS. Cloud/datacenter IPs get
# treated worse by this class of anti-bot protection than residential
# IPs -- already confirmed the hard way in this project on
# nba/scripts/fetch_stats.py (stats.nba.com started failing exclusively
# on the hosted Actions runner with clean local runs on the same code,
# same day -- see CLAUDE.md's "NBA Stats Scraper" section). Don't
# "helpfully" move this into scrape.yml's scrape-nba job; run it locally
# via schedule_2kratings_scrape.bat (see bottom of this file for the
# suggested -- not registered -- schtasks command).
#
# PART 1 -- retry + fallback (mirrors nfl/scripts/scrape_madden.py's
# actual pattern): each team gets a per-request retry+backoff attempt
# (fetch_with_retry, which now actually raises on total failure instead
# of silently falling through to None -- that was a real bug, fixed as
# part of this rebuild). Any team still empty after that gets ONE retry
# pass after a 20s cooldown. Whatever's still empty after both passes
# falls back to that team's existing rows already in nba_ratings_2k.json,
# rather than writing empty/null and erasing known-good data over a
# transient block. Logged as fresh / stale-carryover / missing.
#
# PART 2 -- daily-trickle mode: 2kratings.com has never completed a full
# 30-team run in this project (best result: 8/30 before a block). Each
# run instead pulls only 3 random teams from a persisted rolling pool
# (nba/data/ratings_2k_scrape_state.json) and upserts them into
# nba_ratings_2k.json immediately, rather than waiting for a full cycle.
# When the pool empties, it's reshuffled and refilled for the next
# cycle -- a continuous rolling refresh, not a one-time build.
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_name, normalize_for_matching, NBA_NAME_ALIASES

BASE_URL = "https://www.2kratings.com/teams/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.2kratings.com/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Chromium";v="120", "Not_A Brand";v="8"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

STATS_PATH = os.path.join("nba", "data", "nba_stats.json")
OUT_PATH = os.path.join("nba", "data", "nba_ratings_2k.json")
STATE_PATH = os.path.join("nba", "data", "ratings_2k_scrape_state.json")
ERROR_LOG_PATH = os.path.join("nba", "data", "2kratings_errors.log")
TEAMS_PER_RUN = 3


def log_error(context, exc):
    """Appends the actual exception message before it's re-raised, so an
    unattended Task Scheduler run that dies leaves a trail -- Task
    Scheduler's own history only ever shows a bare non-zero exit code."""
    os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)
    with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {context}: {exc}\n")

# nba_api abbreviation -> 2kratings team-page slug. Built by cross
# referencing 2kratings' own team nav against nba_api's static team list
# (both use the same 30 full team names) -- not guessed/slugified, since
# a couple of teams (e.g. Philadelphia 76ers) don't slugify predictably.
TEAM_SLUGS = {
    'ATL': 'atlanta-hawks',
    'BKN': 'brooklyn-nets',
    'BOS': 'boston-celtics',
    'CHA': 'charlotte-hornets',
    'CHI': 'chicago-bulls',
    'CLE': 'cleveland-cavaliers',
    'DAL': 'dallas-mavericks',
    'DEN': 'denver-nuggets',
    'DET': 'detroit-pistons',
    'GSW': 'golden-state-warriors',
    'HOU': 'houston-rockets',
    'IND': 'indiana-pacers',
    'LAC': 'los-angeles-clippers',
    'LAL': 'los-angeles-lakers',
    'MEM': 'memphis-grizzlies',
    'MIA': 'miami-heat',
    'MIL': 'milwaukee-bucks',
    'MIN': 'minnesota-timberwolves',
    'NOP': 'new-orleans-pelicans',
    'NYK': 'new-york-knicks',
    'OKC': 'oklahoma-city-thunder',
    'ORL': 'orlando-magic',
    'PHI': 'philadelphia-76ers',
    'PHX': 'phoenix-suns',
    'POR': 'portland-trail-blazers',
    'SAC': 'sacramento-kings',
    'SAS': 'san-antonio-spurs',
    'TOR': 'toronto-raptors',
    'UTA': 'utah-jazz',
    'WAS': 'washington-wizards',
}


def fetch_with_retry(session, url, max_retries=4, base_delay=2.0):
    """Raises on total failure -- never returns None. The prior version
    of this function caught exceptions, logged 403s, and fell through the
    loop with no raise/return on exhaustion, which crashed the caller's
    BeautifulSoup(None, ...) call with a TypeError instead of failing
    cleanly. Fixed here as part of the Part 1 rebuild."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_exc = e
            resp = getattr(e, "response", None)
            if resp is not None and getattr(resp, "status_code", None) == 403:
                print(f"    blocked -- server: {resp.headers.get('server')}, "
                      f"retry-after: {resp.headers.get('retry-after')}, "
                      f"cf-ray: {resp.headers.get('cf-ray')}")
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 3)
            print(f"    retry {attempt}/{max_retries} after error ({e}); sleeping {delay:.1f}s")
            time.sleep(delay)
    raise last_exc


def parse_int(text):
    text = (text or "").strip()
    return int(text) if text.lstrip('-').isdigit() else None


def parse_team_roster(html, team_abbr, loaded_at):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="lists-table")
    if table is None:
        raise RuntimeError(f"Could not find lists-table on the {team_abbr} page")

    tbody = table.find("tbody")
    records = []
    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        name_tag = tds[1].find("a", class_="player-name")
        if not name_tag:
            continue
        raw_name = name_tag.get("data-full") or name_tag.get_text(strip=True)

        jersey_el = tds[1].select_one(".badge-icon .text-white")
        jersey = parse_int(jersey_el.get_text(strip=True)) if jersey_el else None

        pos_links = tds[1].select(".entry-subtext-font a[href^='/lists/']")
        positions = "/".join(a.get_text(strip=True) for a in pos_links) or None

        ovr_el = tds[2].select_one(".attribute-box")
        overall_rating = parse_int(ovr_el.get_text(strip=True)) if ovr_el else None

        record = {
            "name": normalize_name(raw_name),
            "2k_name": raw_name,
            "name_norm": normalize_for_matching(raw_name),
            "team": team_abbr,
            "jersey_number": jersey,
            "positions": positions,
            "overall_rating": overall_rating,
            "profile_url": name_tag.get("href"),
            # Added so a future session can tell fresh-this-run rows from
            # stale-carryover ones by inspecting the file alone, without
            # having to trust a console log that's already scrolled away --
            # matches nhl/scripts/scrape_ratings.py's per-row loaded_at.
            "loaded_at": loaded_at,
        }

        # Attribute columns (3PT, DNK, etc.) vary in count/label by page
        # but always follow OVR in column order -- capture them generically
        # by their header text rather than hardcoding two columns.
        header_cells = table.find("thead").find_all("th")[3:]
        for i, th in enumerate(header_cells):
            col_idx = 3 + i
            if col_idx >= len(tds):
                continue
            label = th.get_text(strip=True)
            box = tds[col_idx].select_one(".attribute-box")
            record[f"attr_{label.lower()}"] = parse_int(box.get_text(strip=True)) if box else None

        records.append(record)
    return records


def scrape_team(session, abbr):
    """Returns [] on any failure -- network error, exhausted retries, a
    real block, or a parse failure (missing table) -- so one team's
    failure never crashes the run for the others. Mirrors
    nfl/scripts/scrape_madden.py's scrape_team()."""
    url = BASE_URL + TEAM_SLUGS[abbr]
    try:
        html = fetch_with_retry(session, url)
        loaded_at = datetime.now(timezone.utc).isoformat()
        return parse_team_roster(html, abbr, loaded_at)
    except Exception as e:
        print(f"    ERROR scraping {abbr}: {e}")
        return []


def load_nba_players():
    """Real scraped player universe -- see scrape_contracts_spotrac.py for
    why nba_players_master.json (fictional stub) isn't the match target."""
    with open(STATS_PATH, encoding="utf-8") as f:
        stats = json.load(f)
    return list(stats.values())


def load_existing_ratings_by_team():
    """Base population for both the stale-carryover fallback and the
    merge step -- reads whatever's currently in nba_ratings_2k.json
    (built up incrementally by prior trickle runs), grouped by team.
    Empty dict if the file doesn't exist yet (first run ever)."""
    if not os.path.exists(OUT_PATH):
        return {}
    with open(OUT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    by_team = {}
    for record in data.get("ratings", []):
        by_team.setdefault(record["team"], []).append(record)
    return by_team


def build_match_index(players):
    by_name = {}
    by_name_team = {}
    for p in players:
        key = normalize_for_matching(p["name"])
        by_name.setdefault(key, []).append(p)
        by_name_team[(key, p["team"])] = p
    return by_name, by_name_team


def find_match(record, by_name, by_name_team):
    lookup_name = NBA_NAME_ALIASES.get(record["2k_name"], record["2k_name"])
    if lookup_name is None:
        return None
    name_norm = normalize_for_matching(normalize_name(lookup_name))

    exact = by_name_team.get((name_norm, record["team"]))
    if exact:
        return exact

    candidates = by_name.get(name_norm, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("remaining_pool"):
            return state
    pool = list(TEAM_SLUGS.keys())
    random.shuffle(pool)
    return {"remaining_pool": pool, "cycle": 1, "cycle_started": datetime.now(timezone.utc).isoformat()}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def main():
    session = cffi_requests.Session(impersonate="chrome120")
    session.headers.update(HEADERS)

    state = load_state()
    remaining = state["remaining_pool"]
    chosen = remaining[:TEAMS_PER_RUN]
    print(f"Cycle {state.get('cycle', 1)}: {len(remaining)} teams remaining before this run. "
          f"Picked: {chosen}")

    try:
        players = load_nba_players()
    except Exception as e:
        log_error("load_nba_players", e)
        raise
    by_name, by_name_team = build_match_index(players)
    print(f"Matching against {len(players)} players from nba_stats.json")
    existing_by_team = load_existing_ratings_by_team()

    by_team = {}
    for abbr in chosen:
        by_team[abbr] = scrape_team(session, abbr)
        print(f"{abbr}: {len(by_team[abbr])} rows")
        time.sleep(random.uniform(8, 15))

    failed = [abbr for abbr in chosen if not by_team[abbr]]
    if failed:
        print(f"\n{len(failed)} team(s) failed in-run, retrying after a cooldown: {failed}")
        time.sleep(20)
        for abbr in failed:
            by_team[abbr] = scrape_team(session, abbr)
            print(f"{abbr}: {len(by_team[abbr])} rows (retry)")
            time.sleep(random.uniform(8, 15))

    fresh, stale, missing = [], [], []
    for abbr in chosen:
        if by_team[abbr]:
            fresh.append(abbr)
            continue
        fallback = existing_by_team.get(abbr)
        if fallback:
            by_team[abbr] = fallback
            stale.append(abbr)
        else:
            missing.append(abbr)

    if stale:
        print(f"\nWARNING: kept previous data for (fresh scrape failed both attempts): {stale}")
    if missing:
        print(f"\nWARNING: no data at all for (fresh scrape failed, no prior data to fall back to): {missing}")

    # Only freshly-scraped records need (re)matching -- stale/carried-over
    # records already have player_id from their last successful match.
    matched_fresh = 0
    for abbr in fresh:
        for record in by_team[abbr]:
            p = find_match(record, by_name, by_name_team)
            record["player_id"] = p["player_id"] if p else None
            if p:
                matched_fresh += 1

    # Upsert: keep every existing record for teams NOT touched this run,
    # replace records only for the teams we did touch (fresh or
    # stale-fallback) -- a 3-team-per-run trickle must never wipe out the
    # other 27 teams' already-collected data.
    chosen_set = set(chosen)
    merged_records = []
    for abbr, records in existing_by_team.items():
        if abbr not in chosen_set:
            merged_records.extend(records)
    for abbr in chosen:
        merged_records.extend(by_team.get(abbr, []))

    # Real bug found and fixed here: matching above only ever ran for
    # teams freshly scraped THIS run -- a team that's a stale-carryover
    # or simply wasn't picked today keeps whatever player_id (including
    # None) it had from its last successful fresh scrape, forever, even
    # though nba_stats.json (the match target) is an independently
    # updated source that can start agreeing with a name/team long after
    # the ratings side stops changing. Confirmed concretely on Damian
    # Lillard: both sources already agree on (name="Damian Lillard",
    # team="POR"), yet his record sat with player_id: None because POR
    # hadn't been freshly re-scraped since before that agreement existed.
    # Fixed by re-attempting a match for every currently-unmatched record
    # on every run, not just ones from a freshly-scraped team -- this is
    # a pure in-memory lookup against the index already built above, no
    # extra network cost, so there's no reason to gate it behind a fresh
    # scrape at all.
    rematched_stale_unmatched = 0
    for record in merged_records:
        if record.get("player_id") is None:
            p = find_match(record, by_name, by_name_team)
            if p:
                record["player_id"] = p["player_id"]
                rematched_stale_unmatched += 1
    if rematched_stale_unmatched:
        print(f"\nRe-matched {rematched_stale_unmatched} previously-unmatched record(s) "
              f"against current nba_stats.json data (no fresh scrape needed).")

    unmatched = [
        {"2k_name": r["2k_name"], "team": r["team"], "positions": r.get("positions")}
        for r in merged_records if r.get("player_id") is None
    ]

    if merged_records:
        output = {"ratings": merged_records, "unmatched": unmatched}
        os.makedirs(os.path.join("nba", "data"), exist_ok=True)
        try:
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2)
        except Exception as e:
            log_error("write nba_ratings_2k.json", e)
            raise
        teams_covered = len({r["team"] for r in merged_records})
        matched_total = len(merged_records) - len(unmatched)
        print(f"\n{OUT_PATH}: {len(merged_records)} total records across {teams_covered}/{len(TEAM_SLUGS)} teams "
              f"({len(fresh)} fresh this run, {len(stale)} stale-carryover, {len(missing)} missing)")
        print(f"Matched: {matched_total} / {len(merged_records)} "
              f"({matched_total / len(merged_records) * 100:.1f}%)")
    else:
        print(f"\nNo records at all (fresh or stale) -- {OUT_PATH} not written.")

    # Advance the rolling pool -- refill+reshuffle once it empties so this
    # is a continuous rolling refresh, not a one-time 10-run build.
    state["remaining_pool"] = [a for a in remaining if a not in chosen_set]
    if not state["remaining_pool"]:
        new_pool = list(TEAM_SLUGS.keys())
        random.shuffle(new_pool)
        state["remaining_pool"] = new_pool
        state["cycle"] = state.get("cycle", 1) + 1
        state["cycle_started"] = datetime.now(timezone.utc).isoformat()
        print(f"\nCycle complete -- starting cycle {state['cycle']} with a freshly shuffled 30-team pool.")
    try:
        save_state(state)
    except Exception as e:
        log_error("save_state", e)
        raise
    print(f"{len(state['remaining_pool'])} teams remaining in current cycle.")


if __name__ == "__main__":
    main()

# ══════════════════════════════════════════════════════════════════════
# SCHEDULING (local machine only -- see the "RUN LOCALLY ONLY" note at
# the top of this file). This is a suggested command, NOT registered by
# this script or by Claude Code -- run it yourself if you want the daily
# trickle automated:
#
#   schtasks /create /tn "FieldView NBA 2K Ratings Scrape" ^
#     /tr "C:\Users\wallj\DS_Projects\fieldview\nba\scripts\schedule_2kratings_scrape.bat" ^
#     /sc daily /st 09:15
#
# schedule_2kratings_scrape.bat (see that file, same directory) adds its
# own random 0-30 minute delay before invoking this script, so the
# actual run time still drifts day to day even though the scheduled
# trigger itself fires at a fixed clock time -- schtasks' basic CLI has
# no native random-delay trigger option. Staggered 15 minutes from the
# NHL scraper's suggested 09:00 so the two don't fire in the same window.
# ══════════════════════════════════════════════════════════════════════

# Last verified against the live site: 2026-07-24. This is the most
# likely of the NBA scrapers to break on a redesign -- it scrapes 2K's
# fan-run ratings site (2kratings.com), not an official API, and there
# is no "all players" table: ratings live per-team on 30 separate pages
# (table id="lists-table"), reached only by browsing a team page, not
# from any single index. If this stops working, re-fetch a team page
# (e.g. https://www.2kratings.com/teams/los-angeles-lakers) and re-verify
# the table id and column structure before assuming the parser is still
# right -- don't just bump a selector and hope.
import json
import os
import random
import sys
import time

import requests
from bs4 import BeautifulSoup

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

session = requests.Session()
session.headers.update(HEADERS)

STATS_PATH = os.path.join("nba", "data", "nba_stats.json")
OUT_PATH = os.path.join("nba", "data", "nba_ratings_2k.json")

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


# def fetch_with_retry(url, max_retries=4, base_delay=2.0):
#     for attempt in range(1, max_retries + 1):
#         try:
#             resp = session.get(url, timeout=20)
#             resp.raise_for_status()
#             return resp.text
#         except requests.exceptions.HTTPError as e:
#             is_blocked = getattr(e.response, "status_code", None) == 403
#             if attempt == max_retries:
#                 raise
#             # a 403 means we're actively blocked, not a transient blip --
#             # retrying in a few seconds does nothing, so back off much
#             # harder than the normal exponential schedule.
#             delay = (30 * attempt if is_blocked else base_delay * (2 ** (attempt - 1))) + random.uniform(0, 3)
#             print(f"  retry {attempt}/{max_retries} after error ({e}); sleeping {delay:.1f}s")
#             time.sleep(delay)

from curl_cffi import requests

session = requests.Session(impersonate="chrome120")

def fetch_with_retry(url, max_retries=4, base_delay=2.0):
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            return resp.text
        # except Exception as e:
        #     is_blocked = getattr(getattr(e, "response", None), "status_code", None) == 403
        #     if attempt == max_retries:
        #         raise
        #     delay = (30 * attempt if is_blocked else base_delay * (2 ** (attempt - 1))) + random.uniform(0, 3)
        #     print(f"  retry {attempt}/{max_retries} after error ({e}); sleeping {delay:.1f}s")
        #     time.sleep(delay)
        except Exception as e:
            resp = getattr(e, "response", None)
            if resp is not None and getattr(resp, "status_code", None) == 403:
                print(f"  blocked -- server: {resp.headers.get('server')}, "
                    f"retry-after: {resp.headers.get('retry-after')}, "
                    f"cf-ray: {resp.headers.get('cf-ray')}")


def parse_int(text):
    text = (text or "").strip()
    return int(text) if text.lstrip('-').isdigit() else None


def parse_team_roster(html, team_abbr):
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


def load_nba_players():
    """Real scraped player universe -- see scrape_contracts_spotrac.py for
    why nba_players_master.json (fictional stub) isn't the match target."""
    with open(STATS_PATH, encoding="utf-8") as f:
        stats = json.load(f)
    return list(stats.values())


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


def main():
    players = load_nba_players()
    by_name, by_name_team = build_match_index(players)
    print(f"Matching against {len(players)} players from nba_stats.json")

    all_records = []
    for i, (abbr, slug) in enumerate(TEAM_SLUGS.items(), 1):
        url = BASE_URL + slug
        print(f"[{i}/{len(TEAM_SLUGS)}] {abbr} -- {url}")
        html = fetch_with_retry(url)
        team_records = parse_team_roster(html, abbr)
        all_records.extend(team_records)
        # Bumped to match NHL/MLB's ratings-scraper pacing fix (this one
        # was missed that round) -- 8-15s between team pages, since this
        # only needs to run roughly weekly and ratings barely move day to
        # day. Not expected to fix a real TLS-fingerprint block by itself
        # (curl_cffi is the actual fix for that, already in use here) --
        # this is insurance against a separate, request-volume-triggered
        # cooldown, same reasoning as nhl/scripts/scrape_ratings.py and
        # mlb/scripts/scrape_ratings.py.
        time.sleep(random.uniform(8, 15))

    print(f"\nParsed {len(all_records)} rated players across {len(TEAM_SLUGS)} teams")

    matched = 0
    unmatched = []
    for record in all_records:
        p = find_match(record, by_name, by_name_team)
        if p:
            record["player_id"] = p["player_id"]
            matched += 1
        else:
            record["player_id"] = None
            unmatched.append({
                "2k_name": record["2k_name"],
                "team": record["team"],
                "positions": record["positions"],
            })

    output = {"ratings": all_records, "unmatched": unmatched}

    os.makedirs(os.path.join("nba", "data"), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    pct = (matched / len(all_records) * 100) if all_records else 0
    print(f"\nMatched: {matched} / {len(all_records)} ({pct:.1f}%)")
    print(f"Unmatched: {len(unmatched)}")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
# if __name__ == "__main__":
#     print(fetch_with_retry(BASE_URL + "atlanta-hawks")[:200])
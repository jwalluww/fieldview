import requests
from bs4 import BeautifulSoup
import json
import os
import random
import re
import time
from datetime import datetime, timezone

from name_utils import NAME_ALIASES

# Separate from the nfl/data/{abbr}.json team files -- scrape_depth.py fully
# overwrites those every run (by design), so they can't hold "last known
# good" OTC data between runs. This cache is OTC's own persisted state,
# same concept as the trickle scrapers' rolling-pool state files.
CACHE_PATH = "nfl/data/otc_contracts_cache.json"

TEAMS = [
    {"name": "Arizona Cardinals",    "abbr": "ARZ", "slug": "arizona-cardinals"},
    {"name": "Atlanta Falcons",      "abbr": "ATL", "slug": "atlanta-falcons"},
    {"name": "Baltimore Ravens",     "abbr": "BAL", "slug": "baltimore-ravens"},
    {"name": "Buffalo Bills",        "abbr": "BUF", "slug": "buffalo-bills"},
    {"name": "Carolina Panthers",    "abbr": "CAR", "slug": "carolina-panthers"},
    {"name": "Chicago Bears",        "abbr": "CHI", "slug": "chicago-bears"},
    {"name": "Cincinnati Bengals",   "abbr": "CIN", "slug": "cincinnati-bengals"},
    {"name": "Cleveland Browns",     "abbr": "CLE", "slug": "cleveland-browns"},
    {"name": "Dallas Cowboys",       "abbr": "DAL", "slug": "dallas-cowboys"},
    {"name": "Denver Broncos",       "abbr": "DEN", "slug": "denver-broncos"},
    {"name": "Detroit Lions",        "abbr": "DET", "slug": "detroit-lions"},
    {"name": "Green Bay Packers",    "abbr": "GB",  "slug": "green-bay-packers"},
    {"name": "Houston Texans",       "abbr": "HOU", "slug": "houston-texans"},
    {"name": "Indianapolis Colts",   "abbr": "IND", "slug": "indianapolis-colts"},
    {"name": "Jacksonville Jaguars", "abbr": "JAX", "slug": "jacksonville-jaguars"},
    {"name": "Kansas City Chiefs",   "abbr": "KC",  "slug": "kansas-city-chiefs"},
    {"name": "Las Vegas Raiders",    "abbr": "LV",  "slug": "las-vegas-raiders"},
    {"name": "Los Angeles Chargers", "abbr": "LAC", "slug": "los-angeles-chargers"},
    {"name": "Los Angeles Rams",     "abbr": "LAR", "slug": "los-angeles-rams"},
    {"name": "Miami Dolphins",       "abbr": "MIA", "slug": "miami-dolphins"},
    {"name": "Minnesota Vikings",    "abbr": "MIN", "slug": "minnesota-vikings"},
    {"name": "New England Patriots", "abbr": "NE",  "slug": "new-england-patriots"},
    {"name": "New Orleans Saints",   "abbr": "NO",  "slug": "new-orleans-saints"},
    {"name": "New York Giants",      "abbr": "NYG", "slug": "new-york-giants"},
    {"name": "New York Jets",        "abbr": "NYJ", "slug": "new-york-jets"},
    {"name": "Philadelphia Eagles",  "abbr": "PHI", "slug": "philadelphia-eagles"},
    {"name": "Pittsburgh Steelers",  "abbr": "PIT", "slug": "pittsburgh-steelers"},
    {"name": "San Francisco 49ers",  "abbr": "SF",  "slug": "san-francisco-49ers"},
    {"name": "Seattle Seahawks",     "abbr": "SEA", "slug": "seattle-seahawks"},
    {"name": "Tampa Bay Buccaneers", "abbr": "TB",  "slug": "tampa-bay-buccaneers"},
    {"name": "Tennessee Titans",     "abbr": "TEN", "slug": "tennessee-titans"},
    {"name": "Washington Commanders","abbr": "WAS", "slug": "washington-commanders"},
]

def fetch_with_retry(url, headers, max_retries=5, base_delay=3.0):
    """Mirrors scrape_madden.py's fetch_with_retry -- same retry count and
    backoff formula. A single unretried attempt is what let CAR/IND/MIA/PIT
    go silently missing (transient failure on the one shot scrape_otc took),
    so apply the same per-request retry pattern already proven out there."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response
            raise requests.exceptions.HTTPError(f"Status {response.status_code}")
        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"  retry {attempt}/{max_retries} after error ({e}); sleeping {delay:.1f}s")
            time.sleep(delay)

def find_active_roster_table(soup):
    """The current-year Active Roster table -- confirmed live 2026-08-31
    that a team's page can carry FIVE tables with class 'contracted-players'
    (current year + 4 future-season cap-projection tables, e.g. Miami's
    "Active Roster (52/37/29/20/7 total)"). Each snapshot is wrapped in its
    own div.contracted-players-container, so picking containers[0] is a
    deliberate "the current one" choice, not the accidental first-match a
    bare soup.select_one('table.contracted-players') used to make -- the
    other 4 are out-year projections and must never be read here."""
    containers = soup.select("div.contracted-players-container")
    if not containers:
        return None
    return containers[0].select_one("table.contracted-players")


def find_non_active_table(soup, heading_text):
    """Injured Reserve / Physically Unable to Perform tables, located by
    their own <h5> heading text rather than by CSS class -- Dead Money
    shares the same 'non-active' class but is a different metric (prorated
    dead-cap exposure if the player were released, not a real cap_number)
    and must never be picked up this way."""
    for h5 in soup.find_all("h5"):
        if h5.get_text(strip=True) == heading_text:
            return h5.find_next_sibling("table")
    return None


def parse_active_roster_rows(table):
    contracts = {}
    for row in table.select("tbody tr"):
        name_tag = row.select_one("td.player-information div.name a")

        if not name_tag:
            continue

        name = name_tag.get_text(strip=True)

        # Cap number is the last non-spacer td before the dead money columns
        # It's the td with class="" (no mobile_drop, no spacer) — simplest: grab all tds, cap number is index 11
        tds = row.find_all("td", recursive=False)
        cap_number = None
        for td in tds:
            classes = td.get("class", [])
            if "spacer" not in classes and "mobile_drop" not in classes and "player-information" not in classes:
                text = td.get_text(strip=True)
                if text.startswith("$"):
                    cap_number = text
                    break

        if name and cap_number:
            contracts[name] = {"cap_number": cap_number}

    return contracts


def parse_non_active_rows(table):
    """Injured Reserve / PUP rows are a much simpler two-<td> structure
    (name link, cap number) than the Active Roster table's multi-column
    layout -- confirmed live 2026-08-31. Rows with no <a> tag (the table's
    own TOTAL summary row) are skipped."""
    contracts = {}
    tbody = table.find("tbody")
    if not tbody:
        return contracts
    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 2:
            continue
        name_tag = tds[0].find("a")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        cap_text = tds[1].get_text(strip=True)
        if name and cap_text.startswith("$"):
            contracts[name] = {"cap_number": cap_text}
    return contracts


def scrape_otc(team):
    url = f"https://overthecap.com/salary-cap/{team['slug']}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    print(f"Fetching {team['name']}...")
    try:
        response = fetch_with_retry(url, headers)
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {e}")
        return {}

    soup = BeautifulSoup(response.text, "html.parser")

    table = find_active_roster_table(soup)
    if not table:
        print(f"  ERROR: No contract table found")
        return {}

    contracts = parse_active_roster_rows(table)

    # IR/PUP players have real current-year cap numbers too, just filed off
    # the active table -- only fill in players the Active Roster table
    # didn't already give us, never overwrite it.
    for heading in ("Injured Reserve", "Physically Unable to Perform"):
        extra_table = find_non_active_table(soup, heading)
        if not extra_table:
            continue
        added = 0
        for name, data in parse_non_active_rows(extra_table).items():
            if name not in contracts:
                contracts[name] = data
                added += 1
        if added:
            print(f"  +{added} from {heading}")

    return contracts

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)

def normalize(name):
    name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name.lower())
    name = re.sub(r"[^a-z ]", "", name)
    return re.sub(r'\s+', ' ', name).strip()

def merge_into_team(abbr, contracts):
    filepath = f"nfl/data/{abbr.lower()}.json"
    if not os.path.exists(filepath):
        return

    with open(filepath) as f:
        team_data = json.load(f)

    # Build normalized lookup
    lookup = {normalize(k): v for k, v in contracts.items()}

    matched = 0
    for pos, players in team_data["depth_chart"].items():
        for player in players:
            lookup_name = NAME_ALIASES.get(player["name"], player["name"])
            if lookup_name is None:
                player.setdefault("cap_number", None)
                continue
            key = normalize(lookup_name)
            if key in lookup:
                player["cap_number"] = lookup[key]["cap_number"]
                matched += 1
            else:
                player.setdefault("cap_number", None)

    with open(filepath, "w") as f:
        json.dump(team_data, f, indent=2)

    print(f"  Merged {matched} contracts into {abbr}")

if __name__ == "__main__":
    cache = load_cache()

    by_team = {}
    for team in TEAMS:
        by_team[team["abbr"]] = scrape_otc(team)
        time.sleep(3)

    failed = [t for t in TEAMS if not by_team[t["abbr"]]]
    if failed:
        print(f"\n{len(failed)} team(s) failed in-run, retrying after a cooldown: {[t['name'] for t in failed]}")
        time.sleep(20)
        for team in failed:
            by_team[team["abbr"]] = scrape_otc(team)
            time.sleep(3)

    fresh, stale, missing = [], [], []
    for team in TEAMS:
        abbr = team["abbr"]
        if by_team[abbr]:
            fresh.append(team["name"])
            cache[abbr] = {
                "contracts": by_team[abbr],
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            continue
        cached = cache.get(abbr)
        if cached:
            by_team[abbr] = cached["contracts"]
            stale.append(f"{team['name']} (cached {cached['cached_at']})")
        else:
            missing.append(team["name"])

    if stale:
        print(f"\nWARNING: using cached contract data (fresh scrape failed both attempts) for: {stale}")
    if missing:
        print(f"\nWARNING: no contract data at all (fresh scrape failed, no cache to fall back to) for: {missing}")

    for team in TEAMS:
        contracts = by_team[team["abbr"]]
        if contracts:
            merge_into_team(team["abbr"], contracts)

    save_cache(cache)
    print(f"\nDone -- {len(fresh)} fresh, {len(stale)} stale-cache, {len(missing)} missing.")
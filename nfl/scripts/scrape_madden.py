import requests
from bs4 import BeautifulSoup
import json
import os
import random
import re
import time

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

# maddenratings.com's team roster table only has jersey/position/OVR/GEN/TOTAL --
# no age or years_pro (those only live on ~2,000 individual player pages, not
# worth the extra crawl). build_master.py's load_madden() already reads age/
# years_pro via .get() with no default, so leaving them off each player dict
# here is a no-op there, not a crash. years_pro gets recomputed independently
# from nflreadpy in build_master.py anyway.
ROSTER_URL = "https://www.maddenratings.com/teams/{slug}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch_with_retry(url, max_retries=5, base_delay=3.0):
    """A clean 5-request test showed no blocking, but a real 32-request run
    still 403'd on 4/32 teams -- looks like an intermittent per-request
    challenge/rate-limit rather than a hard block, so retry with backoff
    instead of trusting a single attempt (same reasoning as fetch_stats.py's
    fetch_with_retry for stats.nba.com)."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                return response
            raise requests.exceptions.HTTPError(f"Status {response.status_code}")
        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"  retry {attempt}/{max_retries} after error ({e}); sleeping {delay:.1f}s")
            time.sleep(delay)

def scrape_team(team):
    url = ROSTER_URL.format(slug=team["slug"])
    print(f"Fetching {team['name']}...")
    try:
        response = fetch_with_retry(url)
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    ovr_header = soup.find("th", title="Overall Rating")
    table = ovr_header.find_parent("table") if ovr_header else None
    if not table:
        print(f"  ERROR: No ratings table found")
        return []

    players = []
    for row in table.select("tbody tr"):
        if not row.select_one("td.counter"):
            continue  # in-content ad row, not a player row

        name_tag = row.select_one(".entry-font a")
        subtext = row.select_one(".entry-subtext-font")
        ovr_tag = row.select_one(".rating-updated .attribute-box")
        if not name_tag or not subtext or not ovr_tag:
            continue

        name = name_tag.get_text(strip=True)
        first_name, _, last_name = name.partition(" ")

        jersey_match = re.search(r"#(\d+)", subtext.get_text())
        jersey = int(jersey_match.group(1)) if jersey_match else None

        pos_tag = subtext.select_one("a")
        position = pos_tag.get_text(strip=True) if pos_tag else ""

        try:
            overall = int(float(ovr_tag.get_text(strip=True)))
        except ValueError:
            continue

        players.append({
            "firstName": first_name,
            "lastName": last_name,
            "overallRating": overall,
            "team": {"label": team["name"]},
            "jerseyNum": jersey,
            "position": {"shortLabel": position},
        })

    print(f"  Got {len(players)} players")
    return players

def load_existing_by_team():
    """3-4 of 32 teams reliably 403 per run, but a DIFFERENT 3-4 each time
    (confirmed across two full runs) -- not a fixed blocked page and not
    something a longer per-request backoff clears on its own. Reads like
    Cloudflare bot-management sampling a fraction of requests for a JS
    challenge that a plain `requests` client can never pass (no JS engine),
    rather than a rate limit. A same-run cooldown retry recovers some of
    them; whatever's still missing after that falls back to the previous
    run's data below rather than wiping that team out of the file."""
    path = "nfl/data/madden.json"
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        old_players = json.load(f)
    by_label = {}
    for p in old_players:
        label = p.get("team", {}).get("label", "")
        by_label.setdefault(label, []).append(p)
    return by_label

if __name__ == "__main__":
    existing_by_team = load_existing_by_team()

    all_players = []
    by_team = {}
    for team in TEAMS:
        by_team[team["abbr"]] = scrape_team(team)
        time.sleep(1.5)

    failed = [t for t in TEAMS if not by_team[t["abbr"]]]
    if failed:
        print(f"\n{len(failed)} team(s) failed in-run, retrying after a cooldown: {[t['name'] for t in failed]}")
        time.sleep(20)
        for team in failed:
            by_team[team["abbr"]] = scrape_team(team)
            time.sleep(1.5)

    stale, missing = [], []
    for team in TEAMS:
        if by_team[team["abbr"]]:
            continue
        fallback = existing_by_team.get(team["name"])
        if fallback:
            by_team[team["abbr"]] = fallback
            stale.append(team["name"])
        else:
            missing.append(team["name"])

    if stale:
        print(f"\nWARNING: kept previous run's ratings for (fresh scrape failed both attempts): {stale}")
    if missing:
        print(f"\nWARNING: no data at all (fresh scrape failed and no prior data to fall back to): {missing}")

    for team in TEAMS:
        all_players.extend(by_team[team["abbr"]])

    with open("nfl/data/madden.json", "w") as f:
        json.dump(all_players, f, indent=2)

    print(f"\nDone — {len(all_players)} players written to nfl/data/madden.json")

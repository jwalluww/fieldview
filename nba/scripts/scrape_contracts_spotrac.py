import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_name, normalize_for_matching, NBA_NAME_ALIASES

URL = "https://www.spotrac.com/nba/contracts/remaining"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
# robots.txt: `User-agent: *` sets `Crawl-delay: 5`. The whole league is on
# this one page (confirmed 523 rows, no pagination), so a single request
# normally never needs it -- kept only in case this script grows a retry.
CRAWL_DELAY = 5

STATS_PATH = os.path.join("nba", "data", "nba_stats.json")
OUT_PATH = os.path.join("nba", "data", "contracts_nba.json")


def fetch_page():
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_money(text):
    text = (text or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"[$,]", "", text)
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_pct(text):
    text = (text or "").strip().rstrip("%")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(text):
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def parse_spotrac_id(name_tag):
    """Pull Spotrac's own numeric player id out of the profile link, e.g.
    .../nba/player/_/id/23608/donovan-mitchell -> 23608. Not the same as
    nba_api's PLAYER_ID -- kept for reference/debugging only. Matching
    against nba_stats.json is still name-based, per plan."""
    href = name_tag.get("href", "") if name_tag else ""
    m = re.search(r"/id/(\d+)/", href)
    return int(m.group(1)) if m else None


def parse_table(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="table", class_="table")
    if table is None:
        table = soup.select_one("table.dataTable.rounded-top")
    if table is None:
        raise RuntimeError("Could not find the contracts table on the page")

    tbody = table.find("tbody")
    records = []
    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 8:
            continue

        name_tag = tds[0].find("a")
        raw_name = name_tag.get_text(strip=True) if name_tag else tds[0].get_text(strip=True)
        if not raw_name:
            continue

        canonical_name = normalize_name(raw_name)

        records.append({
            "name": canonical_name,
            "spotrac_name": raw_name,
            "spotrac_id": parse_spotrac_id(name_tag),
            "name_norm": normalize_for_matching(canonical_name),
            "pos": tds[1].get_text(strip=True),
            "team": tds[2].get_text(strip=True),
            "age": parse_int(tds[3].get_text(strip=True)),
            "length_remaining": parse_int(tds[4].get_text(strip=True)),
            "cash_total_remaining": parse_money(tds[5].get_text(strip=True)),
            "cash_guaranteed_remaining": parse_money(tds[6].get_text(strip=True)),
            "pct_guaranteed_remaining": parse_pct(tds[7].get_text(strip=True)),
        })
    return records


def load_nba_players():
    """The real scraped player universe. nba_players_master.json is still
    a fictional mock stub (13 invented names from the frontend-skeleton
    task) so it can't be a match target -- nba_stats.json (582 real
    players from fetch_stats.py) is used instead."""
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
    lookup_name = NBA_NAME_ALIASES.get(record["spotrac_name"], record["spotrac_name"])
    if lookup_name is None:
        return None  # forced no-match (wrong player, don't guess)
    name_norm = normalize_for_matching(normalize_name(lookup_name))

    # Team-qualified match first -- avoids colliding with a different real
    # person who happens to share a name on another team.
    exact = by_name_team.get((name_norm, record["team"]))
    if exact:
        return exact

    # Fall back to a name-only match, but only if it's unambiguous --
    # don't guess between two different real players sharing a name.
    candidates = by_name.get(name_norm, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def main():
    print(f"Fetching {URL} ...")
    html = fetch_page()

    records = parse_table(html)
    print(f"Parsed {len(records)} contract records")

    players = load_nba_players()
    by_name, by_name_team = build_match_index(players)
    print(f"Matching against {len(players)} players from nba_stats.json")

    matched = 0
    unmatched = []
    for record in records:
        p = find_match(record, by_name, by_name_team)
        if p:
            record["player_id"] = p["player_id"]
            matched += 1
        else:
            record["player_id"] = None
            unmatched.append({
                "spotrac_name": record["spotrac_name"],
                "team": record["team"],
                "pos": record["pos"],
            })

    output = {
        "contracts": records,
        "unmatched": unmatched,
    }

    os.makedirs(os.path.join("nba", "data"), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    pct = (matched / len(records) * 100) if records else 0
    print(f"\nMatched: {matched} / {len(records)} ({pct:.1f}%)")
    print(f"Unmatched: {len(unmatched)}")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()

"""shared/scripts/scrape_sofifa.py

Ratings scraper for sofifa.com, shared across soccer leagues -- takes a
league id and an output path as CLI args (`python scrape_sofifa.py
<league_id> <output_path>`) so the same script serves EPL (league 13)
now and MLS (league 39) later without duplicating the parser.

Real response shape confirmed live before writing this parser (2026-08-22),
not assumed from the earlier recon summary:
  - GET /players?type=all&lg[0]={league_id}&offset={n} returns a real
    HTML page (not JSON). Real bug caught on the first live run: this
    docstring originally said "30 players per page" going only off a
    truncated recon grep, but the real page size is 60 -- incrementing
    offset by a hardcoded 30 fetched 50%-overlapping pages and produced
    1055 rows for only 545 unique sofifa_ids on the first EPL pull.
    Fixed by incrementing offset by the actual row count parsed off each
    page instead of a hardcoded constant, so this is self-correcting
    even if the real page size changes again.
  - Termination signal is the presence/absence of a "Next" link inside
    <div class="pagination"> on the page just fetched -- there is no
    total-count element anywhere on the page to loop against instead.
  - Anti-bot posture is far weaker than the other ratings sites in this
    project (theshowratings.com/2kratings.com/nhlratings.net all needed
    curl_cffi impersonation or a proxy). sofifa only checks for a
    complete-looking User-Agent string -- confirmed live: a bare
    "Mozilla/5.0" gets 403'd 3/3 tries, a real full Chrome UA string gets
    200 3/3 tries, using plain `requests` with NO impersonation and NO
    proxy. Don't over-build defenses this site doesn't need.
  - The default player-listing table has NO height/weight columns
    (those only exist in the search-filter sidebar and on individual
    player detail pages, neither of which this script fetches) --
    columns are: Name, Age, Overall rating, Potential, Team & Contract,
    Value, Wage, Total stats. Confirmed by reading the live <thead>.
  - sofifa_id is the numeric `id` attribute on the player photo <img
    class="player-check">, e.g. id="239085" for Haaland -- also embedded
    in the photo CDN path (cdn.sofifa.net/players/239/085/...) and in
    the player URL (/player/239085/erling-haaland/260046/). Verified by
    hand against 2 real, well-known players: Haaland=239085,
    Salah=209331 (recon also checked Messi=158023 on the MLS listing).
  - The URL's THIRD path segment (260046 in the Haaland URL above) is
    NOT a player id -- it's a fixed game-version/squad-update id,
    identical across every single row on a given page (confirmed: every
    player URL on a live pull shared the same trailing number). A real
    lookalike-id trap, same class as nhlratings.net's WordPress post id
    -- caught before it got built into anything, not extracted here.
  - sofifa_id is its own ID space, confirmed NOT shared with FPL's
    numeric `id`/`code`/`opta_code` or ESPN's athlete ids. Matching to
    FPL happens downstream in build_epl_match.py via
    shared/scripts/soccer_name_utils.py, by name -- not attempted here,
    since this script is also meant to serve MLS, which has no
    FPL-equivalent roster to match against at scrape time.
  - Position is read from <span class="pos posN"> where N matches the
    site's own pn[] filter enum (confirmed live: 0=GK, 2=RWB, 3=RB,
    5=CB, 7=LB, 8=LWB, 10=CDM, 12=RM, 14=CM, 16=LM, 18=CAM, 20=RF,
    21=CF, 22=LF, 23=RW, 25=ST, 27=LW) -- genuinely granular, unlike
    FPL's coarse GKP/DEF/MID/FWD.

Run from the repo root, e.g.:
    python shared/scripts/scrape_sofifa.py 13 epl/data/sofifa_epl.json
    python shared/scripts/scrape_sofifa.py 39 mls/data/sofifa_mls.json
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://sofifa.com/players"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TEAM_ID_RE = re.compile(r"/team/(\d+)/")
POS_CLASS_RE = re.compile(r"\bpos(\d+)\b")


def fetch_page(session, league_id, offset):
    params = {"type": "all", "lg[0]": league_id, "offset": offset}
    resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_int(text):
    text = (text or "").strip().replace(",", "")
    m = re.search(r"-?\d+", text)
    return int(m.group()) if m else None


def parse_players(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    tbody = table.find("tbody") if table else None
    if tbody is None:
        return [], False

    records = []
    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 8:
            continue

        avatar_img = tds[0].find("img", class_="player-check")
        sofifa_id = parse_int(avatar_img.get("id")) if avatar_img else None
        if sofifa_id is None:
            continue

        name_link = tds[1].find("a")
        full_name = name_link.get("data-tippy-content") or name_link.get_text(strip=True)
        short_name = name_link.get_text(strip=True)
        profile_url = "https://sofifa.com" + name_link.get("href", "")

        flag_img = tds[1].find("img", class_="flag")
        nationality = flag_img.get("title") if flag_img else None

        pos_span = tds[1].find("span", class_=POS_CLASS_RE)
        position = pos_span.get_text(strip=True) if pos_span else None
        position_id = None
        if pos_span:
            m = POS_CLASS_RE.search(" ".join(pos_span.get("class", [])))
            position_id = int(m.group(1)) if m else None

        age = parse_int(tds[2].get_text())

        ovr_em = tds[3].find("em")
        overall_rating = parse_int(ovr_em.get_text()) if ovr_em else parse_int(tds[3].get_text())

        pot_em = tds[4].find("em")
        potential = parse_int(pot_em.get_text()) if pot_em else parse_int(tds[4].get_text())

        team_link = tds[5].find("a")
        team_name = team_link.get_text(strip=True) if team_link else None
        team_id = None
        if team_link and team_link.get("href"):
            m = TEAM_ID_RE.search(team_link["href"])
            team_id = int(m.group(1)) if m else None
        contract_sub = tds[5].find("div", class_="sub")
        contract_years = contract_sub.get_text(strip=True) if contract_sub else None

        value = tds[6].get_text(strip=True) or None
        wage = tds[7].get_text(strip=True) or None
        total_stats = parse_int(tds[8].get_text()) if len(tds) > 8 else None

        records.append({
            "sofifa_id": sofifa_id,
            "name": full_name,
            "short_name": short_name,
            "nationality": nationality,
            "position": position,
            "position_id": position_id,
            "age": age,
            "overall_rating": overall_rating,
            "potential": potential,
            "team_name": team_name,
            "sofifa_team_id": team_id,
            "contract_years": contract_years,
            "value": value,
            "wage": wage,
            "total_stats": total_stats,
            "profile_url": profile_url,
        })

    # The "Next" link's text is followed by a nested <svg> child, so its
    # tag has no single .string to match against -- check get_text() over
    # every <a> in the pagination block instead.
    pagination = soup.find("div", class_="pagination")
    has_next = False
    if pagination:
        has_next = any("Next" in a.get_text() for a in pagination.find_all("a"))
    return records, has_next


def scrape_league(league_id):
    session = requests.Session()
    all_players = []
    offset = 0
    while True:
        print(f"  fetching offset={offset} ...")
        html = fetch_page(session, league_id, offset)
        records, has_next = parse_players(html)
        if not records:
            print(f"  offset={offset}: no rows, stopping")
            break
        print(f"  offset={offset}: {len(records)} players")
        all_players.extend(records)
        if not has_next:
            break
        offset += len(records)
        time.sleep(1)
    return all_players


def main():
    if len(sys.argv) < 3:
        print("Usage: python scrape_sofifa.py <league_id> <output_path>")
        sys.exit(1)
    league_id = sys.argv[1]
    out_path = sys.argv[2]

    print(f"Scraping sofifa.com league {league_id} ...")
    players = scrape_league(league_id)

    output = {
        "league_id": league_id,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "players": players,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}: {len(players)} players")


if __name__ == "__main__":
    main()

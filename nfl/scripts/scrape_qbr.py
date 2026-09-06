"""Scrapes ESPN's Total QBR leaderboard via the embedded JSON blob on
https://www.espn.com/nfl/qbr -- window['__espnfitt__'] in the raw HTML,
not a rendered page, so a plain requests.get() works (confirmed live:
the page is JS-rendered for a human, but the data is already sitting in
the initial HTML source, same "check the source before reaching for a
headless browser" lesson as this project's other ESPN pages).

Deliberately has NO SEASON/SEASON-1 fallback machinery (unlike
scrape_stats.py/build_db.py's nflreadpy loaders): hitting the bare URL
with no season param already makes ESPN's own site default to the last
completed season automatically once the current season's leaderboard
isn't populated yet -- confirmed live, the page returns "NFL Total QBR -
2025 Season Leaders" unprompted in September 2026. Adding a manual
fallback here would be solving a problem this source doesn't have.
"""
import json
import os

import requests

from build_master import normalize_team

URL = "https://www.espn.com/nfl/qbr"
OUT_PATH = os.path.join('nfl', 'data', 'qbr.json')
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_qbr_html():
    response = requests.get(URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def extract_espnfitt(html):
    """window['__espnfitt__']={...}; is a single JS statement embedded in
    the page -- brace-balance from the assignment to find the exact end
    of the JSON object rather than a regex, since a naive non-greedy
    regex can stop early if the payload happens to contain a similar
    substring anywhere inside a string value."""
    marker = "window['__espnfitt__']="
    start = html.find(marker)
    if start == -1:
        raise ValueError("__espnfitt__ blob not found -- ESPN may have changed the page")

    json_start = start + len(marker)
    depth = 0
    in_str = False
    esc = False
    end = None
    for i in range(json_start, len(html)):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        raise ValueError("could not find end of __espnfitt__ JSON blob")

    return json.loads(html[json_start:end])


def parse_qbr_records(data):
    # Real navigation path confirmed by live investigation -- the exact
    # kind of undocumented structure that breaks silently if ESPN
    # reshapes the page: __espnfitt__ -> page -> content -> table ->
    # playerStats is the per-QB leaderboard array.
    player_stats = data['page']['content']['table']['playerStats']

    records = []
    for p in player_stats:
        athlete = p.get('athlete', {})
        # uid is ESPN's own "sport:league:athlete" id string, e.g.
        # "s:20~l:28~a:4431452" -- more stable than parsing the vanity
        # name out of the href URL.
        uid = athlete.get('uid', '')
        espn_id = uid.split('~a:')[-1] if '~a:' in uid else None
        name = athlete.get('name')
        team = normalize_team(athlete.get('team', ''))

        qbr_value = None
        for stat in p.get('stats', []):
            # schedAdjQBR is the headline "Total QBR" number shown on the
            # page. There's a separate unadjusted "qbr" stat in the same
            # array -- don't confuse the two.
            if stat.get('name') == 'schedAdjQBR':
                try:
                    qbr_value = float(stat.get('value'))
                except (TypeError, ValueError):
                    qbr_value = None
                break

        if not espn_id or not name or qbr_value is None:
            continue

        records.append({
            'espn_id': espn_id,
            'name': name,
            'team': team,
            'qbr': qbr_value,
        })

    return records


def load_existing():
    """None means no cache to fall back to at all; a list (possibly
    empty) means there is one, even if unusable."""
    if not os.path.exists(OUT_PATH):
        return None
    try:
        with open(OUT_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


if __name__ == '__main__':
    records = None
    try:
        html = fetch_qbr_html()
        data = extract_espnfitt(html)
        records = parse_qbr_records(data)
        if not records:
            raise ValueError("parsed 0 QBR records from the page -- treating as a failed scrape")
    except Exception as e:
        print(f"WARNING: QBR scrape failed ({e})")
        existing = load_existing()
        if existing is not None:
            print(f"  falling back to existing {OUT_PATH} ({len(existing)} QBs)")
            records = existing
        else:
            print(f"  no existing {OUT_PATH} to fall back to -- leaving it untouched")

    if records is not None:
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, 'w') as f:
            json.dump(records, f, indent=2)
        print(f"Wrote {OUT_PATH}: {len(records)} QBs")

"""nfl/scripts/scrape_madden_ea.py

Madden NFL ratings from EA's official ratings API (shared/scripts/
ea_ratings.py, slug madden-nfl), replacing scrape_madden.py's
maddenratings.com scraping (Cloudflare 202 challenges kept most teams on
stale rows). Writes the same two files scrape_madden.py wrote, in exactly
the shape the rest of the pipeline already reads:

  nfl/data/madden.json       list of {firstName, lastName, overallRating,
                            team: {label}, jerseyNum, position: {shortLabel}}
  nfl/data/madden_meta.json  per-team (OurLads code) date of the last fresh
                            fetch -- every team gets today's date -- plus
                            "_iteration": {"id", "label"} (EA's ratings
                            iteration, e.g. "Week 6"). Keys starting with
                            "_" are not teams; the frontends skip them.

Mapping notes (verified against the 2026-10 EA data):
  - position.shortLabel: EA's 22 labels are identical to the ones
    maddenratings.com used (QB HB FB WR TE LT LG C RG RT LEDG REDG DT SAM
    MIKE WILL CB FS SS K P LS), so they pass through unchanged. An unknown
    label is kept as-is and reported.
  - team.label: EA says "NY Giants"/"NY Jets"; everything else already
    matches the full names in build_master.MADDEN_TEAM_MAP. EA_TEAM_LABELS
    below normalizes those two, and a card whose team is not one of the 32
    (free agents) is skipped and counted.
  - Names: EA's firstName/lastName are passed through untouched; where EA
    spells a name differently than OurLads/maddenratings did, the aliases
    in build_master.MADDEN_NAME_ALIASES / name_utils.NAME_ALIASES handle it.

Guards (any failure keeps the previous files untouched and exits 0, so
staleness shows up as an old date): ea_ratings' own checks (truncated pull,
duplicate ids, retries), total >= 1,800 and >= 0.97x the previous
madden.json's player count, >= 95% of cards' avatarUrl containing
EDITION_MARKER (the edition check -- bump it when Madden 28 ships), every
card on one iteration, and all 32 teams present.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
import ea_ratings

SLUG = 'madden-nfl'
EDITION_MARKER = 'madden-nfl-27'
ABS_MIN_TOTAL = 1800
MADDEN_PATH = os.path.join('nfl', 'data', 'madden.json')
META_PATH = os.path.join('nfl', 'data', 'madden_meta.json')

# (full name used in madden.json / build_master.MADDEN_TEAM_MAP, OurLads code)
TEAMS = [
    ("Arizona Cardinals", "ARZ"), ("Atlanta Falcons", "ATL"), ("Baltimore Ravens", "BAL"),
    ("Buffalo Bills", "BUF"), ("Carolina Panthers", "CAR"), ("Chicago Bears", "CHI"),
    ("Cincinnati Bengals", "CIN"), ("Cleveland Browns", "CLE"), ("Dallas Cowboys", "DAL"),
    ("Denver Broncos", "DEN"), ("Detroit Lions", "DET"), ("Green Bay Packers", "GB"),
    ("Houston Texans", "HOU"), ("Indianapolis Colts", "IND"), ("Jacksonville Jaguars", "JAX"),
    ("Kansas City Chiefs", "KC"), ("Las Vegas Raiders", "LV"), ("Los Angeles Chargers", "LAC"),
    ("Los Angeles Rams", "LAR"), ("Miami Dolphins", "MIA"), ("Minnesota Vikings", "MIN"),
    ("New England Patriots", "NE"), ("New Orleans Saints", "NO"), ("New York Giants", "NYG"),
    ("New York Jets", "NYJ"), ("Philadelphia Eagles", "PHI"), ("Pittsburgh Steelers", "PIT"),
    ("San Francisco 49ers", "SF"), ("Seattle Seahawks", "SEA"), ("Tampa Bay Buccaneers", "TB"),
    ("Tennessee Titans", "TEN"), ("Washington Commanders", "WAS"),
]
ABBR_BY_NAME = dict(TEAMS)
EA_TEAM_LABELS = {'NY Giants': 'New York Giants', 'NY Jets': 'New York Jets'}

KNOWN_POSITIONS = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT', 'LEDG', 'REDG',
                   'DT', 'SAM', 'MIKE', 'WILL', 'CB', 'FS', 'SS', 'K', 'P', 'LS'}


def previous_total():
    try:
        with open(MADDEN_PATH, encoding='utf-8') as f:
            return len(json.load(f))
    except (OSError, ValueError):
        return 0


def validate(items):
    marked = sum(1 for c in items if EDITION_MARKER in (c.get('avatarUrl') or ''))
    if marked < 0.95 * len(items):
        return f'only {marked}/{len(items)} cards carry "{EDITION_MARKER}" in avatarUrl (previous edition?)'
    iterations = {(c.get('iteration') or {}).get('id') for c in items}
    if len(iterations) != 1 or None in iterations:
        return f'cards span iterations {sorted(map(str, iterations))}'
    teams = {EA_TEAM_LABELS.get((c.get('team') or {}).get('label'), (c.get('team') or {}).get('label')) for c in items}
    missing = set(ABBR_BY_NAME) - teams
    if missing:
        return f'missing teams: {sorted(missing)}'
    return None


def main():
    min_total = max(ABS_MIN_TOTAL, int(previous_total() * 0.97))
    items = ea_ratings.fetch_all(SLUG, None, min_total=min_total, validate=validate)
    if items is None:
        print(f'EA Madden fetch rejected -- keeping the previous {MADDEN_PATH} / {META_PATH}')
        return

    iteration = items[0]['iteration']
    by_team = {name: [] for name, _ in TEAMS}
    skipped, odd_positions = 0, set()
    for c in items:
        label = (c.get('team') or {}).get('label')
        label = EA_TEAM_LABELS.get(label, label)
        if label not in by_team:
            skipped += 1
            continue
        pos = (c.get('position') or {}).get('shortLabel') or ''
        if pos not in KNOWN_POSITIONS:
            odd_positions.add(pos)
        by_team[label].append({
            'firstName': c['firstName'],
            'lastName': c['lastName'],
            'overallRating': c['overallRating'],
            'team': {'label': label},
            'jerseyNum': c.get('jerseyNum'),
            'position': {'shortLabel': pos},
        })

    players = []
    for name, _ in TEAMS:
        # highest rated first within a team, like the maddenratings.com tables were
        players.extend(sorted(by_team[name], key=lambda p: -p['overallRating']))

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    meta = {abbr: today for _, abbr in TEAMS}
    label = iteration.get('label') or iteration.get('id')
    meta['_iteration'] = {'id': iteration.get('id'), 'label': label}

    with open(MADDEN_PATH, 'w', encoding='utf-8') as f:
        json.dump(players, f, indent=2, ensure_ascii=False)
    with open(META_PATH, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f'Wrote {len(players)} players across {len(TEAMS)} teams ({label}); '
          f'{skipped} card(s) with no NFL team skipped')
    if odd_positions:
        print(f'WARNING: position labels not seen before: {sorted(odd_positions)}')


if __name__ == '__main__':
    main()

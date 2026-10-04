"""mlb/scripts/build_mlb_match.py

Phase 2 (MLB): joins the raw statsapi_* tables Phase 1
(scrape_roster.py, scrape_stats.py) loaded into fieldview.duckdb, and
writes a resolved player_match table back to the same DB -- same role
as nfl/scripts/build_match.py and nba/scripts/build_nba_match.py.

Base population is today's 40-man roster (statsapi_roster, rosterType=40Man,
~1,360 rows), NOT the full statsapi_stats_hitting/pitching person_id union.
The 40-man (not the 26-man active roster) so injured-list stars like Judge
and Devers are present; each row carries roster_status (raw code: A, 40M,
D60, D15, RM, PL...) and injured (true for D7/D10/D15/D60). Season stats
include anyone who played in 2026 at all, including traded/released
players no longer on any 40-man -- left-joining stats onto roster keeps
player_match aligned with "who's on a team today". A player with zero 2026
games is a valid null-stats row, not an error.

Position taxonomy is clean here (no NFL EDGE/DI-style collapse):
  IF = 1B/2B/3B/SS, OF = LF/CF/RF, standalone = C/P/DH
Two known single-player edge cases, confirmed against the live data
(not assumed):
  - Shohei Ohtani (position_abbreviation 'TWP') has no fielding
    position -- player_type 'two_way', position_group left null rather
    than forced into a slot. DiamondView's own call how to render that,
    not this script's.
  - Cristian Pache (generic 'OF', no L/C/R split in the source) keeps
    position_group='OF' (so OF-zone substitution gating still works
    normally for him), tagged position_group_source='defaulted' so
    DiamondView knows to default his specific field zone to CF rather
    than treating him as indistinguishable from a real CF.

match_source records where each player's stat rows came from -- the
useful "provenance" signal here, since (unlike NFL/NBA) there's only
one vendor and no fuzzy name matching, just data availability:
'both', 'hitting', 'pitching', or 'roster_only' (no 2026 games yet).

Ratings come from MLB The Show's official API (scrape_show_api.py ->
mlb/data/show_api_live.json, Live-series cards only). The API carries no
MLB player ID, so they're left-joined onto the roster population by
normalized name + team (see match_rating()): exact, then a small alias table
(Leo -> Leonardo Rivas...), then a hyphenated-surname truncation
(Encarnacion-Strand -> Encarnacion), all scoped to the same team and only
accepted when exactly one card qualifies; last, if the API lists the player
as a free agent ("FA") and that name is unique among Live cards, a name-only
match that must also agree on bats/throws and pitcher-vs-hitter. Same-name players (Max Muncy) can only ever match on name + team.
Unmatched roster players get overall_rating = null (never dropped, never
defaulted) and are written to mlb/data/unmatched_mlb.txt. The API has no
potential rating, so the master has no `potential` field.
"""
import json
import os
import re
import unicodedata

import duckdb
import pandas as pd

DB_PATH = os.path.join('mlb', 'data', 'fieldview.duckdb')
RATINGS_PATH = os.path.join('mlb', 'data', 'show_api_live.json')
UNMATCHED_PATH = os.path.join('mlb', 'data', 'unmatched_mlb.txt')

# The Show's team_short_name -> statsapi abbreviation (the only three that differ;
# checked against statsapi_teams / the master's team_abbr set).
SHOW_TEAM_MAP = {'ARI': 'AZ', 'WAS': 'WSH', 'OAK': 'ATH'}

# statsapi (normalized) name -> The Show's (normalized) name, for first-name
# shortenings the generic rules can't see.
NAME_ALIASES = {
    'leo rivas': 'leonardo rivas',
    'cam cauley': 'cameron cauley',
    'robby ahlstrom': 'robert ahlstrom',
    'leo balcazar': 'leonardo balcazar',
}

POSITION_GROUP_MAP = {
    '1B': 'IF', '2B': 'IF', '3B': 'IF', 'SS': 'IF',
    'LF': 'OF', 'CF': 'OF', 'RF': 'OF',
    'C': 'standalone', 'P': 'standalone', 'DH': 'standalone',
}

# Administrative/join columns stripped out of the raw stats rows before
# they're embedded as batting_stats/pitching_stats -- everything else is
# real, unmodified statsapi.mlb.com stat data under its own field names.
STATS_ADMIN_COLS = {'row_id', 'person_id', 'full_name', 'team_id', 'team_abbr', 'resolved_team_abbr', 'group', 'loaded_at'}


def resolve_position_group(position_abbr):
    if position_abbr == 'OF':
        # Group stays 'OF' (clean 3-value enum: IF/OF/standalone) so
        # substitution gating on position_group works uniformly -- the
        # specific "which OF zone" default (CF) is a frontend rendering
        # decision, not a data-layer field. position_group_source is the
        # debug flag that this player's OF slot wasn't in the source data.
        return 'OF', 'defaulted'
    group = POSITION_GROUP_MAP.get(position_abbr)
    return (group, 'mapped') if group else (None, None)


def resolve_player_type(position_abbr):
    if position_abbr == 'P':
        return 'pitcher'
    if position_abbr == 'TWP':
        return 'two_way'
    return 'batter'


# Injured-list status codes on the 40-man (D7/D10/D15/D60). Other non-active codes
# (40M, RM, PL, ...) are not injuries.
IL_CODE = re.compile(r'^D[0-9]+$')


def norm_name(n):
    """Lowercase, strip accents/periods/apostrophes, hyphens -> spaces, drop Jr./Sr./II-IV."""
    n = unicodedata.normalize('NFKD', n)
    n = ''.join(ch for ch in n if not unicodedata.combining(ch)).lower()
    n = re.sub(r"[.'’]", '', n).replace('-', ' ').replace('–', ' ')
    n = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', n)
    return ' '.join(n.split())


def hyphen_head(n):
    """'Christian Encarnacion-Strand' -> 'Christian Encarnacion' (first half of a hyphenated surname), else None."""
    words = n.split()
    if len(words) < 2 or '-' not in words[-1]:
        return None
    return ' '.join(words[:-1] + [words[-1].split('-')[0]])


def build_ratings_index(cards):
    by_name = {}
    for c in cards:
        by_name.setdefault(norm_name(c['name']), []).append(c)
        head = hyphen_head(c['name'])
        if head:  # API-side hyphenated surname: also reachable by its first half
            by_name.setdefault(norm_name(head), []).append(c)
    return by_name


def fa_agrees(card, bats, throws, player_type):
    """Extra checks for the no-team-evidence FA tier: bats/throws must agree (a switch hitter
    or a missing value is compatible) and pitcher-vs-hitter must agree (two-way players skip it)."""
    def same(a, b):
        return not a or not b or a == 'S' or b == 'S' or a == b
    if not same(bats, card.get('bat_hand')):
        return False
    if throws and card.get('throw_hand') and throws != card['throw_hand']:
        return False
    if player_type and player_type != 'two_way' and card.get('is_hitter') is not None:
        if (player_type == 'pitcher') == bool(card['is_hitter']):
            return False
    return True


def match_rating(by_name, name, team_abbr, bats=None, throws=None, player_type=None):
    """-> (card or None, source). Sources: exact, alias, hyphen, fa_name_only; else
    unmatched_{no_name,other_team,ambiguous}."""
    def pick(key):
        cands = [c for c in by_name.get(key, []) if SHOW_TEAM_MAP.get(c['team_short_name'], c['team_short_name']) == team_abbr]
        uniq = {c['uuid']: c for c in cands}
        return list(uniq.values())
    key = norm_name(name)
    tiers = [('exact', key)]
    if key in NAME_ALIASES:
        tiers.append(('alias', NAME_ALIASES[key]))
    head = hyphen_head(name)
    if head:
        tiers.append(('hyphen', norm_name(head)))
    ambiguous = False
    for source, k in tiers:
        got = pick(k)
        if len(got) == 1:
            return got[0], source
        ambiguous = ambiguous or len(got) > 1
    if ambiguous:
        return None, 'unmatched_ambiguous'
    same_name = {c['uuid']: c for c in by_name.get(key, []) + by_name.get(NAME_ALIASES.get(key), [])}
    if len(same_name) == 1:
        only = next(iter(same_name.values()))
        if only['team_short_name'] == 'FA' and fa_agrees(only, bats, throws, player_type):
            return only, 'fa_name_only'
    return None, 'unmatched_other_team' if same_name else 'unmatched_no_name'


def clean(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, 'item') else v


def stats_dict(row):
    return {k: clean(v) for k, v in row.items() if k not in STATS_ADMIN_COLS}


def build_match():
    con = duckdb.connect(DB_PATH)

    roster = con.execute("""
        SELECT r.person_id, r.team_id, r.team_abbr, t.name AS team_name, r.full_name, r.status_code,
               r.jersey_number, r.position_abbreviation, r.position_name,
               p.height, p.weight, p.bat_side, p.pitch_hand, p.birth_date
        FROM statsapi_roster r
        LEFT JOIN statsapi_people p ON p.person_id = r.person_id
        LEFT JOIN statsapi_teams t ON t.id = r.team_id
        ORDER BY r.row_id
    """).fetchdf()

    hitting = con.execute("""
        SELECT h.*, t.abbreviation AS resolved_team_abbr
        FROM statsapi_stats_hitting h
        LEFT JOIN statsapi_teams t ON t.id = h.team_id
    """).fetchdf()

    pitching = con.execute("""
        SELECT pt.*, t.abbreviation AS resolved_team_abbr
        FROM statsapi_stats_pitching pt
        LEFT JOIN statsapi_teams t ON t.id = pt.team_id
    """).fetchdf()

    con.close()

    hitting_by_id = {int(r['person_id']): r for _, r in hitting.iterrows()}
    pitching_by_id = {int(r['person_id']): r for _, r in pitching.iterrows()}

    ratings_exists = os.path.exists(RATINGS_PATH)
    ratings_index = {}
    if ratings_exists:
        with open(RATINGS_PATH, encoding='utf-8') as f:
            ratings_index = build_ratings_index(json.load(f))

    matches = []
    rating_sources = {}
    unmatched_ratings = []
    for _, r in roster.iterrows():
        pid = int(r['person_id'])
        pos_abbr = clean(r['position_abbreviation'])
        position_group, position_group_source = resolve_position_group(pos_abbr)

        hit_row = hitting_by_id.get(pid)
        pitch_row = pitching_by_id.get(pid)
        rating_card, rating_source = match_rating(ratings_index, clean(r['full_name']), clean(r['team_abbr']),
                                                     clean(r['bat_side']), clean(r['pitch_hand']), resolve_player_type(pos_abbr)) if ratings_exists else (None, 'no_snapshot')
        rating_sources[rating_source] = rating_sources.get(rating_source, 0) + 1
        if rating_card is None:
            unmatched_ratings.append((clean(r['full_name']), clean(r['team_abbr']), rating_source))
        if hit_row is not None and pitch_row is not None:
            match_source = 'both'
        elif hit_row is not None:
            match_source = 'hitting'
        elif pitch_row is not None:
            match_source = 'pitching'
        else:
            match_source = 'roster_only'

        matches.append({
            'person_id': pid,
            'name': clean(r['full_name']),
            'team': clean(r['team_name']),
            'team_abbr': clean(r['team_abbr']),
            'position': pos_abbr,
            'position_name': clean(r['position_name']),
            'position_group': position_group,
            'position_group_source': position_group_source,
            'player_type': resolve_player_type(pos_abbr),
            'jersey_number': clean(r['jersey_number']),
            'height': clean(r['height']),
            'weight': clean(r['weight']),
            'bats': clean(r['bat_side']),
            'throws': clean(r['pitch_hand']),
            'batting_stats': stats_dict(hit_row) if hit_row is not None else None,
            'pitching_stats': stats_dict(pitch_row) if pitch_row is not None else None,
            'roster_status': clean(r['status_code']),
            'injured': bool(IL_CODE.match(clean(r['status_code']) or '')),
            'match_source': match_source,
            'overall_rating': clean(rating_card['ovr']) if rating_card is not None else None,
        })

    match_df = pd.DataFrame(matches)
    con = duckdb.connect(DB_PATH)
    con.register('_tmp_match', match_df)
    con.execute("CREATE OR REPLACE TABLE player_match AS SELECT * FROM _tmp_match")
    con.unregister('_tmp_match')
    con.close()

    total = len(match_df)
    matched_stats = (match_df['match_source'] != 'roster_only').sum()
    matched_ratings = match_df['overall_rating'].notna().sum()
    twp = match_df[match_df['player_type'] == 'two_way']['name'].tolist()
    defaulted = match_df[match_df['position_group_source'] == 'defaulted']['name'].tolist()
    print(f"player_match: {total} players")
    print(f"Matched to hitting and/or pitching stats: {matched_stats} / {total} ({matched_stats / total:.1%})")
    if ratings_exists:
        print(f"Matched to The Show ratings: {matched_ratings} / {total} ({matched_ratings / total:.1%}) -- by tier: "
              + ', '.join(f"{k}={v}" for k, v in sorted(rating_sources.items())))
        with open(UNMATCHED_PATH, 'w', encoding='utf-8') as f:
            for name, team, why in sorted(unmatched_ratings, key=lambda x: (x[1] or '', x[0] or '')):
                f.write(f"{name} (team={team}, {why})" + "\n")
        print(f"  unmatched list: {UNMATCHED_PATH} ({len(unmatched_ratings)} players)")
    else:
        print("show_api_live.json not present -- overall_rating is null for everyone")
    print(f"two_way players: {twp}")
    print(f"defaulted position_group (generic OF -> CF): {defaulted}")


if __name__ == '__main__':
    build_match()

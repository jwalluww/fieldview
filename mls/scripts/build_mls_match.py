"""mls/scripts/build_mls_match.py

Phase 2 (MLS): base population is mls_roster.json (ESPN), matched
separately against mls_asa_stats.json (ASA advanced metrics) and
mls_sofifa.json (sofifa ratings + granular position) by name -- neither
source shares an ID space with ESPN's athlete ids, same situation as
every other soccer/ratings join in this project. Writes a resolved
player_match table... this script has no DuckDB layer (unlike EPL) --
per spec, reads/writes JSON directly, no build_mls_db.py step.

BASE POPULATION FILTERING (real, not hypothetical): ESPN's raw 1057-row
bulk athlete list is NOT clean current-MLS-roster data as-is. Confirmed
live by inspecting the actual scrape output:
  - 5 players are tagged to "MLS All-Stars" or "Liga MX All-Stars" --
    real exhibition rosters, not real clubs.
  - 42 players are tagged to team_id "359", which is not one of ESPN's
    32 usa.1 teams at all -- their names (Kepa Arrizabalaga, David Raya,
    Declan Rice, Bukayo Saka-adjacent Arsenal squad members, etc.) are
    unmistakably Arsenal FC's EPL roster. ESPN's season/2026/athletes
    bulk endpoint for usa.1 appears to have picked up an unrelated
    club's full squad, almost certainly from a real preseason US
    exhibition tour rather than any MLS competition -- not a filtering
    edge case worth agonizing over, just excluded outright.
  Both groups (47 players total) are dropped before matching. Real
  count after filtering: 1010 players across the 30 real current clubs.

TEAM-NAME ALIASES verified by diffing the three sources' REAL live team
lists against each other programmatically (not guessed) -- all three
land on exactly 30 real current clubs once each source's own padding is
excluded (ESPN: -2 All-Star exhibition entries; ASA: -1 defunct
historical entry, Chivas USA, folded 2014; sofifa: no padding at all).
23/30 (ESPN<->ASA) and 23/30 (ESPN<->sofifa) team names already agree
after normalize_for_matching() alone (case/punctuation-insensitive) --
only the genuine remaining mismatches get an explicit alias entry below,
each confirmed against the real team lists, not pattern-guessed:
  ESPN<->ASA (4): LAFC/Portland Timbers/Red Bull New York/Vancouver
    Whitecaps differ from ASA's Los Angeles FC/Portland Timbers FC/
    New York Red Bulls/Vancouver Whitecaps FC.
  ESPN<->sofifa (7): the same 3 suffix/word-order cases as ASA (LAFC,
    Red Bull New York, Vancouver Whitecaps) PLUS 4 more FC/CF-suffix
    drops sofifa uses that ASA doesn't (Atlanta United FC/Chicago Fire
    FC/Houston Dynamo FC/Inter Miami CF -> Atlanta United/Chicago Fire/
    Houston Dynamo/Inter Miami).

Matching tiers mirror epl/scripts/build_epl_match.py exactly (exact
name+team, then unique name-only, then team-scoped token-overlap for
partial/abbreviated legal names) -- reimplemented here as one generic
helper reused for both joins, since EPL's version was written inline
and this script needs the same logic against two different target
datasets, not because the underlying matching approach differs.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
from soccer_name_utils import normalize_name, normalize_for_matching, SOCCER_NAME_ALIASES

ROSTER_PATH = os.path.join('mls', 'data', 'mls_roster.json')
ASA_PATH = os.path.join('mls', 'data', 'mls_asa_stats.json')
SOFIFA_PATH = os.path.join('mls', 'data', 'mls_sofifa.json')
OUT_PATH = os.path.join('mls', 'data', 'mls_player_match.json')

EXHIBITION_TEAMS = {'MLS All-Stars', 'Liga MX All-Stars'}
STRAY_TEAM_IDS = {'359'}  # confirmed = Arsenal FC's EPL squad, leaked into usa.1's bulk athlete list

# Verified against the three sources' real live team lists (see module
# docstring) -- only genuine post-normalization mismatches.
ESPN_TO_ASA_TEAM = {
    'LAFC': 'Los Angeles FC',
    'Portland Timbers': 'Portland Timbers FC',
    'Red Bull New York': 'New York Red Bulls',
    'Vancouver Whitecaps': 'Vancouver Whitecaps FC',
}

ESPN_TO_SOFIFA_TEAM = {
    'Atlanta United FC': 'Atlanta United',
    'Chicago Fire FC': 'Chicago Fire',
    'Houston Dynamo FC': 'Houston Dynamo',
    'Inter Miami CF': 'Inter Miami',
    'LAFC': 'Los Angeles FC',
    'Red Bull New York': 'New York Red Bulls',
    'Vancouver Whitecaps': 'Vancouver Whitecaps FC',
}


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_roster():
    data = load_json(ROSTER_PATH)
    players = list(data['players'].values())
    filtered = [
        p for p in players
        if p['team_name'] not in EXHIBITION_TEAMS and p['team_id'] not in STRAY_TEAM_IDS
    ]
    return filtered, len(players) - len(filtered)


def build_index(records, name_key, team_key):
    """Generic (by_name, by_name_team, by_team) index, reused for both
    the ASA join and the sofifa join -- same shape as EPL's
    build_sofifa_index, parameterized on which fields hold the name/team
    for whichever source is being indexed."""
    by_name, by_name_team, by_team = {}, {}, {}
    for r in records:
        name = r.get(name_key)
        team = r.get(team_key)
        if not name:
            continue
        name_norm = normalize_for_matching(name)
        team_norm = normalize_for_matching(team) if team else None
        by_name.setdefault(name_norm, []).append(r)
        if team_norm:
            by_name_team[(name_norm, team_norm)] = r
            by_team.setdefault(team_norm, []).append(r)
    return by_name, by_name_team, by_team


def find_token_overlap_match(espn_name, target_team_norm, by_team):
    """Reimplementation of epl/scripts/build_epl_match.py's tier-3
    matcher -- same real need (sources disagree on how much of a
    player's full legal name they carry), same fix (first-token gate +
    any-further-token overlap, scoped to the resolved team, unique hit
    required). See that file's docstring for the concrete real-player
    cases that motivated this."""
    candidates = by_team.get(target_team_norm, [])
    if not candidates:
        return None
    espn_words = espn_name.split()
    if not espn_words:
        return None
    espn_first_norm = normalize_for_matching(espn_words[0])
    espn_tokens = {normalize_for_matching(w) for w in espn_words}

    hits = []
    for r in candidates:
        target_name = r.get('_match_name', '')
        target_words = target_name.split()
        if not target_words:
            continue
        target_first_norm = normalize_for_matching(target_words[0])
        if target_first_norm != espn_first_norm:
            continue
        target_tokens = {normalize_for_matching(w) for w in target_words}
        if (target_tokens - {target_first_norm}) & (espn_tokens - {espn_first_norm}):
            hits.append(r)
    return hits[0] if len(hits) == 1 else None


def find_match(espn_name, espn_team, team_alias_map, by_name, by_name_team, by_team):
    lookup_name = SOCCER_NAME_ALIASES.get(espn_name, espn_name)
    if lookup_name is None:
        return None, None
    name_norm = normalize_for_matching(normalize_name(lookup_name))

    target_team = team_alias_map.get(espn_team, espn_team)
    team_norm = normalize_for_matching(target_team) if target_team else None

    if team_norm:
        exact = by_name_team.get((name_norm, team_norm))
        if exact is not None:
            return exact, 'name_team'

    candidates = by_name.get(name_norm, [])
    if len(candidates) == 1:
        return candidates[0], 'name_only'

    if team_norm:
        token_match = find_token_overlap_match(lookup_name, team_norm, by_team)
        if token_match is not None:
            return token_match, 'token_overlap'

    return None, None


def build_match():
    roster, excluded = load_roster()
    print(f"ESPN roster: {len(roster) + excluded} raw players, "
          f"{excluded} excluded (exhibition-team/stray-team_id), {len(roster)} base population")

    asa_data = load_json(ASA_PATH)
    asa_stats = asa_data['stats']
    asa_team_by_id = {t['team_id']: t['team_name'] for t in asa_data['teams']}
    multi_team = 0
    for row in asa_stats:
        row['_match_name'] = row.get('player_name')
        team_id = row.get('team_id')
        # Real shape, not a bug: a player transferred mid-season gets ONE
        # xgoals row for the whole season with team_id as a LIST of every
        # club they played for (15/797 rows, confirmed live) instead of
        # a split per-team row. Team is genuinely ambiguous here, so
        # _match_team is left unresolved (None) rather than guessing
        # first/last -- find_match() already falls back to name-only/
        # token-overlap cleanly whenever team_norm is None.
        if isinstance(team_id, list):
            multi_team += 1
            row['_match_team'] = None
        else:
            row['_match_team'] = asa_team_by_id.get(team_id)
    if multi_team:
        print(f"  {multi_team} ASA stat row(s) span multiple teams (mid-season transfer) -- team left unresolved for matching")
    asa_by_name, asa_by_name_team, asa_by_team = build_index(asa_stats, '_match_name', '_match_team')

    sofifa_data = load_json(SOFIFA_PATH)
    sofifa_players = sofifa_data['players']
    for row in sofifa_players:
        row['_match_name'] = row.get('name')
        row['_match_team'] = row.get('team_name')
    sofifa_by_name, sofifa_by_name_team, sofifa_by_team = build_index(sofifa_players, '_match_name', '_match_team')

    matches = []
    asa_counts = {'name_team': 0, 'name_only': 0, 'token_overlap': 0, 'unmatched': 0}
    sofifa_counts = {'name_team': 0, 'name_only': 0, 'token_overlap': 0, 'unmatched': 0}
    asa_unmatched, sofifa_unmatched = [], []

    for p in roster:
        espn_name = p['full_name']
        espn_team = p['team_name']

        asa_row, asa_source = find_match(espn_name, espn_team, ESPN_TO_ASA_TEAM,
                                          asa_by_name, asa_by_name_team, asa_by_team)
        if asa_row is None:
            asa_source = 'unmatched'
            asa_unmatched.append({'name': espn_name, 'team': espn_team})
        asa_counts[asa_source] += 1

        sofifa_row, sofifa_source = find_match(espn_name, espn_team, ESPN_TO_SOFIFA_TEAM,
                                                sofifa_by_name, sofifa_by_name_team, sofifa_by_team)
        if sofifa_row is None:
            sofifa_source = 'unmatched'
            sofifa_unmatched.append({'name': espn_name, 'team': espn_team})
        sofifa_counts[sofifa_source] += 1

        matches.append({
            'player_id': p['athlete_id'],
            'name': espn_name,
            'team': espn_team,
            'team_abbreviation': p['team_abbreviation'],
            'jersey': p['jersey'],
            'age': p['age'],
            'height': p['height'],
            'weight': p['weight'],
            'citizenship': p['citizenship'],
            'position_group': p['position_abbreviation'],
            'standard_pos': sofifa_row.get('position') if sofifa_row else None,
            'overall_rating': sofifa_row.get('overall_rating') if sofifa_row else None,
            'potential': sofifa_row.get('potential') if sofifa_row else None,
            'sofifa_id': sofifa_row.get('sofifa_id') if sofifa_row else None,
            'sofifa_match_source': sofifa_source,
            'asa_player_id': asa_row.get('player_id') if asa_row else None,
            'asa_match_source': asa_source,
            'stats': {k: v for k, v in asa_row.items()
                      if k not in ('_match_name', '_match_team', 'player_id', 'player_name',
                                   'primary_broad_position', 'primary_general_position',
                                   'nationality', 'birth_date')} if asa_row else None,
        })

    output = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'players': matches,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total = len(matches)
    asa_matched = total - asa_counts['unmatched']
    sofifa_matched = total - sofifa_counts['unmatched']
    print(f"\nplayer_match: {total} players (base population)")
    print(f"\nASA match rate: {asa_matched}/{total} ({asa_matched/total:.1%})")
    print(f"  via name+team: {asa_counts['name_team']}")
    print(f"  via name only (unique): {asa_counts['name_only']}")
    print(f"  via token overlap: {asa_counts['token_overlap']}")
    print(f"  unmatched: {asa_counts['unmatched']}")
    print(f"\nsofifa match rate: {sofifa_matched}/{total} ({sofifa_matched/total:.1%})")
    print(f"  via name+team: {sofifa_counts['name_team']}")
    print(f"  via name only (unique): {sofifa_counts['name_only']}")
    print(f"  via token overlap: {sofifa_counts['token_overlap']}")
    print(f"  unmatched: {sofifa_counts['unmatched']}")

    with open(os.path.join('mls', 'data', 'unmatched_asa.txt'), 'w', encoding='utf-8') as f:
        for u in asa_unmatched:
            f.write(f"{u['name']} (team={u['team']})\n")
    with open(os.path.join('mls', 'data', 'unmatched_sofifa.txt'), 'w', encoding='utf-8') as f:
        for u in sofifa_unmatched:
            f.write(f"{u['name']} (team={u['team']})\n")
    print(f"\nUnmatched lists written to mls/data/unmatched_asa.txt ({len(asa_unmatched)}) "
          f"and mls/data/unmatched_sofifa.txt ({len(sofifa_unmatched)})")


if __name__ == '__main__':
    build_match()

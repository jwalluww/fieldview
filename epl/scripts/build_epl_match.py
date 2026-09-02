"""epl/scripts/build_epl_match.py

Phase 2 (EPL): joins fpl_players (base population, roster+season stats)
against sofifa_ratings (granular position + overall_rating/potential),
the two raw tables Phase 1 (build_epl_db.py) loaded, and writes a
resolved player_match table back to the same DB. Same role as
mlb/scripts/build_mlb_match.py.

Base population is fpl_players (FPL's own bootstrap-static, live and
current), same reasoning as NHL's roster-vs-stats precedent: FPL is
"who's really on a team's roster today," sofifa's FC26 database is a
squad snapshot that can lag behind real transfers/promotions. Confirmed
this actually matters here, not hypothetically -- see EPL_TEAM_ALIASES
below.

No shared ID space between FPL and sofifa (confirmed in recon and again
here), so matching is name-based via shared/scripts/soccer_name_utils.py,
same situation as NHL's ratings site. Exact (name, team) match preferred;
falls back to a name-only match ONLY if it's unique across all of sofifa
(same two-tier lookup as NBA's build_nba_match.py's find_match).

EPL_TEAM_ALIASES (FPL team_name -> sofifa team_name) verified against
both sources' real live output, not guessed -- 17 of FPL's 20 teams are
just naming variants (e.g. "Man City" / "Manchester City"). The other 3
are a genuine roster mismatch, not a naming difference: FPL's live
2026-27 teams include Coventry City, Hull City, and Ipswich Town, while
sofifa's FC26 database still has Burnley, West Ham United, and
Wolverhampton Wanderers in the EPL-13 pull instead -- the two sources
disagree on which 3 clubs hold the league's last 3 promotion/relegation
slots (likely sofifa's squad-update snapshot lagging real 2026-27
confirmation). Players on either side's mismatched trio get no
team-based tiebreak; they can still resolve through the name-only
fallback if their name is unique in sofifa, otherwise they're
genuinely unmatched -- not a bug to "fix" by forcing a team match that
isn't real.

standard_pos holds sofifa's GRANULAR position (ST/CAM/CDM/LB/CB/...),
not a coarse group -- position_group holds FPL's coarse GKP/DEF/MID/FWD
instead. This is the reverse of NFL's ourlads_pos(specific)/
standard_pos(group) naming, deliberately: in soccer the ST/CB/CDM-style
label IS the conventional "standard" way a position gets discussed, and
GKP/DEF/MID/FWD is really just a coarse fantasy-squad-slot bucket, not
the other way around. Per explicit instruction for this build.
"""
import os
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
from soccer_name_utils import normalize_name, normalize_for_matching, SOCCER_NAME_ALIASES

DB_PATH = os.path.join('epl', 'data', 'fieldview.duckdb')

# Verified against real live output from both sources (see module
# docstring) -- 17 real naming variants. The 3 FPL teams with no entry
# here (Coventry City, Hull City, Ipswich Town) have no sofifa
# counterpart at all in the current EPL-13 pull, not a missed alias.
EPL_TEAM_ALIASES = {
    'Arsenal': 'Arsenal FC',
    'Aston Villa': 'Aston Villa',
    'Bournemouth': 'AFC Bournemouth',
    'Brentford': 'Brentford',
    'Brighton': 'Brighton & Hove Albion',
    'Chelsea': 'Chelsea FC',
    'Crystal Palace': 'Crystal Palace',
    'Everton': 'Everton FC',
    'Fulham': 'Fulham FC',
    'Leeds': 'Leeds United',
    'Liverpool': 'Liverpool FC',
    'Man City': 'Manchester City',
    'Man Utd': 'Manchester United',
    'Newcastle': 'Newcastle United',
    "Nott'm Forest": 'Nottingham Forest',
    'Spurs': 'Tottenham Hotspur',
    'Sunderland': 'Sunderland AFC',
}

# FPL admin/game-mechanics columns stripped before the remaining season
# stats get embedded onto the output record -- everything else is real
# FPL data under its own field name, same convention as MLB's
# STATS_ADMIN_COLS.
FPL_ADMIN_COLS = {
    'row_id', 'id', 'code', 'opta_code', 'photo', 'first_name',
    'second_name', 'web_name', 'known_name', 'team_code',
    'team_join_date', 'team_name', 'team_short_name', 'position',
    'position_short', 'loaded_at',
}


def clean(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, 'item') else v


def stats_dict(row):
    return {k: clean(v) for k, v in row.items() if k not in FPL_ADMIN_COLS}


def build_sofifa_index(sofifa):
    by_name = {}
    by_name_team = {}
    by_team = {}
    for _, r in sofifa.iterrows():
        name_norm = normalize_for_matching(clean(r['name']))
        team_norm = normalize_for_matching(clean(r['team_name']))
        by_name.setdefault(name_norm, []).append(r)
        by_name_team[(name_norm, team_norm)] = r
        by_team.setdefault(team_norm, []).append(r)
    return by_name, by_name_team, by_team


def find_token_overlap_match(fpl_name, sofifa_team_norm, by_team):
    """Real, non-hypothetical need: sofifa and FPL disagree on how much
    of a player's full legal name they store, and not in one consistent
    direction -- confirmed on 3 different real players in the same run:
      - sofifa abbreviates a middle name FPL spells out in full
        ("Gabriel dos S. Magalhães" vs "Gabriel dos Santos Magalhães")
      - sofifa drops a trailing surname FPL keeps
        ("Kepa Arrizabalaga" vs "Kepa Arrizabalaga Revuelta")
      - sofifa carries MORE legal name than FPL does
        ("Gabriel Teodoro Martinelli Silva" vs "Gabriel Martinelli Silva")
    No single prefix/substring rule catches all three. What all three
    share: same first name token, plus at least one further token in
    common (a shared middle or last name). Scoped to sofifa rows on the
    player's own team (already resolved via EPL_TEAM_ALIASES) to keep
    false positives unlikely, and only accepted if exactly one sofifa
    row on that team satisfies it -- an ambiguous (0 or 2+) result is
    left unmatched rather than guessed.
    """
    candidates = by_team.get(sofifa_team_norm, [])
    if not candidates:
        return None
    fpl_words = fpl_name.split()
    if not fpl_words:
        return None
    # Real bug caught on the first live run: normalize_for_matching()
    # strips ALL spaces by design (it's meant to produce one glued
    # matching key, not a tokenizable string) -- normalizing the whole
    # name first and then calling .split() on the result just returns a
    # single one-element "token" with no spaces left to split on, so the
    # overlap check below could never find a shared token. Fixed by
    # splitting the RAW name into words first, THEN normalizing each
    # word individually.
    fpl_first_norm = normalize_for_matching(fpl_words[0])
    fpl_tokens = {normalize_for_matching(w) for w in fpl_words}

    hits = []
    for r in candidates:
        sofifa_words = clean(r['name']).split()
        if not sofifa_words:
            continue
        sofifa_first_norm = normalize_for_matching(sofifa_words[0])
        if sofifa_first_norm != fpl_first_norm:
            continue
        sofifa_tokens = {normalize_for_matching(w) for w in sofifa_words}
        # exclude the (already-matched) first token from the overlap check
        if (sofifa_tokens - {sofifa_first_norm}) & (fpl_tokens - {fpl_first_norm}):
            hits.append(r)

    return hits[0] if len(hits) == 1 else None


def find_token_set_match(fpl_name, sofifa_team_norm, by_team):
    """Catches a genuine full name-order swap (e.g. FPL's "Mitoma
    Kaoru" vs sofifa's "Kaoru Mitoma") that find_token_overlap_match()
    can't reach -- that function requires the first word of both names
    to match before checking further overlap, which is correct for its
    own documented cases (same first name, different tail) but breaks
    completely when the two words are simply reversed, since neither
    first word matches the other's first word at all. This checks the
    full token SET for exact equality regardless of order, scoped to
    the player's own team, only accepted if exactly one candidate
    qualifies -- same ambiguity bar as find_token_overlap_match.
    """
    candidates = by_team.get(sofifa_team_norm, [])
    if not candidates:
        return None
    fpl_tokens = {normalize_for_matching(w) for w in fpl_name.split()}
    if not fpl_tokens:
        return None

    hits = []
    for r in candidates:
        sofifa_words = clean(r['name']).split()
        if not sofifa_words:
            continue
        sofifa_tokens = {normalize_for_matching(w) for w in sofifa_words}
        if sofifa_tokens == fpl_tokens:
            hits.append(r)

    return hits[0] if len(hits) == 1 else None


def find_sofifa_match(fpl_name, fpl_team, by_name, by_name_team, by_team):
    lookup_name = SOCCER_NAME_ALIASES.get(fpl_name, fpl_name)
    if lookup_name is None:
        return None, None
    name_norm = normalize_for_matching(normalize_name(lookup_name))

    sofifa_team = EPL_TEAM_ALIASES.get(fpl_team, fpl_team)
    team_norm = normalize_for_matching(sofifa_team)

    exact = by_name_team.get((name_norm, team_norm))
    if exact is not None:
        return exact, 'name_team'

    candidates = by_name.get(name_norm, [])
    if len(candidates) == 1:
        return candidates[0], 'name_only'

    token_match = find_token_overlap_match(lookup_name, team_norm, by_team)
    if token_match is not None:
        return token_match, 'token_overlap'

    swap_match = find_token_set_match(lookup_name, team_norm, by_team)
    if swap_match is not None:
        return swap_match, 'token_set_swap'

    return None, None


def build_match():
    con = duckdb.connect(DB_PATH)
    fpl = con.execute("SELECT * FROM fpl_players ORDER BY row_id").fetchdf()
    sofifa = con.execute("SELECT * FROM sofifa_ratings").fetchdf()
    con.close()

    by_name, by_name_team, by_team = build_sofifa_index(sofifa)

    matches = []
    match_source_counts = {'name_team': 0, 'name_only': 0, 'token_overlap': 0, 'token_set_swap': 0, 'unmatched': 0}
    unmatched_rows = []

    for _, r in fpl.iterrows():
        fpl_name = f"{clean(r['first_name'])} {clean(r['second_name'])}".strip()
        fpl_team = clean(r['team_name'])

        sofifa_row, match_source = find_sofifa_match(fpl_name, fpl_team, by_name, by_name_team, by_team)
        if sofifa_row is None:
            match_source = 'unmatched'
            unmatched_rows.append({'name': fpl_name, 'team': fpl_team, 'web_name': clean(r['web_name'])})
        match_source_counts[match_source] += 1

        matches.append({
            'player_id': int(r['id']),
            'name': fpl_name,
            'web_name': clean(r['web_name']),
            'team': fpl_team,
            'team_short': clean(r['team_short_name']),
            'position_group': clean(r['position_short']),
            'standard_pos': clean(sofifa_row['position']) if sofifa_row is not None else None,
            'overall_rating': clean(sofifa_row['overall_rating']) if sofifa_row is not None else None,
            'potential': clean(sofifa_row['potential']) if sofifa_row is not None else None,
            'sofifa_id': clean(sofifa_row['sofifa_id']) if sofifa_row is not None else None,
            'match_source': match_source,
            'stats': stats_dict(r),
        })

    match_df = pd.DataFrame(matches)
    con = duckdb.connect(DB_PATH)
    con.register('_tmp_match', match_df)
    con.execute("CREATE OR REPLACE TABLE player_match AS SELECT * FROM _tmp_match")
    con.unregister('_tmp_match')
    con.close()

    total = len(match_df)
    matched = total - match_source_counts['unmatched']
    print(f"player_match: {total} players")
    print(f"Matched to sofifa_ratings: {matched} / {total} ({matched / total:.1%})")
    print(f"  via name+team: {match_source_counts['name_team']}")
    print(f"  via name only (unique): {match_source_counts['name_only']}")
    print(f"  via team-scoped token overlap (partial-legal-name match): {match_source_counts['token_overlap']}")
    print(f"  via team-scoped token set match (full name-order swap): {match_source_counts['token_set_swap']}")
    print(f"  unmatched: {match_source_counts['unmatched']}")
    with open(os.path.join('epl', 'data', 'unmatched_epl.txt'), 'w', encoding='utf-8') as f:
        for u in unmatched_rows:
            f.write(f"{u['name']} (web_name={u['web_name']}, team={u['team']})\n")
    print(f"\nFull unmatched list written to epl/data/unmatched_epl.txt ({len(unmatched_rows)} players)")


if __name__ == '__main__':
    build_match()

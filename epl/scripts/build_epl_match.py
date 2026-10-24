"""epl/scripts/build_epl_match.py

Phase 2 (EPL): joins fpl_players (base population, roster+season stats)
against ea_ratings (EA's official FC ratings: granular position +
overall_rating), the two raw tables Phase 1 (build_epl_db.py) loaded, and writes a
resolved player_match table back to the same DB. Same role as
mlb/scripts/build_mlb_match.py.

Base population is fpl_players (FPL's own bootstrap-static, live and
current), same reasoning as NHL's roster-vs-stats precedent: FPL is
"who's really on a team's roster today."

RATINGS SOURCE (2026-10): EA's official ratings API replaced sofifa
(which only re-publishes EA's data). EA's card id is the sofifa player
id and lands in the existing sofifa_id field. The table keeps the same
column shape the old ea_ratings table had (name, team_name,
position, overall_rating, sofifa_id) minus potential, which EA does not
publish; `name` is EA's firstName + lastName.

No shared ID space between FPL and EA (FPL's code/opta_code are not
sofifa ids), so matching is name-based via
shared/scripts/soccer_name_utils.py. Exact (name, team) match preferred;
falls back to a name-only match ONLY if it's unique across all of EA's
EPL cards (same two-tier lookup as NBA's build_nba_match.py's find_match),
then the team-scoped token tiers.

EPL_TEAM_ALIASES (FPL team_name -> EA team label) verified against the
real live output of both sources, not guessed. Unlike sofifa's old
pull, EA's EPL cards cover all 20 of FPL's current clubs, including
Coventry City, Hull City and Ipswich -- 5 of the 20 are naming variants
(e.g. "Man City" / "Manchester City"), the rest agree as-is.

standard_pos holds EA's GRANULAR position (ST/CAM/CDM/LB/CB/...),
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
# docstring) -- only the 5 genuine naming variants; the other 15 FPL
# team names are identical to EA's labels.
EPL_TEAM_ALIASES = {
    'Bournemouth': 'AFC Bournemouth',
    'Ipswich Town': 'Ipswich',
    'Leeds': 'Leeds United',
    'Man City': 'Manchester City',
    'Newcastle': 'Newcastle Utd',
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


def build_ea_index(ea):
    by_name = {}
    by_name_team = {}
    by_team = {}
    for _, r in ea.iterrows():
        team_norm = normalize_for_matching(clean(r['team_name']))
        # EA stores a card under its legal first+last name AND, for players
        # known by a shorter name, a commonName ("Heung Min Son"). FPL often
        # carries one or the other, so every card is indexed under both
        # (same sofifa_id on each copy -- the tiers dedupe by it).
        variants = [r]
        common = clean(r['common_name'])
        if common and normalize_for_matching(common) != normalize_for_matching(clean(r['name'])):
            alt = r.copy()
            alt['name'] = common
            variants.append(alt)
        for v in variants:
            name_norm = normalize_for_matching(clean(v['name']))
            by_name.setdefault(name_norm, []).append(v)
            by_name_team[(name_norm, team_norm)] = v
            by_team.setdefault(team_norm, []).append(v)
    return by_name, by_name_team, by_team


def _unique_card(hits):
    """One hit, counting a card's legal-name and commonName copies as one."""
    return hits[0] if len({clean(h['sofifa_id']) for h in hits}) == 1 else None


def find_token_overlap_match(fpl_name, ea_team_norm, by_team):
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
    candidates = by_team.get(ea_team_norm, [])
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
        ea_words = clean(r['name']).split()
        if not ea_words:
            continue
        ea_first_norm = normalize_for_matching(ea_words[0])
        if ea_first_norm != fpl_first_norm:
            continue
        ea_tokens = {normalize_for_matching(w) for w in ea_words}
        # exclude the (already-matched) first token from the overlap check
        if (ea_tokens - {ea_first_norm}) & (fpl_tokens - {fpl_first_norm}):
            hits.append(r)

    return _unique_card(hits)


def find_token_set_match(fpl_name, ea_team_norm, by_team):
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
    candidates = by_team.get(ea_team_norm, [])
    if not candidates:
        return None
    fpl_tokens = {normalize_for_matching(w) for w in fpl_name.split()}
    if not fpl_tokens:
        return None

    hits = []
    for r in candidates:
        ea_words = clean(r['name']).split()
        if not ea_words:
            continue
        ea_tokens = {normalize_for_matching(w) for w in ea_words}
        if ea_tokens == fpl_tokens:
            hits.append(r)

    return _unique_card(hits)


# EA's granular position -> the FPL group(s) it may legitimately sit in.
# Wingers/wide mids and wing-backs are genuinely split across FPL's buckets
# (e.g. Saka is an EA RW but an FPL MID), so they accept two groups;
# keepers, centre-backs/full-backs, holding/central mids and strikers don't.
EA_POS_TO_FPL_GROUPS = {
    'GK': {'GKP'},
    'CB': {'DEF'}, 'LB': {'DEF'}, 'RB': {'DEF'},
    'LWB': {'DEF', 'MID'}, 'RWB': {'DEF', 'MID'},
    'CDM': {'MID'}, 'CM': {'MID'},
    'CAM': {'MID', 'FWD'}, 'LM': {'MID', 'FWD'}, 'RM': {'MID', 'FWD'},
    'LW': {'MID', 'FWD'}, 'RW': {'MID', 'FWD'},
    'ST': {'FWD'}, 'CF': {'FWD'},
}


def find_league_token_match(fpl_name, fpl_group, by_team):
    """Final tier: no team-scoped match found, so look across ALL of EA's
    EPL cards. Real need: EA's club label lags real transfers (Emiliano
    Martinez is Aston Villa on EA, Chelsea on FPL), so every team-scoped
    tier above can't see him; and FPL's legal name is longer than EA's
    ("Emiliano Martinez Romero" vs "Emiliano Martinez"). A card qualifies
    on the same first-token + shared-further-token test as
    find_token_overlap_match (shared token must be 4+ letters so "de"/"da"
    can't link strangers), on exact token-set equality, or on sharing two
    or more 4+-letter tokens whatever the first token ("Francisco Evanilson
    de Lima Barbosa" vs EA's "F. Evanilson de Lima Barbosa", "Junior
    Kroupi" vs "Eli Junior Kroupi"). Accepted only if
    exactly one card qualifies league-wide AND its EA position is
    compatible with the player's FPL position group."""
    words = fpl_name.split()
    if not words:
        return None
    first = normalize_for_matching(words[0])
    tokens = {normalize_for_matching(w) for w in words}
    strong, weak = [], []
    for rows in by_team.values():
        for r in rows:
            r_words = clean(r['name']).split()
            if not r_words:
                continue
            r_first = normalize_for_matching(r_words[0])
            r_tokens = {normalize_for_matching(w) for w in r_words}
            shared = {x for x in (r_tokens - {r_first}) & (tokens - {first}) if len(x) >= 4}
            if (r_first == first and shared) or r_tokens == tokens:
                strong.append(r)
            elif len({x for x in r_tokens & tokens if len(x) >= 4}) >= 2:
                weak.append(r)
    # the looser two-shared-tokens rule only runs when no strict hit exists,
    # so it can't add a second candidate to a player the strict rules resolve
    card = _unique_card(strong) if strong else _unique_card(weak)
    if card is None:
        return None
    if fpl_group not in EA_POS_TO_FPL_GROUPS.get(clean(card['position']), set()):
        return None
    return card


def find_ea_match(fpl_name, fpl_team, fpl_group, by_name, by_name_team, by_team):
    lookup_name = SOCCER_NAME_ALIASES.get(fpl_name, fpl_name)
    if lookup_name is None:
        return None, None
    name_norm = normalize_for_matching(normalize_name(lookup_name))

    ea_team = EPL_TEAM_ALIASES.get(fpl_team, fpl_team)
    team_norm = normalize_for_matching(ea_team)

    exact = by_name_team.get((name_norm, team_norm))
    if exact is not None:
        return exact, 'name_team'

    candidates = by_name.get(name_norm, [])
    if len({clean(c['sofifa_id']) for c in candidates}) == 1:
        return candidates[0], 'name_only'

    token_match = find_token_overlap_match(lookup_name, team_norm, by_team)
    if token_match is not None:
        return token_match, 'token_overlap'

    swap_match = find_token_set_match(lookup_name, team_norm, by_team)
    if swap_match is not None:
        return swap_match, 'token_set_swap'

    league_match = find_league_token_match(lookup_name, fpl_group, by_team)
    if league_match is not None:
        return league_match, 'league_token'

    return None, None


def build_match():
    con = duckdb.connect(DB_PATH)
    fpl = con.execute("SELECT * FROM fpl_players ORDER BY row_id").fetchdf()
    ea = con.execute("SELECT * FROM ea_ratings").fetchdf()
    con.close()

    by_name, by_name_team, by_team = build_ea_index(ea)

    matches = []
    match_source_counts = {'name_team': 0, 'name_only': 0, 'token_overlap': 0, 'token_set_swap': 0, 'league_token': 0, 'unmatched': 0}
    unmatched_rows = []

    for _, r in fpl.iterrows():
        fpl_name = f"{clean(r['first_name'])} {clean(r['second_name'])}".strip()
        fpl_team = clean(r['team_name'])

        ea_row, match_source = find_ea_match(fpl_name, fpl_team, clean(r['position_short']), by_name, by_name_team, by_team)
        if ea_row is None:
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
            'standard_pos': clean(ea_row['position']) if ea_row is not None else None,
            'overall_rating': clean(ea_row['overall_rating']) if ea_row is not None else None,
            'sofifa_id': clean(ea_row['sofifa_id']) if ea_row is not None else None,
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
    print(f"Matched to EA ratings: {matched} / {total} ({matched / total:.1%})")
    print(f"  via name+team: {match_source_counts['name_team']}")
    print(f"  via name only (unique): {match_source_counts['name_only']}")
    print(f"  via team-scoped token overlap (partial-legal-name match): {match_source_counts['token_overlap']}")
    print(f"  via team-scoped token set match (full name-order swap): {match_source_counts['token_set_swap']}")
    print(f"  via league-wide token match + position group (team label lag / long legal names): {match_source_counts['league_token']}")
    print(f"  unmatched: {match_source_counts['unmatched']}")
    with open(os.path.join('epl', 'data', 'unmatched_epl.txt'), 'w', encoding='utf-8') as f:
        for u in unmatched_rows:
            f.write(f"{u['name']} (web_name={u['web_name']}, team={u['team']})\n")
    print(f"\nFull unmatched list written to epl/data/unmatched_epl.txt ({len(unmatched_rows)} players)")


if __name__ == '__main__':
    build_match()

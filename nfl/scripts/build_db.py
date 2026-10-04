"""Phase 1 raw ingestion: load each source's existing scraper output into
its own DuckDB table, unmodified -- no joins, no matching. Matching logic
stays in build_master.py until Phase 2 ports it into the DB layer.

Run from the repo root: python nfl/scripts/build_db.py
"""
import glob
import json
import os

import duckdb
import pandas as pd

from season_utils import get_current_season

SEASON = get_current_season()
DB_PATH = os.path.join('nfl', 'data', 'fieldview.duckdb')

# Files under nfl/data/ that are not per-team OurLads depth charts.
NON_TEAM_FILES = {'madden.json', 'madden_meta.json', 'advanced_meta.json', 'spotrac_contracts.json', 'players_master.json'}
ADV_META_PATH = os.path.join('nfl', 'data', 'advanced_meta.json')


def write_table(con, name, df):
    df = df.copy()
    df['loaded_at'] = pd.Timestamp.now()
    con.register('_tmp_df', df)
    con.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp_df')
    con.unregister('_tmp_df')
    print(f"  {name}: {len(df)} rows")


def load_ourlads_players():
    """Flatten the 32 per-team depth-chart files into one row-per-player
    table. `stats` is a nested dict that varies by position, so it's kept
    as a JSON string column rather than exploded into columns here --
    faithful raw storage, not the position-aware normalization
    build_master.py's normalize_stats() does."""
    rows = []
    for filepath in sorted(glob.glob(os.path.join('nfl', 'data', '*.json'))):
        if os.path.basename(filepath) in NON_TEAM_FILES:
            continue
        with open(filepath, 'r') as f:
            team_data = json.load(f)
        if type(team_data) is list:
            team_data = team_data[0]

        team = team_data.get('team', '')
        abbr = team_data.get('abbr', '')
        source = team_data.get('source', '')
        base_defense = team_data.get('base_defense', '')

        for ourlads_pos, players in team_data.get('depth_chart', {}).items():
            for p in players:
                row = {
                    'team': team,
                    'abbr': abbr,
                    'source': source,
                    'base_defense': base_defense,
                    'ourlads_pos': ourlads_pos,
                    'name': p.get('name'),
                    'depth': p.get('depth'),
                    'injured': p.get('injured'),
                    'attainment': p.get('attainment'),
                    'standard_slot': p.get('standard_slot'),
                    'standard_pos': p.get('standard_pos'),
                    'cap_number': p.get('cap_number'),
                    'stats_json': json.dumps(p.get('stats', {})),
                    'stats_season': p.get('stats_season'),
                    'madden': p.get('madden'),
                    'jersey': p.get('jersey'),
                    'age': p.get('age'),
                    'years_pro': p.get('years_pro'),
                    'madden_rank': p.get('madden_rank'),
                    'madden_rank_total': p.get('madden_rank_total'),
                    'madden_pos_label': p.get('madden_pos_label'),
                }
                rows.append(row)
    for i, row in enumerate(rows):
        row['row_id'] = i
    return pd.DataFrame(rows)


def load_madden_ratings():
    path = os.path.join('nfl', 'data', 'madden.json')
    with open(path, 'r') as f:
        records = json.load(f)
    return pd.json_normalize(records)


def load_spotrac_contracts():
    path = os.path.join('nfl', 'data', 'spotrac_contracts.json')
    with open(path, 'r') as f:
        records = json.load(f)
    return pd.DataFrame(records)


def load_nflreadpy_rosters():
    """Same SEASON/SEASON+1 fallback build_master.py's load_nflreadpy_gsis()
    uses -- raw rows only, no name/team normalization columns added."""
    import nflreadpy as nfl
    try:
        df = nfl.load_rosters([SEASON, SEASON + 1]).to_pandas()
    except Exception:
        df = nfl.load_rosters([SEASON]).to_pandas()
    return df


def load_gsis_crosswalk():
    url = "https://github.com/dynastyprocess/data/raw/master/files/db_playerids.csv"
    return pd.read_csv(url)


def load_snap_counts():
    import nflreadpy as nfl
    try:
        return nfl.load_snap_counts([SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} snap counts not published yet ({e}) -- falling back to {SEASON - 1}")
        return nfl.load_snap_counts([SEASON - 1]).to_pandas()


def load_injuries():
    import nflreadpy as nfl
    return nfl.load_injuries([SEASON]).to_pandas()


def load_pbp_cached():
    """Shared pbp load for load_penalties() and load_qb_dropback_stats()
    -- avoids fetching the same season file twice in one run."""
    import nflreadpy as nfl
    try:
        return nfl.load_pbp([SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} play-by-play not published yet ({e}) -- falling back to {SEASON - 1}")
        return nfl.load_pbp([SEASON - 1]).to_pandas()


def load_penalties(pbp):
    """Season penalty counts, filtered to the two types overwhelmingly
    attributable to a specific offensive lineman (Offensive Holding,
    False Start). penalty_player_id is already in the same 00-XXXXXXX
    gsis_id format used everywhere else in this pipeline."""
    pen = pbp[(pbp['penalty'] == 1) &
              (pbp['penalty_type'].isin(['Offensive Holding', 'False Start']))]
    return pen[['penalty_player_id', 'penalty_type']].dropna(subset=['penalty_player_id'])


def load_qb_dropback_stats(pbp):
    """Season EPA/dropback and success rate per QB. nflverse's pbp
    already has pre-computed qb_epa (isolated QB credit, not the
    generic epa column which mixes credit across play types) and
    success (nflverse's own standard success-rate flag) columns per
    play -- no manual down/distance formula needed. Dropback =
    pass_attempt or sack (a sack is a failed dropback by definition;
    excluding it would flatter sack-prone QBs)."""
    dropbacks = pbp[(pbp['pass_attempt'] == 1) | (pbp['sack'] == 1)]
    return dropbacks.groupby('passer_player_id').agg(
        epa_per_play=('qb_epa', 'mean'),
        success_rate=('success', 'mean'),
    ).reset_index()


def load_ngs_passing():
    """NGS Time to Throw + NFL's own official CPOE (completion_percentage
    _above_expectation -- the league's published model, not nflverse's
    separate pbp-derived cpoe column), keyed by player_gsis_id.

    IMPORTANT: load_nextgen_stats() mixes weekly rows (week=1,2,3...)
    and ONE season-aggregate row (week=0) in the same dataframe for a
    given season -- confirmed by real inspection. Must filter to
    week == 0, or every downstream lookup gets multiple rows per
    player and silently breaks."""
    import nflreadpy as nfl
    try:
        df = nfl.load_nextgen_stats(stat_type='passing', seasons=[SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} NGS passing stats not published yet ({e}) -- falling back to {SEASON - 1}")
        df = nfl.load_nextgen_stats(stat_type='passing', seasons=[SEASON - 1]).to_pandas()
    return df[df['week'] == 0]


def load_qbr_ratings():
    path = os.path.join('nfl', 'data', 'qbr.json')
    with open(path, 'r') as f:
        records = json.load(f)
    return pd.json_normalize(records)


def load_ngs_rushing():
    """RYOE/attempt + box rate, both pre-computed by NGS. Same
    week==0-only gotcha as load_ngs_passing() -- mixes weekly rows and
    one season-aggregate row."""
    import nflreadpy as nfl
    try:
        df = nfl.load_nextgen_stats(stat_type='rushing', seasons=[SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} NGS rushing stats not published yet ({e}) -- falling back to {SEASON - 1}")
        df = nfl.load_nextgen_stats(stat_type='rushing', seasons=[SEASON - 1]).to_pandas()
    return df[df['week'] == 0]


def load_pfr_advstats_safe(stat_type):
    """Wraps load_pfr_advstats with a fallback that fires on EITHER
    an exception (season not yet valid) OR an empty result (season
    valid but PFR hasn't published charted data for it yet -- these
    are different failure modes, both need the same fallback).
    Confirmed live at the 2026 season's Week 1: load_pfr_advstats no
    longer raises (nflverse's own date validation accepts the season)
    but returns zero rows, since PFR/Sportradar's own charting lags
    behind -- the exception-only version of this check silently let
    every RB/WR/TE's PFR-sourced stats go null with no error anywhere."""
    import nflreadpy as nfl
    try:
        df = nfl.load_pfr_advstats([SEASON], stat_type=stat_type, summary_level='season').to_pandas()
    except ValueError as e:
        print(f"  {SEASON} PFR {stat_type} advstats not published yet ({e}) -- falling back to {SEASON - 1}")
        return nfl.load_pfr_advstats([SEASON - 1], stat_type=stat_type, summary_level='season').to_pandas()
    if len(df) == 0:
        print(f"  {SEASON} PFR {stat_type} advstats returned zero rows (not charted yet) -- falling back to {SEASON - 1}")
        return nfl.load_pfr_advstats([SEASON - 1], stat_type=stat_type, summary_level='season').to_pandas()
    return df


def dedupe_pfr_multiteam(df):
    """A player traded mid-season gets one row per team stint PLUS one
    combined aggregate row (tm like '2TM'/'3TM') in PFR's own
    season-level table -- confirmed live on Trayveon Williams (LAC+CLE,
    rows tm='LAC'/'CLE'/'2TM'), and separately confirmed on 13 different
    WR/TE (Zay Flowers, Ty Lockett, etc.) once this loader was extended
    to that position group. Keep only the aggregate row when present, or
    merging/keying on pfr_id cross-multiplies or collides on anyone
    traded (3 rush rows x 3 rec rows = 9 merged rows for one real person
    in RB's case -- confirmed, this is what broke the first run;
    duplicate pfr_id keys for WR/TE, confirmed the same way when this
    loader was extended to that group)."""
    df = df.copy()
    df['_is_multiteam'] = df['tm'].str.match(r'^\d+TM$', na=False)
    df = df.sort_values('_is_multiteam', ascending=False)
    return df.drop_duplicates(subset='pfr_id', keep='first').drop(columns='_is_multiteam')


def load_pfr_rb_stats(rush, rec):
    """YAC/attempt (rushing table) + a combined broken-tackle rate
    across both rushing and receiving touches. pfr_id is the join
    key -- this pipeline already resolves pfr_id per player via
    find_pfr_id()/pfr_id_direct (the same mechanism snap_pct already
    uses), so no new crosswalk is needed here. Takes rush/rec as
    params (fetched once in build_db() via load_pfr_advstats_safe) so
    the 'rec' table -- also needed by load_pfr_wr_te_stats() -- isn't
    pulled twice in one run."""
    rush = dedupe_pfr_multiteam(rush[rush['pos'].isin(['RB', 'FB'])])[['pfr_id', 'att', 'yac_att', 'brk_tkl']]
    rec = dedupe_pfr_multiteam(rec[rec['pos'].isin(['RB', 'FB'])])[['pfr_id', 'rec', 'brk_tkl']]
    merged = rush.merge(rec, on='pfr_id', how='outer', suffixes=('_rush', '_rec'))
    merged['touches'] = merged['att'].fillna(0) + merged['rec'].fillna(0)
    merged['broken_tackle_rate'] = (
        (merged['brk_tkl_rush'].fillna(0) + merged['brk_tkl_rec'].fillna(0))
        / merged['touches'].replace(0, pd.NA) * 100
    )
    return merged[['pfr_id', 'yac_att', 'broken_tackle_rate']]


def load_pfr_wr_te_stats(rec):
    """Drop rate + a receiving-only broken-tackle rate for WR/TE.
    Simpler than RB's version -- WR/TE don't have meaningful rushing
    touches, so no rush+rec combination is needed, just
    rec['brk_tkl'] / rec['rec']. Takes the same rec dataframe
    load_pfr_rb_stats() uses (fetched once in build_db()), not a
    second independent pull. Also needs the same multi-team dedup RB's
    loader uses -- confirmed live this bug isn't RB-specific, 13 real
    traded WR/TE had duplicate pfr_id rows without it."""
    rec = dedupe_pfr_multiteam(rec[rec['pos'].isin(['WR', 'TE'])])
    rec['broken_tackle_rate'] = rec['brk_tkl'] / rec['rec'] * 100
    rec['drop_rate'] = rec['drop_percent'] * 100
    return rec[['pfr_id', 'drop_rate', 'broken_tackle_rate']]


def load_pfr_def_stats(pfr_def):
    """Defender advanced stats straight from PFR's season 'def' table
    (pressures, sacks, combined tackles, missed tackles, and coverage
    allowed). `season` is kept on every row: PFR's charting lags, so this
    can be last season while SEASON has already flipped -- every rate built
    from it (snaps, TFL, PBU) must use this same season, never SEASON."""
    d = dedupe_pfr_multiteam(pfr_def)
    return d[['pfr_id', 'season', 'prss', 'sk', 'int', 'comb', 'm_tkl', 'm_tkl_percent',
              'tgt', 'cmp_percent', 'yds_tgt', 'rat', 'dadot']]


def load_def_snaps(season):
    """Season-total defensive snaps per pfr_id for the SAME season the
    PFR def table returned (the cached snap_counts table is SEASON,
    which may be a different, partial season)."""
    import nflreadpy as nfl
    snaps = nfl.load_snap_counts([season]).to_pandas()
    # PFR season advstats, TFL and PBU are regular season only; the snap
    # counts also carry playoff games (WC/DIV/CON/SB), which would inflate
    # the denominator for every playoff team's defenders.
    snaps = snaps[snaps['game_type'] == 'REG']
    out = snaps.groupby('pfr_player_id', as_index=False)['defense_snaps'].sum()
    out = out.rename(columns={'pfr_player_id': 'pfr_id'})
    out['season'] = season
    return out


def load_def_season_stats(season):
    """TFL and pass deflections for the same season as the PFR def
    table, summed per player from nflreadpy weekly stats (keyed by gsis
    player_id)."""
    import nflreadpy as nfl
    ps = nfl.load_player_stats([season], 'reg').to_pandas()
    out = ps.groupby('player_id', as_index=False)[['def_tackles_for_loss', 'def_pass_defended']].sum()
    out['season'] = season
    return out


def load_target_share():
    """Season-long target share, keyed by nflreadpy's own player_id --
    confirmed real (00-XXXXXXX gsis_id format), lines up directly with
    this pipeline's gid, no separate resolution needed. Needs its own
    summary_level='reg' call rather than reusing scrape_stats.py's
    weekly-sum output -- summing a ratio like target_share across weeks
    produces a meaningless number. Confirmed this fails with
    ConnectionError specifically (a missing not-yet-published parquet
    file), not ValueError like every other new source this round.

    Covers RB, WR, and TE -- this source already carries real
    target_share for all three (confirmed live), not RB-only."""
    import nflreadpy as nfl
    try:
        df = nfl.load_player_stats([SEASON], summary_level='reg').to_pandas()
    except ConnectionError as e:
        print(f"  {SEASON} player stats not published yet ({e}) -- falling back to {SEASON - 1}")
        df = nfl.load_player_stats([SEASON - 1], summary_level='reg').to_pandas()
    return df[df['position'].isin(['RB', 'WR', 'TE'])][['player_id', 'season', 'target_share']]


def load_ngs_receiving():
    """aDOT, air yards share, average separation, and YAC above
    expectation -- all pre-computed by NGS, no manual math needed.
    Same week==0-only gotcha as the QB/RB NGS loaders. Confirmed this
    source does NOT have load_pfr_advstats_safe()'s empty-result
    problem (real current-season data already present, including week
    1) -- exception-only fallback matches the existing NGS
    passing/rushing pattern."""
    import nflreadpy as nfl
    try:
        df = nfl.load_nextgen_stats(stat_type='receiving', seasons=[SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} NGS receiving stats not published yet ({e}) -- falling back to {SEASON - 1}")
        df = nfl.load_nextgen_stats(stat_type='receiving', seasons=[SEASON - 1]).to_pandas()
    return df[df['week'] == 0]


def season_of(df):
    """The season a loaded source table actually came from, read from its own
    `season` column AFTER any SEASON -> SEASON-1 fallback; None if unreadable."""
    if df is None or len(df) == 0 or 'season' not in df.columns:
        return None
    s = df['season'].dropna()
    return int(s.max()) if len(s) else None


def load_league_max_games(season):
    """Most regular-season games any team has played in `season` (completed games
    only, so a season in progress gives its current week count, not 17)."""
    import nflreadpy as nfl
    sc = nfl.load_schedules([season]).to_pandas()
    played = sc[(sc['game_type'] == 'REG') & sc['result'].notna()]
    return int(pd.concat([played['home_team'], played['away_team']]).value_counts().max())


def load_adv_volume(seasons):
    """Regular-season pass attempts / carries / targets per gsis player_id for each
    season an offense advanced stat actually came from -- the volume the frontend's
    sample-size gate must use (same season as the stat, never the current-season
    stats block). Rows are only written when the source has them."""
    import nflreadpy as nfl
    ps = nfl.load_player_stats(list(seasons), summary_level='reg').to_pandas()
    if 'season_type' in ps.columns:
        ps = ps[ps['season_type'] == 'REG']
    ps = ps[ps['player_id'].notna()]
    return ps[['player_id', 'season', 'attempts', 'carries', 'targets']].rename(
        columns={'attempts': 'att', 'carries': 'car', 'targets': 'tgt'})


def build_db():
    field_season = {}  # advanced field -> season its value actually came from

    def note(fields, df):
        s = season_of(df)
        if s is None:
            print(f"  WARNING: could not read the season for {fields} -- left out of advanced_meta.json")
            return
        for f in fields:
            field_season[f] = s

    con = duckdb.connect(DB_PATH)
    try:
        print("Loading ourlads_players...")
        write_table(con, 'ourlads_players', load_ourlads_players())

        print("Loading madden_ratings...")
        write_table(con, 'madden_ratings', load_madden_ratings())

        print("Loading spotrac_contracts...")
        write_table(con, 'spotrac_contracts', load_spotrac_contracts())

        print("Loading nflreadpy_rosters...")
        write_table(con, 'nflreadpy_rosters', load_nflreadpy_rosters())

        print("Loading gsis_crosswalk...")
        write_table(con, 'gsis_crosswalk', load_gsis_crosswalk())

        print("Loading snap_counts...")
        write_table(con, 'snap_counts', load_snap_counts())

        print("Loading injuries...")
        write_table(con, 'injuries', load_injuries())

        print("Loading play-by-play (penalties + QB dropback stats)...")
        pbp = load_pbp_cached()
        write_table(con, 'penalties', load_penalties(pbp))
        write_table(con, 'qb_dropback_stats', load_qb_dropback_stats(pbp))
        note(['epa_per_play', 'success_rate'], pbp)

        print("Loading NGS passing (CPOE + Time to Throw)...")
        ngs_passing = load_ngs_passing()
        write_table(con, 'ngs_passing', ngs_passing)
        note(['ngs_time_to_throw', 'cpoe'], ngs_passing)

        print("Loading QBR ratings...")
        qbr = load_qbr_ratings()
        write_table(con, 'qbr_ratings', qbr)
        note(['qbr'], qbr)

        print("Loading NGS rushing (RYOE/att + box rate)...")
        ngs_rushing = load_ngs_rushing()
        write_table(con, 'ngs_rushing', ngs_rushing)
        note(['ryoe_per_att', 'box_rate'], ngs_rushing)

        print("Loading PFR advstats (RB + WR/TE)...")
        pfr_rush = load_pfr_advstats_safe('rush')
        pfr_rec = load_pfr_advstats_safe('rec')
        write_table(con, 'pfr_rb_stats', load_pfr_rb_stats(pfr_rush, pfr_rec))
        write_table(con, 'pfr_wr_te_stats', load_pfr_wr_te_stats(pfr_rec))
        note(['yac_per_att'], pfr_rush)
        note(['drop_rate', 'broken_tackle_rate_rec'], pfr_rec)
        # RB broken_tackle_rate combines rush + rec; if the two ever fell back
        # differently, record the older season (the conservative one).
        rush_s, rec_s = season_of(pfr_rush), season_of(pfr_rec)
        if rush_s is not None and rec_s is not None:
            field_season['broken_tackle_rate'] = min(rush_s, rec_s)

        print("Loading PFR advstats (defense) + same-season snaps/TFL/PBU...")
        pfr_def = load_pfr_advstats_safe('def')
        def_season = int(pfr_def['season'].iloc[0])
        write_table(con, 'pfr_def_stats', load_pfr_def_stats(pfr_def))
        write_table(con, 'def_snaps_season', load_def_snaps(def_season))
        write_table(con, 'def_season_stats', load_def_season_stats(def_season))

        print("Loading target share (RB/WR/TE)...")
        target_share = load_target_share()
        write_table(con, 'target_share', target_share)
        note(['target_share'], target_share)

        print("Loading NGS receiving (aDOT, air yards share, separation, YAC+)...")
        ngs_receiving = load_ngs_receiving()
        write_table(con, 'ngs_receiving', ngs_receiving)
        note(['adot', 'air_yards_share', 'avg_separation', 'yac_above_expectation'], ngs_receiving)

        print("Loading same-season volume for the offense sample-size gate...")
        seasons = sorted(set(field_season.values()))
        volume_cols = ['player_id', 'season', 'att', 'car', 'tgt']
        league_max_games = {}
        try:
            volume = load_adv_volume(seasons)
            for s in seasons:
                # A season only gets a league_max_games entry once its volume loaded,
                # so a failed load leaves the frontend gate inert for it (not "everyone unqualified").
                if (volume['season'] == s).any():
                    league_max_games[str(s)] = load_league_max_games(s)
                else:
                    print(f"  WARNING: no volume rows for {s} -- gate stays inert for it")
        except Exception as e:
            print(f"  WARNING: adv volume load failed ({type(e).__name__}: {e}) -- gate stays inert")
            volume = pd.DataFrame(columns=volume_cols)
        write_table(con, 'adv_volume', volume)

        with open(ADV_META_PATH, 'w') as f:
            json.dump({'field_season': dict(sorted(field_season.items())),
                       'league_max_games': league_max_games}, f, indent=2)
        print(f"  wrote {ADV_META_PATH}: {len(field_season)} fields, league_max_games {league_max_games}")
    finally:
        con.close()

    print(f"\nWrote {DB_PATH}")


if __name__ == '__main__':
    build_db()

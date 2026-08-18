"""nhl/scripts/season_utils.py

Resolves "current season" for NHL by asking the API directly, not by
guessing from today's date. Same role as nfl/scripts/season_utils.py's
get_current_season(), but NHL needs two different answers depending on
what you're pulling -- confirmed against live data on 2026-08-18
(NHL offseason, ~6 weeks before the 2026-27 puck drop):

- Roster endpoint (teams.team_roster): the *upcoming* season id already
  returns the fuller, more current roster during the offseason -- NHL
  updates it live as free agency/trades happen. The prior season's id
  returns a stale, partial roster (departed UFAs already missing,
  incoming signees not yet added under the old id). Confirmed on TOR:
  20252026 -> 18 players, 20262027 -> 25 players, same day.
- Stats endpoints (stats.skater_stats_summary / goalie_stats_summary):
  the upcoming season id returns zero rows (no games played yet) until
  the season actually starts. The prior (most recently completed)
  season id is what "current stats" has to mean until puck drop.

resolve_seasons() calls standings.season_standing_manifest() (list of
every season with its real standingsEnd date) and picks the most
recently *completed* season as of today, rather than assuming an
October/April cutoff -- the manifest already knows the real calendar,
so there's no reason to hardcode one.
"""
from datetime import date


def resolve_seasons(client, today=None):
    """Returns (roster_season, stats_season) as YYYYYYYY strings.

    roster_season is one cycle ahead of stats_season (e.g. "20262027"
    vs "20252026") -- see module docstring for why they differ.
    """
    today = today or date.today().isoformat()
    manifest = client.standings.season_standing_manifest()
    completed = [s for s in manifest if s['standingsEnd'] <= today]
    last_completed = max(completed, key=lambda s: s['id'])

    stats_season_id = last_completed['id']
    roster_season_id = stats_season_id + 10001  # e.g. 20252026 -> 20262027

    return str(roster_season_id), str(stats_season_id)

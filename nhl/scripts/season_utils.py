"""nhl/scripts/season_utils.py

Resolves "current season" for NHL by asking the API directly, not by
guessing from today's date. Same role as nfl/scripts/season_utils.py's
get_current_season(), but NHL needs two different answers depending on
what you're pulling:

- Roster endpoint (teams.team_roster): while a season is underway, that
  season's id has the current roster. During the offseason gap (one
  season already finished, the next not yet started), the season that
  just ended goes stale (departed UFAs still listed, incoming signees
  missing) while the *upcoming* season id already has the fuller,
  more current roster -- NHL updates it live as free agency/trades
  happen. Confirmed on TOR during the 2026 offseason: 20252026 -> 18
  players, 20262027 -> 25 players, same day.
- Stats endpoints (stats.skater_stats_summary / goalie_stats_summary):
  a season with no games played yet returns zero rows. During the
  offseason gap that means the season that just ended is what "current
  stats" has to mean; once the new season is underway, its own
  (however partial) stats are the current ones.

resolve_seasons() calls standings.season_standing_manifest() (every
season with its real standingsStart/standingsEnd dates) and finds
`current` -- the season with the latest standingsStart that has already
begun as of today. If `current` has ALSO already ended
(standingsEnd <= today -- the offseason gap), stats_season stays on
`current` and roster_season moves one cycle ahead. If `current` is
still underway, stats_season and roster_season are the same season --
there's no gap to split them during an active season.

Replaces an earlier version that defined "current" purely by
standingsEnd (the most recently *completed* season) and derived
roster_season as a fixed +10001 offset from stats_season. That
version never advanced stats_season until a season fully finished
(~June) rather than when it started (~October) -- it would have kept
serving the prior season's stats for the entire ~8-month span of every
new NHL season. Fixed 2026-08-31.
"""
from datetime import date


def resolve_seasons(client, today=None):
    """Returns (roster_season, stats_season) as YYYYYYYY strings.

    Both come from the same `current` season lookup -- see module
    docstring for when they match and when they're a cycle apart.
    """
    today = today or date.today().isoformat()
    manifest = client.standings.season_standing_manifest()
    started = [s for s in manifest if s['standingsStart'] <= today]
    current = max(started, key=lambda s: s['standingsStart'])

    stats_season_id = current['id']
    if current['standingsEnd'] <= today:
        # Offseason gap -- stats stay on the season that just ended,
        # rosters move to the upcoming one.
        roster_season_id = stats_season_id + 10001
    else:
        # Season in progress -- both point at it.
        roster_season_id = stats_season_id

    return str(roster_season_id), str(stats_season_id)

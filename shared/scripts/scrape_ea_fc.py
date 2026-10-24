"""shared/scripts/scrape_ea_fc.py

Pulls EA SPORTS FC's official player ratings (via ea_ratings.fetch_all)
and writes one league's men's cards to a raw snapshot, the replacement
for scrape_sofifa.py's output. Usage (same CLI shape as the sofifa one):

    python shared/scripts/scrape_ea_fc.py <epl|mls> <output_path>

One snapshot per league (epl/data/ea_fc_epl.json, mls/data/ea_fc_mls.json)
rather than one shared file, so the scrape-epl and scrape-mls jobs, which
run concurrently and each commit only their own data dir, never both
edit the same file. Also writes a ratings_meta.json beside the snapshot
({"ratings_last_changed": "YYYY-MM-DD"}) for the PitchView caption.

EA's card `id` is the sofifa player id (recon: 544/552 EPL sofifa ids hit,
543 with identical OVR), kept as `ea_id`/`sofifa_id` downstream.

ratings_last_changed is diff-based, same pattern as nba_depth_chart.json's
last_changed: carried forward when the cards (id/name/OVR/team/position)
are identical to the previous snapshot, bumped to today when anything
differs, so the caption means "EA last changed these ratings", not "we
last scraped".

If the fetch is rejected by ea_ratings' guards (or the edition check
below), the previous snapshot is left untouched and the script exits 0 --
staleness then shows up as an old ratings_last_changed.

Edition check used (FC cards carry no edition marker; avatar URLs say
FC25 even in the current edition): men's totalItems must reach at least
17,000 (last season's men's total was 16,228, this season's is 17,849)
and 0.97x the previous snapshot's source_total, and the league must show
a sane card/club count.
"""
import json
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ea_ratings

SLUG = 'ea-sports-fc'
ABS_MIN_MENS_TOTAL = 17000

# league arg -> (EA leagueName, min cards, min clubs) from the 2026-10-24
# recon (EPL 612 cards / 20 clubs, MLS 806 cards / 30 clubs).
LEAGUES = {
    'epl': ('Premier League', 500, 18),
    'mls': ('MLS', 650, 28),
}


def load_previous(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def compact(card):
    return {
        'id': card['id'],
        'first_name': card.get('firstName'),
        'last_name': card.get('lastName'),
        'common_name': card.get('commonName'),
        'overall_rating': card.get('overallRating'),
        'team_name': (card.get('team') or {}).get('label'),
        'position': (card.get('position') or {}).get('shortLabel'),
        'league': card.get('leagueName'),
    }


def main(league_key, out_path):
    league, min_cards, min_clubs = LEAGUES[league_key]
    prev = load_previous(out_path)
    prev_total = (prev or {}).get('source_total') or 0
    min_total = max(ABS_MIN_MENS_TOTAL, int(prev_total * 0.97))

    def validate(items):
        mine = [c for c in items if c.get('leagueName') == league]
        clubs = {(c.get('team') or {}).get('label') for c in mine}
        if len(mine) < min_cards:
            return f'only {len(mine)} {league} cards (expected >= {min_cards})'
        if len(clubs) < min_clubs:
            return f'only {len(clubs)} {league} clubs (expected >= {min_clubs})'
        return None

    items = ea_ratings.fetch_all(SLUG, {'gender': 0}, min_total=min_total, validate=validate)
    if items is None:
        print(f'EA FC fetch rejected -- keeping the previous snapshot at {out_path}'
              f'{"" if prev else " (none exists yet!)"}')
        return

    cards = sorted((compact(c) for c in items if c.get('leagueName') == league), key=lambda c: c['id'])
    today = date.today().isoformat()
    if prev and prev.get('players') == cards and prev.get('ratings_last_changed'):
        changed = prev['ratings_last_changed']
        print(f'{len(cards)} {league} cards unchanged since {changed}')
    else:
        changed = today
        print(f'{len(cards)} {league} cards -- ratings changed (or first run), ratings_last_changed={changed}')

    out = {
        'league': league,
        'source': f'https://drop-api.ea.com/rating/{SLUG}',
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'ratings_last_changed': changed,
        'source_total': len(items),
        'players': cards,
    }
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    with open(os.path.join(os.path.dirname(out_path) or '.', 'ratings_meta.json'), 'w', encoding='utf-8') as f:
        json.dump({'ratings_last_changed': changed}, f, indent=1)
    print(f'Wrote {out_path}')


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in LEAGUES:
        sys.exit('usage: python shared/scripts/scrape_ea_fc.py <epl|mls> <output_path>')
    main(sys.argv[1], sys.argv[2])

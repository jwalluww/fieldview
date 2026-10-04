"""
mlb/scripts/scrape_show_api.py

Pulls MLB The Show's official public API (mlb26.theshow.com/apis) --
replaces theshowratings.com + ScraperAPI as the MLB ratings source. No
Cloudflare, plain requests with a browser User-Agent works.

  items.json?type=mlb_card&page=N  -> {page, per_page: 25, total_pages, items[]}
  roster_updates.json              -> {roster_updates: [{id, name: "October 02, 2026"}]}

Keeps only series == "Live" (the one current card per real player; every
other series is a special/promo card). Writes:
  mlb/data/show_api_live.json  -- raw Live cards (trimmed to the fields the
                                  match step uses), the raw snapshot
  mlb/data/ratings_meta.json   -- {ratings_as_of, roster_update_id, ...}
                                  ratings_as_of = newest roster update's date,
                                  shown on DiamondView.

The API has no MLB player ID and no potential rating, so build_mlb_match.py
joins on normalized name + team.

If the fetch fails or looks truncated and a snapshot already exists, the
snapshot is left alone and the script exits 0 (the matcher keeps using it;
the "Ratings as of" caption just stays at the old date, which is how
staleness stays visible). With no snapshot at all it exits 1.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://mlb26.theshow.com/apis"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
CARDS_PATH = os.path.join("mlb", "data", "show_api_live.json")
META_PATH = os.path.join("mlb", "data", "ratings_meta.json")
KEEP_FIELDS = ["uuid", "name", "ovr", "team", "team_short_name", "display_position",
               "display_secondary_positions", "rarity", "series", "jersey_number",
               "age", "bat_hand", "throw_hand", "is_hitter", "two_way"]
MIN_LIVE_CARDS = 1500  # ~2,084 expected; anything far below means a truncated pull


def get_json(path, params=None, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(f"{BASE_URL}/{path}", params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  retry {attempt + 1}/{retries} after error: {e} (waiting {wait}s)")
            time.sleep(wait)


def fetch_live_cards():
    first = get_json("items.json", {"type": "mlb_card", "page": 1})
    total_pages = first["total_pages"]
    cards = list(first["items"])
    page = 2
    while page <= total_pages:
        items = get_json("items.json", {"type": "mlb_card", "page": page}).get("items", [])
        if not items:
            break
        cards.extend(items)
        page += 1  # one page at a time, whatever size came back
    print(f"items.json: {len(cards)} cards over {page - 1}/{total_pages} pages")
    live = {}
    for c in cards:
        if c.get("series") == "Live":
            live[c["uuid"]] = {k: c.get(k) for k in KEEP_FIELDS}
    return list(live.values())


def fetch_ratings_as_of():
    updates = get_json("roster_updates.json")["roster_updates"]
    newest = max(updates, key=lambda u: u["id"])
    as_of = datetime.strptime(newest["name"].strip(), "%B %d, %Y").date().isoformat()
    return newest["id"], as_of


def main():
    have_snapshot = os.path.exists(CARDS_PATH)
    try:
        live = fetch_live_cards()
        if len(live) < MIN_LIVE_CARDS:
            raise RuntimeError(f"only {len(live)} Live cards (expected >= {MIN_LIVE_CARDS}) -- treating as truncated")
        update_id, as_of = fetch_ratings_as_of()
    except Exception as e:
        print(f"The Show API fetch failed: {e}")
        if have_snapshot:
            print("Keeping the existing snapshot (ratings_as_of is unchanged).")
            return 0
        return 1

    with open(CARDS_PATH, "w", encoding="utf-8") as f:
        json.dump(live, f, ensure_ascii=False)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({"ratings_as_of": as_of, "roster_update_id": update_id, "live_cards": len(live),
                   "scraped_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    print(f"{len(live)} Live cards written; ratings as of {as_of} (roster update {update_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

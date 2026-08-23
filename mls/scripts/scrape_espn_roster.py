"""mls/scripts/scrape_espn_roster.py

Phase 1a (MLS): ESPN's "core" API (sports.core.api.espn.com) is the only
usable ESPN host for this project -- site.api.espn.com returns a real
Akamai 403 for this whole machine's egress IP, confirmed network-level
(hit an NFL endpoint too), not soccer-specific. See PitchView recon.

No bulk full-object athlete endpoint exists anywhere on the core API
(re-confirmed live before writing this script, not assumed from the
earlier recon session): `.../seasons/2026/athletes?limit=1000` and the
plain `.../leagues/usa.1/athletes?limit=1000` variant both return real
counts (1057 total, pageCount=2 at limit=1000) but `items[]` are
`{"$ref": ...}` pointers only, same as the team list
(`.../seasons/2026/teams?limit=1000`, 32 real teams, also ref-only).
So this script does two bulk ref-list pulls (teams, 32; athletes, 1057
across 2 pages) up front, then loops individual detail calls.

Confirmed safe at full 1057-call scale in the recon session (all 200,
zero errors, ~0.07s/call, no throttling) -- no retry/backoff here by
design, matching that finding. Per-call try/except logging instead, so
one bad athlete id doesn't kill an otherwise-clean run.

Real field names confirmed live against a fresh pull before writing this
mapping (Lionel Messi, athlete 45843, and Chicago Fire FC, team 182):
  - Name: `fullName` (e.g. "Lionel Messi"), plus `firstName`/`lastName`/
    `displayName`/`shortName` variants -- fullName kept as the primary
    name field, matching sofifa's `name` field and FPL's constructed
    first+second name in the other two sports' pipelines.
  - `jersey` is a plain string/int field directly on the athlete object
    (not nested), e.g. "10" for Messi.
  - `position` is INLINE on the athlete detail response, not a $ref --
    `{id, name, displayName, abbreviation, leaf}` (e.g. "Forward"/"F"),
    same coarse (non-leaf) granularity confirmed in the original recon.
    No extra call needed for this field.
  - `team` IS a bare `$ref` with no inline name -- resolved here via a
    one-time `team_id -> {name, abbreviation}` lookup built from the 32
    real team-detail calls, extracting the id from the athlete's own
    team $ref URL.
  - `status` (`{id, name, type, abbreviation}`, e.g. "Active") and the
    top-level `active` boolean are both captured raw and NOT filtered
    out by this script -- population filtering (e.g. dropping inactive/
    practice-squad players) is a build_mls_match.py decision, reported
    on separately rather than silently applied here.
  - `height`/`weight` ARE present here (inches/lbs), unlike FPL, which
    had neither for EPL -- a real difference between the two leagues'
    sources worth keeping, not normalizing away.

Run from the repo root: python mls/scripts/scrape_espn_roster.py
"""
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

BASE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/usa.1"
OUT_PATH = os.path.join("mls", "data", "mls_roster.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

REF_ID_RE = re.compile(r"/(\d+)(?:\?|$)")


def get_json(session, url, params=None):
    resp = session.get(url, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_all_refs(session, url, params=None):
    """Follows ESPN core API's {count, pageCount, items[{$ref}]} paging
    shape -- used for both the team list and the athlete list, which
    share this exact structure (confirmed live on both)."""
    params = dict(params or {})
    refs = []
    page = 1
    while True:
        params["page"] = page
        data = get_json(session, url, params=params)
        items = data.get("items", [])
        if not items:
            break
        refs.extend(item["$ref"] for item in items)
        if page >= data.get("pageCount", page):
            break
        page += 1
    return refs


def ref_id(ref_url):
    m = REF_ID_RE.search(ref_url.split("?")[0])
    return m.group(1) if m else None


def build_team_lookup(session):
    print("Fetching team list...")
    team_refs = fetch_all_refs(session, f"{BASE}/seasons/2026/teams", params={"limit": 1000})
    print(f"  {len(team_refs)} teams")

    lookup = {}
    for ref in team_refs:
        tid = ref_id(ref)
        try:
            team = get_json(session, ref)
        except Exception as e:
            print(f"  ERROR fetching team {tid}: {e}")
            continue
        lookup[tid] = {
            "team_id": tid,
            "team_name": team.get("name"),
            "team_abbreviation": team.get("abbreviation"),
            "team_short_name": team.get("shortDisplayName"),
        }
    print(f"  resolved {len(lookup)}/{len(team_refs)} team details")
    return lookup


def build_athlete_record(athlete, team_lookup):
    team_ref = (athlete.get("team") or {}).get("$ref")
    team_id = ref_id(team_ref) if team_ref else None
    team_info = team_lookup.get(team_id, {})
    position = athlete.get("position") or {}
    status = athlete.get("status") or {}

    return {
        "athlete_id": str(athlete["id"]),
        "full_name": athlete.get("fullName"),
        "first_name": athlete.get("firstName"),
        "last_name": athlete.get("lastName"),
        "display_name": athlete.get("displayName"),
        "short_name": athlete.get("shortName"),
        "jersey": athlete.get("jersey"),
        "age": athlete.get("age"),
        "date_of_birth": athlete.get("dateOfBirth"),
        "height": athlete.get("height"),
        "weight": athlete.get("weight"),
        "citizenship": athlete.get("citizenship"),
        "position": position.get("name"),
        "position_abbreviation": position.get("abbreviation"),
        "position_id": position.get("id"),
        "team_id": team_id,
        "team_name": team_info.get("team_name"),
        "team_abbreviation": team_info.get("team_abbreviation"),
        "status": status.get("name"),
        "active": athlete.get("active"),
    }


def main():
    session = requests.Session()

    team_lookup = build_team_lookup(session)

    print("\nFetching bulk athlete id list...")
    athlete_refs = fetch_all_refs(session, f"{BASE}/seasons/2026/athletes", params={"limit": 1000})
    print(f"  {len(athlete_refs)} athletes")

    roster = {}
    errors = []
    t0 = time.time()
    for i, ref in enumerate(athlete_refs):
        aid = ref_id(ref)
        try:
            athlete = get_json(session, ref)
            roster[aid] = build_athlete_record(athlete, team_lookup)
        except Exception as e:
            errors.append((aid, str(e)))
            print(f"  ERROR fetching athlete {aid}: {e}")
        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            print(f"  {i + 1}/{len(athlete_refs)} done in {elapsed:.1f}s")

    elapsed = time.time() - t0
    print(f"\nFetched {len(roster)}/{len(athlete_refs)} athletes in {elapsed:.1f}s "
          f"({len(errors)} error(s))")

    output = {
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "players": roster,
        "errors": errors,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUT_PATH}: {len(roster)} players")


if __name__ == "__main__":
    main()

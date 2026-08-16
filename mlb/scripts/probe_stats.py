"""
mlb/scripts/probe_stats.py — throwaway, delete once we've decided

Tests whether /v1/stats supports a bulk full-league pull (all hitters,
all pitchers, one call each) or whether we're stuck with the ~780-call
per-player hydrate pattern that's the only one proven in the wrapper
library's source.
"""
import requests
import json

BASE_URL = "https://statsapi.mlb.com/api/v1"


def probe_bulk(group):
    resp = requests.get(f"{BASE_URL}/stats", params={
        "stats": "season",
        "group": group,
        "sportIds": 1,
        "season": 2026,
        "limit": 2000,
    }, timeout=30)
    print(f"=== group={group} status={resp.status_code} ===")
    if resp.status_code != 200:
        print(resp.text[:500])
        return
    data = resp.json()
    splits = data.get("stats", [{}])[0].get("splits", [])
    print(f"players returned: {len(splits)}")
    if splits:
        first = splits[0]
        print("sample player:", first.get("player", {}).get("fullName"))
        print("sample stat keys:", list(first.get("stat", {}).keys())[:10])
    with open(f"mlb_stats_probe_{group}.json", "w") as f:
        json.dump(data, f, indent=2)


def probe_bulk_full(group):
    resp = requests.get(f"{BASE_URL}/stats", params={
        "stats": "season",
        "group": group,
        "sportIds": 1,
        "season": 2026,
        "limit": 2000,
        "playerPool": "all",
    }, timeout=30)
    print(f"=== group={group} playerPool=all status={resp.status_code} ===")
    if resp.status_code != 200:
        print(resp.text[:500])
        return
    data = resp.json()
    splits = data.get("stats", [{}])[0].get("splits", [])
    print(f"players returned: {len(splits)}")


if __name__ == "__main__":
    probe_bulk("hitting")
    probe_bulk("pitching")
    probe_bulk_full("hitting")
    probe_bulk_full("pitching")

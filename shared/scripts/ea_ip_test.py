"""TEMPORARY: checks EA's drop-api from a GitHub Actions runner. Deleted after the test."""
import os
import random
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
CASES = [("ea-sports-fc", 100), ("madden-nfl", 100), ("nhl", 50)]

lines = []
for slug, limit in CASES:
    headers = {"User-Agent": UA, "Accept": "application/json",
               "drop-referrer": f"https://www.ea.com/games/{slug}/ratings"}
    params = {"locale": "en", "limit": limit, "cb": str(random.randint(10**8, 10**9))}
    try:
        r = requests.get(f"https://drop-api.ea.com/rating/{slug}", params=params, headers=headers, timeout=30)
        try:
            j = r.json()
            items = j.get("items") or []
            first = items[0] if items else {}
            line = (f"{slug}: status={r.status_code} totalItems={j.get('totalItems')} n={len(items)} "
                    f"first={first.get('firstName')} {first.get('lastName')} ovr={first.get('overallRating')} "
                    f"avatar={str(first.get('avatarUrl'))[:90]}")
        except ValueError:
            line = f"{slug}: status={r.status_code} non-JSON body: {r.text[:200]!r}"
    except Exception as e:
        line = f"{slug}: request failed: {e}"
    print(line)
    lines.append(line)


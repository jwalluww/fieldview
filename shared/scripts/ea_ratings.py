"""shared/scripts/ea_ratings.py

Shared fetcher for EA's official ratings API (drop-api.ea.com), the data
behind ea.com/games/{franchise}/ratings. Used by scrape_ea_fc.py (EPL +
MLS); written so Madden (slug madden-nfl) can use it next with no changes
here. Recon-verified facts this module depends on:

  - GET https://drop-api.ea.com/rating/{slug}?locale=en&limit=N&offset=M
    with slugs ea-sports-fc / madden-nfl / nhl. No auth, no cookies.
  - The `drop-referrer: https://www.ea.com/games/{slug}/ratings` header is
    REQUIRED. Without it EA silently serves LAST season's ratings (and the
    nhl slug returns zero items) while still answering 200.
  - EA's CDN caches by URL for ~10 minutes and ignores that header, so a
    header-less request can poison the cache for the same URL. Every
    request therefore carries a throwaway random `cb` param.
  - Page size is hard-capped (100 for FC/Madden, 50 for NHL); a bigger
    `limit` is a 400. Pages are walked by the number of items actually
    returned. `totalItems` is only trustworthy on page 1 (later pages
    report 0).
  - Verified from a GitHub Actions runner too (2026-10-24).

fetch_all() returns the list of raw cards, or None when anything looks
wrong (request failures after retries, a truncated pull, a total far
below expectation, or cards that fail the caller's edition check). The
caller then keeps its previous snapshot -- never overwrite good data with
a bad fetch.
"""
import random
import time

import requests

API_URL = 'https://drop-api.ea.com/rating/{slug}'
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
PAGE_SIZE = {'ea-sports-fc': 100, 'madden-nfl': 100, 'nhl': 50}
DEFAULT_PAGE_SIZE = 50


def build_headers(slug):
    """Request headers; module-level so a test can monkeypatch it to
    simulate the missing-header failure."""
    return {
        'User-Agent': USER_AGENT,
        'Accept': 'application/json',
        'drop-referrer': f'https://www.ea.com/games/{slug}/ratings',
    }


def _get_page(slug, params, retries):
    last_err = None
    for attempt in range(retries):
        if attempt:
            time.sleep(2 ** attempt)  # 2s, 4s, 8s...
        try:
            q = dict(params, cb=str(random.randint(10 ** 8, 10 ** 9)))
            r = requests.get(API_URL.format(slug=slug), params=q,
                             headers=build_headers(slug), timeout=60)
            if r.status_code != 200:
                last_err = f'HTTP {r.status_code}'
                continue
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last_err = str(e)
    print(f'  ea_ratings: giving up on {slug} offset={params.get("offset", 0)}: {last_err}')
    return None


def fetch_all(slug, extra_params=None, min_total=None, validate=None, retries=4):
    """Fetch every card for `slug`.

    extra_params: extra query params (e.g. {'gender': 0}, {'iteration': ...}).
    min_total:    minimum acceptable totalItems from page 1. A total below
                  this is treated as the previous edition / a broken
                  response and returns None.
    validate:     optional callable(items) -> None if fine, else a string
                  reason. The caller's edition/sanity check.
    Returns the list of cards, or None (caller keeps its old snapshot).
    """
    limit = PAGE_SIZE.get(slug, DEFAULT_PAGE_SIZE)
    base = dict(extra_params or {}, locale='en', limit=limit)

    first = _get_page(slug, base, retries)
    if first is None:
        return None
    total = first.get('totalItems') or 0
    if min_total is not None and total < min_total:
        print(f'  ea_ratings: {slug} totalItems={total} is below the expected minimum '
              f'{min_total} (previous edition, or the drop-referrer header was ignored) -- rejecting')
        return None

    items = list(first.get('items') or [])
    offset = len(items)
    while items and offset < total:
        page = _get_page(slug, dict(base, offset=offset), retries)
        if page is None:
            return None
        got = page.get('items') or []
        if not got:
            break
        items.extend(got)
        offset += len(got)  # by what the page actually returned
        time.sleep(0.1)

    if total == 0 or len(items) < total:
        print(f'  ea_ratings: {slug} truncated pull ({len(items)} of {total}) -- rejecting')
        return None
    ids = {c.get('id') for c in items}
    if len(ids) != len(items):
        print(f'  ea_ratings: {slug} returned duplicate card ids ({len(items)} cards, {len(ids)} unique) -- rejecting')
        return None

    if validate is not None:
        reason = validate(items)
        if reason:
            print(f'  ea_ratings: {slug} failed the edition check: {reason} -- rejecting')
            return None
    return items

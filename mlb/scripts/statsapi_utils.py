"""
mlb/scripts/statsapi_utils.py
Shared helper for MLB statsapi.mlb.com scrapers.
"""
import time
import requests


def fetch_with_retry(url, params=None, retries=3, backoff=2, timeout=30):
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            print(f"  retry {attempt+1}/{retries} after error: {e} (waiting {wait}s)")
            time.sleep(wait)

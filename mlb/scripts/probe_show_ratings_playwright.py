"""
mlb/scripts/probe_show_ratings_playwright.py -- throwaway, delete once
we know the shape.

One-page prototype only (not a 30-team build): does a real headless
Chromium session clear theshowratings.com's Cloudflare block where
curl_cffi's TLS impersonation has now failed 3 times in a row (blocked
on team #1 every time)? And separately: does the ratings table load
via a plain XHR/fetch call under the hood, which might be a less-
protected endpoint reachable directly without a browser at all?

Logs every network response during page load/settle so we can see
both answers from one run.
"""
import json

from playwright.sync_api import sync_playwright

URL = "https://www.theshowratings.com/teams/arizona-diamondbacks"


def main():
    responses = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        def on_response(resp):
            responses.append({
                "url": resp.url,
                "status": resp.status,
                "content_type": resp.headers.get("content-type", ""),
            })

        page.on("response", on_response)

        print(f"Navigating to {URL} ...")
        main_resp = page.goto(URL, timeout=30000, wait_until="domcontentloaded")
        print(f"Main document response: status={main_resp.status}")

        # Give the page a moment to settle / fire any XHR calls.
        page.wait_for_timeout(4000)

        title = page.title()
        print(f"Page title: {title!r}")

        body_text = page.inner_text("body")
        print(f"Body text length: {len(body_text)}")
        print(f"Body text first 300 chars: {body_text[:300]!r}")

        has_table = page.locator("table.table-striped").count()
        print(f"table.table-striped elements found: {has_table}")

        cf_challenge_markers = ["Checking your browser", "cf-browser-verification",
                                 "Just a moment", "Access to this page is forbidden"]
        hit_markers = [m for m in cf_challenge_markers if m.lower() in body_text.lower()]
        print(f"Cloudflare challenge/block markers found in body: {hit_markers}")

        browser.close()

    print(f"\nTotal network responses captured: {len(responses)}")
    json_responses = [r for r in responses if "json" in r["content_type"].lower()]
    print(f"JSON-content-type responses: {len(json_responses)}")
    for r in json_responses:
        print(f"  {r['status']} {r['content_type']} {r['url']}")

    non_200 = [r for r in responses if r["status"] >= 400]
    print(f"\nNon-2xx/3xx responses: {len(non_200)}")
    for r in non_200[:10]:
        print(f"  {r['status']} {r['url']}")

    with open("mlb/scripts/probe_playwright_responses.json", "w", encoding="utf-8") as f:
        json.dump(responses, f, indent=2)
    print("\nFull response log saved to mlb/scripts/probe_playwright_responses.json")


if __name__ == "__main__":
    main()

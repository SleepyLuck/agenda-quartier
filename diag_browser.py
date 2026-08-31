"""TEMP diagnostic: does rendering pianofabriek.be/activiteiten in a real
headless browser (JS executed) actually surface event text that a raw
requests.get() can't see? Writes nothing; only prints. Deleted after use.
"""
import re
from playwright.sync_api import sync_playwright

UA = "neighbourhood-events/1.0 (personal event aggregator; contact: you@example.org)"
URL = "https://www.pianofabriek.be/activiteiten"

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    page = browser.new_page(user_agent=UA)
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    html = page.content()
    text = page.inner_text("body")
    browser.close()

print(f"rendered html: {len(html)} chars, rendered visible text: {len(text)} chars")

date_like = re.findall(
    r"\b\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?\b"
    r"|\b(?:jan|feb|mrt|apr|mei|jun|jul|aug|sep|okt|nov|dec)\w*\b",
    text, re.I,
)
print(f"date-like tokens in rendered text: {len(date_like)}")

ldjson_blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>', html, re.I)
print(f"ld+json script tags in rendered html: {len(ldjson_blocks)}")

print()
print("=" * 78)
print("First 3000 chars of rendered visible text:")
print("=" * 78)
print(text[:3000])

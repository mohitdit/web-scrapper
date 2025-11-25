import asyncio
import json
import os
from datetime import datetime
from scrapers.site_x_scraper import WisconsinScraper


def save_html_file(html_content, docket, county_name):
    os.makedirs("data/html_output", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    file_name = f"{docket}{county_name.replace(' ', '')}_{timestamp}.html"
    file_path = os.path.join("data/html_output", file_name)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"📁 Saved HTML to: {file_path}")

    return file_path


def run_test():
    sqs_record = {
        "InitialURL": "https://wcca.wicourts.gov",
        "stateName": "WISCONSIN",
        "stateAbbreviation": "WI",
        "urlFormat": "https://wcca.wicourts.gov/caseDetail.html?caseNo=[DocketYear][DocketType][MaxDocketNumber]&countyNo=[CountyID]&index=0&isAdvanced=true&mode=details",
        "countyNo": 6,
        "countyName": "Buffalo County",
        "docketNumber": "001462",
        "docketYear": 2025,
        "docketType": "TR",
        "IsDownloadRequired": "true",
        "docketUpdateDateTime": "2025-11-11T10:10:00Z"
    }

    scraper = WisconsinScraper()
    print("\n🚀 Starting Wisconsin Court Scraper...\n")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(scraper.process_single_case(sqs_record))
        loop.close()

        print("✅ Scraper completed successfully.\n")

        docket = result["docket"]
        html = result["html"]
        county = sqs_record["countyName"]

        print("📌 Docket:", docket)
        print("📄 HTML Size:", len(html), "characters\n")

        # ⭐ SAVE HTML TO FILE
        save_html_file(html, docket, county)

    except Exception as ex:
        print("\n❌ ERROR during scraping:", ex, "\n")



if __name__ == "__main__":
    run_test()

Yallaiah Ganduri, 38 min
main.py
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import asyncio
import warnings
import json

# --- utils/browser_manager.py ---

async def get_stealth_browser():
    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ]
    )

    context = await browser.new_context()
    page = await context.new_page()

    # NEW API - Stealth v2.0.0
    stealth = Stealth()
    await stealth.apply_stealth_async(page)

    return browser, context

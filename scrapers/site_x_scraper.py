import asyncio
from utils.browser_manager import get_stealth_browser


class WisconsinScraper:

    CAPTCHA_TEXT = "Please complete the CAPTCHA."
    CLICK_HERE_SELECTOR = "text=Click here"
    CASE_SUMMARY_SELECTOR = "text=Case summary"

    async def open_case_detail(self, url: str):
        browser, context = await get_stealth_browser()
        page = await context.new_page()

        print(f"Opening URL: {url}")
        await page.goto(url, wait_until="domcontentloaded")

        # CAPTCHA check
        try:
            # Wait for the main content or the CAPTCHA text, whichever appears first
            await page.wait_for_selector(
                f"{self.CASE_SUMMARY_SELECTOR}, text='{self.CAPTCHA_TEXT}'", 
                timeout=10000
            )
        except Exception:
            # If neither appears in 10s, assume a general failure or slow load
            print("Timeout waiting for initial page content.")

        html_content = await page.content()
        if self.CAPTCHA_TEXT in html_content:
            print("CAPTCHA redirect detected. Clicking the link...")
            try:
                # Use expect_navigation to wait for the page after the click
                async with page.expect_navigation():
                    await page.click(self.CLICK_HERE_SELECTOR)
                print("Click successful, waiting for new page load...")
            except Exception as e:
                print(f"Error clicking CAPTCHA link: {e}")
                # You might want to re-raise the exception or return failure here
                await browser.close()
                raise

        # Wait for Case Summary - This is the final successful state
        # print("Waiting for Case Summary selector...")
        # await page.wait_for_selector(self.CASE_SUMMARY_SELECTOR, timeout=20000)

        html = await page.content()

        await browser.close()
        return html

    async def process_single_case(self, sqs_record: dict):
        docket_year = sqs_record["docketYear"]
        docket_type = sqs_record["docketType"]
        docket_number = sqs_record["docketNumber"]
        county_no = sqs_record["countyNo"]

        url = (
            "https://wcca.wicourts.gov/caseDetail.html?caseNo="
            f"{docket_year}{docket_type}{docket_number}"
            f"&countyNo={county_no}&index=0&isAdvanced=true&mode=details"
        )

        html = await self.open_case_detail(url)

        return {
            "docket": docket_number,
            "html": html,
        }
import asyncio
import os
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

# ---------------- CONFIG ----------------
START_DOCKET_STR = "001555"
ZFILL_WIDTH = len(START_DOCKET_STR)
DOCKET_YEAR = 2025
DOCKET_TYPE = "TR"
COUNTY_NO = 6
COUNTY_NAME = "Buffalo County"
MAX_ATTEMPTS = 2000
HEADLESS_AFTER_BYPASS = True   # continue headless after you manually bypass once
SAVE_STORAGE_STATE = True      # save state.json after manual bypass
STATE_FILE = "state.json"
OUTPUT_DIR = "data/html_output"
CLICK_HERE_TEXT = "Click here"  # text to click for simple interstitials
# ----------------------------------------

UNAVAILABLE_TITLE = "Your request could not be processed."
UNAVAILABLE_SNIPPET_1 = "Your request could not be processed."
UNAVAILABLE_SNIPPET_2 = "That case does not exist or you are not allowed to see it."


def build_case_url(docket_year: int, docket_type: str, docket_number: str, county_no: int) -> str:
    return (
        "https://wcca.wicourts.gov/caseDetail.html?"
        f"caseNo={docket_year}{docket_type}{docket_number}"
        f"&countyNo={county_no}&index=0&isAdvanced=true&mode=details"
    )


def save_html_file(html_content: str, docket: str, county_name: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"{docket}{county_name.replace(' ', '')}_{timestamp}.html"
    file_path = os.path.join(OUTPUT_DIR, file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return file_path


def html_indicates_unavailable(html: str) -> bool:
    if not html:
        return True
    lower = html.lower()
    if UNAVAILABLE_TITLE.lower() in lower:
        return True
    return (UNAVAILABLE_SNIPPET_1.lower() in lower) and (UNAVAILABLE_SNIPPET_2.lower() in lower)


async def detect_hcaptcha_or_visual_captcha(html: str) -> bool:
    """Return True if page contains hcaptcha or recognizable visual captcha markers."""
    l = html.lower()
    if "h-captcha" in l or "hcaptcha" in l or "recaptcha" in l or "captcha" in l:
        return True
    return False


async def try_click_interstitial(page, max_retries: int = 3) -> bool:
    """
    Attempt to click a 'Click here' link/button automatically.
    Returns True if clicking likely succeeded (page changed and no visible captcha markers),
    or False if failed / visual captcha present.
    """
    for attempt in range(1, max_retries + 1):
        try:
            # If there is a direct text match, click it
            await page.wait_for_timeout(500)  # tiny wait
            # attempt click by text
            clicked = False
            try:
                await page.click(f"text={CLICK_HERE_TEXT}", timeout=4000)
                clicked = True
            except Exception:
                # maybe it's an <a> with that text but not clickable by text selector - try generic anchors
                anchors = await page.query_selector_all("a")
                for a in anchors:
                    txt = (await a.inner_text()).strip().lower()
                    if CLICK_HERE_TEXT.lower() in txt:
                        await a.click()
                        clicked = True
                        break

            if clicked:
                # wait for navigation or network idle briefly
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    # not fatal, try to continue
                    pass

                # get fresh HTML and check for captcha markers
                html = await page.content()
                if await detect_hcaptcha_or_visual_captcha(html):
                    # clicking revealed a real captcha; cannot bypass
                    return False
                # likely success
                return True
            else:
                # no click target found; return False to indicate no simple interstitial
                return False

        except Exception as e:
            # try again
            await page.wait_for_timeout(500 + attempt * 300)
            continue

    return False


async def ensure_session_state(page, initial_url):
    """
    If state.json exists, we assume session is ready. If not, open headful and let user interact,
    then save storage_state to STATE_FILE so headless run can continue automatically.
    """
    if os.path.exists(STATE_FILE):
        print("Found existing session state (state.json). Reusing it.")
        return True

    # No state saved; open interactive page so user can manually click/solve once.
    print("No state.json found. Opening interactive browser so you can manually bypass interstitial (click 'Click here' / solve CAPTCHA).")
    try:
        await page.goto(initial_url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeoutError:
        print("Warning: navigation timed out; continue and inspect the browser window.")

    # Wait up to a reasonable time for the user to interact
    print("Please complete the interstitial in the opened browser window now.")
    print("After you finish clicking/solving, type 'done' in the terminal and press Enter to continue...")
    # run blocking input in executor so event loop stays alive
    await asyncio.get_event_loop().run_in_executor(None, input)

    # verify page after user action
    html = await page.content()
    if html_indicates_unavailable(html):
        print("After manual interaction the page still shows 'unavailable'. You may need to try a different docket or page.")
        # still save what we have
    # Save storage state for later automated runs
    if SAVE_STORAGE_STATE:
        await page.context.storage_state(path=STATE_FILE)
        print("Saved session state to", STATE_FILE)
    return True


async def run_main():
    start_int = int(START_DOCKET_STR)
    zfill_width = ZFILL_WIDTH
    saved = []

    async with async_playwright() as p:
        # If we have state.json, create context with it (headless). Otherwise start headful for manual bypass,
        # then save and relaunch headless.
        if os.path.exists(STATE_FILE):
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(storage_state=STATE_FILE,
                                                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
            page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            print("Launched headless browser with saved session.")
        else:
            # launch headful for manual bypass
            browser = await p.chromium.launch(headless=False, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
            page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            initial_url = build_case_url(DOCKET_YEAR, DOCKET_TYPE, str(start_int).zfill(zfill_width), COUNTY_NO)
            await ensure_session_state(page, initial_url)

            if HEADLESS_AFTER_BYPASS and os.path.exists(STATE_FILE):
                # close and relaunch headless with saved state
                await context.close()
                await browser.close()
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
                context = await browser.new_context(storage_state=STATE_FILE,
                                                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
                page = await context.new_page()
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
                print("Re-launched headless browser using saved state.json")

        # Now we have a usable page + context; iterate dockets automatically
        current = start_int
        attempts = 0
        last_valid_docket = None
        last_valid_url = None

        while attempts < MAX_ATTEMPTS:
            docket_str = str(current).zfill(zfill_width)
            url = build_case_url(DOCKET_YEAR, DOCKET_TYPE, docket_str, COUNTY_NO)
            print(f"\nNavigating to docket {docket_str} -> {url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except PlaywrightTimeoutError:
                print("Warning: navigation timed out for", docket_str)

            await asyncio.sleep(0.5)
            html = await page.content()

            # If simple interstitial appears, attempt automatic click retries
            lower = html.lower()
            if CLICK_HERE_TEXT.lower() in lower or "checking your browser" in lower:
                print("Simple interstitial found — attempting automatic click bypass...")
                ok = await try_click_interstitial(page, max_retries=3)
                if not ok:
                    # If we detect a visual hcaptcha or fail, stop because we cannot bypass reliably
                    if await detect_hcaptcha_or_visual_captcha(await page.content()):
                        print("Detected a visual CAPTCHA (hcaptcha/recaptcha). Cannot auto-solve. Stopping loop.")
                        break
                    else:
                        print("Automatic click attempt did not succeed (no visible 'Click here' or no navigation). Continuing to next attempt.")
                        # try to refresh the html variable
                        html = await page.content()

            # final check for the 'unavailable' stop marker
            if html_indicates_unavailable(html):
                print(f"Unavailable marker found at docket {docket_str}. Stopping iteration.")
                first_invalid = docket_str
                break

            # Save the HTML for the valid docket
            path = save_html_file(html, docket_str, COUNTY_NAME)
            saved.append((docket_str, url, path))
            last_valid_docket = docket_str
            last_valid_url = url
            print(f"Saved docket {docket_str} -> {path} (size {len(html)} bytes)")

            # polite delay
            await asyncio.sleep(0.35)
            current += 1
            attempts += 1
        else:
            first_invalid = None
            print("Reached MAX_ATTEMPTS without finding unavailable page.")

        # cleanup
        await context.close()
        await browser.close()

    # Summary
    print("\n==== SUMMARY ====")
    print("Start docket:", START_DOCKET_STR)
    print("Last valid docket:", last_valid_docket)
    print("Last valid URL:", last_valid_url)
    print("First invalid docket (stopping point):", first_invalid)
    print("Total saved pages:", len(saved))
    for d, u, p in saved:
        print(f"  {d} -> {u} -> {p}")

    return {
        "start": START_DOCKET_STR,
        "last_valid_docket": last_valid_docket,
        "last_valid_url": last_valid_url,
        "first_invalid_docket": first_invalid,
        "saved_files": saved
    }


if __name__ == "__main__":
    asyncio.run(run_main())
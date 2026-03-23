"""
automation/refresh_runner.py
--
Playwright-based automation that logs into a legacy web reporting portal
and triggers report refresh.

Usage:
    python refresh_runner.py --locations 1,2,3
    python refresh_runner.py --locations all --concurrency 5

Environment variables:
    REPORT_URL    Base URL of the reporting portal
    REPORT_USER   Login username
    REPORT_PASS   Login password
    DB_HOST / DB_USER / DB_PASS / DB_NAME   MySQL job tracking
"""

import asyncio
import argparse
import os
import logging
from datetime import datetime, timezone
from typing import Optional

import aiomysql
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BASE_URL    = os.getenv("REPORT_URL",  "http://localhost:5001")
REPORT_USER = os.getenv("REPORT_USER", "admin")
REPORT_PASS = os.getenv("REPORT_PASS", "password")
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 3306))
DB_USER     = os.getenv("DB_USER",     "pipeline_user")
DB_PASS     = os.getenv("DB_PASS",     "pipeline_pass")
DB_NAME     = os.getenv("DB_NAME",     "refresh_jobs")

# Database tools and helpers

async def get_db_pool():
    return await aiomysql.create_pool(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASS, db=DB_NAME, autocommit=True, minsize=1, maxsize=10
    )

async def log_job_start(pool, location_id: str, run_id: str):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO refresh_jobs (run_id, location_id, status, started_at)
                VALUES (%s, %s, 'running', NOW())
                ON DUPLICATE KEY UPDATE status='running', started_at=NOW()
            """, (run_id, location_id))

async def log_job_result(pool, location_id: str, run_id: str, status: str, error: Optional[str] = None):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE refresh_jobs
                SET status=%s, completed_at=NOW(), error_message=%s
                WHERE run_id=%s AND location_id=%s
            """, (status, error, run_id, location_id))

# Browser session start

async def create_authenticated_session(playwright, headless=True):
    """Launches browser, authenticates, returns (browser, context, page)."""
    browser = await playwright.chromium.launch(headless=headless)
    context = await browser.new_context(ignore_https_errors=True)
    page    = await context.new_page()

    log.info("Navigating to login: %s", BASE_URL)
    await page.goto(f"{BASE_URL}/", wait_until="networkidle")
    await page.fill("input[name='username']", REPORT_USER)
    await page.fill("input[name='password']", REPORT_PASS)
    await page.click("button[type='submit']")
    await page.wait_for_url(f"{BASE_URL}/dashboard", timeout=10_000)
    log.info("Authentication successful.")
    return browser, context, page

# Location refresh logic

async def refresh_location(page, pool, location_id: str, run_id: str) -> bool:
    await log_job_start(pool, location_id, run_id)
    try:
        log.info("Refreshing location %s ...", location_id)
        if "/dashboard" not in page.url:
            await page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle")

        btn = page.locator(f"#btn-{location_id}")
        await btn.wait_for(state="visible", timeout=8_000)
        await btn.click()

        status_cell = page.locator(f"#row-{location_id} td:nth-child(3)")
        await poll_for_status(status_cell, ["COMPLETE", "ERROR"], timeout=60_000)

        final = (await status_cell.inner_text()).strip()
        if final == "COMPLETE":
            log.info("Location %s: COMPLETE", location_id)
            await log_job_result(pool, location_id, run_id, "complete")
            return True
        else:
            log.warning("Location %s: ERROR", location_id)
            await log_job_result(pool, location_id, run_id, "error", "Portal returned ERROR status")
            return False

    except PlaywrightTimeout as e:
        msg = f"Timeout on location {location_id}: {e}"
        log.error(msg)
        await log_job_result(pool, location_id, run_id, "timeout", msg)
        return False
    except Exception as e:
        msg = f"Unexpected error on location {location_id}: {e}"
        log.error(msg)
        await log_job_result(pool, location_id, run_id, "error", msg)
        return False

async def poll_for_status(locator, expected: list, timeout: int):
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < deadline:
        text = (await locator.inner_text()).strip()
        if text in expected:
            return text
        await asyncio.sleep(0.8)
    raise PlaywrightTimeout(f"Status never reached {expected} within {timeout}ms")

# Batch runner

async def run_batch(location_ids: list, concurrency: int = 5, headless: bool = True):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log.info("Run %s — %d locations, concurrency=%d", run_id, len(location_ids), concurrency)

    pool      = await get_db_pool()
    semaphore = asyncio.Semaphore(concurrency)
    results   = {"success": 0, "failure": 0}

    async with async_playwright() as playwright:
        workers = []
        for _ in range(min(concurrency, len(location_ids))):
            b, c, p = await create_authenticated_session(playwright, headless=headless)
            workers.append((b, c, p))

        worker_queue = asyncio.Queue()
        for w in workers:
            await worker_queue.put(w)

        async def process(loc_id):
            async with semaphore:
                b, c, page = await worker_queue.get()
                try:
                    ok = await refresh_location(page, pool, loc_id, run_id)
                    results["success" if ok else "failure"] += 1
                finally:
                    await worker_queue.put((b, c, page))

        await asyncio.gather(*[process(lid) for lid in location_ids])

        for b, c, p in workers:
            await c.close()
            await b.close()

    pool.close()
    await pool.wait_closed()
    log.info("Run %s complete — Success: %d, Failure: %d", run_id, results["success"], results["failure"])
    return results

# Entry

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reporting Portal Refresh Runner")
    parser.add_argument("--locations",   default="all", help="Comma-separated location IDs, or 'all'")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--headless",    action="store_true", default=True)
    args = parser.parse_args()

    location_list = (
        [str(i) for i in range(1, 21)]
        if args.locations == "all"
        else [s.strip() for s in args.locations.split(",")]
    )
    asyncio.run(run_batch(location_list, concurrency=args.concurrency, headless=args.headless))
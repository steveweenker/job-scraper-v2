import os
import json
import logging
import asyncio
from datetime import time as dtime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application
from bot import JobBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SITES_FILE = "sites.json"
SEEN_FILE = "seen_jobs.json"


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def scheduled_scan(job_bot: JobBot):
    if job_bot.is_scanning:
        logger.info("Scan already in progress, skipping scheduled run.")
        return

    job_bot.is_scanning = True
    logger.info("Starting scheduled scan...")

    try:
        new_jobs = job_bot.scraper.run_scan(job_bot.seen_ids)

        for job in new_jobs:
            text = job_bot.scraper.format_job(job)
            await job_bot.send_message(text)
            job_bot.seen_ids.add(job["id"])
            await asyncio.sleep(0.5)

        job_bot.save_seen()

        stats = job_bot.scraper.last_stats
        sources_checked = len([s for s in stats.get("sources", {}).values() if "total" in s])
        total = stats.get("total_fetched", 0)
        now_str = __import__("datetime").datetime.now().strftime("%d %b %Y, %I:%M %p")

        if new_jobs:
            summary = (
                f"✅ <b>Scan Complete</b> — {now_str}\n\n"
                f"🔍 Sources checked: {sources_checked}\n"
                f"📄 Total jobs found: {total}\n"
                f"🆕 New jobs sent: {len(new_jobs)}"
            )
        else:
            summary = (
                f"✅ <b>Scan Complete</b> — {now_str}\n\n"
                f"🔍 Sources checked: {sources_checked}\n"
                f"📄 Total jobs found: {total}\n"
                f"🆕 New jobs: 0\n\n"
                f"No new matching postings right now."
            )

        await job_bot.send_message(summary)
        logger.info(f"Scan complete. {len(new_jobs)} new jobs sent.")

    except Exception as e:
        logger.error(f"Scheduled scan error: {e}")
        await job_bot.send_message(f"❌ Scheduled scan error: {e}")
    finally:
        job_bot.is_scanning = False


def main():
    job_bot = JobBot()

    if not job_bot.token:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    if not job_bot.chat_id:
        logger.error("TELEGRAM_CHAT_ID not set!")
        return

    app = job_bot.build_app()

    async def post_init(application: Application):
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            scheduled_scan,
            CronTrigger(hour="9,21", minute=0),
            args=[job_bot],
            id="scheduled_scan",
            name="Job scan every 12 hours",
        )
        scheduler.start()
        logger.info("Scheduler started: scans at 09:00 and 21:00 daily.")

        await application.bot.send_message(
            chat_id=job_bot.chat_id,
            text="🚀 <b>Job Scraper Bot v2 is live!</b>\n\n"
                 "Scanning Workday, Adzuna, Jooble, and RemoteOK.\n"
                 "Scheduled: every 12h (09:00 & 21:00).\n\n"
                 "Type /help for commands.",
            parse_mode="HTML",
        )

    app.post_init = post_init
    logger.info("Starting bot polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

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
        sites = job_bot.sites_config.get("sites", [])
        total_sources = len(sites) + 6

        status_msg = await job_bot.send_message(
            f"🔍 <b>Auto-scan started</b> — Scanning {total_sources} sources...\n\n"
            f"⏳ Workday: {len(sites)} companies\n"
            f"⏳ Adzuna: {'Active' if job_bot.scraper.adzuna.available else 'No key'}\n"
            f"⏳ Jooble: {'Active' if job_bot.scraper.jooble.available else 'No key'}\n"
            f"⏳ RemoteOK: Active\n"
            f"⏳ LinkedIn: Active\n"
            f"⏳ Remotive: Active\n"
            f"⏳ Arbeitnow: Active"
        )

        all_jobs = []
        stats = {}

        # Workday
        try:
            workday_jobs = []
            for site in sites:
                site_jobs = job_bot.scraper.workday.scrape_site(site)
                workday_jobs.extend(site_jobs)
                stats[f"Workday ({site['name']})"] = {"total": len(site_jobs), "source": "Workday"}
            all_jobs.extend(workday_jobs)
        except Exception as e:
            logger.error(f"Workday error: {e}")

        # Adzuna
        try:
            adzuna_jobs = job_bot.scraper.adzuna.scrape()
            all_jobs.extend(adzuna_jobs)
            stats["Adzuna"] = {"total": len(adzuna_jobs), "source": "Adzuna"}
        except Exception as e:
            stats["Adzuna"] = {"error": str(e), "source": "Adzuna"}

        # Jooble
        try:
            jooble_jobs = job_bot.scraper.jooble.scrape()
            all_jobs.extend(jooble_jobs)
            stats["Jooble"] = {"total": len(jooble_jobs), "source": "Jooble"}
        except Exception as e:
            stats["Jooble"] = {"error": str(e), "source": "Jooble"}

        # RemoteOK
        try:
            remote_jobs = job_bot.scraper.remoteok.scrape()
            all_jobs.extend(remote_jobs)
            stats["RemoteOK"] = {"total": len(remote_jobs), "source": "RemoteOK"}
        except Exception as e:
            stats["RemoteOK"] = {"error": str(e), "source": "RemoteOK"}

        # LinkedIn
        try:
            linkedin_jobs = job_bot.scraper.linkedin.scrape()
            all_jobs.extend(linkedin_jobs)
            stats["LinkedIn"] = {"total": len(linkedin_jobs), "source": "LinkedIn"}
        except Exception as e:
            stats["LinkedIn"] = {"error": str(e), "source": "LinkedIn"}

        # Remotive
        try:
            remotive_jobs = job_bot.scraper.remotive.scrape()
            all_jobs.extend(remotive_jobs)
            stats["Remotive"] = {"total": len(remotive_jobs), "source": "Remotive"}
        except Exception as e:
            stats["Remotive"] = {"error": str(e), "source": "Remotive"}

        # Arbeitnow
        try:
            arbeitnow_jobs = job_bot.scraper.arbeitnow.scrape()
            all_jobs.extend(arbeitnow_jobs)
            stats["Arbeitnow"] = {"total": len(arbeitnow_jobs), "source": "Arbeitnow"}
        except Exception as e:
            stats["Arbeitnow"] = {"error": str(e), "source": "Arbeitnow"}

        filtered = job_bot.scraper.filter_jobs(all_jobs)
        new_jobs = [j for j in filtered if j["id"] not in job_bot.seen_ids]

        job_bot.scraper.last_run = __import__("datetime").datetime.now().isoformat()
        job_bot.scraper.last_stats = {
            "total_fetched": len(all_jobs),
            "matching": len(filtered),
            "new_jobs": len(new_jobs),
            "sources": stats,
        }

        for job in new_jobs:
            text = job_bot.scraper.format_job(job)
            await job_bot.send_message(text)
            job_bot.seen_ids.add(job["id"])
            await asyncio.sleep(0.5)

        job_bot.save_seen()

        now_str = __import__("datetime").datetime.now().strftime("%d %b %Y, %I:%M %p")
        if new_jobs:
            summary = (
                f"✅ <b>Auto-scan Complete</b> — {now_str}\n\n"
                f"📄 Total fetched: {len(all_jobs)}\n"
                f"🎯 Matching India SE/Fresher: {len(filtered)}\n"
                f"🆕 New jobs sent: {len(new_jobs)}\n\n"
                f"📋 <b>Source Breakdown:</b>\n"
            )
        else:
            summary = (
                f"✅ <b>Auto-scan Complete</b> — {now_str}\n\n"
                f"📄 Total fetched: {len(all_jobs)}\n"
                f"🎯 Matching India SE/Fresher: {len(filtered)}\n"
                f"🆕 New jobs: 0\n\n"
                f"No new matching postings right now.\n\n"
                f"📋 <b>Source Breakdown:</b>\n"
            )

        for name, detail in stats.items():
            if "error" in detail:
                summary += f"  ❌ {name}: error\n"
            else:
                summary += f"  ✅ {name}: {detail.get('total', 0)} jobs\n"

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
        job_bot.bot = application.bot
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
                 "Scanning 7 sources: Workday, Adzuna, Jooble, RemoteOK, LinkedIn, Remotive, Arbeitnow.\n"
                 "Scheduled: every 12h (09:00 & 21:00).\n\n"
                 "Type /help for commands.",
            parse_mode="HTML",
        )

    app.post_init = post_init
    logger.info("Starting bot polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

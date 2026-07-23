import os
import json
import logging
import asyncio
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from scraper import JobScraper

logger = logging.getLogger(__name__)

SEEN_FILE = "seen_jobs.json"
SITES_FILE = "sites.json"


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class JobBot:
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.env = {
            "ADZUNA_APP_ID": os.environ.get("ADZUNA_APP_ID", ""),
            "ADZUNA_APP_KEY": os.environ.get("ADZUNA_APP_KEY", ""),
            "JOOBLE_API_KEY": os.environ.get("JOOBLE_API_KEY", ""),
        }
        self.sites_config = load_json(SITES_FILE, {"sites": [], "search_queries": ["Software Engineer"]})
        self.seen_data = load_json(SEEN_FILE, {"sent_ids": []})
        self.seen_ids = set(self.seen_data.get("sent_ids", []))
        self.scraper = JobScraper(self.sites_config, self.env)
        self.is_scanning = False
        self.bot = None

    def save_seen(self):
        self.seen_data["sent_ids"] = list(self.seen_ids)
        save_json(SEEN_FILE, self.seen_data)

    async def send_message(self, text, parse_mode="HTML"):
        if not self.bot:
            self.bot = Bot(token=self.token)
        await self.bot.send_message(
            chat_id=self.chat_id, text=text, parse_mode=parse_mode,
            disable_web_page_preview=True,
        )

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Job Scraper Bot v2</b>\n\n"
            "Scans 7 sources for entry-level IT fresher jobs in India:\n"
            "Workday, Adzuna, Jooble, RemoteOK, LinkedIn, Remotive, Arbeitnow\n\n"
            "Roles: SDE, Full Stack, AI/ML, Java, Python, DevOps, Data, QA & more\n"
            "Experience: 0-3 years (fresher friendly)\n\n"
            "Type /help to see all commands.",
            parse_mode="HTML",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 <b>Available Commands</b>\n\n"
            "/check - Force scan now (with live progress)\n"
            "/sources - Show active job sources\n"
            "/sites - List Workday companies\n"
            "/addsite &lt;name&gt; &lt;slug&gt; &lt;sub&gt; &lt;path&gt; - Add company\n"
            "/rmsite &lt;name&gt; - Remove company\n"
            "/status - Last run info\n"
            "/seen - Recently sent jobs\n"
            "/help - This message",
            parse_mode="HTML",
        )

    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.is_scanning:
            await update.message.reply_text("⏳ Scan already in progress...")
            return

        self.is_scanning = True
        status_msg = await update.message.reply_text("🔍 <b>Starting scan...</b>")
        self.bot = context.bot

        try:
            sites = self.sites_config.get("sites", [])
            total_sources = len(sites) + 6

            all_jobs = []
            stats = {}

            await status_msg.edit_text(
                f"🔍 <b>Scanning {total_sources} sources...</b>\n\n"
                f"🔄 Workday: {len(sites)} companies...\n"
                f"⏳ Adzuna\n⏳ Jooble\n⏳ RemoteOK\n⏳ LinkedIn\n⏳ Remotive\n⏳ Arbeitnow"
            )

            workday_jobs = []
            for site in sites:
                try:
                    site_jobs = self.scraper.workday.scrape_site(site)
                    workday_jobs.extend(site_jobs)
                    stats[f"Workday ({site['name']})"] = {"total": len(site_jobs), "source": "Workday"}
                except Exception as e:
                    stats[f"Workday ({site['name']})"] = {"error": str(e), "source": "Workday"}
            all_jobs.extend(workday_jobs)

            await status_msg.edit_text(
                f"🔍 <b>Scanning {total_sources} sources...</b>\n\n"
                f"✅ Workday: <b>{len(workday_jobs)}</b> jobs\n"
                f"🔄 Adzuna...\n⏳ Jooble\n⏳ RemoteOK\n⏳ LinkedIn\n⏳ Remotive\n⏳ Arbeitnow"
            )

            try:
                adzuna_jobs = self.scraper.adzuna.scrape()
                all_jobs.extend(adzuna_jobs)
                stats["Adzuna"] = {"total": len(adzuna_jobs), "source": "Adzuna"}
            except Exception as e:
                stats["Adzuna"] = {"error": str(e), "source": "Adzuna"}
                adzuna_jobs = []

            await status_msg.edit_text(
                f"🔍 <b>Scanning {total_sources} sources...</b>\n\n"
                f"✅ Workday: <b>{len(workday_jobs)}</b> jobs\n"
                f"✅ Adzuna: <b>{len(adzuna_jobs)}</b> jobs\n"
                f"🔄 Jooble...\n⏳ RemoteOK\n⏳ LinkedIn\n⏳ Remotive\n⏳ Arbeitnow"
            )

            try:
                jooble_jobs = self.scraper.jooble.scrape()
                all_jobs.extend(jooble_jobs)
                stats["Jooble"] = {"total": len(jooble_jobs), "source": "Jooble"}
            except Exception as e:
                stats["Jooble"] = {"error": str(e), "source": "Jooble"}
                jooble_jobs = []

            await status_msg.edit_text(
                f"🔍 <b>Scanning {total_sources} sources...</b>\n\n"
                f"✅ Workday: <b>{len(workday_jobs)}</b> jobs\n"
                f"✅ Adzuna: <b>{len(adzuna_jobs)}</b> jobs\n"
                f"✅ Jooble: <b>{len(jooble_jobs)}</b> jobs\n"
                f"🔄 RemoteOK...\n⏳ LinkedIn\n⏳ Remotive\n⏳ Arbeitnow"
            )

            try:
                remote_jobs = self.scraper.remoteok.scrape()
                all_jobs.extend(remote_jobs)
                stats["RemoteOK"] = {"total": len(remote_jobs), "source": "RemoteOK"}
            except Exception as e:
                stats["RemoteOK"] = {"error": str(e), "source": "RemoteOK"}
                remote_jobs = []

            await status_msg.edit_text(
                f"🔍 <b>Scanning {total_sources} sources...</b>\n\n"
                f"✅ Workday: <b>{len(workday_jobs)}</b> jobs\n"
                f"✅ Adzuna: <b>{len(adzuna_jobs)}</b> jobs\n"
                f"✅ Jooble: <b>{len(jooble_jobs)}</b> jobs\n"
                f"✅ RemoteOK: <b>{len(remote_jobs)}</b> jobs\n"
                f"🔄 LinkedIn...\n⏳ Remotive\n⏳ Arbeitnow"
            )

            try:
                linkedin_jobs = self.scraper.linkedin.scrape()
                all_jobs.extend(linkedin_jobs)
                stats["LinkedIn"] = {"total": len(linkedin_jobs), "source": "LinkedIn"}
            except Exception as e:
                stats["LinkedIn"] = {"error": str(e), "source": "LinkedIn"}
                linkedin_jobs = []

            await status_msg.edit_text(
                f"🔍 <b>Scanning {total_sources} sources...</b>\n\n"
                f"✅ Workday: <b>{len(workday_jobs)}</b> jobs\n"
                f"✅ Adzuna: <b>{len(adzuna_jobs)}</b> jobs\n"
                f"✅ Jooble: <b>{len(jooble_jobs)}</b> jobs\n"
                f"✅ RemoteOK: <b>{len(remote_jobs)}</b> jobs\n"
                f"✅ LinkedIn: <b>{len(linkedin_jobs)}</b> jobs\n"
                f"🔄 Remotive...\n⏳ Arbeitnow"
            )

            try:
                remotive_jobs = self.scraper.remotive.scrape()
                all_jobs.extend(remotive_jobs)
                stats["Remotive"] = {"total": len(remotive_jobs), "source": "Remotive"}
            except Exception as e:
                stats["Remotive"] = {"error": str(e), "source": "Remotive"}
                remotive_jobs = []

            await status_msg.edit_text(
                f"🔍 <b>Scanning {total_sources} sources...</b>\n\n"
                f"✅ Workday: <b>{len(workday_jobs)}</b> jobs\n"
                f"✅ Adzuna: <b>{len(adzuna_jobs)}</b> jobs\n"
                f"✅ Jooble: <b>{len(jooble_jobs)}</b> jobs\n"
                f"✅ RemoteOK: <b>{len(remote_jobs)}</b> jobs\n"
                f"✅ LinkedIn: <b>{len(linkedin_jobs)}</b> jobs\n"
                f"✅ Remotive: <b>{len(remotive_jobs)}</b> jobs\n"
                f"🔄 Arbeitnow..."
            )

            try:
                arbeitnow_jobs = self.scraper.arbeitnow.scrape()
                all_jobs.extend(arbeitnow_jobs)
                stats["Arbeitnow"] = {"total": len(arbeitnow_jobs), "source": "Arbeitnow"}
            except Exception as e:
                stats["Arbeitnow"] = {"error": str(e), "source": "Arbeitnow"}
                arbeitnow_jobs = []

            await status_msg.edit_text(
                f"🔍 <b>All sources scanned! Filtering for India IT fresher roles...</b>\n\n"
                f"📄 Total raw: <b>{len(all_jobs)}</b>"
            )

            filtered = self.scraper.filter_jobs(all_jobs)
            new_jobs = [j for j in filtered if j["id"] not in self.seen_ids]

            self.scraper.last_run = datetime.now().isoformat()
            self.scraper.last_stats = {
                "total_fetched": len(all_jobs),
                "matching": len(filtered),
                "new_jobs": len(new_jobs),
                "sources": stats,
            }

            for job in new_jobs:
                text = self.scraper.format_job(job)
                await self.send_message(text)
                self.seen_ids.add(job["id"])
                await asyncio.sleep(0.5)

            self.save_seen()

            now = datetime.now().strftime("%d %b %Y, %I:%M %p")
            if new_jobs:
                summary = (
                    f"✅ <b>Scan Complete</b> — {now}\n\n"
                    f"📄 Total fetched: {len(all_jobs)}\n"
                    f"🎯 Matching India IT Fresher: {len(filtered)}\n"
                    f"🆕 New jobs sent: {len(new_jobs)}\n\n"
                    f"📋 <b>Source Breakdown:</b>\n"
                )
            else:
                summary = (
                    f"✅ <b>Scan Complete</b> — {now}\n\n"
                    f"📄 Total fetched: {len(all_jobs)}\n"
                    f"🎯 Matching India IT Fresher: {len(filtered)}\n"
                    f"🆕 New jobs: 0\n\n"
                    f"No new matching postings right now.\n\n"
                    f"📋 <b>Source Breakdown:</b>\n"
                )

            for name, detail in stats.items():
                if "error" in detail:
                    summary += f"  ❌ {name}: error\n"
                else:
                    summary += f"  ✅ {name}: {detail.get('total', 0)} jobs\n"

            await status_msg.edit_text(summary)

        except Exception as e:
            logger.error(f"Scan error: {e}")
            await status_msg.edit_text(f"❌ Error during scan: {e}")
        finally:
            self.is_scanning = False

    async def cmd_sources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sources = self.scraper.get_sources_status()
        lines = ["📡 <b>Job Sources (7 total)</b>\n"]
        for name, status in sources.items():
            icon = "✅" if "Active" in status or "configured" in status else "⚠️"
            lines.append(f"{icon} <b>{name}</b> — {status}")
        lines.append("\n💡 Adzuna & Jooble need API keys for more results.")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_sites(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sites = self.sites_config.get("sites", [])
        if not sites:
            await update.message.reply_text("No Workday sites configured.")
            return
        lines = [f"🏢 <b>Workday Companies ({len(sites)})</b>\n"]
        for i, s in enumerate(sites, 1):
            url = f"https://{s['slug']}.{s['subdomain']}.myworkdayjobs.com/en-US/{s['site_path']}"
            lines.append(f"{i}. <b>{s['name']}</b>\n   {url}\n")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_addsite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if len(args) < 4:
            await update.message.reply_text(
                "Usage: /addsite &lt;name&gt; &lt;slug&gt; &lt;subdomain&gt; &lt;site_path&gt;\n\n"
                "Example: /addsite Cisco cisco wd1 External",
                parse_mode="HTML",
            )
            return
        name, slug, subdomain, site_path = args[0], args[1], args[2], args[3]
        career_url = args[4] if len(args) > 4 else f"https://{slug}.{subdomain}.myworkdayjobs.com"
        new_site = {"name": name, "slug": slug, "subdomain": subdomain, "site_path": site_path, "career_url": career_url}
        self.sites_config["sites"].append(new_site)
        save_json(SITES_FILE, self.sites_config)
        await update.message.reply_text(
            f"✅ Added <b>{name}</b>\nhttps://{slug}.{subdomain}.myworkdayjobs.com/en-US/{site_path}",
            parse_mode="HTML",
        )

    async def cmd_rmsite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /rmsite &lt;company_name&gt;")
            return
        name = " ".join(args)
        for i, s in enumerate(self.sites_config.get("sites", [])):
            if s["name"].lower() == name.lower():
                removed = self.sites_config["sites"].pop(i)
                save_json(SITES_FILE, self.sites_config)
                await update.message.reply_text(f"✅ Removed <b>{removed['name']}</b>", parse_mode="HTML")
                return
        await update.message.reply_text(f"❌ Company '{name}' not found. Use /sites to see all.")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats = self.scraper.last_stats
        if not stats:
            await update.message.reply_text("No scans yet. Use /check to start.")
            return
        lines = [
            "📊 <b>Last Scan Status</b>\n",
            f"🕐 Last run: {self.scraper.last_run or 'Never'}",
            f"📄 Total fetched: {stats.get('total_fetched', 0)}",
            f"🎯 Matching India IT Fresher: {stats.get('matching', 0)}",
            f"🆕 New jobs sent: {stats.get('new_jobs', 0)}",
            f"📨 All-time sent: {len(self.seen_ids)}",
            "",
            "<b>Per-source breakdown:</b>",
        ]
        for name, detail in stats.get("sources", {}).items():
            if "error" in detail:
                lines.append(f"  ❌ {name}: {detail['error']}")
            else:
                lines.append(f"  ✅ {name}: {detail.get('total', 0)} jobs")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_seen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.seen_ids:
            await update.message.reply_text("No jobs sent yet.")
            return
        lines = ["📨 <b>Recently Sent Jobs</b>\n"]
        for jid in list(self.seen_ids)[-20:]:
            parts = jid.split("|")
            source = parts[0] if len(parts) > 0 else "?"
            job_name = parts[-1].split("/")[-1].replace("_", " ") if "/" in parts[-1] else parts[-1]
            lines.append(f"• [{source}] {job_name}")
        if len(self.seen_ids) > 20:
            lines.append(f"\n... and {len(self.seen_ids) - 20} more")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Type /help to see available commands.")

    def build_app(self):
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("check", self.cmd_check))
        app.add_handler(CommandHandler("sources", self.cmd_sources))
        app.add_handler(CommandHandler("sites", self.cmd_sites))
        app.add_handler(CommandHandler("addsite", self.cmd_addsite))
        app.add_handler(CommandHandler("rmsite", self.cmd_rmsite))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("seen", self.cmd_seen))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        return app

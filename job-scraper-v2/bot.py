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

    def save_seen(self):
        self.seen_data["sent_ids"] = list(self.seen_ids)
        save_json(SEEN_FILE, self.seen_data)

    async def send_message(self, text, parse_mode="HTML"):
        from telegram import Bot
        bot = Bot(token=self.token)
        await bot.send_message(
            chat_id=self.chat_id, text=text, parse_mode=parse_mode,
            disable_web_page_preview=True,
        )

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Job Scraper Bot v2</b>\n\n"
            "Scans Workday, Adzuna, Jooble, and RemoteOK for "
            "entry-level Software Engineer roles in India.\n\n"
            "Type /help to see all commands.",
            parse_mode="HTML",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 <b>Available Commands</b>\n\n"
            "/check - Force scan now\n"
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
        msg = await update.message.reply_text("🔍 Scanning all job sources...")

        try:
            new_jobs = self.scraper.run_scan(self.seen_ids)

            for job in new_jobs:
                text = self.scraper.format_job(job)
                await self.send_message(text)
                self.seen_ids.add(job["id"])
                await asyncio.sleep(0.5)

            self.save_seen()

            stats = self.scraper.last_stats
            sources_checked = len([s for s in stats.get("sources", {}).values() if "total" in s])
            total = stats.get("total_fetched", 0)
            now = datetime.now().strftime("%d %b %Y, %I:%M %p")

            if new_jobs:
                summary = (
                    f"✅ <b>Scan Complete</b> — {now}\n\n"
                    f"🔍 Sources checked: {sources_checked}\n"
                    f"📄 Total jobs found: {total}\n"
                    f"🆕 New jobs sent: {len(new_jobs)}"
                )
            else:
                summary = (
                    f"✅ <b>Scan Complete</b> — {now}\n\n"
                    f"🔍 Sources checked: {sources_checked}\n"
                    f"📄 Total jobs found: {total}\n"
                    f"🆕 New jobs: 0\n\n"
                    f"No new matching postings right now."
                )

            await msg.edit_text(summary)
        except Exception as e:
            logger.error(f"Scan error: {e}")
            await msg.edit_text(f"❌ Error during scan: {e}")
        finally:
            self.is_scanning = False

    async def cmd_sources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sources = self.scraper.get_sources_status()
        lines = ["📡 <b>Job Sources</b>\n"]
        for name, status in sources.items():
            icon = "✅" if "Active" in status or "configured" in status else "⚠️"
            lines.append(f"{icon} <b>{name}</b> — {status}")
        lines.append("\n💡 Add API keys in Railway env vars to activate more sources.")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_sites(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sites = self.sites_config.get("sites", [])
        if not sites:
            await update.message.reply_text("No Workday sites configured.")
            return
        lines = ["🏢 <b>Workday Companies</b>\n"]
        for i, s in enumerate(sites, 1):
            url = f"https://{s['slug']}.{s['subdomain']}.myworkdayjobs.com/en-US/{s['site_path']}"
            lines.append(f"{i}. <b>{s['name']}</b>\n   {url}\n")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_addsite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args
        if len(args) < 4:
            await update.message.reply_text(
                "Usage: /addsite &lt;name&gt; &lt;slug&gt; &lt;subdomain&gt; &lt;site_path&gt;\n\n"
                "Example: /addsite Cisco cisco wd1 cisco",
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
            f"🎯 Matching India SE: {stats.get('matching', 0)}",
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

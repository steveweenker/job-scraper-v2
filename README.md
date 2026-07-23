# Job Scraper Bot v2

Telegram bot that scans multiple job sources for entry-level Software Engineer roles in India.

## Sources

| Source | API Key Required | Free Tier |
|--------|-----------------|-----------|
| **Workday** | No | Unlimited |
| **Adzuna** | Yes | 500-1000 calls/month |
| **Jooble** | Yes | Unlimited |
| **RemoteOK** | No | Unlimited |

## Quick Start

### 1. Get API Keys (Optional)

**Adzuna** (recommended):
1. Go to https://developer.adzuna.com
2. Register for free
3. Copy your `app_id` and `app_key`

**Jooble** (recommended):
1. Go to https://jooble.org/api
2. Request a free API key

### 2. Deploy to Railway

1. Push this repo to GitHub
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Set environment variables:

```
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
ADZUNA_APP_ID=your-adzuna-app-id
ADZUNA_APP_KEY=your-adzuna-app-key
JOOBLE_API_KEY=your-jooble-key
```

4. Railway will auto-deploy

### 3. Start the Bot

Send `/start` to your bot in Telegram.

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List all commands |
| `/check` | Force scan now |
| `/sources` | Show active sources |
| `/sites` | List Workday companies |
| `/addsite` | Add a Workday company |
| `/rmsite` | Remove a Workday company |
| `/status` | Last scan stats |
| `/seen` | Recently sent jobs |

## How It Works

- Runs every 12 hours (09:00 and 21:00 IST)
- Scans all configured sources
- Filters for India-based entry-level SE roles
- Sends new jobs to your Telegram
- Sends summary message even when 0 new jobs

## Adding Workday Companies

```
/addsite CompanyName slug subdomain site_path
```

Example:
```
/addsite Cisco cisco wd1 cisco
```

## Files

- `main.py` — Entry point with scheduler
- `bot.py` — Telegram bot commands
- `scraper.py` — Job scrapers for all sources
- `sites.json` — Workday company configs
- `seen_jobs.json` — Tracks sent jobs (auto-created)

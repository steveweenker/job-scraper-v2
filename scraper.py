import json
import os
import re
import time
import logging
import urllib.request
import urllib.parse
import ssl
from datetime import datetime

logger = logging.getLogger(__name__)

INDIA_LOCATIONS = [
    "india", "pune", "bangalore", "bengaluru", "gurugram", "gurgaon",
    "vadodara", "hyderabad", "noida", "chennai", "mumbai", "delhi",
    "nagpur", "coimbatore", "kochi", "jaipur", "ahmedabad", "lucknow",
    "indore", "bhopal", "mysore", "mangalore", "visakhapatnam",
    "vijayawada", "tiruchirappalli", "madurai", "thiruvananthapuram", "kolkata",
    "remote", "anywhere", "work from home", "india remote",
]

TITLE_ALLOW = [
    r"software\s+engineer",
    r"software\s+developer",
    r"\bsde\b",
    r"developer\s+associate",
    r"graduate\s+software",
    r"trainee\s+software",
    r"junior\s+software",
    r"fresher\s+software",
    r"software\s+trainee",
    r"software\s+analyst",
    r"systems?\s+engineer",
    r"technical\s+analyst",
    r"programmer\s+analyst",
    r"application\s+developer",
    r"full[\s-]?stack",
    r"back[\s-]?end",
    r"front[\s-]?end",
    r"java\s+developer",
    r"python\s+developer",
    r"cloud\s+engineer",
    r"devops\s+engineer",
    r"data\s+engineer",
    r"ml\s+engineer",
    r"machine\s+learning",
    r"backend\s+developer",
    r"frontend\s+developer",
    r"mobile\s+developer",
    r"ios\s+developer",
    r"android\s+developer",
    r"qa\s+engineer",
    r"test\s+engineer",
    r"automation\s+engineer",
    r"platform\s+engineer",
    r"infrastructure",
    r"release\s+engineer",
    r"build\s+engineer",
    r"site\s+reliability",
    r"\bsre\b",
    r"technical\s+support\s+engineer",
]

TITLE_EXCLUDE = [
    r"\bsenior\b", r"\bsr[\.\s]", r"\blead\b", r"\bprincipal\b",
    r"\bstaff\b", r"\barchitect\b", r"\bmanager\b", r"\bdirector\b",
    r"\bvice\s+president\b", r"\bvp\b", r"\bhead\b",
    r"\bII\b", r"\bIII\b", r"\bIV\b", r"\bV\b",
    r"[\s\-]2\b", r"[\s\-]3\b", r"[\s\-]4\b", r"[\s\-]5\b",
    r"\bintern\b", r"\binternship\b", r"\bcontract\b",
    r"\bconsultant\b", r"\badvisory\b",
]

WORKDAY_QUERIES = [
    "Software Engineer", "Associate Software Engineer", "Software Developer",
    "SDE", "Systems Engineer", "Java Developer", "Python Developer",
    "Cloud Engineer", "DevOps Engineer", "Data Engineer",
    "Full Stack Developer", "Backend Developer", "Frontend Developer",
    "Fresher", "Graduate Engineer", "Trainee",
]


class WorkdayScraper:
    def __init__(self, sites):
        self.sites = sites
        self.ctx = ssl.create_default_context()

    def fetch_jobs(self, api_url, offset=0, limit=20, search_text="Software Engineer"):
        payload = json.dumps({
            "appliedFacets": {}, "limit": limit, "offset": offset, "searchText": search_text
        }).encode("utf-8")
        req = urllib.request.Request(api_url, data=payload, headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        }, method="POST")
        with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def scrape_site(self, site, progress_callback=None):
        api_url = f"https://{site['slug']}.{site['subdomain']}.myworkdayjobs.com/wday/cxs/{site['slug']}/{site['site_path']}/jobs"
        api_base = f"https://{site['slug']}.{site['subdomain']}.myworkdayjobs.com/en-US/{site['site_path']}"

        all_jobs = []
        seen_ids = set()

        for query in WORKDAY_QUERIES:
            offset = 0
            no_new_streak = 0
            while no_new_streak < 2:
                try:
                    data = self.fetch_jobs(api_url, offset=offset, limit=20, search_text=query)
                    jobs = data.get("jobPostings", [])
                    if not jobs:
                        break
                    new_count = 0
                    for j in jobs:
                        jid = j.get("externalPath", j.get("title", ""))
                        if jid not in seen_ids:
                            seen_ids.add(jid)
                            all_jobs.append({
                                "id": f"workday|{site['name']}|{jid}",
                                "title": j.get("title", ""),
                                "company": site["name"],
                                "location": j.get("locationsText", "N/A"),
                                "posted": j.get("postedOn", "N/A"),
                                "url": api_base + jid if jid else "",
                                "source": "Workday",
                            })
                            new_count += 1
                    no_new_streak = no_new_streak + 1 if new_count == 0 else 0
                    offset += 20
                    time.sleep(0.2)
                except Exception as e:
                    logger.error(f"Workday {site['name']} error: {e}")
                    break
            time.sleep(0.3)

        return all_jobs


class AdzunaScraper:
    def __init__(self, app_id, app_key):
        self.app_id = app_id
        self.app_key = app_key
        self.ctx = ssl.create_default_context()
        self.available = bool(app_id and app_key)

    def scrape(self):
        if not self.available:
            return []
        jobs = []
        queries = [
            "software engineer fresher", "software developer junior",
            "SDE fresher", "full stack developer", "java developer",
            "python developer", "cloud engineer", "data engineer",
            "backend developer", "frontend developer",
        ]
        for q in queries:
            try:
                url = f"https://api.adzuna.com/v1/api/jobs/in/search/1?app_id={self.app_id}&app_key={self.app_key}&q={urllib.parse.quote(q)}&results_per_page=50&what=software+engineer&where=india&max_days_old=14"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, context=self.ctx, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for j in data.get("results", []):
                    loc = j.get("location", {}).get("display_name", "")
                    title = j.get("title", "")
                    desc = j.get("description", "")
                    company = j.get("company", {}).get("display_name", "Unknown")
                    jobs.append({
                        "id": f"adzuna|{j.get('id', '')}",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "posted": j.get("created", ""),
                        "url": j.get("redirect_url", ""),
                        "source": "Adzuna",
                        "description": desc[:200] if desc else "",
                    })
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Adzuna error: {e}")
        return jobs


class JoobleScraper:
    def __init__(self, api_key):
        self.api_key = api_key
        self.ctx = ssl.create_default_context()
        self.available = bool(api_key)

    def scrape(self):
        if not self.available:
            return []
        jobs = []
        queries = [
            "software engineer fresher India", "software developer junior India",
            "SDE entry level India", "full stack developer India",
            "java developer India", "python developer India",
            "cloud engineer India", "data engineer India",
            "backend developer India", "frontend developer India",
            "freshers software engineer India", "trainee software India",
        ]
        for q in queries:
            try:
                url = f"https://jooble.org/api/"
                payload = json.dumps({"keywords": q, "page": 1, "count": 50}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": self.api_key,
                    "User-Agent": "Mozilla/5.0"
                }, method="POST")
                with urllib.request.urlopen(req, context=self.ctx, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for j in data.get("jobs", []):
                    loc = j.get("location", "")
                    title = j.get("title", "")
                    company = j.get("company", "Unknown")
                    jobs.append({
                        "id": f"jooble|{j.get('id', '')}",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "posted": j.get("date", ""),
                        "url": j.get("link", ""),
                        "source": "Jooble",
                        "description": j.get("snippet", "")[:200],
                    })
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Jooble error: {e}")
        return jobs


class RemoteOKScraper:
    def __init__(self):
        self.ctx = ssl.create_default_context()

    def scrape(self):
        jobs = []
        tags_to_search = [
            "software-engineer", "developer", "python", "java",
            "javascript", "full-stack", "backend", "frontend",
            "devops", "data-engineer", "cloud", "sre",
            "mobile", "react", "node", "golang", "rust",
        ]
        try:
            url = "https://remoteok.com/api"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=self.ctx, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for j in data:
                if not isinstance(j, dict) or "id" not in j:
                    continue
                title = j.get("position", "")
                company = j.get("company", "Unknown")
                location = j.get("location", "Remote")
                tags = " ".join(j.get("tags", []))
                jobs.append({
                    "id": f"remoteok|{j.get('id', '')}",
                    "title": title,
                    "company": company,
                    "location": location,
                    "posted": j.get("date", ""),
                    "url": f"https://remoteok.com/remote-jobs/{j.get('id', '')}",
                    "source": "RemoteOK",
                    "description": tags[:200],
                })
        except Exception as e:
            logger.error(f"RemoteOK error: {e}")
        return jobs


class LinkedInScraper:
    def __init__(self):
        self.ctx = ssl.create_default_context()

    def scrape(self):
        jobs = []
        queries = [
            "software engineer fresher india",
            "software developer entry level india",
            "SDE junior india",
            "full stack developer india",
            "java developer fresher india",
            "python developer india",
        ]
        try:
            for q in queries:
                encoded = urllib.parse.quote(q)
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded}&location=India&f_TPR=r604800&start=0"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                })
                with urllib.request.urlopen(req, context=self.ctx, timeout=15) as resp:
                    html = resp.read().decode("utf-8")
                import re as re_mod
                cards = re_mod.findall(r'<li class=".*?".*?</li>', html, re_mod.DOTALL)
                for card in cards[:25]:
                    title_m = re_mod.search(r'class="base-search-card__title"[^>]*>(.*?)</h3>', card, re_mod.DOTALL)
                    company_m = re_mod.search(r'class="base-search-card__subtitle"[^>]*>.*?>(.*?)</a>', card, re_mod.DOTALL)
                    link_m = re_mod.search(r'href="(https://www\.linkedin\.com/jobs/view/[^"]+)"', card)
                    loc_m = re_mod.search(r'class="job-search-card__location"[^>]*>(.*?)</span>', card, re_mod.DOTALL)
                    title = title_m.group(1).strip() if title_m else ""
                    company = company_m.group(1).strip() if company_m else "Unknown"
                    link = link_m.group(1) if link_m else ""
                    loc = loc_m.group(1).strip() if loc_m else ""
                    if title:
                        jobs.append({
                            "id": f"linkedin|{link.split('view/')[-1].split('?')[0] if 'view/' in link else title}",
                            "title": title,
                            "company": company,
                            "location": loc,
                            "posted": "Recent",
                            "url": link,
                            "source": "LinkedIn",
                            "description": "",
                        })
                time.sleep(1)
        except Exception as e:
            logger.error(f"LinkedIn error: {e}")
        return jobs


class JobScraper:
    def __init__(self, sites_config, env):
        self.sites = sites_config.get("sites", [])
        self.title_allow = sites_config.get("title_allow", TITLE_ALLOW)
        self.title_exclude = sites_config.get("title_exclude", TITLE_EXCLUDE)
        self.india_locations = sites_config.get("india_locations", INDIA_LOCATIONS)

        self.workday = WorkdayScraper(self.sites)
        self.adzuna = AdzunaScraper(env.get("ADZUNA_APP_ID", ""), env.get("ADZUNA_APP_KEY", ""))
        self.jooble = JoobleScraper(env.get("JOOBLE_API_KEY", ""))
        self.remoteok = RemoteOKScraper()
        self.linkedin = LinkedInScraper()

        self.last_run = None
        self.last_stats = {}

    def is_india_job(self, job):
        loc = (job.get("location", "") or "").lower()
        return any(ind in loc for ind in self.india_locations)

    def matches_title(self, title):
        for pat in self.title_exclude:
            if re.search(pat, title, re.IGNORECASE):
                return False
        for pat in self.title_allow:
            if re.search(pat, title, re.IGNORECASE):
                return True
        return False

    def filter_jobs(self, jobs):
        seen = set()
        result = []
        for job in jobs:
            if job["id"] in seen:
                continue
            seen.add(job["id"])

            if not self.is_india_job(job):
                continue
            if not self.matches_title(job.get("title", "")):
                continue

            result.append(job)
        return result

    def get_sources_status(self):
        return {
            "Workday": f"{len(self.sites)} companies configured",
            "Adzuna": "Active" if self.adzuna.available else "No API key",
            "Jooble": "Active" if self.jooble.available else "No API key",
            "RemoteOK": "Active",
            "LinkedIn": "Active (public)",
        }

    def run_scan(self, sent_ids=None, progress_callback=None):
        if sent_ids is None:
            sent_ids = set()

        all_jobs = []
        stats = {}

        async def notify(msg):
            if progress_callback:
                await progress_callback(msg)

        import asyncio

        # Workday
        workday_jobs = []
        for i, site in enumerate(self.sites):
            try:
                site_jobs = self.workday.scrape_site(site)
                workday_jobs.extend(site_jobs)
                stats[f"Workday ({site['name']})"] = {"total": len(site_jobs), "source": "Workday"}
                logger.info(f"Workday {site['name']}: {len(site_jobs)} jobs")
            except Exception as e:
                stats[f"Workday ({site['name']})"] = {"error": str(e), "source": "Workday"}
        all_jobs.extend(workday_jobs)

        # Adzuna
        try:
            adzuna_jobs = self.adzuna.scrape()
            all_jobs.extend(adzuna_jobs)
            stats["Adzuna"] = {"total": len(adzuna_jobs), "source": "Adzuna"}
            logger.info(f"Adzuna: {len(adzuna_jobs)} jobs")
        except Exception as e:
            stats["Adzuna"] = {"error": str(e), "source": "Adzuna"}

        # Jooble
        try:
            jooble_jobs = self.jooble.scrape()
            all_jobs.extend(jooble_jobs)
            stats["Jooble"] = {"total": len(jooble_jobs), "source": "Jooble"}
            logger.info(f"Jooble: {len(jooble_jobs)} jobs")
        except Exception as e:
            stats["Jooble"] = {"error": str(e), "source": "Jooble"}

        # RemoteOK
        try:
            remote_jobs = self.remoteok.scrape()
            all_jobs.extend(remote_jobs)
            stats["RemoteOK"] = {"total": len(remote_jobs), "source": "RemoteOK"}
            logger.info(f"RemoteOK: {len(remote_jobs)} jobs")
        except Exception as e:
            stats["RemoteOK"] = {"error": str(e), "source": "RemoteOK"}

        # LinkedIn
        try:
            linkedin_jobs = self.linkedin.scrape()
            all_jobs.extend(linkedin_jobs)
            stats["LinkedIn"] = {"total": len(linkedin_jobs), "source": "LinkedIn"}
            logger.info(f"LinkedIn: {len(linkedin_jobs)} jobs")
        except Exception as e:
            stats["LinkedIn"] = {"error": str(e), "source": "LinkedIn"}

        filtered = self.filter_jobs(all_jobs)
        new_jobs = [j for j in filtered if j["id"] not in sent_ids]

        self.last_run = datetime.now().isoformat()
        self.last_stats = {
            "total_fetched": len(all_jobs),
            "matching": len(filtered),
            "new_jobs": len(new_jobs),
            "sources": stats,
        }

        return new_jobs

    def format_job(self, job):
        source_tag = f"[{job.get('source', '?')}]"
        msg = (
            f"{source_tag} <b>{job.get('company', 'Unknown')}: {job['title']}</b>\n"
            f"📍 {job.get('location', 'N/A')}\n"
            f"📅 Posted: {job.get('posted', 'N/A')}\n"
        )
        desc = job.get("description", "")
        if desc:
            msg += f"\n{desc[:150]}...\n"
        msg += f"\n🔗 <a href=\"{job.get('url', '')}\">Apply here</a>"
        return msg

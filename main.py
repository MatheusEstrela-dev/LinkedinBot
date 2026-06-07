import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import schedule
from dotenv import load_dotenv

load_dotenv()

from src import auth, database, matcher, notifier, scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

PROFILE_PATH = Path(__file__).parent / "config" / "profile.json"


def load_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_pipeline():
    profile = load_profile()
    min_score = profile.get("min_score", 50)

    logger.info("Starting pipeline...")
    jobs = scraper.fetch_jobs(profile)
    logger.info("Found %d jobs", len(jobs))

    notified = 0
    for job in jobs:
        job_id = job.get("id")
        if not job_id or database.seen(job_id):
            continue

        total, breakdown = matcher.score(job, profile)
        logger.info("  [%3d] %s — %s", total, job["title"], job["company"])

        if total >= min_score:
            database.save(job, total)
            notifier.send(job, total, breakdown)
            notified += 1

    logger.info("Pipeline done. Notified: %d / %d", notified, len(jobs))


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Job Matcher Bot")
    parser.add_argument("--once", action="store_true", help="Run pipeline once and exit")
    parser.add_argument("--bot", action="store_true", help="Enable interactive Telegram bot (commands /ask, /vagas)")
    parser.add_argument("--interval", type=int, default=4, help="Hours between runs (default: 4)")
    args = parser.parse_args()

    database.init()

    # Se não tiver cookie mas tiver email/senha, faz login automático
    if not os.environ.get("LI_AT_COOKIE") and os.environ.get("LI_EMAIL"):
        from src import auth
        auth.refresh_cookie()

    if args.once:
        run_pipeline()
        return

    if args.bot:
        # Inicia bot interativo em thread separada
        import threading
        from src.bot import start_bot
        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()

    logger.info("Scheduler started. Running every %d hour(s).", args.interval)
    run_pipeline()  # run immediately on start
    schedule.every(args.interval).hours.do(run_pipeline)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()

"""
ConFireTV Scheduler

Runs two scheduled jobs:
  1. Daily report email at configured time (default 21:00 IST)
  2. Bedtime enforcer — force-stops all apps at configured bedtime

Run alongside the poller:  python scheduler.py

APScheduler is used with a BackgroundScheduler + BlockingScheduler to keep
this simple and self-contained (no Celery/Redis needed).
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitor import db
from monitor.notifier import send_daily_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CFG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config() -> dict:
    with open(CFG_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def job_daily_report():
    """Send daily summary email + push notification."""
    cfg = load_config()
    log.info("Sending daily report...")
    try:
        totals = db.get_daily_totals()
        sessions = db.get_session_log()
        send_daily_report(cfg, totals=totals, session_count=len(sessions))
    except Exception as e:
        log.error("Daily report failed: %s", e, exc_info=True)


def job_bedtime_enforce():
    """Force-stop any running app at bedtime."""
    cfg = load_config()
    active = db.get_active_session()
    if not active:
        log.info("Bedtime enforcer: no active session.")
        return

    ip = cfg["firetv"]["ip"]
    port = cfg["firetv"]["port"]
    package = active["package"]

    log.info("Bedtime: stopping %s on %s:%d", package, ip, port)
    try:
        subprocess.run(
            ["adb", "-s", f"{ip}:{port}", "shell", "am", "force-stop", package],
            timeout=10, capture_output=True
        )
        db.close_session(active["id"], datetime.now())
        log.info("Bedtime enforcer: stopped %s", package)
    except Exception as e:
        log.error("Bedtime enforcer error: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_hhmm(s: str):
    """Parse 'HH:MM' and return (hour, minute)."""
    h, m = s.strip().split(":")
    return int(h), int(m)


def day_abbr_to_cron(days: list) -> str:
    """Convert list like ['mon','tue','sun'] to APScheduler cron day_of_week string."""
    mapping = {
        "mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
        "fri": "fri", "sat": "sat", "sun": "sun",
    }
    return ",".join(mapping[d.lower()] for d in days if d.lower() in mapping) or "mon-sun"


def main():
    cfg = load_config()
    db.init_db()

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # 1. Daily report
    report_time = cfg["notifications"].get("daily_report_time", "21:00")
    rh, rm = parse_hhmm(report_time)
    scheduler.add_job(
        job_daily_report,
        CronTrigger(hour=rh, minute=rm, timezone="Asia/Kolkata"),
        id="daily_report",
        name="Daily Summary Report",
        replace_existing=True,
    )
    log.info("Daily report scheduled at %02d:%02d IST", rh, rm)

    # 2. Bedtime enforcer
    bedtime = cfg.get("bedtime", {})
    bt_time = bedtime.get("enforce_time", "").strip()
    bt_days = bedtime.get("days", ["mon","tue","wed","thu","fri","sat","sun"])

    if bt_time:
        bh, bm = parse_hhmm(bt_time)
        dow = day_abbr_to_cron(bt_days)
        scheduler.add_job(
            job_bedtime_enforce,
            CronTrigger(hour=bh, minute=bm, day_of_week=dow, timezone="Asia/Kolkata"),
            id="bedtime",
            name="Bedtime Enforcer",
            replace_existing=True,
        )
        log.info("Bedtime enforcer scheduled at %02d:%02d IST on %s", bh, bm, dow)
    else:
        log.info("Bedtime enforcer disabled (no enforce_time set in config)")

    log.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()

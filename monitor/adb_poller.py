"""
ADB Polling Daemon for ConFireTV.

Connects to Fire TV Stick over ADB/WiFi, polls the foreground app every
N seconds, records sessions to the SQLite database, and enforces per-app
daily limits by force-stopping apps that exceed their quota.

Run directly:  python -m monitor.adb_poller
"""

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import yaml
from datetime import datetime
from typing import Optional

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor import db
from monitor.notifier import send_limit_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def build_package_map(cfg: dict) -> dict:
    """Returns {package_name: app_key}."""
    return {
        v["package"]: k
        for k, v in cfg["app_packages"].items()
    }


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------

def _adb_binary() -> str:
    """
    Locate the adb binary cross-platform.
    Returns the full path if found via PATH, otherwise falls back to 'adb'
    (works if the user added it to PATH manually).
    """
    binary = shutil.which("adb")
    if binary:
        return binary
    # Common install locations as fallback
    candidates = []
    if platform.system() == "Windows":
        candidates = [
            r"C:\platform-tools\adb.exe",
            os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        ]
    elif platform.system() == "Darwin":
        candidates = ["/opt/homebrew/bin/adb", "/usr/local/bin/adb"]
    else:
        candidates = ["/usr/bin/adb", "/usr/local/bin/adb"]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "adb"   # last resort — let subprocess raise a clear error


def _install_hint() -> str:
    sys_name = platform.system()
    if sys_name == "Windows":
        return (
            "Download Android Platform Tools from "
            "https://developer.android.com/studio/releases/platform-tools "
            "and add the folder to your Windows PATH."
        )
    if sys_name == "Darwin":
        return "brew install android-platform-tools"
    return "sudo apt install adb  # or: sudo pacman -S android-tools"


def adb(ip: str, port: int, *args) -> Optional[str]:
    """Run an adb device command (-s IP:PORT …), return stdout or None on error."""
    binary = _adb_binary()
    cmd = [binary, "-s", f"{ip}:{port}"] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            err = result.stderr.strip()
            if err:
                log.warning("ADB command failed [%s]: %s", " ".join(args), err)
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.warning("ADB command timed out: %s", " ".join(args))
        return None
    except FileNotFoundError:
        log.error("adb not found. %s", _install_hint())
        return None


def _adb_connect_cmd(ip: str, port: int) -> Optional[str]:
    """
    Run 'adb connect IP:PORT' — must NOT use -s flag; device isn't connected yet.
    """
    binary = _adb_binary()
    cmd = [binary, "connect", f"{ip}:{port}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (result.stdout + result.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("ADB connect error: %s", e)
        return None


def connect(ip: str, port: int) -> bool:
    """Connect to Fire TV via TCP/IP, then verify the shell responds."""
    out = _adb_connect_cmd(ip, port)
    if not out or ("connected" not in out and "already connected" not in out):
        log.warning(
            "ADB connect to %s:%d failed: %s\n"
            "  → Check that ADB debugging is ON on the Fire TV:\n"
            "    Settings → My Fire TV → Developer Options → ADB Debugging: ON\n"
            "  → Make sure the Fire TV IP in config.yaml matches:\n"
            "    Settings → My Fire TV → About → Network",
            ip, port, out or "(no output)"
        )
        return False

    # Verify the shell actually works (TV may require accepting ADB dialog)
    verify = adb(ip, port, "shell", "echo", "adb_ok")
    if not verify or "adb_ok" not in verify:
        log.warning(
            "ADB connected to %s:%d but shell is not responding.\n"
            "  → Check your Fire TV screen — it may be showing an 'Allow ADB debugging?' dialog.\n"
            "    Accept it and tick 'Always allow from this computer'.",
            ip, port
        )
        return False

    log.info("ADB connected and verified: %s:%d", ip, port)
    return True


def get_foreground_app(ip: str, port: int) -> Optional[str]:
    """
    Returns the package name of the foreground app on Fire TV, or None.
    Tries multiple detection methods — different Fire OS firmware versions
    use different dumpsys output formats.
    """
    # Patterns tried against window/activity output, in priority order
    WINDOW_PATTERNS = [
        r"mCurrentFocus=Window\{[^}]+\s+([\w\.]+)/",           # standard Fire OS
        r"mCurrentFocus=Window\{[^}]+\s+([\w\.]+)\s",          # no slash variant
        r"mFocusedApp.*?ActivityRecord\{[^}]+\s+([\w\.]+)/",   # mFocusedApp line
        r"mFocusedApp=.*?([\w\.]+)/[\w\.]+",                   # compact form
    ]
    ACTIVITY_PATTERNS = [
        r"mResumedActivity[:\s=]+ActivityRecord\{[^}]+\s+([\w\.]+)/",
        r"ResumedActivity[:\s=]+ActivityRecord\{[^}]+\s+([\w\.]+)/",
        r"mResumedActivity[:\s=]+([\w\.]+)/",
    ]

    def try_patterns(text, patterns):
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    # Method 1: dumpsys window (primary — Fire OS 6/7/8)
    out = adb(ip, port, "shell", "dumpsys", "window")
    if out:
        pkg = try_patterns(out, WINDOW_PATTERNS)
        if pkg:
            return pkg

    # Method 2: dumpsys window windows (older Fire OS)
    out2 = adb(ip, port, "shell", "dumpsys", "window", "windows")
    if out2 and out2 != out:
        pkg = try_patterns(out2, WINDOW_PATTERNS)
        if pkg:
            return pkg

    # Method 3: dumpsys activity activities
    out3 = adb(ip, port, "shell", "dumpsys", "activity", "activities")
    if out3:
        pkg = try_patterns(out3, ACTIVITY_PATTERNS)
        if pkg:
            return pkg

    # Method 4: dumpsys activity top
    out4 = adb(ip, port, "shell", "dumpsys", "activity", "top")
    if out4:
        m = re.search(r"ACTIVITY\s+([\w\.]+)/", out4)
        if m:
            return m.group(1)
        # Some Fire OS versions: "    comp=ComponentInfo{com.pkg/activity}"
        m = re.search(r"comp=ComponentInfo\{([\w\.]+)/", out4)
        if m:
            return m.group(1)

    # Method 5: SurfaceFlinger — works on some Amazon custom builds
    out5 = adb(ip, port, "shell", "dumpsys", "SurfaceFlinger")
    if out5:
        m = re.search(r"#00\s+([\w\.]+)/", out5)
        if not m:
            m = re.search(r"Layer\s*name=.*([\w\.]{5,})\.", out5)
        if m:
            return m.group(1)

    log.warning(
        "Could not detect foreground app — all methods failed. "
        "Run 'python diagnose.py' to see the raw ADB output and find which "
        "detection pattern matches your Fire TV firmware."
    )
    return None


def force_stop_app(ip: str, port: int, package: str):
    """Force-stop an app (sends child back to home screen)."""
    log.info("Force-stopping %s", package)
    adb(ip, port, "shell", "am", "force-stop", package)


# ---------------------------------------------------------------------------
# Poller state
# ---------------------------------------------------------------------------

class Poller:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ip: str = cfg["firetv"]["ip"]
        self.port: int = cfg["firetv"]["port"]
        self.poll_interval: int = cfg["firetv"]["poll_interval"]
        self.package_map: dict = build_package_map(cfg)
        self.child_name: str = cfg["child"]["name"]
        self.daily_limit_min: int = cfg["child"]["daily_limit_minutes"]

        # Runtime state
        self.current_session_id: Optional[int] = None
        self.current_app_key: Optional[str] = None
        self.current_package: Optional[str] = None

        # Track which apps have already triggered an alert today
        self.alerted_today: set = set()
        self.last_alert_date = None

    def _app_limits(self) -> dict:
        """Merge config limits with DB overrides. Returns {app_key: minutes}."""
        limits = dict(self.cfg.get("app_limits", {}))
        db_limits = db.get_limits()
        limits.update(db_limits)
        return limits

    def _reset_daily_alerts_if_needed(self):
        today = datetime.now().date()
        if self.last_alert_date != today:
            self.alerted_today.clear()
            self.last_alert_date = today

    def _check_limits(self, totals: dict):
        """Check if any app (or total) exceeded its daily limit and enforce."""
        self._reset_daily_alerts_if_needed()
        limits = self._app_limits()
        threshold = self.cfg["notifications"].get("alert_threshold_percent", 80)

        for app_key, total_s in totals.items():
            if app_key not in limits or limits[app_key] == 0:
                continue
            limit_s = limits[app_key] * 60
            pct = (total_s / limit_s) * 100

            # Hard limit exceeded — force stop
            if total_s >= limit_s:
                if self.current_app_key == app_key:
                    log.warning(
                        "%s exceeded daily limit for %s (%d min). Stopping.",
                        self.child_name, app_key, limits[app_key]
                    )
                    force_stop_app(self.ip, self.port, self.current_package)
                    send_limit_alert(
                        self.cfg,
                        app_key=app_key,
                        used_min=total_s // 60,
                        limit_min=limits[app_key],
                        exceeded=True,
                    )
                continue

            # Approaching limit — alert once
            alert_key = f"{app_key}_{datetime.now().date()}"
            if pct >= threshold and alert_key not in self.alerted_today:
                log.info("Approaching limit for %s: %.0f%%", app_key, pct)
                self.alerted_today.add(alert_key)
                send_limit_alert(
                    self.cfg,
                    app_key=app_key,
                    used_min=total_s // 60,
                    limit_min=limits[app_key],
                    exceeded=False,
                )

        # Check total daily limit
        total_all_s = sum(
            s for k, s in totals.items()
            if k != "firetv_home"
        )
        total_limit_s = self.daily_limit_min * 60
        if total_limit_s > 0 and total_all_s >= total_limit_s:
            if self.current_app_key and self.current_app_key != "firetv_home":
                log.warning(
                    "%s exceeded total daily limit (%d min). Stopping current app.",
                    self.child_name, self.daily_limit_min
                )
                force_stop_app(self.ip, self.port, self.current_package)
                send_limit_alert(
                    self.cfg,
                    app_key="total",
                    used_min=total_all_s // 60,
                    limit_min=self.daily_limit_min,
                    exceeded=True,
                )

    def _handle_app_switch(self, new_package: Optional[str]):
        now = datetime.now()

        new_app_key = self.package_map.get(new_package) if new_package else None

        # Same app, no change
        if new_app_key == self.current_app_key:
            return

        # Close previous session
        if self.current_session_id is not None:
            db.close_session(self.current_session_id, now)
            log.info(
                "Session ended: %s",
                self.current_app_key or self.current_package,
            )
            self.current_session_id = None

        # Open new session (track known apps only — ignore unknown system packages)
        if new_app_key and new_package:
            self.current_session_id = db.open_session(new_app_key, new_package, now)
            log.info("Session started: %s (%s)", new_app_key, new_package)
        elif new_package:
            log.info(
                "Foreground app not in tracking list: %s "
                "(add to config.yaml → app_packages if you want to track it)",
                new_package
            )

        self.current_app_key = new_app_key
        self.current_package = new_package

    def run(self):
        log.info("ConFireTV poller starting. Target: %s:%d", self.ip, self.port)
        db.init_db()
        db.close_all_open_sessions(datetime.now())

        # Sync config limits into DB
        for app_key, minutes in self.cfg.get("app_limits", {}).items():
            db.upsert_limit(app_key, minutes)

        connected = False
        while True:
            try:
                if not connected:
                    connected = connect(self.ip, self.port)
                    if not connected:
                        log.warning("Retrying ADB connection in 30s...")
                        time.sleep(30)
                        continue

                package = get_foreground_app(self.ip, self.port)
                if package is None:
                    log.warning("Could not get foreground app (TV off or ADB issue?)")
                    connected = False
                else:
                    self._handle_app_switch(package)
                    totals = db.get_daily_totals()
                    self._check_limits(totals)

            except KeyboardInterrupt:
                log.info("Stopping poller...")
                if self.current_session_id is not None:
                    db.close_session(self.current_session_id, datetime.now())
                break
            except Exception as e:
                log.error("Unexpected error: %s", e, exc_info=True)

            time.sleep(self.poll_interval)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = load_config()
    Poller(cfg).run()

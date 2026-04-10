#!/usr/bin/env python3
"""
ConFireTV — Cross-platform service manager.

Works on Windows, macOS, and Linux.

Usage:
    python manage.py status
    python manage.py start
    python manage.py stop
    python manage.py restart
    python manage.py logs                        # tail all logs
    python manage.py logs poller|web|scheduler   # tail one log
"""

import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT    = Path(__file__).parent.resolve()
LOGS    = ROOT / "logs"
SYSTEM  = platform.system()   # "Windows", "Darwin", "Linux"

SERVICES = ["poller", "web", "scheduler"]

# Per-platform service labels
LABELS = {
    "Windows": {s: f"ConFireTV-{s.capitalize()}" for s in SERVICES},
    "Darwin":  {s: f"com.confiretvmonitor.{s}"   for s in SERVICES},
    "Linux":   {s: f"confiretvmonitor-{s}"        for s in SERVICES},
}

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── Status ────────────────────────────────────────────────────────────────────

def _status_windows(svc):
    label = LABELS["Windows"][svc]
    r = _run(["sc", "query", label])
    if r.returncode != 0:
        return "not_installed"
    if "RUNNING" in r.stdout:
        return "running"
    return "stopped"


def _status_macos(svc):
    label = LABELS["Darwin"][svc]
    r = _run(["launchctl", "list", label])
    if r.returncode != 0:
        return "not_loaded"
    if '"PID"' in r.stdout:
        return "running"
    return "stopped"


def _status_linux(svc):
    label = LABELS["Linux"][svc]
    r = _run(["systemctl", "is-active", label])
    state = r.stdout.strip()
    return "running" if state == "active" else state


def get_status(svc):
    if SYSTEM == "Windows": return _status_windows(svc)
    if SYSTEM == "Darwin":  return _status_macos(svc)
    return _status_linux(svc)


def do_status():
    print(f"\n{BOLD}ConFireTV Service Status{RESET}")
    print("─" * 40)
    for svc in SERVICES:
        state = get_status(svc)
        if state == "running":
            dot = f"{GREEN}● RUNNING{RESET}"
        elif state in ("not_installed", "not_loaded"):
            dot = f"{YELLOW}○ NOT INSTALLED{RESET}"
        else:
            dot = f"{RED}✗ {state.upper()}{RESET}"
        label = LABELS.get(SYSTEM, LABELS["Linux"])[svc]
        print(f"  {dot}  {label}")

    print(f"\n  Dashboard:  {CYAN}http://localhost:8000{RESET}")
    print(f"  Logs dir:   {LOGS}\n")
    _print_install_hint()


def _print_install_hint():
    if SYSTEM == "Windows":
        if any(get_status(s) == "not_installed" for s in SERVICES):
            print(f"  {YELLOW}Services not installed. Run as Administrator:{RESET}")
            print(f"    platform\\windows\\install_service.bat\n")
    elif SYSTEM == "Darwin":
        if any(get_status(s) == "not_loaded" for s in SERVICES):
            print(f"  {YELLOW}Services not installed. Run:{RESET}")
            print(f"    bash platform/macos/install_service.sh\n")
    else:
        if any(get_status(s) not in ("running", "stopped") for s in SERVICES):
            print(f"  {YELLOW}Services not installed. Run:{RESET}")
            print(f"    sudo bash platform/linux/install_service.sh\n")


# ── Start / Stop / Restart ────────────────────────────────────────────────────

def _ctrl_windows(action, svc):
    label = LABELS["Windows"][svc]
    cmd = {"start": ["nssm", "start", label],
           "stop":  ["nssm", "stop",  label]}[action]
    r = _run(cmd)
    return r.returncode == 0


def _ctrl_macos(action, svc):
    plist = Path.home() / "Library" / "LaunchAgents" / f"{LABELS['Darwin'][svc]}.plist"
    if not plist.exists():
        print(f"  {YELLOW}Not installed. Run: bash platform/macos/install_service.sh{RESET}")
        return False
    cmd = {"start": ["launchctl", "load",   "-w", str(plist)],
           "stop":  ["launchctl", "unload", str(plist)]}[action]
    r = _run(cmd)
    return r.returncode == 0


def _ctrl_linux(action, svc):
    label = LABELS["Linux"][svc]
    r = _run(["sudo", "systemctl", action, label])
    return r.returncode == 0


def do_start():
    print(f"\n{BOLD}Starting ConFireTV services...{RESET}")
    for svc in SERVICES:
        ok = (_ctrl_windows if SYSTEM == "Windows" else
              _ctrl_macos   if SYSTEM == "Darwin"  else
              _ctrl_linux)("start", svc)
        mark = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
        print(f"  {mark} {svc}")
    time.sleep(2)
    do_status()


def do_stop():
    print(f"\n{BOLD}Stopping ConFireTV services...{RESET}")
    for svc in reversed(SERVICES):   # stop scheduler first, then web, then poller
        ok = (_ctrl_windows if SYSTEM == "Windows" else
              _ctrl_macos   if SYSTEM == "Darwin"  else
              _ctrl_linux)("stop", svc)
        mark = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
        print(f"  {mark} {svc}")


def do_restart():
    do_stop()
    time.sleep(2)
    do_start()


# ── Logs ──────────────────────────────────────────────────────────────────────

def _tail_file(path: Path, prefix: str, lines: int = 20):
    """Generator that yields new lines appended to a file (like tail -f)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with open(path, encoding="utf-8", errors="replace") as f:
        # Seek to end minus last N lines
        content = f.read()
        last_lines = content.splitlines()[-lines:]
        for line in last_lines:
            print(f"{CYAN}[{prefix}]{RESET} {line}")
        while True:
            line = f.readline()
            if line:
                print(f"{CYAN}[{prefix}]{RESET} {line}", end="")
                sys.stdout.flush()
            else:
                time.sleep(0.3)


def do_logs(target=None):
    LOGS.mkdir(exist_ok=True)
    targets = [target] if target else SERVICES
    invalid = [t for t in targets if t not in SERVICES]
    if invalid:
        print(f"Unknown service: {invalid[0]}. Choose from: {', '.join(SERVICES)}")
        sys.exit(1)

    print(f"\n{BOLD}Tailing log(s): {', '.join(targets)}  (Ctrl+C to stop){RESET}\n")

    if len(targets) == 1:
        # Single log — no threading needed
        _tail_file(LOGS / f"{targets[0]}.log", targets[0])
    else:
        # Multiple logs — one thread per file
        threads = []
        for svc in targets:
            t = threading.Thread(
                target=_tail_file,
                args=(LOGS / f"{svc}.log", svc),
                daemon=True,
            )
            t.start()
            threads.append(t)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")


# ── Entry point ───────────────────────────────────────────────────────────────

COMMANDS = {
    "status":  lambda _: do_status(),
    "start":   lambda _: do_start(),
    "stop":    lambda _: do_stop(),
    "restart": lambda _: do_restart(),
    "logs":    lambda args: do_logs(args[0] if args else None),
}

if __name__ == "__main__":
    if SYSTEM == "Windows":
        # Enable ANSI colours on Windows 10+
        os.system("")

    args = sys.argv[1:]
    cmd  = args[0].lower() if args else "status"

    if cmd not in COMMANDS:
        print(f"Usage: python manage.py [{'|'.join(COMMANDS)}]")
        sys.exit(1)

    try:
        COMMANDS[cmd](args[1:])
    except KeyboardInterrupt:
        print("\nInterrupted.")

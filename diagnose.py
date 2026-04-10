"""
ConFireTV Diagnostic Script
Run this to quickly test your ADB connection and foreground app detection.

Usage:
    python diagnose.py

It will print step-by-step results so you can see exactly what's working
and what needs to be fixed.
"""

import os
import re
import subprocess
import sys
import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(ROOT, "config.yaml")

RESET  = "\033[0m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"

def ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg):  print(f"  {RED}✗{RESET} {msg}")
def warn(msg):  print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg):  print(f"  {CYAN}→{RESET} {msg}")
def head(msg):  print(f"\n{BOLD}{msg}{RESET}")


def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT", -1
    except FileNotFoundError:
        return None, "NOT_FOUND", -1


def main():
    print(f"\n{BOLD}ConFireTV — ADB Diagnostic{RESET}")
    print("=" * 48)

    # ── 1. Config ──────────────────────────────────────────────
    head("1. Loading config.yaml")
    try:
        with open(CFG_PATH) as f:
            cfg = yaml.safe_load(f)
        ip   = cfg["firetv"]["ip"]
        port = cfg["firetv"]["port"]
        ok(f"Config loaded. Fire TV target: {ip}:{port}")
        ok(f"Child: {cfg['child']['name']}")
    except Exception as e:
        fail(f"Could not load config.yaml: {e}")
        sys.exit(1)

    # ── 2. ADB binary ──────────────────────────────────────────
    head("2. Checking ADB binary")
    stdout, stderr, rc = run(["adb", "version"])
    if rc == 0 and stdout:
        ok(f"Found: {stdout.splitlines()[0]}")
    else:
        fail("adb not found in PATH.")
        info("Install:  macOS → brew install android-platform-tools")
        info("          Ubuntu → sudo apt install adb")
        sys.exit(1)

    # ── 3. Connect ─────────────────────────────────────────────
    head(f"3. Connecting to Fire TV at {ip}:{port}")
    stdout, stderr, rc = run(["adb", "connect", f"{ip}:{port}"])
    out = (stdout or "") + (stderr or "")
    if "connected" in out.lower():
        ok(f"Connect result: {out.strip()}")
    elif "refused" in out.lower():
        fail(f"Connection refused: {out.strip()}")
        info("→ ADB debugging may be OFF on the Fire TV.")
        info("  Settings → My Fire TV → Developer Options → ADB Debugging: ON")
        sys.exit(1)
    elif "unable to connect" in out.lower() or "cannot connect" in out.lower():
        fail(f"Cannot reach Fire TV: {out.strip()}")
        info("→ Check that the IP in config.yaml is correct.")
        info(f"  Fire TV IP: Settings → My Fire TV → About → Network")
        info(f"  Current config IP: {ip}")
        sys.exit(1)
    else:
        warn(f"Unexpected connect result: {out.strip()}")

    # ── 4. Shell verify ────────────────────────────────────────
    head("4. Verifying ADB shell responds")
    stdout, stderr, rc = run(["adb", "-s", f"{ip}:{port}", "shell", "echo", "adb_ok"])
    if stdout and "adb_ok" in stdout:
        ok("Shell is responding.")
    else:
        fail(f"Shell not responding. stderr: {stderr}")
        info("→ Check your Fire TV screen for an 'Allow ADB debugging?' popup.")
        info("  Accept it and tick 'Always allow from this computer'.")
        info("  Then run this script again.")
        sys.exit(1)

    # ── 5. Installed packages ──────────────────────────────────
    head("5. Checking installed packages for tracked apps")
    stdout, _, _ = run(["adb", "-s", f"{ip}:{port}", "shell", "pm", "list", "packages"])
    installed = set(l.replace("package:", "").strip() for l in (stdout or "").splitlines())

    # Broad search terms to find packages even when exact name differs
    SEARCH_HINTS = {
        "youtube":    ["youtube"],
        "hotstar":    ["hotstar", "starv", "stv", "disneyplus", "disney"],
        "prime_video":["amazon.avod", "primevideo", "amazon.firetv.primevideo"],
        "sun_next":   ["sun.sun", "sunnxt", "sunott", "sunnetwork", "sun.nxt"],
        "firetv_home":["tv.launcher", "firetv"],
    }

    for app_key, app_info in cfg.get("app_packages", {}).items():
        pkg = app_info["package"]
        name = app_info["display_name"]
        if pkg in installed:
            ok(f"{name}: {pkg}")
        else:
            warn(f"{name}: package '{pkg}' NOT found on this Fire TV")
            # Try to find alternatives
            hints = SEARCH_HINTS.get(app_key, [app_key])
            matches = [p for p in installed if any(h in p.lower() for h in hints)]
            if matches:
                info(f"  Possible package(s) for {name}:")
                for m in matches:
                    print(f"         {CYAN}{m}{RESET}")
                info(f"  Update config.yaml → app_packages → {app_key} → package: \"{matches[0]}\"")
            else:
                info(f"  Could not find {name} automatically. Run:")
                info(f"  adb -s {ip}:{port} shell pm list packages | grep -i {hints[0]}")

    # ── 6. Foreground app detection ────────────────────────────
    head("6. Detecting foreground app")
    print("  Open YouTube, Hotstar, or Sun NXT on the TV right now, then press Enter.")
    input("  Press Enter when an app is open and visible on the TV screen...")

    detected = None

    def try_patterns(text, patterns):
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    WINDOW_PATTERNS = [
        r"mCurrentFocus=Window\{[^}]+\s+([\w\.]+)/",
        r"mCurrentFocus=Window\{[^}]+\s+([\w\.]+)\s",
        r"mFocusedApp.*?ActivityRecord\{[^}]+\s+([\w\.]+)/",
        r"mFocusedApp=.*?([\w\.]+)/[\w\.]+",
    ]
    ACTIVITY_PATTERNS = [
        r"mResumedActivity[:\s=]+ActivityRecord\{[^}]+\s+([\w\.]+)/",
        r"ResumedActivity[:\s=]+ActivityRecord\{[^}]+\s+([\w\.]+)/",
        r"mResumedActivity[:\s=]+([\w\.]+)/",
    ]

    print("\n  [Method 1] dumpsys window")
    stdout, _, _ = run(["adb", "-s", f"{ip}:{port}", "shell", "dumpsys", "window"])
    if stdout:
        detected = try_patterns(stdout, WINDOW_PATTERNS)
        if detected:
            ok(f"Detected: {detected}")
        else:
            # Always print the raw focus lines so we can debug
            focus_lines = [
                l.strip() for l in stdout.splitlines()
                if any(k in l for k in ["Focus", "mCurrent", "mFocused", "Resumed"])
            ]
            if focus_lines:
                warn("Pattern did not match. Raw focus lines from dumpsys window:")
                for l in focus_lines[:8]:
                    info(f"  {l}")
                print(f"\n  {YELLOW}>>> Copy the lines above and share with the developer to add a new pattern.{RESET}")
            else:
                warn("No focus lines at all in dumpsys window output.")
                info("(This is unusual — Fire TV may be in deep sleep or screensaver)")
    else:
        warn("dumpsys window returned no output")

    if not detected:
        print("\n  [Method 2] dumpsys window windows")
        stdout, _, _ = run(["adb", "-s", f"{ip}:{port}", "shell", "dumpsys", "window", "windows"])
        if stdout:
            detected = try_patterns(stdout, WINDOW_PATTERNS)
            if detected:
                ok(f"Detected (method 2): {detected}")
            else:
                focus_lines = [l.strip() for l in stdout.splitlines() if "Focus" in l or "mCurrent" in l]
                if focus_lines:
                    warn("Method 2 focus lines (for debugging):")
                    for l in focus_lines[:5]:
                        info(f"  {l}")

    if not detected:
        print("\n  [Method 3] dumpsys activity activities")
        stdout, _, _ = run(["adb", "-s", f"{ip}:{port}", "shell", "dumpsys", "activity", "activities"])
        if stdout:
            detected = try_patterns(stdout, ACTIVITY_PATTERNS)
            if detected:
                ok(f"Detected (method 3): {detected}")
            else:
                resumed = [l.strip() for l in stdout.splitlines() if "Resumed" in l or "mResumed" in l]
                if resumed:
                    warn("Method 3 Resumed lines (for debugging):")
                    for l in resumed[:5]:
                        info(f"  {l}")

    if not detected:
        print("\n  [Method 4] dumpsys activity top")
        stdout, _, _ = run(["adb", "-s", f"{ip}:{port}", "shell", "dumpsys", "activity", "top"])
        if stdout:
            m = re.search(r"ACTIVITY\s+([\w\.]+)/", stdout)
            if not m:
                m = re.search(r"comp=ComponentInfo\{([\w\.]+)/", stdout)
            if m:
                detected = m.group(1)
                ok(f"Detected (method 4): {detected}")
            else:
                warn("Method 4 top lines:")
                for l in stdout.splitlines()[:6]:
                    info(f"  {l.strip()}")

    # ── 7. Summary ─────────────────────────────────────────────
    head("7. Summary")
    if detected:
        cfg_packages = {v["package"]: k for k, v in cfg.get("app_packages", {}).items()}
        if detected in cfg_packages:
            ok(f"Package '{detected}' is tracked as '{cfg_packages[detected]}' — everything looks good!")
            ok("The poller should record sessions normally.")
        else:
            warn(f"Package '{detected}' is NOT in your config.yaml tracking list.")
            info("To track it, add an entry to config.yaml → app_packages:")
            print(f"""
    new_app_key:
      package: "{detected}"
      display_name: "My App Name"
      color: "#AABBCC"
""")
            info("And add it to app_limits:")
            print(f"""
    new_app_key: 60   # minutes per day
""")
    else:
        fail("Could not detect foreground app with any method.")
        info("Make sure an app (YouTube, Hotstar, etc.) is actually open and visible on TV.")
        info("If the TV is on the home screen, open an app and run diagnose.py again.")

    print()


if __name__ == "__main__":
    main()

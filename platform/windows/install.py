"""
ConFireTV - Windows Service Installer (Python version)
Run as Administrator:  python install.py
Or double-click install.bat which calls this script.

Replaces install_service.bat to avoid cmd.exe batch parsing issues.
"""

import ctypes
import os
import shutil
import socket
import subprocess
import sys

# ── Project paths ────────────────────────────────────────────────────────────

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
VENV_PYTHON  = os.path.join(PROJECT_DIR, "venv", "Scripts", "python.exe")
VENV_UVICORN = os.path.join(PROJECT_DIR, "venv", "Scripts", "uvicorn.exe")
LOGS_DIR     = os.path.join(PROJECT_DIR, "logs")


# ── Helpers ──────────────────────────────────────────────────────────────────

def ok(msg):  print(f"  [OK]   {msg}")
def err(msg): print(f"  [ERR]  {msg}")
def info(msg):print(f"         {msg}")
def sep():    print()

def run(cmd, **kw):
    """Run a command, return (returncode, stdout, stderr)."""
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def nssm(*args):
    return run(["nssm"] + list(args))

def sc(*args):
    return run(["sc"] + list(args))


# ── Checks ───────────────────────────────────────────────────────────────────

def check_admin():
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if not is_admin:
        err("This script must be run as Administrator.")
        info("Right-click install.bat and choose 'Run as administrator'")
        sys.exit(1)
    ok("Running as Administrator")


def check_nssm():
    path = shutil.which("nssm")
    if not path and os.path.isfile(r"C:\Windows\System32\nssm.exe"):
        path = r"C:\Windows\System32\nssm.exe"
    if not path:
        err("NSSM not found in PATH.")
        sep()
        info("NSSM is a free Windows service manager.")
        info("Install steps:")
        info("  1. Download from: https://nssm.cc/download")
        info("  2. Extract the zip and open the win64 folder.")
        info("  3. Copy nssm.exe to C:\\Windows\\System32\\")
        info("Then re-run this installer.")
        sys.exit(1)
    ok(f"NSSM found: {path}")
    return path


def check_venv():
    if not os.path.isfile(VENV_PYTHON):
        err(f"venv not found at: {VENV_PYTHON}")
        sep()
        info("Create it by running in the project folder:")
        info("  python -m venv venv")
        info("  venv\\Scripts\\pip install -r requirements.txt")
        sys.exit(1)
    ok(f"Python venv: {VENV_PYTHON}")


def check_config():
    cfg = os.path.join(PROJECT_DIR, "config.yaml")
    if not os.path.isfile(cfg):
        err("config.yaml not found.")
        info("Copy config.yaml.example to config.yaml and fill in your settings.")
        sys.exit(1)
    ok("config.yaml found")


def find_adb():
    path = shutil.which("adb")
    if not path:
        candidates = [
            r"C:\platform-tools\adb.exe",
            os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                path = c
                break
    if not path:
        err("adb.exe not found.")
        sep()
        info("Download Android Platform Tools from:")
        info("  https://developer.android.com/studio/releases/platform-tools")
        info("Extract to C:\\platform-tools\\ and add to system PATH.")
        sys.exit(1)
    adb_dir = os.path.dirname(path)
    ok(f"adb.exe found: {path}")
    return adb_dir


# ── Service management ────────────────────────────────────────────────────────

SERVICES = ["ConFireTV-Poller", "ConFireTV-Web", "ConFireTV-Scheduler"]


def service_exists(name):
    code, _, _ = sc("query", name)
    return code == 0


def remove_old_services():
    sep()
    print("  Removing any existing ConFireTV services...")
    for svc in SERVICES:
        if service_exists(svc):
            run(["nssm", "stop", svc])
            run(["nssm", "remove", svc, "confirm"])
            print(f"  [REMOVED] {svc}")
        else:
            print(f"  [SKIP]    {svc} (not installed)")


def install_services(adb_dir):
    sep()
    print("  Installing services...")

    adb_path_env = f"PATH={adb_dir};{os.environ.get('SystemRoot', 'C:\\Windows')}\\System32;{os.environ.get('SystemRoot', 'C:\\Windows')}"

    # ── Poller ────────────────────────────────────────────────────────────────
    run(["nssm", "install",   "ConFireTV-Poller", VENV_PYTHON])
    run(["nssm", "set", "ConFireTV-Poller", "AppParameters",      "-m monitor.adb_poller"])
    run(["nssm", "set", "ConFireTV-Poller", "AppDirectory",       PROJECT_DIR])
    run(["nssm", "set", "ConFireTV-Poller", "DisplayName",        "ConFireTV Monitor (ADB Poller)"])
    run(["nssm", "set", "ConFireTV-Poller", "Description",        "Monitors Amazon Fire TV Stick via ADB."])
    run(["nssm", "set", "ConFireTV-Poller", "Start",              "SERVICE_AUTO_START"])
    run(["nssm", "set", "ConFireTV-Poller", "AppStdout",          os.path.join(LOGS_DIR, "poller.log")])
    run(["nssm", "set", "ConFireTV-Poller", "AppStderr",          os.path.join(LOGS_DIR, "poller.log")])
    run(["nssm", "set", "ConFireTV-Poller", "AppRotateFiles",     "1"])
    run(["nssm", "set", "ConFireTV-Poller", "AppRotateBytes",     "5242880"])
    run(["nssm", "set", "ConFireTV-Poller", "AppRestartDelay",    "10000"])
    run(["nssm", "set", "ConFireTV-Poller", "AppEnvironmentExtra", adb_path_env])
    ok("ConFireTV-Poller installed")

    # ── Web ───────────────────────────────────────────────────────────────────
    run(["nssm", "install",   "ConFireTV-Web", VENV_UVICORN])
    run(["nssm", "set", "ConFireTV-Web", "AppParameters",      "web.app:app --host 0.0.0.0 --port 8000"])
    run(["nssm", "set", "ConFireTV-Web", "AppDirectory",       PROJECT_DIR])
    run(["nssm", "set", "ConFireTV-Web", "DisplayName",        "ConFireTV Dashboard (Web Server)"])
    run(["nssm", "set", "ConFireTV-Web", "Description",        "Web dashboard for ConFireTV. Access at http://localhost:8000"])
    run(["nssm", "set", "ConFireTV-Web", "Start",              "SERVICE_AUTO_START"])
    run(["nssm", "set", "ConFireTV-Web", "AppStdout",          os.path.join(LOGS_DIR, "web.log")])
    run(["nssm", "set", "ConFireTV-Web", "AppStderr",          os.path.join(LOGS_DIR, "web.log")])
    run(["nssm", "set", "ConFireTV-Web", "AppRotateFiles",     "1"])
    run(["nssm", "set", "ConFireTV-Web", "AppRotateBytes",     "5242880"])
    run(["nssm", "set", "ConFireTV-Web", "AppRestartDelay",    "5000"])
    run(["nssm", "set", "ConFireTV-Web", "AppEnvironmentExtra", adb_path_env])
    ok("ConFireTV-Web installed")

    # ── Scheduler ─────────────────────────────────────────────────────────────
    run(["nssm", "install",   "ConFireTV-Scheduler", VENV_PYTHON])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppParameters",      "scheduler.py"])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppDirectory",       PROJECT_DIR])
    run(["nssm", "set", "ConFireTV-Scheduler", "DisplayName",        "ConFireTV Scheduler (Reports and Bedtime)"])
    run(["nssm", "set", "ConFireTV-Scheduler", "Description",        "Sends daily reports and enforces bedtime on Fire TV."])
    run(["nssm", "set", "ConFireTV-Scheduler", "Start",              "SERVICE_AUTO_START"])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppStdout",          os.path.join(LOGS_DIR, "scheduler.log")])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppStderr",          os.path.join(LOGS_DIR, "scheduler.log")])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppRotateFiles",     "1"])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppRotateBytes",     "5242880"])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppRestartDelay",    "10000"])
    run(["nssm", "set", "ConFireTV-Scheduler", "AppEnvironmentExtra", adb_path_env])
    ok("ConFireTV-Scheduler installed")


def start_services():
    sep()
    print("  Starting services...")
    for svc in SERVICES:
        code, out, serr = run(["nssm", "start", svc])
        if code == 0 or "START_PENDING" in out or "running" in out.lower():
            ok(f"{svc} started")
        else:
            # Check if already running
            scode, sout, _ = sc("query", svc)
            if "RUNNING" in sout:
                ok(f"{svc} already running")
            else:
                print(f"  [WARN]  {svc} may not have started — check logs")


def configure_firewall():
    sep()
    print("  Configuring Windows Firewall (port 8000)...")
    run(["netsh", "advfirewall", "firewall", "delete", "rule", 'name=ConFireTV Dashboard'])
    code, _, _ = run([
        "netsh", "advfirewall", "firewall", "add", "rule",
        "name=ConFireTV Dashboard",
        "dir=in", "action=allow", "protocol=TCP", "localport=8000"
    ])
    if code == 0:
        ok("Firewall rule added — dashboard reachable from WiFi devices")
    else:
        print("  [WARN]  Firewall rule may not have been added — run manually if needed")


def get_local_ips():
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip.startswith("192.") or ip.startswith("10.") or ip.startswith("172."):
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    return ips


def print_summary():
    sep()
    print("  " + "=" * 43)
    print("  Installation complete!")
    sep()
    print("  Dashboard (this PC):       http://localhost:8000")
    for ip in get_local_ips():
        print(f"  Dashboard (other devices): http://{ip}:8000")
    sep()
    print("  Manage:    platform\\windows\\manage.bat status")
    print("  Logs:      platform\\windows\\manage.bat logs")
    print("  Stop all:  platform\\windows\\manage.bat stop")
    sep()
    print("  Services start automatically at every Windows boot.")
    print("  " + "=" * 43)
    sep()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sep()
    print("  ConFireTV - Windows Service Installer")
    print("  " + "=" * 43)
    print(f"  Project: {PROJECT_DIR}")
    sep()

    check_admin()
    check_nssm()
    check_venv()
    check_config()
    adb_dir = find_adb()

    os.makedirs(LOGS_DIR, exist_ok=True)
    ok(f"Logs directory: {LOGS_DIR}")

    configure_firewall()
    remove_old_services()
    install_services(adb_dir)
    start_services()
    print_summary()

    input("  Press Enter to close...")


if __name__ == "__main__":
    main()

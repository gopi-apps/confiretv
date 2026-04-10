"""
FastAPI web server for ConFireTV dashboard.

Routes:
  GET  /                      — dashboard HTML
  GET  /api/status            — live status (current app, session time)
  GET  /api/today             — today's per-app totals + limits
  GET  /api/sessions          — today's session log
  GET  /api/weekly            — last 7 days per-app totals
  POST /api/kill-app          — force-stop current app on Fire TV
  POST /api/set-limit         — update per-app daily limit
  POST /api/set-daily-limit   — update overall daily limit
  GET  /api/debug             — ADB connection diagnostics (use when status is stuck)
  GET  /api/service-status   — whether poller/web/scheduler background services are running

Run:  uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import subprocess
import yaml
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from monitor import db

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "config.yaml")

def load_config() -> dict:
    with open(CFG_PATH) as f:
        return yaml.safe_load(f)


def save_config(cfg: dict):
    with open(CFG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


app = FastAPI(title="ConFireTV")
templates = Jinja2Templates(directory=os.path.join(ROOT, "web", "templates"))

static_dir = os.path.join(ROOT, "web", "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

db.init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg():
    return load_config()


def _app_info(cfg: dict) -> dict:
    """Returns {app_key: {display_name, color, package}}"""
    return cfg.get("app_packages", {})


def _adb(ip: str, port: int, *args) -> Optional[str]:
    cmd = ["adb", "-s", f"{ip}:{port}"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _seconds_to_hm(seconds: int) -> str:
    h, m = divmod(seconds // 60, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    cfg = _cfg()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "child_name": cfg["child"]["name"],
        "daily_limit_min": cfg["child"]["daily_limit_minutes"],
    })


# ---------------------------------------------------------------------------
# API: Status
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    cfg = _cfg()
    active = db.get_active_session()
    app_info = _app_info(cfg)

    if active:
        app_key = active["app_key"]
        start = datetime.fromisoformat(active["start_time"])
        elapsed_s = int((datetime.now() - start).total_seconds())
        info = app_info.get(app_key, {})
        return {
            "watching": True,
            "app_key": app_key,
            "display_name": info.get("display_name", app_key),
            "color": info.get("color", "#555"),
            "elapsed_s": elapsed_s,
            "elapsed_hm": _seconds_to_hm(elapsed_s),
            "since": start.strftime("%I:%M %p"),
        }
    return {"watching": False}


# ---------------------------------------------------------------------------
# API: Today's usage
# ---------------------------------------------------------------------------

@app.get("/api/today")
async def get_today():
    cfg = _cfg()
    totals = db.get_daily_totals()
    limits_db = db.get_limits()
    app_info = _app_info(cfg)
    config_limits = cfg.get("app_limits", {})

    result = []
    for app_key, info in app_info.items():
        if app_key == "firetv_home":
            continue
        total_s = totals.get(app_key, 0)
        limit_min = limits_db.get(app_key, config_limits.get(app_key, 0))
        result.append({
            "app_key": app_key,
            "display_name": info.get("display_name", app_key),
            "color": info.get("color", "#555"),
            "total_s": total_s,
            "total_hm": _seconds_to_hm(total_s),
            "limit_min": limit_min,
            "limit_s": limit_min * 60,
            "pct": min(100, int((total_s / (limit_min * 60)) * 100)) if limit_min else 0,
        })

    total_all_s = sum(r["total_s"] for r in result)
    daily_limit_min = cfg["child"]["daily_limit_minutes"]

    return {
        "apps": sorted(result, key=lambda x: -x["total_s"]),
        "total_s": total_all_s,
        "total_hm": _seconds_to_hm(total_all_s),
        "daily_limit_min": daily_limit_min,
        "daily_limit_s": daily_limit_min * 60,
        "daily_pct": min(100, int((total_all_s / (daily_limit_min * 60)) * 100)) if daily_limit_min else 0,
        "date": date.today().strftime("%d %B %Y"),
    }


# ---------------------------------------------------------------------------
# API: Session log
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
async def get_sessions(for_date: Optional[str] = None):
    cfg = _cfg()
    app_info = _app_info(cfg)

    if for_date:
        try:
            d = date.fromisoformat(for_date)
        except ValueError:
            raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")
    else:
        d = None

    sessions = db.get_session_log(for_date=d)
    result = []
    for s in sessions:
        info = app_info.get(s["app_key"], {})
        start_dt = datetime.fromisoformat(s["start_time"])
        result.append({
            **s,
            "display_name": info.get("display_name", s["app_key"]),
            "color": info.get("color", "#555"),
            "start_fmt": start_dt.strftime("%I:%M %p"),
            "duration_hm": _seconds_to_hm(s["duration_s"] or 0),
        })
    return {"sessions": result}


# ---------------------------------------------------------------------------
# API: Weekly chart data
# ---------------------------------------------------------------------------

@app.get("/api/weekly")
async def get_weekly():
    cfg = _cfg()
    app_info = _app_info(cfg)
    raw = db.get_weekly_totals()

    # Build last-7-days labels
    today = date.today()
    days = [(today - timedelta(days=6 - i)) for i in range(7)]
    labels = [d.strftime("%a %d") for d in days]
    day_keys = [d.isoformat() for d in days]

    # Pivot: {app_key: [total_s per day]}
    pivot = {
        k: {dk: 0 for dk in day_keys}
        for k in app_info
        if k != "firetv_home"
    }
    for row in raw:
        if row["app_key"] in pivot:
            pivot[row["app_key"]][row["day"]] = row["total_s"]

    datasets = []
    for app_key, daily in pivot.items():
        info = app_info.get(app_key, {})
        datasets.append({
            "app_key": app_key,
            "label": info.get("display_name", app_key),
            "color": info.get("color", "#555"),
            "data": [daily[dk] // 60 for dk in day_keys],  # minutes
        })

    return {
        "labels": labels,
        "datasets": sorted(datasets, key=lambda x: -sum(x["data"])),
    }


# ---------------------------------------------------------------------------
# API: Controls
# ---------------------------------------------------------------------------

@app.post("/api/kill-app")
async def kill_current_app():
    cfg = _cfg()
    active = db.get_active_session()
    if not active:
        return {"success": False, "message": "No active app session found."}

    package = active["package"]
    ip = cfg["firetv"]["ip"]
    port = cfg["firetv"]["port"]

    out = _adb(ip, port, "shell", "am", "force-stop", package)
    if out is None:
        return {"success": False, "message": "ADB command failed. Is the Fire TV reachable?"}

    db.close_session(active["id"], datetime.now())
    return {
        "success": True,
        "message": f"Stopped {active['app_key']} on Fire TV.",
        "package": package,
    }


@app.post("/api/set-limit")
async def set_app_limit(request: Request):
    body = await request.json()
    app_key = body.get("app_key", "").strip()
    limit_min = body.get("limit_min")

    if not app_key:
        raise HTTPException(400, "app_key is required")
    try:
        limit_min = int(limit_min)
        if limit_min < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(400, "limit_min must be a non-negative integer")

    db.upsert_limit(app_key, limit_min)

    # Also persist to config.yaml
    cfg = _cfg()
    cfg.setdefault("app_limits", {})[app_key] = limit_min
    save_config(cfg)

    return {"success": True, "app_key": app_key, "limit_min": limit_min}


@app.get("/api/service-status")
async def get_service_status():
    """Check if the three background services are running via launchctl."""
    services = ["poller", "web", "scheduler"]
    result = {}
    for svc in services:
        label = f"com.confiretvmonitor.{svc}"
        try:
            r = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and '"PID"' in r.stdout:
                import re as _re
                pid_match = _re.search(r'"PID"\s*=\s*(\d+)', r.stdout)
                result[svc] = {"running": True, "pid": int(pid_match.group(1)) if pid_match else None}
            else:
                result[svc] = {"running": False, "pid": None}
        except Exception:
            result[svc] = {"running": False, "pid": None}
    return result


@app.get("/api/debug")
async def get_debug():
    """
    Run ADB diagnostics and return raw output.
    Open http://localhost:8000/api/debug in browser if status is stuck on 'TV is idle'.
    """
    import re as _re
    cfg = _cfg()
    ip = cfg["firetv"]["ip"]
    port = cfg["firetv"]["port"]
    result = {"ip": ip, "port": port, "steps": []}

    def step(name, cmd, out):
        result["steps"].append({"name": name, "cmd": " ".join(cmd), "output": out or "(no output / error)"})

    # Step 1: adb connect (no -s)
    cmd1 = ["adb", "connect", f"{ip}:{port}"]
    try:
        r = subprocess.run(cmd1, capture_output=True, text=True, timeout=10)
        connect_out = (r.stdout + r.stderr).strip()
    except Exception as e:
        connect_out = f"ERROR: {e}"
    step("adb connect", cmd1, connect_out)
    result["connect_ok"] = "connected" in connect_out.lower()

    # Step 2: verify shell
    cmd2 = ["adb", "-s", f"{ip}:{port}", "shell", "echo", "adb_ok"]
    try:
        r = subprocess.run(cmd2, capture_output=True, text=True, timeout=10)
        shell_out = (r.stdout + r.stderr).strip()
    except Exception as e:
        shell_out = f"ERROR: {e}"
    step("shell echo test", cmd2, shell_out)
    result["shell_ok"] = "adb_ok" in shell_out

    if not result["shell_ok"]:
        result["diagnosis"] = (
            "Shell not responding. Check: (1) ADB debugging ON on Fire TV, "
            "(2) Accept 'Allow ADB debugging?' dialog on TV screen, "
            "(3) Correct IP in config.yaml"
        )
        return result

    # Step 3: dumpsys window (method 1)
    cmd3 = ["adb", "-s", f"{ip}:{port}", "shell", "dumpsys", "window"]
    try:
        r = subprocess.run(cmd3, capture_output=True, text=True, timeout=15)
        win_out = r.stdout.strip()
    except Exception as e:
        win_out = f"ERROR: {e}"

    # Extract relevant lines only (keep output small)
    focus_lines = [l for l in win_out.splitlines() if "Focus" in l or "mCurrent" in l or "mResumed" in l]
    step("dumpsys window (focus lines)", cmd3, "\n".join(focus_lines[:20]) or win_out[:500])

    # Step 4: try to extract package
    detected = None
    for pattern in [
        r"mCurrentFocus=Window\{[^}]+\s+([\w\.]+)/",
        r"mFocusedApp.*?ActivityRecord\{[^}]+\s+([\w\.]+)/",
    ]:
        m = _re.search(pattern, win_out)
        if m:
            detected = m.group(1)
            break

    # Step 5: fallback to activity activities
    if not detected:
        cmd4 = ["adb", "-s", f"{ip}:{port}", "shell", "dumpsys", "activity", "activities"]
        try:
            r = subprocess.run(cmd4, capture_output=True, text=True, timeout=15)
            act_out = r.stdout.strip()
        except Exception as e:
            act_out = f"ERROR: {e}"
        act_lines = [l for l in act_out.splitlines() if "Resumed" in l or "mResumed" in l]
        step("dumpsys activity activities (Resumed lines)", cmd4, "\n".join(act_lines[:10]) or act_out[:300])
        for pattern in [
            r"mResumedActivity[:\s]+ActivityRecord\{[^}]+\s+([\w\.]+)/",
            r"ResumedActivity[:\s]+ActivityRecord\{[^}]+\s+([\w\.]+)/",
        ]:
            m = _re.search(pattern, act_out)
            if m:
                detected = m.group(1)
                break

    result["detected_package"] = detected
    cfg_packages = {v["package"]: k for k, v in cfg.get("app_packages", {}).items()}
    result["in_tracking_list"] = cfg_packages.get(detected, f"NOT TRACKED — add to config.yaml if needed") if detected else None
    result["diagnosis"] = (
        f"Package detected: {detected} → tracked as '{cfg_packages.get(detected)}'"
        if detected and detected in cfg_packages
        else (
            f"Package '{detected}' is not in your config.yaml app_packages list. "
            f"Add it to track it." if detected
            else "No foreground package detected. Is an app open on the TV?"
        )
    )
    return result


@app.post("/api/set-daily-limit")
async def set_daily_limit(request: Request):
    body = await request.json()
    try:
        limit_min = int(body.get("limit_min", -1))
        if limit_min < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(400, "limit_min must be a non-negative integer")

    cfg = _cfg()
    cfg["child"]["daily_limit_minutes"] = limit_min
    save_config(cfg)

    return {"success": True, "daily_limit_min": limit_min}

"""
Notifications for ConFireTV.

Supports:
  1. Gmail SMTP — daily summary report and limit alerts
  2. ntfy.sh    — instant push notification to parent's mobile (free, no signup)
"""

import logging
import smtplib
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ntfy.sh push notification (instant, works on Android + iOS)
# ---------------------------------------------------------------------------

def send_push(cfg: dict, title: str, message: str, priority: str = "default"):
    """
    Send a push notification via ntfy.sh.
    Install the ntfy app on your phone and subscribe to your topic.
    Topic is set in config.yaml → notifications → ntfy_topic
    """
    topic = cfg["notifications"].get("ntfy_topic", "").strip()
    if not topic:
        return

    try:
        url = f"https://ntfy.sh/{topic}"
        data = message.encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                # ntfy accepts percent-encoded UTF-8 in headers; avoids latin-1 errors
                # for characters like em-dash that urllib would otherwise reject.
                "Title": urllib.parse.quote(title, safe=" ,!?()-_:."),
                "Priority": priority,
                "Tags": "tv,child",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log.info("Push notification sent: %s", title)
    except Exception as e:
        log.warning("Push notification failed: %s", e)


# ---------------------------------------------------------------------------
# Gmail SMTP email
# ---------------------------------------------------------------------------

def send_email(cfg: dict, subject: str, body_html: str):
    """Send an HTML email via Gmail SMTP."""
    ncfg = cfg["notifications"]
    sender = ncfg.get("sender_email", "").strip()
    password = ncfg.get("sender_app_password", "").strip()
    recipient = ncfg.get("recipient_email", "").strip()

    if not sender or not password or not recipient:
        log.warning("Email not configured — skipping email notification")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"ConFireTV <{sender}>"
    msg["To"] = recipient
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(ncfg["smtp_host"], ncfg["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        log.info("Email sent to %s: %s", recipient, subject)
    except smtplib.SMTPAuthenticationError:
        log.error(
            "Email authentication failed for %s. "
            "For Gmail: use an App Password from https://myaccount.google.com/apppasswords — "
            "NOT your regular password. "
            "If App Passwords are unavailable (passkey accounts), switch to Brevo SMTP "
            "(see config.yaml notifications section for instructions).",
            sender,
        )
    except Exception as e:
        log.error("Email failed: %s", e)


# ---------------------------------------------------------------------------
# Alert: limit approaching or exceeded
# ---------------------------------------------------------------------------

def send_limit_alert(
    cfg: dict,
    app_key: str,
    used_min: int,
    limit_min: int,
    exceeded: bool,
):
    """Send alert when a child approaches or exceeds their app/daily limit."""
    app_display = _app_display_name(cfg, app_key)
    child_name = cfg["child"]["name"]

    if exceeded:
        title = f"TV Limit Reached — {app_display}"
        message = (
            f"{child_name} has used {used_min} min of {app_display} today "
            f"(limit: {limit_min} min). The app has been stopped."
        )
        priority = "high"
    else:
        pct = int((used_min / limit_min) * 100)
        title = f"TV Limit Warning — {app_display} ({pct}%)"
        message = (
            f"{child_name} has used {used_min} min of {app_display} today "
            f"(limit: {limit_min} min). {limit_min - used_min} min remaining."
        )
        priority = "default"

    send_push(cfg, title=title, message=message, priority=priority)

    # Also email for exceeded events
    if exceeded:
        html = _render_alert_email(child_name, app_display, used_min, limit_min)
        send_email(cfg, subject=title, body_html=html)


# ---------------------------------------------------------------------------
# Daily summary report
# ---------------------------------------------------------------------------

def send_daily_report(cfg: dict, totals: dict, session_count: int):
    """
    Send the end-of-day summary email + push.
    totals: {app_key: total_seconds}
    """
    child_name = cfg["child"]["name"]
    today = date.today().strftime("%d %B %Y")
    total_all_min = sum(s for k, s in totals.items() if k != "firetv_home") // 60

    title = f"TV Summary for {child_name} — {today}"
    push_lines = [f"Total: {total_all_min} min across {session_count} sessions"]
    for app_key, total_s in sorted(totals.items(), key=lambda x: -x[1]):
        if app_key == "firetv_home":
            continue
        push_lines.append(f"  {_app_display_name(cfg, app_key)}: {total_s // 60} min")

    send_push(cfg, title=title, message="\n".join(push_lines))

    html = _render_daily_email(cfg, child_name, today, totals, session_count, total_all_min)
    send_email(cfg, subject=title, body_html=html)


# ---------------------------------------------------------------------------
# Email HTML templates
# ---------------------------------------------------------------------------

def _app_display_name(cfg: dict, app_key: str) -> str:
    if app_key == "total":
        return "Total Screen Time"
    pkgs = cfg.get("app_packages", {})
    return pkgs.get(app_key, {}).get("display_name", app_key.replace("_", " ").title())


def _app_color(cfg: dict, app_key: str) -> str:
    pkgs = cfg.get("app_packages", {})
    return pkgs.get(app_key, {}).get("color", "#555555")


def _render_daily_email(
    cfg: dict,
    child_name: str,
    today: str,
    totals: dict,
    session_count: int,
    total_all_min: int,
) -> str:
    daily_limit = cfg["child"]["daily_limit_minutes"]
    rows_html = ""
    for app_key, total_s in sorted(totals.items(), key=lambda x: -x[1]):
        if app_key == "firetv_home":
            continue
        color = _app_color(cfg, app_key)
        name  = _app_display_name(cfg, app_key)
        mins  = total_s // 60
        limit = cfg.get("app_limits", {}).get(app_key, 0)
        limit_str = f"{limit} min" if limit else "No limit"
        rows_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
              background:{color};margin-right:8px;"></span>{name}
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;">
            <strong>{mins} min</strong>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;
            color:#888;">{limit_str}</td>
        </tr>"""

    status_color = "#e74c3c" if total_all_min > daily_limit else "#27ae60"
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:16px;">
      <h2 style="color:#232F3E;">TV Summary — {child_name}</h2>
      <p style="color:#555;">{today}</p>
      <div style="background:#f8f9fa;border-radius:8px;padding:16px;margin-bottom:16px;">
        <span style="font-size:24px;font-weight:bold;color:{status_color};">{total_all_min} min</span>
        <span style="color:#888;margin-left:8px;">/ {daily_limit} min daily limit</span><br>
        <span style="color:#888;font-size:13px;">{session_count} watching sessions today</span>
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="background:#232F3E;color:white;">
            <th style="padding:8px 12px;text-align:left;">App</th>
            <th style="padding:8px 12px;text-align:right;">Used</th>
            <th style="padding:8px 12px;text-align:right;">Limit</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style="color:#aaa;font-size:11px;margin-top:24px;">
        Sent by ConFireTV
      </p>
    </body></html>
    """


def _render_alert_email(
    child_name: str,
    app_display: str,
    used_min: int,
    limit_min: int,
) -> str:
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:16px;">
      <h2 style="color:#e74c3c;">TV Limit Reached</h2>
      <p><strong>{child_name}</strong> has exceeded their daily limit for
        <strong>{app_display}</strong>.</p>
      <ul>
        <li>Used today: <strong>{used_min} min</strong></li>
        <li>Daily limit: <strong>{limit_min} min</strong></li>
      </ul>
      <p>The app has been automatically stopped.</p>
      <p style="color:#aaa;font-size:11px;">Sent by ConFireTV</p>
    </body></html>
    """

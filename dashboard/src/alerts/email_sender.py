"""
Envoi d'email via SMTP.
Supporte Gmail (app password), Outlook, ou n'importe quel SMTP.

Config dans dashboard/.env :
    ALERT_EMAIL_FROM=ton.email@gmail.com
    ALERT_EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # App password Gmail
    ALERT_EMAIL_TO=isaac@techunt.fr
    ALERT_EMAIL_SMTP_HOST=smtp.gmail.com        # optionnel
    ALERT_EMAIL_SMTP_PORT=587                   # optionnel
"""
import smtplib
import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_env():
    """Load .env file from dashboard/ or project root."""
    env_paths = [
        Path(__file__).parent.parent.parent / ".env",  # dashboard/.env
        Path(__file__).parent.parent.parent.parent / ".env",  # project root/.env
    ]
    for p in env_paths:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


def get_config() -> dict:
    _load_env()
    return {
        "from_addr": os.environ.get("ALERT_EMAIL_FROM", ""),
        "password":  os.environ.get("ALERT_EMAIL_PASSWORD", ""),
        "to_addr":   os.environ.get("ALERT_EMAIL_TO", ""),
        "smtp_host": os.environ.get("ALERT_EMAIL_SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("ALERT_EMAIL_SMTP_PORT", "587")),
    }


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["from_addr"] and cfg["password"] and cfg["to_addr"])


def send_email(subject: str, html_body: str, to_addr: str = None) -> bool:
    """
    Send an HTML email.
    Returns True if successful, False otherwise.
    """
    cfg = get_config()
    to = to_addr or cfg["to_addr"]

    if not cfg["from_addr"] or not cfg["password"]:
        logger.error("[Email] ALERT_EMAIL_FROM ou ALERT_EMAIL_PASSWORD manquant dans .env")
        return False
    if not to:
        logger.error("[Email] ALERT_EMAIL_TO manquant dans .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Techunt Veille <{cfg['from_addr']}>"
    msg["To"] = to

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["from_addr"], cfg["password"])
            server.sendmail(cfg["from_addr"], [to], msg.as_string())
        logger.info(f"[Email] ✅ Envoyé à {to} — {subject[:60]}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "[Email] ❌ Authentification échouée. "
            "Pour Gmail : utilise un App Password (myaccount.google.com/apppasswords)"
        )
        return False
    except Exception as e:
        logger.error(f"[Email] ❌ Erreur envoi : {e}")
        return False


def send_daily_digest(days_back: int = 1) -> bool:
    """Build and send the daily digest."""
    from alerts.daily_digest import get_digest_data, build_html, get_subject

    data = get_digest_data(days_back=days_back)
    subject = get_subject(data)
    html = build_html(data)
    return send_email(subject, html)

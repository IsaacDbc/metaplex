"""
Scheduler d'alertes email — envoie le digest à 8h00 chaque matin.

Lancement :
    python -m alerts.scheduler          # tourne en arrière-plan
    python -m alerts.scheduler --test   # envoie immédiatement pour tester
"""
import sys
import os
import logging
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_digest(days_back: int = 1):
    """Run pipeline then send digest."""
    logger.info("🔄 Lancement du pipeline de collecte…")
    try:
        from pipeline import run_pipeline
        stats = run_pipeline(verbose=False)
        logger.info(f"✅ Pipeline terminé : {stats['funding']} levées, {stats['jobs']} offres")
    except Exception as e:
        logger.warning(f"Pipeline error (on continue quand même): {e}")

    logger.info("📧 Génération et envoi du digest…")
    from alerts.email_sender import send_daily_digest, is_configured

    if not is_configured():
        logger.error(
            "❌ Email non configuré. Crée dashboard/.env avec :\n"
            "  ALERT_EMAIL_FROM=ton@gmail.com\n"
            "  ALERT_EMAIL_PASSWORD=xxxx xxxx xxxx xxxx\n"
            "  ALERT_EMAIL_TO=destinataire@email.com"
        )
        return False

    ok = send_daily_digest(days_back=days_back)
    if ok:
        logger.info(f"✅ Digest envoyé ({datetime.now().strftime('%d/%m/%Y %H:%M')})")
    else:
        logger.error("❌ Échec de l'envoi")
    return ok


def start_scheduler(send_time: str = "08:00"):
    """Start APScheduler to send digest every day at send_time."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    hour, minute = send_time.split(":")
    scheduler = BlockingScheduler(timezone="Europe/Paris")

    scheduler.add_job(
        run_digest,
        CronTrigger(hour=int(hour), minute=int(minute)),
        id="daily_digest",
        name=f"Digest email quotidien à {send_time}",
        replace_existing=True,
    )

    logger.info(f"⏰ Scheduler démarré — digest envoyé tous les jours à {send_time} (Paris)")
    logger.info("   Ctrl+C pour arrêter")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler arrêté.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheduler alertes email Techunt")
    parser.add_argument("--test", action="store_true", help="Envoie le digest immédiatement")
    parser.add_argument("--time", default="08:00", help="Heure d'envoi (défaut: 08:00)")
    parser.add_argument("--days", type=int, default=1, help="Jours en arrière pour le digest (défaut: 1)")
    args = parser.parse_args()

    if args.test:
        logger.info("🧪 Mode test — envoi immédiat du digest")
        run_digest(days_back=args.days)
    else:
        start_scheduler(send_time=args.time)

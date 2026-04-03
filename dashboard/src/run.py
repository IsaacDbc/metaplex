"""
Point d'entrée CLI + scheduler automatique.

Usage:
  # Lancer le pipeline une fois
  python run.py --once

  # Lancer le dashboard + pipeline auto toutes les heures
  python run.py --dashboard

  # Lancer seulement le scheduler en arrière-plan
  python run.py --scheduler

  # Forcer un refresh immédiat
  python run.py --refresh
"""
import argparse
import logging
import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console
from rich.logging import RichHandler

sys.path.insert(0, os.path.dirname(__file__))
from storage import init_db
from pipeline import run_pipeline

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)

DASHBOARD_FILE = Path(__file__).parent / "dashboard.py"
LOCK_FILE = Path(__file__).parent.parent / "data" / ".pipeline_running"


def scheduled_job():
    """Job exécuté par le scheduler."""
    if LOCK_FILE.exists():
        logger.warning("Pipeline déjà en cours, skip.")
        return

    try:
        LOCK_FILE.touch()
        console.rule(f"[yellow]🔄 Pipeline auto — {datetime.now().strftime('%d/%m %H:%M')}")
        stats = run_pipeline(verbose=True)
        console.print(f"[green]✅ Pipeline terminé : {stats}")
    except Exception as e:
        logger.error(f"Erreur pipeline : {e}")
    finally:
        LOCK_FILE.unlink(missing_ok=True)


def launch_dashboard():
    """Lance Streamlit dans un sous-processus."""
    console.print("[bold cyan]🚀 Lancement du tableau de bord Streamlit…")
    console.print("[dim]→ http://localhost:8501[/dim]")
    try:
        subprocess.run(
            [
                sys.executable, "-m", "streamlit", "run",
                str(DASHBOARD_FILE),
                "--server.port", "8501",
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false",
            ],
            check=True,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard arrêté.")
    except FileNotFoundError:
        console.print("[red]Streamlit non trouvé. Lance: pip install streamlit")


def launch_scheduler(interval_minutes: int = 60):
    """Lance le scheduler APScheduler."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduled_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="pipeline",
        name="Veille Recrutement Tech",
        replace_existing=True,
        next_run_time=datetime.now(),  # Run immediately on start
    )
    scheduler.start()
    console.print(
        f"[green]⏰ Scheduler démarré — refresh toutes les {interval_minutes} minutes"
    )
    console.print("[dim]Ctrl+C pour arrêter[/dim]")

    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        console.print("[yellow]Scheduler arrêté.")


def main():
    parser = argparse.ArgumentParser(
        description="Veille Recrutement Tech — Pipeline + Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Exécuter le pipeline une seule fois et quitter",
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Lancer le dashboard Streamlit (+ pipeline auto en arrière-plan)",
    )
    parser.add_argument(
        "--scheduler", action="store_true",
        help="Lancer seulement le scheduler (sans dashboard)",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Forcer un refresh immédiat du pipeline",
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="Intervalle de refresh en minutes (défaut: 60)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Logs détaillés",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Init DB
    init_db()

    if args.once or args.refresh:
        console.rule("[bold yellow]🔄 Exécution pipeline")
        stats = run_pipeline(verbose=True)
        console.print(f"\n[bold green]✅ Terminé : {stats}")

    elif args.scheduler:
        launch_scheduler(args.interval)

    elif args.dashboard:
        # Start scheduler in background, then launch streamlit
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            scheduled_job,
            trigger=IntervalTrigger(minutes=args.interval),
            id="pipeline",
            next_run_time=datetime.now(),
        )
        scheduler.start()
        console.print(
            f"[green]⏰ Scheduler démarré ({args.interval}min)"
        )

        # Run initial pipeline immediately in background
        console.rule("[bold yellow]🔄 Pipeline initial")
        try:
            run_pipeline(verbose=True)
        except Exception as e:
            logger.warning(f"Pipeline initial échoué : {e}")

        # Launch dashboard
        launch_dashboard()
        scheduler.shutdown()

    else:
        # Default: run once + show instructions
        console.rule("[bold yellow]🎯 Veille Recrutement Tech")
        console.print("\n[cyan]Commandes disponibles:")
        console.print("  [bold]python run.py --once[/bold]       → Pipeline une fois")
        console.print("  [bold]python run.py --dashboard[/bold]  → Dashboard + auto-refresh")
        console.print("  [bold]python run.py --scheduler[/bold]  → Scheduler seul")
        console.print("\n[dim]Exemple rapide: python run.py --once && streamlit run dashboard.py")
        console.print("\n")
        console.print("[yellow]Lancement du pipeline initial…")
        stats = run_pipeline(verbose=True)
        console.print(f"\n[bold green]✅ Pipeline terminé : {stats}")
        console.print("\n[cyan]Lance maintenant le dashboard avec:")
        console.print("  [bold]streamlit run dashboard.py[/bold]")


if __name__ == "__main__":
    main()

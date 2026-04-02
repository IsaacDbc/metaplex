"""
Recruiter Contact Scraper — main entry point.

Usage:
  python main.py [options]

Examples:
  # Search for HR contacts in Paris tech companies
  python main.py --roles "Head of Talent" "DRH" --regions "Paris" --industries "startup tech" "SaaS"

  # Search Hunter.io for specific company domains
  python main.py --hunter-domains stripe.com doctolib.fr contentsquare.com

  # Scrape specific company websites
  python main.py --company-urls https://www.contentsquare.com https://www.dataiku.com

  # Full pipeline: search + enrich + export
  python main.py --roles "Head of Talent" --regions "Paris" --enrich --output results.csv
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv(Path(__file__).parent.parent / ".env")

from config import TARGET_ROLES, TARGET_REGIONS, TARGET_INDUSTRIES
from models import Contact
from utils import deduplicate_contacts
from export import to_csv, to_json, print_summary
import scrapers.google_search as google_scraper
import scrapers.linkedin_scraper as linkedin_scraper
import scrapers.hunter_io as hunter_scraper
import scrapers.company_websites as company_scraper

console = Console()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scraper de contacts RH/Talent pour le recrutement tech",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--roles", nargs="+", default=TARGET_ROLES[:5],
        metavar="ROLE",
        help='Job titles to search (default: top 5 from config). E.g. "Head of Talent" "DRH"',
    )
    parser.add_argument(
        "--regions", nargs="+", default=["Paris", "France"],
        metavar="REGION",
        help="Geographic regions to search in (default: Paris, France)",
    )
    parser.add_argument(
        "--industries", nargs="+", default=TARGET_INDUSTRIES[:3],
        metavar="INDUSTRY",
        help="Industry keywords (default: top 3 from config)",
    )

    # Source selection
    parser.add_argument("--no-google", action="store_true", help="Skip Google/Bing search")
    parser.add_argument("--no-linkedin", action="store_true", help="Skip LinkedIn scraper")
    parser.add_argument(
        "--hunter-domains", nargs="+", default=[], metavar="DOMAIN",
        help="Company domains to search via Hunter.io API",
    )
    parser.add_argument(
        "--company-urls", nargs="+", default=[], metavar="URL",
        help="Company website URLs to scrape for team/contact pages",
    )

    # Enrichment
    parser.add_argument(
        "--enrich", action="store_true",
        help="Enrich contacts with Hunter.io email finder/verifier",
    )

    # Output
    parser.add_argument(
        "--output", default="", metavar="FILENAME",
        help="Output CSV filename (default: contacts_TIMESTAMP.csv)",
    )
    parser.add_argument(
        "--output-dir", default="output", metavar="DIR",
        help="Output directory (default: ./output)",
    )
    parser.add_argument("--json", action="store_true", help="Also export JSON")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum confidence score filter (0-1)")

    # Misc
    parser.add_argument("--proxy", default="", help="Proxy URL (e.g. http://user:pass@host:port)")
    parser.add_argument("--max-pages", type=int, default=3, help="Max LinkedIn pages per query (default: 3)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    console.rule("[bold blue]Recruiter Contact Scraper")
    console.print(f"[cyan]Roles:[/cyan] {', '.join(args.roles)}")
    console.print(f"[cyan]Regions:[/cyan] {', '.join(args.regions)}")
    console.print(f"[cyan]Industries:[/cyan] {', '.join(args.industries)}")
    console.print()

    all_contacts: list[Contact] = []

    # --- Google/Bing search ---
    if not args.no_google:
        console.print("[bold yellow]► Google/Bing search...[/bold yellow]")
        count = 0
        for contact in google_scraper.run(
            roles=args.roles,
            regions=args.regions,
            industries=args.industries,
            proxy=args.proxy or None,
        ):
            all_contacts.append(contact)
            count += 1
            if count % 10 == 0:
                console.print(f"  {count} contacts found so far...")
        console.print(f"  [green]✓ {count} contacts from web search[/green]")

    # --- LinkedIn ---
    if not args.no_linkedin:
        console.print("[bold yellow]► LinkedIn search...[/bold yellow]")
        li_at = os.getenv("LINKEDIN_LI_AT", "")
        if not li_at:
            console.print("  [dim]Skipping LinkedIn (LINKEDIN_LI_AT not set in .env)[/dim]")
        else:
            count = 0
            for contact in linkedin_scraper.run(
                roles=args.roles,
                regions=args.regions,
                max_pages=args.max_pages,
                proxy=args.proxy or None,
            ):
                all_contacts.append(contact)
                count += 1
            console.print(f"  [green]✓ {count} contacts from LinkedIn[/green]")

    # --- Hunter.io domain search ---
    if args.hunter_domains:
        console.print("[bold yellow]► Hunter.io domain search...[/bold yellow]")
        api_key = os.getenv("HUNTER_API_KEY", "")
        if not api_key:
            console.print("  [dim]Skipping Hunter.io (HUNTER_API_KEY not set in .env)[/dim]")
        else:
            hr_keywords = ["hr", "talent", "people", "recruitment", "rh", "drh", "procurement"]
            contacts = hunter_scraper.run_domain_search(args.hunter_domains, hr_keywords)
            all_contacts.extend(contacts)
            console.print(f"  [green]✓ {len(contacts)} contacts from Hunter.io[/green]")

    # --- Company website scraper ---
    if args.company_urls:
        console.print("[bold yellow]► Company website scraper...[/bold yellow]")
        count = 0
        for contact in company_scraper.run(args.company_urls, proxy=args.proxy or None):
            all_contacts.append(contact)
            count += 1
        console.print(f"  [green]✓ {count} contacts from company websites[/green]")

    if not all_contacts:
        console.print("[red]No contacts found. Try different roles, regions, or add API keys.[/red]")
        return

    # --- Deduplication ---
    before = len(all_contacts)
    all_contacts = deduplicate_contacts(all_contacts)
    console.print(f"\n[cyan]Deduplication:[/cyan] {before} → {len(all_contacts)} unique contacts")

    # --- Enrichment ---
    if args.enrich and os.getenv("HUNTER_API_KEY"):
        console.print("[bold yellow]► Enriching with Hunter.io...[/bold yellow]")
        hr_keywords = ["hr", "talent", "people", "recruitment", "rh", "drh", "procurement"]
        enriched = 0
        for i, c in enumerate(all_contacts):
            if c.first_name and c.last_name and not c.email:
                from scrapers.hunter_io import enrich_contact_with_hunter
                all_contacts[i] = enrich_contact_with_hunter(c, hr_keywords)
                enriched += 1
        console.print(f"  [green]✓ Enriched {enriched} contacts[/green]")

    # --- Filter by score ---
    if args.min_score > 0:
        all_contacts = [c for c in all_contacts if c.confidence_score >= args.min_score]
        console.print(f"[cyan]After score filter ({args.min_score}):[/cyan] {len(all_contacts)} contacts")

    # --- Export ---
    console.rule("[bold blue]Results")
    print_summary(all_contacts)

    output_dir = args.output_dir
    csv_path = to_csv(all_contacts, output_dir=output_dir, filename=args.output)
    if csv_path:
        console.print(f"\n[bold green]CSV exported:[/bold green] {csv_path}")

    if args.json:
        json_path = to_json(all_contacts, output_dir=output_dir)
        if json_path:
            console.print(f"[bold green]JSON exported:[/bold green] {json_path}")

    console.print(f"\n[bold]Total:[/bold] {len(all_contacts)} contacts exported.")


if __name__ == "__main__":
    main()

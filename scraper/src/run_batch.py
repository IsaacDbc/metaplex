"""
Batch run: scrape a large list of French tech companies for HR/talent contacts.
Uses company website scraping + Google/Bing search.
"""
import os
import sys
import logging
sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.logging import RichHandler

from models import Contact
from utils import deduplicate_contacts
from export import to_csv, to_json, print_summary
import scrapers.company_websites as company_scraper
import scrapers.google_search as google_scraper

logging.basicConfig(level=logging.WARNING, handlers=[RichHandler()])
console = Console()

# ---- Big list of French tech companies ----
COMPANY_URLS = [
    # Licornes / scale-ups FR
    "https://www.doctolib.fr",
    "https://www.contentsquare.com",
    "https://www.dataiku.com",
    "https://www.payfit.com",
    "https://www.pennylane.com",
    "https://www.spendesk.com",
    "https://www.qonto.com",
    "https://www.alan.com",
    "https://www.back.market",
    "https://www.mirakl.com",
    "https://www.meero.com",
    "https://www.swile.co",
    "https://www.360learning.com",
    "https://www.inato.com",
    "https://www.ledger.com",
    "https://www.vestiairecollective.com",
    "https://www.teads.com",
    "https://www.kyriba.com",
    "https://www.doctrine.fr",
    "https://www.captive.ai",

    # ESN / recrutement tech
    "https://www.soprasteria.com",
    "https://www.capgemini.com",
    "https://www.alten.com",
    "https://www.altran.com",
    "https://www.devoteam.com",
    "https://www.aubay.com",
    "https://www.sqli.com",
    "https://www.wavestone.com",
    "https://www.synapse.fr",
    "https://www.experis.fr",
    "https://www.hays.fr",
    "https://www.michael-page.fr",
    "https://www.robertwalters.fr",
    "https://www.talent.io",
    "https://www.welcometothejungle.com",

    # Fintech / insurtech
    "https://www.shine.fr",
    "https://www.lydia-app.com",
    "https://www.leocare.eu",
    "https://www.luko.eu",
    "https://www.younited-credit.com",
    "https://www.floa.bank",
    "https://www.mango-pay.com",
    "https://www.treezor.com",

    # SaaS / B2B tech
    "https://www.livestorm.co",
    "https://www.slite.com",
    "https://www.crisp.chat",
    "https://www.brevo.com",
    "https://www.axeptio.eu",
    "https://www.talkspirit.com",
    "https://www.ringover.com",
    "https://www.aircall.io",
    "https://www.dougs.fr",
    "https://www.indy.fr",
    "https://www.sellsy.fr",
    "https://www.modjo.ai",
    "https://www.salesloft.com",

    # Deep tech / AI
    "https://www.owkin.com",
    "https://www.nabla.com",
    "https://www.pixelgen.ai",
    "https://www.mistral.ai",
    "https://www.bioptimus.com",
    "https://www.ikigai.ai",

    # E-commerce / marketplace
    "https://www.vinted.fr",
    "https://www.leboncoin.fr",
    "https://www.malt.fr",
    "https://www.legalplace.fr",
    "https://www.brigad.co",
    "https://www.jow.fr",

    # Mobility / logistique
    "https://www.Shipup.co",
    "https://www.stuart.com",
    "https://www.convelio.com",
    "https://www.ovrsea.com",
    "https://www.kargotech.com",

    # Healthtech
    "https://www.lifen.fr",
    "https://www.synapse-medicine.com",
    "https://www.mesvaccins.net",
    "https://www.epione.fr",

    # Cybersecurity
    "https://www.sekoia.io",
    "https://www.vade.com",
    "https://www.alsid.com",
    "https://www.stormshield.com",

    # HR Tech
    "https://www.lucca.fr",
    "https://www.javelo.io",
    "https://www.elevo.fr",
    "https://www.gymlib.com",
    "https://www.maki-people.com",
    "https://www.worklife.eu",
]

ROLES = [
    "DRH",
    "Directeur des Ressources Humaines",
    "Head of Talent",
    "Head of Talent Acquisition",
    "Head of People",
    "Talent Acquisition Manager",
    "Responsable RH",
    "Chief People Officer",
    "VP People",
    "Head of Recruitment",
    "Head of HR",
    "CHRO",
    "Head of Procurement",
]

REGIONS = ["Paris", "France", "Lyon", "Bordeaux", "Nantes"]
INDUSTRIES = ["startup tech", "SaaS", "fintech", "scale-up", "ESN"]

def main():
    all_contacts: list[Contact] = []

    # --- Company website scraping ---
    console.rule("[bold yellow]Scraping company websites")
    console.print(f"[cyan]{len(COMPANY_URLS)} companies in list[/cyan]")

    count = 0
    for contact in company_scraper.run(COMPANY_URLS):
        all_contacts.append(contact)
        count += 1
        if count % 5 == 0:
            console.print(f"  {count} contacts found...")

    console.print(f"[green]✓ {count} contacts from company websites[/green]")

    # --- Google/Bing search ---
    console.rule("[bold yellow]Google/Bing search")
    count_web = 0
    for contact in google_scraper.run(
        roles=ROLES[:6],
        regions=REGIONS[:3],
        industries=INDUSTRIES[:3],
    ):
        all_contacts.append(contact)
        count_web += 1
        if count_web % 10 == 0:
            console.print(f"  {count_web} contacts from web...")

    console.print(f"[green]✓ {count_web} contacts from web search[/green]")

    # --- Dedup ---
    before = len(all_contacts)
    all_contacts = deduplicate_contacts(all_contacts)
    console.print(f"\n[cyan]Dedup:[/cyan] {before} → {len(all_contacts)} unique")

    # --- Export ---
    console.rule("[bold blue]Export")
    print_summary(all_contacts)

    csv_path = to_csv(all_contacts, output_dir="../output", filename="contacts_tech_hr.csv")
    json_path = to_json(all_contacts, output_dir="../output", filename="contacts_tech_hr.json")

    console.print(f"\n[bold green]CSV:[/bold green] {csv_path}")
    console.print(f"[bold green]JSON:[/bold green] {json_path}")
    console.print(f"[bold]Total: {len(all_contacts)} contacts[/bold]")

if __name__ == "__main__":
    main()

"""
Data models for scraped contacts.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime


@dataclass
class Contact:
    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    job_title: str = ""
    company: str = ""
    company_website: str = ""
    company_industry: str = ""
    company_size: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    location: str = ""
    source: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    confidence_score: float = 0.0  # 0-1, based on data completeness
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def compute_score(self):
        """Score based on how complete the contact data is."""
        score = 0.0
        if self.full_name:
            score += 0.2
        if self.job_title:
            score += 0.15
        if self.company:
            score += 0.15
        if self.email:
            score += 0.3
        if self.phone:
            score += 0.1
        if self.linkedin_url:
            score += 0.1
        self.confidence_score = round(score, 2)
        return self

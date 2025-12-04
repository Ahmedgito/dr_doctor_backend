"""Doctor parsing logic for Marham platform."""

from __future__ import annotations

from typing import List, Optional
from bs4 import BeautifulSoup

from scrapers.models.doctor_model import DoctorModel
from scrapers.utils.parser_helpers import clean_text

BASE_URL = "https://www.marham.pk"


class DoctorParser:
    """Parser for extracting doctor data from Marham HTML."""

    PLATFORM = "marham"

    @staticmethod
    def parse_doctor_card(card: BeautifulSoup, hospital_url: str) -> Optional[DoctorModel]:
        """Parse a doctor card element into a DoctorModel.
        
        Args:
            card: BeautifulSoup element representing a doctor card
            hospital_url: URL of the hospital this doctor is associated with
            
        Returns:
            DoctorModel instance or None if parsing fails
        """
        try:
            name_tag = card.select_one("a.dr_profile_opened_from_hospital_profile h3, h3")
            name = clean_text(name_tag.get_text()) if name_tag else None

            parent_a = name_tag.parent if name_tag else None
            profile_href = parent_a.get("href") if parent_a and parent_a.has_attr("href") else None
            profile_url = f"{BASE_URL}{profile_href}" if profile_href and profile_href.startswith("/") else profile_href

            specialty_tag = card.select_one("p.mb-0.text-sm")
            specialty = [clean_text(specialty_tag.get_text())] if specialty_tag and clean_text(specialty_tag.get_text()) else []

            qualifications_tag = card.select_one('p.text-sm:not(.mb-0)')
            qualifications = clean_text(qualifications_tag.get_text()) if qualifications_tag else None

            experience_tag = card.select_one('.row .col-4:nth-child(2) p.text-bold.text-sm')
            experience = clean_text(experience_tag.get_text()) if experience_tag else None

            if not name or not profile_url:
                return None

            # Create a minimal doctor model; hospital affiliations are set later
            model = DoctorModel(
                name=name,
                specialty=specialty,
                fees=None,
                city="Karachi",
                area=None,
                hospital=None,
                hospitals=None,
                address=None,
                rating=None,
                experience=experience,
                profile_url=profile_url,
                platform=DoctorParser.PLATFORM,
            )
            return model
        except Exception as exc:  # noqa: BLE001
            from scrapers.logger import logger
            logger.warning("Failed to parse doctor card on {}: {}", hospital_url, exc)
            return None

    @staticmethod
    def extract_doctors_from_list(html: str, hospital_url: str) -> List[dict]:
        """Extract doctor names and URLs from the doctor list in the 'About' section.
        
        Format: <ul><li><a href="...">Dr. Name</a></li></ul>
        
        Args:
            html: HTML content of the hospital page
            hospital_url: URL of the hospital page
            
        Returns:
            List of dicts with keys: name, profile_url, hospital_url
        """
        soup = BeautifulSoup(html, "html.parser")
        doctors_from_list = []
        
        # Look for doctor list links in the About section
        doctor_list_links = soup.select("div.row.justify-content-center ul li a")
        for link in doctor_list_links:
            doctor_name = clean_text(link.get_text())
            doctor_href = link.get("href")
            
            if doctor_name and doctor_href:
                profile_url = f"{BASE_URL}{doctor_href}" if doctor_href.startswith("/") else doctor_href
                doctors_from_list.append({
                    "name": doctor_name,
                    "profile_url": profile_url,
                    "hospital_url": hospital_url,
                })
                from scrapers.logger import logger
                logger.info("Found doctor in About list: {} -> {}", doctor_name, profile_url)
        
        return doctors_from_list


"""Hospital parsing logic for Marham platform."""

from __future__ import annotations

from typing import List
from bs4 import BeautifulSoup

from scrapers.utils.parser_helpers import clean_text

BASE_URL = "https://www.marham.pk"


class HospitalParser:
    """Parser for extracting hospital data from Marham HTML."""

    PLATFORM = "marham"

    @staticmethod
    def parse_hospital_cards(html: str) -> List[dict]:
        """Parse hospital cards from listing page HTML.
        
        Args:
            html: HTML content of the hospital listing page
            
        Returns:
            List of hospital dictionaries with name, city, area, address, url
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".row.shadow-card")
        hospitals: List[dict] = []

        for card in cards:
            # Extract name and URL from the main hospital link
            name_tag = card.select_one(".hosp_list_selected_hosp_name")
            if not name_tag:
                continue

            # Full text includes city at end (e.g., "Hashmanis Hospital - M A Jinnah Road, Karachi")
            full_name = clean_text(name_tag.get_text())
            href = name_tag.get("href") if name_tag.has_attr("href") else None
            url = href if href and href.startswith("http") else f"{BASE_URL}{href}" if href else None

            if not url or not full_name:
                continue

            # Split name and city: last part after comma is the city
            parts = full_name.rsplit(",", 1)
            name = clean_text(parts[0]) if parts else full_name
            city = clean_text(parts[1]) if len(parts) > 1 else "Karachi"

            # Extract address: look for p.text-sm elements (skip the empty one)
            address_paragraphs = card.select("p.text-sm")
            address = None
            for p in address_paragraphs:
                text = clean_text(p.get_text())
                if text:  # Skip empty paragraphs
                    address = text
                    break

            # Extract area from address (last part before the city)
            # e.g., "JM-75, Off M A Jinnah Road, Jacob Lines, Karachi" → "Jacob Lines"
            area = None
            if address:
                address_parts = address.rsplit(",", 1)
                if len(address_parts) > 1:
                    # Remove city from the end and get the last comma-separated part
                    remaining = address_parts[0]
                    remaining_parts = remaining.rsplit(",", 1)
                    area = clean_text(remaining_parts[1]) if len(remaining_parts) > 1 else None

            hospital = {
                "name": name,
                "city": city,
                "area": area,
                "address": address,
                "platform": HospitalParser.PLATFORM,
                "url": url,
            }

            hospitals.append(hospital)

        return hospitals

    @staticmethod
    def parse_full_hospital(html: str, url: str) -> dict:
        """Parse hospital page to extract enriched hospital information.
        
        Args:
            html: HTML content of the hospital detail page
            url: URL of the hospital page
            
        Returns:
            Dictionary with enriched hospital data including specialties, timing, about text
        """
        soup = BeautifulSoup(html, "html.parser")
        
        def _first(el):
            return el.get_text(strip=True) if el else None

        name = clean_text(_first(soup.select_one(".hospital-title, h1, .hosp_name")))
        address = clean_text(_first(soup.select_one(".address, .hospital-address, p.text-sm")))
        city = clean_text(_first(soup.select_one(".city"))) or "Karachi"
        area = clean_text(_first(soup.select_one(".area")))
        timing = clean_text(_first(soup.select_one(".timing, .hospital-timing")))

        # Extract specialties list from the hospital page
        specialties: List[str] = []
        specialty_links = soup.select("a.hosp_prof_selected_speciality")
        for link in specialty_links:
            spec_text = clean_text(link.get_text())
            if spec_text and spec_text not in specialties:
                specialties.append(spec_text)

        # Extract "About" description from the hospital page
        about_text = None
        about_div = soup.select_one("div.row.justify-content-center")
        if about_div:
            # Extract all text content from paragraphs and lists in the about section
            paragraphs = about_div.select("p")
            about_parts = []
            for p in paragraphs:
                p_text = clean_text(p.get_text())
                if p_text:
                    about_parts.append(p_text)
            
            if about_parts:
                # Join first few paragraphs to create a summary (limit to ~500 chars for brevity)
                about_text = " ".join(about_parts[:3])  # Take first 3 paragraphs
                if len(about_text) > 500:
                    about_text = about_text[:500] + "..."

        return {
            "name": name,
            "address": address,
            "city": city,
            "area": area,
            "platform": HospitalParser.PLATFORM,
            "url": url,
            "timing": timing,
            "specialties": specialties,
            "about": about_text,
        }


"""Hospital parsing logic for Marham platform."""

from __future__ import annotations

import re
from typing import List
from bs4 import BeautifulSoup

from scrapers.utils.parser_helpers import clean_text
from scrapers.utils.url_parser import parse_hospital_url

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
            url: URL of the hospital page (format: marham.pk/hospitals/(city)/(name)/(area))
            
        Returns:
            Dictionary with enriched hospital data including specialties, timing, about text
        """
        soup = BeautifulSoup(html, "html.parser")
        
        def _first(el):
            return el.get_text(strip=True) if el else None

        # Extract city, name, area from URL first (most reliable)
        url_parts = parse_hospital_url(url)
        
        name = clean_text(_first(soup.select_one(".hospital-title, h1, .hosp_name"))) or url_parts.get("name")
        address = clean_text(_first(soup.select_one(".address, .hospital-address, p.text-sm")))
        city = url_parts.get("city") or clean_text(_first(soup.select_one(".city"))) or "Karachi"
        area = url_parts.get("area") or clean_text(_first(soup.select_one(".area")))
        timing = clean_text(_first(soup.select_one(".timing, .hospital-timing")))

        # Extract specialties list from the hospital page
        specialties: List[str] = []
        specialty_links = soup.select("a.hosp_prof_selected_speciality")
        for link in specialty_links:
            spec_text = clean_text(link.get_text())
            if spec_text and spec_text not in specialties:
                specialties.append(spec_text)

        # Parse comprehensive About section
        about_data = HospitalParser._parse_about_section(soup)
        
        # Extract doctor list from About section
        doctors_list = HospitalParser._extract_doctors_from_about(soup)
        
        result = {
            "name": name,
            "address": address,
            "city": city,
            "area": area,
            "platform": HospitalParser.PLATFORM,
            "url": url,
            "timing": timing,
            "specialties": specialties,
        }
        
        # Merge about section data
        result.update(about_data)
        
        # Add doctor list (will be updated with full info in Phase 2)
        if doctors_list:
            result["doctors"] = doctors_list
        
        return result
    
    @staticmethod
    def _extract_doctors_from_about(soup: BeautifulSoup) -> List[dict]:
        """Extract doctor names and URLs from the About section doctor list.
        
        Returns list of dicts with keys: name, profile_url
        """
        doctors = []
        try:
            about_section = soup.select_one("div.row.justify-content-center, div.col-12.col-md-8")
            if not about_section:
                return doctors
            
            # Look for "Doctor list" section
            for h2 in about_section.select("h2"):
                h2_text = clean_text(h2.get_text())
                if "Doctor list" in h2_text or "doctors" in h2_text.lower():
                    # Get the ul list after this h2
                    next_ul = h2.find_next_sibling("ul") or h2.find_next("ul")
                    if next_ul:
                        for li in next_ul.select("li"):
                            # Check for links
                            link = li.select_one("a")
                            if link:
                                doctor_name = clean_text(link.get_text())
                                doctor_href = link.get("href")
                                if doctor_name and doctor_href:
                                    # Only include doctor URLs, not hospital URLs
                                    if "/doctors/" in doctor_href:
                                        profile_url = f"{BASE_URL}{doctor_href}" if doctor_href.startswith("/") else doctor_href
                                        doctors.append({
                                            "name": doctor_name,
                                            "profile_url": profile_url,
                                        })
                    break
        except Exception:
            pass
        
        return doctors

    @staticmethod
    def _parse_about_section(soup: BeautifulSoup) -> dict:
        """Parse the comprehensive About section from hospital page.
        
        Extracts: about text, founded year, achievements, departments, procedures,
        facilities, support services, fees, contact number.
        """
        result = {}
        
        try:
            # Find the About section
            about_section = soup.select_one("div.row.justify-content-center, div.col-12.col-md-8")
            
            if not about_section:
                # Fallback: look for h2 containing "About"
                for div in soup.select("div"):
                    h2 = div.select_one("h2")
                    if h2 and "About" in h2.get_text():
                        about_section = div
                        break
            
            if about_section:
                full_text = about_section.get_text()
                
                # Extract full about text (all paragraphs)
                paragraphs = about_section.select("p")
                about_parts = []
                for p in paragraphs:
                    p_text = clean_text(p.get_text())
                    if p_text:
                        about_parts.append(p_text)
                
                if about_parts:
                    result["about"] = " ".join(about_parts)
                
                # Extract founded year
                import re
                founded_match = re.search(r"founded\s+in\s+(\d{4})", full_text, re.IGNORECASE)
                if founded_match:
                    try:
                        result["founded_year"] = int(founded_match.group(1))
                    except (ValueError, AttributeError):
                        pass
                
                # Extract achievements/proud moments
                achievements = []
                # Look for section with "Proud Moments" or "achievements"
                for h2 in about_section.select("h2"):
                    h2_text = clean_text(h2.get_text())
                    if "Proud Moments" in h2_text or "achievements" in h2_text.lower():
                        # Get the ul list after this h2
                        next_ul = h2.find_next_sibling("ul") or h2.find_next("ul")
                        if next_ul:
                            for li in next_ul.select("li"):
                                achievement_text = clean_text(li.get_text())
                                if achievement_text:
                                    achievements.append(achievement_text)
                        break
                
                if achievements:
                    result["achievements"] = achievements
                
                # Extract clinical departments
                departments = []
                for h2 in about_section.select("h2"):
                    h2_text = clean_text(h2.get_text())
                    if "Clinical Departments" in h2_text:
                        next_ul = h2.find_next_sibling("ul") or h2.find_next("ul")
                        if next_ul:
                            for li in next_ul.select("li"):
                                dept_text = clean_text(li.get_text())
                                if dept_text and dept_text not in departments:
                                    departments.append(dept_text)
                        break
                
                if departments:
                    result["clinical_departments"] = departments
                
                # Extract specialized procedures (organized by category)
                procedures = {}
                current_category = None
                
                for h3 in about_section.select("h3"):
                    h3_text = clean_text(h3.get_text())
                    # Check if it's a procedure category (contains numbers like "1-", "2-")
                    if re.match(r"^\d+[-–]", h3_text):
                        # Extract category name (remove number prefix)
                        category = re.sub(r"^\d+[-–]\s*", "", h3_text).strip()
                        current_category = category
                        procedures[category] = []
                        
                        # Get procedures from next ul
                        next_ul = h3.find_next_sibling("ul") or h3.find_next("ul")
                        if next_ul:
                            for li in next_ul.select("li"):
                                proc_text = clean_text(li.get_text())
                                if proc_text:
                                    procedures[category].append(proc_text)
                
                if procedures:
                    result["specialized_procedures"] = procedures
                
                # Extract facilities and services
                facilities = []
                for h2 in about_section.select("h2"):
                    h2_text = clean_text(h2.get_text())
                    if "Facilities and Services" in h2_text or "Facilities" in h2_text:
                        # Get all ul lists after this h2
                        next_elements = h2.find_next_siblings()
                        for elem in next_elements:
                            if elem.name == "ul":
                                for li in elem.select("li"):
                                    facility_text = clean_text(li.get_text())
                                    if facility_text:
                                        facilities.append(facility_text)
                            elif elem.name == "h2":  # Stop at next section
                                break
                        break
                
                if facilities:
                    result["facilities"] = facilities
                
                # Extract clinical support services
                support_services = []
                for h2 in about_section.select("h2"):
                    h2_text = clean_text(h2.get_text())
                    if "Clinical support services" in h2_text or "support services" in h2_text.lower():
                        next_ul = h2.find_next_sibling("ul") or h2.find_next("ul")
                        if next_ul:
                            for li in next_ul.select("li"):
                                service_text = clean_text(li.get_text())
                                if service_text:
                                    support_services.append(service_text)
                        break
                
                if support_services:
                    result["clinical_support_services"] = support_services
                
                # Extract fees range
                fees_match = re.search(r"fee[s]?\s+(?:at|ranges?|between)\s+([^.]*)", full_text, re.IGNORECASE)
                if fees_match:
                    fees_text = clean_text(fees_match.group(1))
                    if fees_text:
                        result["fees_range"] = fees_text
                
                # Extract contact number
                contact_match = re.search(r"contact\s+(?:number|at)?[:\s]+([\d-]+)", full_text, re.IGNORECASE)
                if contact_match:
                    result["contact_number"] = contact_match.group(1).strip()
                else:
                    # Try alternative pattern: "helpline at 0311-1222398"
                    helpline_match = re.search(r"helpline\s+(?:at|:)?\s*([\d-]+)", full_text, re.IGNORECASE)
                    if helpline_match:
                        result["contact_number"] = helpline_match.group(1).strip()
                
        except Exception as e:
            from scrapers.logger import logger
            logger.debug("Error parsing about section: {}", e)
        
        return result


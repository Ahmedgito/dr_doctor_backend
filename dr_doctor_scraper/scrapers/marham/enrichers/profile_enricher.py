"""Profile enrichment logic for Marham doctors."""

from __future__ import annotations

from typing import List, Optional
from bs4 import BeautifulSoup

from scrapers.models.doctor_model import DoctorModel
from scrapers.utils.parser_helpers import clean_text

BASE_URL = "https://www.marham.pk"


class ProfileEnricher:
    """Enriches doctor profiles with detailed information from profile pages."""

    @staticmethod
    def parse_doctor_profile(html: str) -> dict:
        """Parse a doctor's profile page HTML for specialties, PMDC verification, practices, etc.
        
        Args:
            html: HTML content of the doctor's profile page
            
        Returns:
            Dictionary with enriched data: specialties, pmdc_verified, practices, 
            qualifications, experience_years, work_history
        """
        soup = BeautifulSoup(html, "html.parser")
        result = {"specialties": [], "pmdc_verified": False}

        # PMDC verified badge: look for a green text badge containing 'PMDC' or 'PMDC Verified'
        try:
            badge = soup.select_one("span.text-green.text-bold")
            if badge and "PMDC" in badge.get_text():
                result["pmdc_verified"] = True
        except Exception:
            result["pmdc_verified"] = False

        # Specialties: look for a strong.text-sm inside header or intro paragraph
        try:
            spec_tag = soup.select_one("p.mt-10 strong.text-sm, strong.text-sm")
            if spec_tag:
                text = spec_tag.get_text(separator=",")
                parts = [clean_text(p) for p in text.split(",") if clean_text(p)]
                result["specialties"] = parts
        except Exception:
            result["specialties"] = []

        # Parse practice entries (per-hospital fee/timings/location)
        practices = ProfileEnricher._parse_practices(soup)
        result["practices"] = practices

        # Parse qualifications from Qualification table
        qualifications = ProfileEnricher._parse_qualifications(soup)
        result["qualifications"] = qualifications

        # Parse experience: years of practice and work history
        experience_years, work_history = ProfileEnricher._parse_experience(soup)
        result["experience_years"] = experience_years
        result["work_history"] = work_history

        return result

    @staticmethod
    def _parse_practices(soup: BeautifulSoup) -> List[dict]:
        """Parse practice entries from the profile page."""
        practices = []
        try:
            # Find section by header text
            sections = soup.select("section")
            target = None
            for sec in sections:
                h2 = sec.select_one("h2")
                if h2 and "Practice Address" in h2.get_text():
                    target = sec
                    break

            if not target:
                # fallback: search by class or h2 text
                target = soup.select_one("section.p-xy") or soup.select_one("section")

            if target:
                cards = target.select("div.mt-4.row.cursor-pointer")
                for c in cards:
                    try:
                        h_id = c.get("h_id")
                        d_id = c.get("d_id")
                        # hospital link (callcenter) if present
                        a = c.select_one("a.pc_practice_detail_card_dr_profile_tapped, a.oc_practice_detail_card_dr_profile_tapped")
                        hospital_url = None
                        if a and a.has_attr("href"):
                            hospital_url = a.get("href")
                            if hospital_url and hospital_url.startswith("/"):
                                hospital_url = f"{BASE_URL}{hospital_url}"

                        hospital_name_tag = c.select_one("h3")
                        hospital_name = clean_text(hospital_name_tag.get_text()) if hospital_name_tag else None

                        # area
                        area = ProfileEnricher._extract_area(c)

                        # fee
                        fee = ProfileEnricher._extract_fee(c)

                        # timings: table rows under this card
                        timings = ProfileEnricher._extract_timings(c)

                        # location: look for iframe with data-lat/data-lng
                        lat, lng = ProfileEnricher._extract_location(c)

                        practices.append({
                            "h_id": h_id,
                            "d_id": d_id,
                            "hospital_name": hospital_name,
                            "hospital_url": hospital_url,
                            "area": area,
                            "fee": fee,
                            "timings": timings,
                            "lat": lat,
                            "lng": lng,
                        })
                    except Exception:
                        continue
        except Exception:
            pass

        return practices

    @staticmethod
    def _extract_area(card: BeautifulSoup) -> Optional[str]:
        """Extract area from practice card."""
        area_tag = card.select_one("p:contains('Area:')")
        if not area_tag:
            # try generic p containing 'Area'
            for p in card.select("p"):
                if "Area:" in p.get_text():
                    area_tag = p
                    break
        if area_tag:
            area_text = area_tag.get_text()
            # extract after 'Area:'
            parts = area_text.split("Area:")
            if len(parts) > 1:
                return clean_text(parts[1])
        return None

    @staticmethod
    def _extract_fee(card: BeautifulSoup) -> Optional[int]:
        """Extract fee from practice card."""
        fee_tag = None
        for p in card.select("p"):
            t = p.get_text()
            if "Rs." in t or "Rs" in t:
                fee_tag = p
                break
        if fee_tag:
            digits = "".join(ch for ch in fee_tag.get_text() if ch.isdigit())
            return int(digits) if digits else None
        return None

    @staticmethod
    def _extract_timings(card: BeautifulSoup) -> dict:
        """Extract timings from practice card."""
        timings = {}
        for tr in card.select("table tr"):
            tds = tr.select("td")
            if len(tds) >= 2:
                day = clean_text(tds[0].get_text())
                time_text = clean_text(tds[1].get_text())
                if day:
                    timings[day] = time_text
        return timings

    @staticmethod
    def _extract_location(card: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
        """Extract lat/lng from practice card."""
        lat = None
        lng = None
        iframe = card.select_one("iframe[data-lat], iframe[data-src]")
        if iframe:
            lat_attr = iframe.get("data-lat") or iframe.get("data-lat")
            lng_attr = iframe.get("data-lng") or iframe.get("data-lng")
            try:
                if lat_attr:
                    lat = float(lat_attr)
                if lng_attr:
                    lng = float(lng_attr)
            except Exception:
                lat = None
                lng = None
        return lat, lng

    @staticmethod
    def _parse_qualifications(soup: BeautifulSoup) -> List[dict]:
        """Parse qualifications from Qualification table."""
        qualifications = []
        try:
            # Find the Qualification section (h2 with text "Qualification")
            target_section = None
            for div in soup.select("div"):
                h2 = div.select_one("h2")
                if h2 and "Qualification" in h2.get_text():
                    target_section = div
                    break

            if target_section:
                # Find table within this section
                table = target_section.select_one("table")
                if table:
                    # Parse tbody rows, extract institute (td[0]) and degree (td[1])
                    tbody = table.select_one("tbody")
                    if tbody:
                        for tr in tbody.select("tr"):
                            tds = tr.select("td")
                            if len(tds) >= 2:
                                institute = clean_text(tds[0].get_text())
                                degree = clean_text(tds[1].get_text())
                                if institute and degree:
                                    qualifications.append({
                                        "institute": institute,
                                        "degree": degree,
                                    })
        except Exception:
            pass

        return qualifications

    @staticmethod
    def _parse_experience(soup: BeautifulSoup) -> tuple[Optional[int], List[dict]]:
        """Parse experience years and work history."""
        experience_years = None
        work_history = []

        try:
            # Extract years from intro: look for "X Yrs Experience" pattern
            for p in soup.select("p"):
                text = p.get_text()
                if "Yrs Experience" in text or "Years Experience" in text:
                    # Extract number from text like "20 Yrs Experience"
                    digits = "".join(ch for ch in text if ch.isdigit())
                    if digits:
                        experience_years = int(digits)
                    break
        except Exception:
            pass

        try:
            # Find the Experience section (h2 with text "Experience")
            target_section = None
            for div in soup.select("div"):
                h2 = div.select_one("h2")
                if h2 and "Experience" in h2.get_text() and "Qualification" not in h2.get_text():
                    target_section = div
                    break

            if target_section:
                # Find table within this section
                table = target_section.select_one("table")
                if table:
                    # Parse tbody rows, extract institute (td[0]) and designation (td[1])
                    tbody = table.select_one("tbody")
                    if tbody:
                        for tr in tbody.select("tr"):
                            tds = tr.select("td")
                            if len(tds) >= 2:
                                institute = clean_text(tds[0].get_text())
                                designation = clean_text(tds[1].get_text())
                                if institute and designation:
                                    work_history.append({
                                        "institute": institute,
                                        "designation": designation,
                                    })
        except Exception:
            pass

        return experience_years, work_history


"""Profile enrichment logic for Marham doctors."""

from __future__ import annotations

import re
from typing import List, Optional
from bs4 import BeautifulSoup

from scrapers.models.doctor_model import DoctorModel
from scrapers.utils.parser_helpers import clean_text
from scrapers.utils.url_parser import is_hospital_url, is_video_consultation_url, parse_hospital_url

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
            qualifications, experience_years, work_history, services, diseases, symptoms,
            professional_statement, patients_treated, reviews_count, patient_satisfaction_score,
            phone, consultation_types
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

        # Parse services that the doctor offers/treats
        services = ProfileEnricher._parse_services(soup)
        result["services"] = services

        # Parse diseases that the doctor can treat
        diseases = ProfileEnricher._parse_diseases(soup)
        result["diseases"] = diseases

        # Parse symptoms that the doctor looks into
        symptoms = ProfileEnricher._parse_symptoms(soup)
        result["symptoms"] = symptoms

        # Parse professional statement and additional info
        professional_info = ProfileEnricher._parse_professional_statement(soup)
        result.update(professional_info)

        return result

    @staticmethod
    def _parse_practices(soup: BeautifulSoup) -> List[dict]:
        """Parse practice entries from the profile page.
        
        Distinguishes between:
        - Video Consultations (private practice): class 'oc_practice_detail_card_dr_profile_tapped', contains "Video Consultation"
        - Hospitals: class 'pc_practice_detail_card_dr_profile_tapped', has hospital name and Google Maps location
        """
        practices = []
        try:
            # Find section by header text "Practice Address and Timings"
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
                        
                        # Check if this is a video consultation (private practice)
                        oc_link = c.select_one("a.oc_practice_detail_card_dr_profile_tapped")
                        pc_link = c.select_one("a.pc_practice_detail_card_dr_profile_tapped")
                        
                        hospital_name_tag = c.select_one("h3")
                        hospital_name = clean_text(hospital_name_tag.get_text()) if hospital_name_tag else None
                        
                        # Determine if this is video consultation
                        is_private_practice = False
                        if oc_link or (hospital_name and "Video Consultation" in hospital_name):
                            is_private_practice = True
                        
                        # Get the appropriate link
                        practice_link = oc_link if oc_link else pc_link
                        practice_url = None
                        if practice_link and practice_link.has_attr("href"):
                            practice_url = practice_link.get("href")
                            if practice_url and practice_url.startswith("/"):
                                practice_url = f"{BASE_URL}{practice_url}"
                        
                        # For hospitals, extract hospital URL from the link
                        # Hospital links look like: /doctors/karachi/urologist/dr-feroze-ahmed-mahar/callcenter?h_id=5907
                        # We need to construct the actual hospital URL from h_id or extract it
                        hospital_url = None
                        if not is_private_practice and practice_url:
                            # Try to extract hospital URL from the practice link
                            # If it contains 'callcenter?h_id=', we can construct hospital URL
                            if "callcenter" in practice_url or "h_id" in practice_url:
                                # For now, use the practice_url as hospital_url
                                # The actual hospital URL might need to be looked up separately
                                hospital_url = practice_url
                        
                        # area (only for hospitals, not video consultations)
                        area = None
                        if not is_private_practice:
                            area = ProfileEnricher._extract_area(c)

                        # fee
                        fee = ProfileEnricher._extract_fee(c)

                        # timings: table rows under this card
                        timings = ProfileEnricher._extract_timings(c)

                        # location: extract from Google Maps iframe (only for hospitals)
                        lat, lng = None, None
                        if not is_private_practice:
                            lat, lng = ProfileEnricher._extract_location(c)

                        practices.append({
                            "h_id": h_id,
                            "d_id": d_id,
                            "hospital_name": hospital_name,
                            "hospital_url": hospital_url,
                            "practice_url": practice_url,  # The booking/appointment URL
                            "area": area,
                            "fee": fee,
                            "timings": timings,
                            "lat": lat,
                            "lng": lng,
                            "is_private_practice": is_private_practice,
                        })
                    except Exception as exc:  # noqa: BLE001
                        from scrapers.logger import logger
                        logger.debug("Error parsing practice card: {}", exc)
                        continue
        except Exception as exc:  # noqa: BLE001
            from scrapers.logger import logger
            logger.debug("Error parsing practices section: {}", exc)

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
        """Extract lat/lng from practice card's Google Maps iframe.
        
        Checks both:
        1. data-lat/data-lng attributes
        2. src attribute with Google Maps URL (q=lat,lng format)
        """
        lat = None
        lng = None
        
        # Look for Google Maps iframe
        iframe = card.select_one("iframe.google-map, iframe[src*='maps.google.com'], iframe[data-src*='maps.google.com']")
        
        if iframe:
            # First try data attributes
            lat_attr = iframe.get("data-lat")
            lng_attr = iframe.get("data-lng")
            
            if lat_attr and lng_attr:
                try:
                    lat = float(lat_attr)
                    lng = float(lng_attr)
                    return lat, lng
                except (ValueError, TypeError):
                    pass
            
            # If data attributes don't work, extract from src or data-src URL
            # Google Maps URL format: ...?q=24.882573516287152,67.0821573527601&...
            src = iframe.get("src") or iframe.get("data-src") or ""
            
            if src:
                # Pattern: q=lat,lng or /@lat,lng
                coords_match = re.search(r'[?&]q=([\d.-]+),([\d.-]+)|/@([\d.-]+),([\d.-]+)', src)
                if coords_match:
                    try:
                        lat = float(coords_match.group(1) or coords_match.group(3))
                        lng = float(coords_match.group(2) or coords_match.group(4))
                        # Validate reasonable coordinates for Pakistan
                        if 23.0 <= lat <= 37.0 and 60.0 <= lng <= 78.0:
                            return lat, lng
                    except (ValueError, TypeError):
                        pass
        
        return lat, lng

    @staticmethod
    def _parse_qualifications(soup: BeautifulSoup) -> List[dict]:
        """Parse qualifications from Qualification table.
        
        Expected HTML structure:
        <div class="col-12 col-md-12 bg-marham-light-border shadow-card">
            <h2 class="pt-10">Qualification</h2>
            <table>
                <thead>
                    <tr><th>Institute</th><th>Degree</th></tr>
                </thead>
                <tbody>
                    <tr><td>Institute Name</td><td>Degree</td></tr>
                </tbody>
            </table>
        </div>
        """
        qualifications = []
        try:
            # Find the Qualification section - look for div containing h2 with "Qualification"
            # Try specific selector first (more reliable)
            qualification_sections = soup.select("div.bg-marham-light-border.shadow-card, div.col-12.col-md-12")
            
            target_section = None
            for div in qualification_sections:
                h2 = div.select_one("h2")
                if h2:
                    h2_text = clean_text(h2.get_text())
                    if h2_text and "Qualification" in h2_text:
                        target_section = div
                        break
            
            # Fallback: search all divs if specific selector didn't work
            if not target_section:
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
        except Exception as e:
            from scrapers.logger import logger
            logger.debug("Error parsing qualifications: {}", e)

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
            # Expected HTML structure:
            # <div class="col-12 col-md-12 bg-marham-light-border shadow-card">
            #     <h2 class="pt-10">Experience</h2>
            #     <table>
            #         <thead>
            #             <tr><th>Institute</th><th>Designation</th></tr>
            #         </thead>
            #         <tbody>
            #             <tr><td>Hospital Name</td><td>Role/Designation</td></tr>
            #         </tbody>
            #     </table>
            # </div>
            
            # Try specific selector first (more reliable)
            experience_sections = soup.select("div.bg-marham-light-border.shadow-card, div.col-12.col-md-12")
            
            target_section = None
            for div in experience_sections:
                h2 = div.select_one("h2")
                if h2:
                    h2_text = clean_text(h2.get_text())
                    if h2_text and "Experience" in h2_text and "Qualification" not in h2_text:
                        target_section = div
                        break
            
            # Fallback: search all divs if specific selector didn't work
            if not target_section:
                for div in soup.select("div"):
                    h2 = div.select_one("h2")
                    if h2:
                        h2_text = clean_text(h2.get_text())
                        if h2_text and "Experience" in h2_text and "Qualification" not in h2_text:
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
        except Exception as e:
            from scrapers.logger import logger
            logger.debug("Error parsing experience: {}", e)

        return experience_years, work_history

    @staticmethod
    def _parse_services(soup: BeautifulSoup) -> List[str]:
        """Parse services that the doctor offers/treats.
        
        Expected HTML structure:
        <div class="col-12 col-md-12 bg-marham-light-border border-card mt-3">
            <h2 class="">Services</h2>
            <ul class="grid-list">
                <li>
                    <a class="sevice_dr_profile_clicked" data-service="Service Name" href="...">
                        Service Name
                    </a>
                </li>
            </ul>
        </div>
        
        Returns:
            List of service names (e.g., ["Extracorporeal Shockwave Lithotripsy", "Hypospadias Repair"])
        """
        services = []
        try:
            # Find the Services section - look for div containing h2 with "Services"
            # Try specific selector first (more reliable)
            service_sections = soup.select("div.bg-marham-light-border.border-card, div.col-12.col-md-12")
            
            target_section = None
            for div in service_sections:
                h2 = div.select_one("h2")
                if h2:
                    h2_text = clean_text(h2.get_text())
                    if h2_text and "Services" in h2_text:
                        target_section = div
                        break
            
            # Fallback: search all divs if specific selector didn't work
            if not target_section:
                for div in soup.select("div"):
                    h2 = div.select_one("h2")
                    if h2:
                        h2_text = clean_text(h2.get_text())
                        if h2_text and "Services" in h2_text:
                            target_section = div
                            break

            if target_section:
                # Find the ul with class "grid-list"
                services_list = target_section.select_one("ul.grid-list")
                if services_list:
                    # Extract service names from anchor tags
                    for li in services_list.select("li"):
                        anchor = li.select_one("a.sevice_dr_profile_clicked, a")
                        if anchor:
                            # Try data-service attribute first, then text content
                            service_name = anchor.get("data-service") or clean_text(anchor.get_text())
                            if service_name and service_name not in services:
                                services.append(service_name)
        except Exception as e:
            from scrapers.logger import logger
            logger.debug("Error parsing services: {}", e)

        return services

    @staticmethod
    def _parse_diseases(soup: BeautifulSoup) -> List[str]:
        """Parse diseases that the doctor can treat.
        
        Expected HTML structure:
        <div class="col-12 col-md-12 bg-marham-light-border border-card">
            <h2 class="pt-3">Diseases</h2>
            <ul class="grid-list">
                <li>
                    <a class="disease_dr_profile_clicked" data-disease="Disease Name" href="...">
                        Disease Name
                    </a>
                </li>
            </ul>
        </div>
        
        Returns:
            List of disease names (e.g., ["Bladder Prolapse", "Urinary Incontinence"])
        """
        diseases = []
        try:
            # Find the Diseases section - look for div containing h2 with "Diseases"
            # Try specific selector first (more reliable)
            disease_sections = soup.select("div.bg-marham-light-border.border-card, div.col-12.col-md-12")
            
            target_section = None
            for div in disease_sections:
                h2 = div.select_one("h2")
                if h2:
                    h2_text = clean_text(h2.get_text())
                    if h2_text and "Diseases" in h2_text:
                        target_section = div
                        break
            
            # Fallback: search all divs if specific selector didn't work
            if not target_section:
                for div in soup.select("div"):
                    h2 = div.select_one("h2")
                    if h2:
                        h2_text = clean_text(h2.get_text())
                        if h2_text and "Diseases" in h2_text:
                            target_section = div
                            break

            if target_section:
                # Find the ul with class "grid-list"
                diseases_list = target_section.select_one("ul.grid-list")
                if diseases_list:
                    # Extract disease names from anchor tags
                    for li in diseases_list.select("li"):
                        anchor = li.select_one("a.disease_dr_profile_clicked, a")
                        if anchor:
                            # Try data-disease attribute first, then text content
                            disease_name = anchor.get("data-disease") or clean_text(anchor.get_text())
                            if disease_name and disease_name not in diseases:
                                diseases.append(disease_name)
        except Exception as e:
            from scrapers.logger import logger
            logger.debug("Error parsing diseases: {}", e)

        return diseases

    @staticmethod
    def _parse_symptoms(soup: BeautifulSoup) -> List[str]:
        """Parse symptoms that the doctor looks into.
        
        Expected HTML structure:
        <div class="col-12 col-md-12 bg-marham-light-border border-card">
            <h2 class="pt-3">Symptoms</h2>
            <ul class="grid-list">
                <li class="symptom_dr_profile_clicked">
                    <a href="...">Symptom Name</a>
                </li>
            </ul>
        </div>
        
        Returns:
            List of symptom names (e.g., ["Urogenital system", "Prostate issues"])
        """
        symptoms = []
        try:
            # Find the Symptoms section - look for div containing h2 with "Symptoms"
            # Try specific selector first (more reliable)
            symptom_sections = soup.select("div.bg-marham-light-border.border-card, div.col-12.col-md-12")
            
            target_section = None
            for div in symptom_sections:
                h2 = div.select_one("h2")
                if h2:
                    h2_text = clean_text(h2.get_text())
                    if h2_text and "Symptoms" in h2_text:
                        target_section = div
                        break
            
            # Fallback: search all divs if specific selector didn't work
            if not target_section:
                for div in soup.select("div"):
                    h2 = div.select_one("h2")
                    if h2:
                        h2_text = clean_text(h2.get_text())
                        if h2_text and "Symptoms" in h2_text:
                            target_section = div
                            break

            if target_section:
                # Find the ul with class "grid-list"
                symptoms_list = target_section.select_one("ul.grid-list")
                if symptoms_list:
                    # Extract symptom names from anchor tags
                    # Note: class "symptom_dr_profile_clicked" is on the <li>, not the <a>
                    for li in symptoms_list.select("li.symptom_dr_profile_clicked, li"):
                        anchor = li.select_one("a")
                        if anchor:
                            symptom_name = clean_text(anchor.get_text())
                            if symptom_name and symptom_name not in symptoms:
                                symptoms.append(symptom_name)
        except Exception as e:
            from scrapers.logger import logger
            logger.debug("Error parsing symptoms: {}", e)

        return symptoms

    @staticmethod
    def _parse_professional_statement(soup: BeautifulSoup) -> dict:
        """Parse professional statement section with bio, stats, and contact info.
        
        Expected HTML structure:
        <section>
            <div class="container bg-white mt-10 pb-10">
                <div class="row">
                    <div class="column">
                        <h2 class="pt-10">Professional Statement by Dr. ...</h2>
                        <div>
                            <p>...bio text...</p>
                            <p><strong>Patient Satisfaction Score:</strong> ...</p>
                            <p><strong>Dr. ... Appointment Details:</strong></p>
                            <div>Contact info, timings, phone, fee</div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
        
        Returns:
            Dictionary with: professional_statement, patients_treated, reviews_count,
            patient_satisfaction_score, phone, consultation_types
        """
        result = {}
        
        try:
            # Find the Professional Statement section
            statement_section = None
            
            # Try to find section with h2 containing "Professional Statement"
            for section in soup.select("section"):
                h2 = section.select_one("h2")
                if h2 and "Professional Statement" in h2.get_text():
                    statement_section = section
                    break
            
            if not statement_section:
                # Fallback: look for div with class containing "bg-white"
                statement_section = soup.select_one("div.bg-white, section")
            
            if statement_section:
                # Extract full professional statement text
                content_div = statement_section.select_one("div.column, div.container")
                if content_div:
                    # Get all text content, preserving structure
                    paragraphs = content_div.select("p")
                    statement_parts = []
                    for p in paragraphs:
                        text = clean_text(p.get_text())
                        if text:
                            statement_parts.append(text)
                    
                    if statement_parts:
                        result["professional_statement"] = " ".join(statement_parts)
                    
                    # Extract structured data from text
                    full_text = content_div.get_text()
                    
                    # Extract patients treated count
                    # Pattern: "has treated over 331 number of patients" or "treated over 331 patients"
                    patients_match = re.search(r"treated\s+(?:over\s+)?(\d+)\s+(?:number\s+of\s+)?patients", full_text, re.IGNORECASE)
                    if patients_match:
                        try:
                            result["patients_treated"] = int(patients_match.group(1))
                        except (ValueError, AttributeError):
                            pass
                    
                    # Extract reviews count
                    # Pattern: "has 157 number of reviews" or "157 reviews"
                    reviews_match = re.search(r"(\d+)\s+(?:number\s+of\s+)?reviews", full_text, re.IGNORECASE)
                    if reviews_match:
                        try:
                            result["reviews_count"] = int(reviews_match.group(1))
                        except (ValueError, AttributeError):
                            pass
                    
                    # Extract patient satisfaction score
                    # Pattern: "95 patient satisfaction score" or "satisfaction score: 95"
                    satisfaction_match = re.search(r"(?:patient\s+)?satisfaction\s+score[:\s]+(\d+)", full_text, re.IGNORECASE)
                    if satisfaction_match:
                        try:
                            result["patient_satisfaction_score"] = float(satisfaction_match.group(1))
                        except (ValueError, AttributeError):
                            pass
                    
                    # Extract phone number
                    # Pattern: phone numbers like "042-32591427" or "04232591427"
                    phone_match = re.search(r"(\d{3,4}[-.\s]?\d{7,8})", full_text)
                    if phone_match:
                        result["phone"] = phone_match.group(1).strip()
                    
                    # Extract consultation types
                    # Pattern: "available for Marham's in-person and online video consultation"
                    consultation_types = []
                    if "in-person" in full_text.lower() or "in person" in full_text.lower():
                        consultation_types.append("in-person")
                    if "online" in full_text.lower() or "video consultation" in full_text.lower():
                        consultation_types.append("online")
                    if consultation_types:
                        result["consultation_types"] = consultation_types
                    
        except Exception as e:
            from scrapers.logger import logger
            logger.debug("Error parsing professional statement: {}", e)
        
        return result

